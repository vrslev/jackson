import signal
from dataclasses import dataclass, field
from functools import lru_cache

import anyio
import jack
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from jackson.api import models
from jackson.jack_client import JackClient
from jackson.logging import get_logger
from jackson.port_connection import ClientShould, PortName

app = FastAPI()
uvicorn_err_log = get_logger("uvicorn.error", "HttpServer")
uvicorn_access_log = get_logger("uvicorn.access", "HttpServer")


class StructuredHTTPException(HTTPException):
    def __init__(self, status_code: int, data: BaseModel) -> None:
        super().__init__(
            status_code=status_code,
            detail={"message": data.__class__.__name__, "data": data.dict()},
        )


@lru_cache
def get_jack_client():
    return JackClient("APIServer", server_name=app.state.jack_server_name)


@app.get("/init", response_model=models.InitResponse)
async def init(jack_client: JackClient = Depends(get_jack_client)):
    inputs = jack_client.get_ports("system:.*", is_input=True)
    outputs = jack_client.get_ports("system:.*", is_output=True)

    return models.InitResponse(
        inputs=len(inputs),
        outputs=len(outputs),
        rate=jack_client.samplerate,
        buffer_size=jack_client.blocksize,
    )


def get_port_or_fail(
    jack_client: JackClient, type: models.PortDirectionType, name: PortName
):
    try:
        return jack_client.get_port_by_name(str(name))
    except jack.JackError:
        raise StructuredHTTPException(404, models.PortNotFound(type=type, name=name))


def validate_playback_port_has_no_connections(
    jack_client: JackClient, destination_name: PortName, client_should: ClientShould
):
    port = get_port_or_fail(jack_client, type="destination", name=destination_name)

    if client_should != "send":
        return

    if not (connections := jack_client.get_all_connections(port)):
        return

    data = models.PlaybackPortAlreadyHasConnections(
        port=destination_name, connections=[PortName.parse(p.name) for p in connections]
    )
    raise StructuredHTTPException(status.HTTP_409_CONFLICT, data)


async def retry_connect_ports(
    jack_client: JackClient, source: PortName, destination: PortName
):
    try:
        await jack_client.connect_retry(str(source), str(destination))
    except jack.JackError:
        raise StructuredHTTPException(
            status.HTTP_424_FAILED_DEPENDENCY,
            models.FailedToConnectPorts(source=source, destination=destination),
        )


async def connect_ports(
    client: JackClient,
    source: PortName,
    destination: PortName,
    client_should: ClientShould,
):
    get_port_or_fail(client, type="source", name=source)
    validate_playback_port_has_no_connections(client, destination, client_should)
    await retry_connect_ports(client, source, destination)


@app.patch("/connect")
async def connect(
    connections: list[models.Connection],
    jack_client: JackClient = Depends(get_jack_client),
):
    for conn in connections:
        await connect_ports(
            jack_client, conn.source, conn.destination, conn.client_should
        )
    # TODO: Validate (check if allowed) source and destination
    return models.ConnectResponse()


# @app.on_event("shutdown") # type: ignore
# def on_shutdown():
#     get_jack_client.cache_clear()


@dataclass
class APIServer:
    app: FastAPI
    server: uvicorn.Server = field(init=False)
    _started: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        config = uvicorn.Config(app=app, host="0.0.0.0", workers=1, log_config=None)
        self.server = uvicorn.Server(config)
        self.server.config.load()
        self.server.lifespan = self.server.config.lifespan_class(self.server.config)

    async def start(self):
        self._started = True
        await self.server.startup()  # type: ignore

    async def stop(self):
        if self._started:
            self.server.should_exit = True
            await self.server.shutdown()


async def uvicorn_signal_handler(scope: anyio.CancelScope):
    with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
        async for _ in signals:
            scope.cancel()
            return

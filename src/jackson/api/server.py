import signal
from dataclasses import dataclass, field
from functools import lru_cache
from typing import cast

import anyio
import jack
import jack_server
import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from jackson.api import models
from jackson.jack_client import connect_ports_retry, init_jack_client
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
def get_jack_client() -> jack.Client:
    return init_jack_client("APIServer", server_name=app.state.jack_server_name)


@app.get("/init", response_model=models.InitResponse)
async def init(jack_client: jack.Client = Depends(get_jack_client)):
    inputs = jack_client.get_ports("system:.*", is_input=True)
    outputs = jack_client.get_ports("system:.*", is_output=True)

    return models.InitResponse(
        inputs=len(inputs),
        outputs=len(outputs),
        rate=cast(jack_server.SampleRate, jack_client.samplerate),
        buffer_size=jack_client.blocksize,
    )


def get_port_or_fail(
    client: jack.Client, type: models.PortDirectionType, name: PortName
):
    try:
        return client.get_port_by_name(str(name))
    except jack.JackError:
        raise StructuredHTTPException(404, models.PortNotFound(type=type, name=name))


def validate_playback_port_has_no_connections(
    client: jack.Client, name: PortName, client_should: ClientShould
):
    port = get_port_or_fail(client, type="destination", name=name)

    if client_should != "send":
        return

    if not (connections := client.get_all_connections(port)):
        return

    port_names = [PortName.parse(p.name) for p in connections]
    data = models.PlaybackPortAlreadyHasConnections(port=name, connections=port_names)
    raise StructuredHTTPException(status.HTTP_409_CONFLICT, data)


async def retry_connect_ports(
    client: jack.Client, source: PortName, destination: PortName
):
    try:
        await connect_ports_retry(client, str(source), str(destination))
    except jack.JackError:
        raise StructuredHTTPException(
            status.HTTP_424_FAILED_DEPENDENCY,
            models.FailedToConnectPorts(source=source, destination=destination),
        )


async def connect_ports(
    client: jack.Client,
    source: PortName,
    destination: PortName,
    client_should: ClientShould,
):
    get_port_or_fail(client, type="source", name=source)
    validate_playback_port_has_no_connections(
        client, name=destination, client_should=client_should
    )
    await retry_connect_ports(client, source, destination)


@app.patch("/connect")
async def connect(
    connections: list[models.Connection] = Body(...),
    jack_client: jack.Client = Depends(get_jack_client),
):
    # TODO: Validate (check if allowed) source and destination
    for conn in connections:
        await connect_ports(
            jack_client,
            source=conn.source,
            destination=conn.destination,
            client_should=conn.client_should,
        )
    return models.ConnectResponse()


@dataclass
class APIServer:
    jack_server_name: str
    server: uvicorn.Server = field(init=False)
    _started: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        app.state.jack_server_name = self.jack_server_name
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

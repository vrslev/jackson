import signal
from functools import lru_cache

import anyio
import jack
import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, status
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


async def connect_retry(
    client: JackClient, source: PortName, destination: PortName
) -> None:
    """Connect ports for sure.

    Several issues could come up while connecting JACK ports.

    1. "Cannot connect ports owned by inactive clients: "MyName" is not active"
        This means that client is not initialized yet.

    2. "Unknown destination port in attempted (dis)connection src_name  dst_name"
        I.e. port is not initialized yet.
    """

    exc = None
    dest_name = str(destination)

    for _ in range(100):
        try:
            connections = client.get_all_connections(
                client.get_port_by_name(str(source))
            )
            if any(p.name == dest_name for p in connections):
                return

            client.connect(source, destination)
            return

        except jack.JackError as e:
            exc = e
            await anyio.sleep(0.1)

    assert exc
    raise exc


async def retry_connect_ports(
    jack_client: JackClient, source: PortName, destination: PortName
):
    try:
        await connect_retry(jack_client, source, destination)
    except jack.JackError:
        raise StructuredHTTPException(
            status.HTTP_424_FAILED_DEPENDENCY,
            models.FailedToConnectPorts(source=source, destination=destination),
        )


@app.patch("/connect", response_model=models.ConnectResponse)
async def connect(
    source: PortName,
    destination: PortName,
    client_should: ClientShould = Body(...),
    jack_client: JackClient = Depends(get_jack_client),
):
    # TODO: Validate (check if allowed) source and destination
    get_port_or_fail(jack_client, type="source", name=source)
    validate_playback_port_has_no_connections(jack_client, destination, client_should)
    await retry_connect_ports(jack_client, source, destination)
    return models.ConnectResponse(source=source, destination=destination)


# @app.on_event("shutdown") # type: ignore
# def on_shutdown():
#     get_jack_client.cache_clear()


class APIServer(uvicorn.Server):
    def __init__(self, app: FastAPI) -> None:
        self._started = False

        config = uvicorn.Config(app=app, host="0.0.0.0", workers=1, log_config=None)
        super().__init__(config)

        self.config.load()
        self.lifespan = self.config.lifespan_class(self.config)

    async def start(self):
        self._started = True
        await self.startup()  # type: ignore

    async def stop(self):
        if self._started:
            self.should_exit = True
            await self.shutdown()


async def uvicorn_signal_handler(scope: anyio.CancelScope):
    with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
        async for _ in signals:
            scope.cancel()
            return

import signal
from functools import lru_cache
from typing import Any, cast

import anyio
import jack
import uvicorn  # type: ignore
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

import jack_server
from jackson.logging import get_configured_logger
from jackson.services.jack_client import JackClient
from jackson.services.models import (
    ConnectResponse,
    InitResponse,
    PlaybackPortAlreadyHasConnections,
    PortDirectionType,
    PortName,
    PortNotFound,
)

app = FastAPI()
log = get_configured_logger(__name__, "HttpServer")

# Configure uvicorn loggers
for logger_name in ("uvicorn.error", "uvicorn.access"):
    get_configured_logger(logger_name, "HttpServer")


class StructuredDetail(BaseModel):
    message: str
    data: BaseModel | None


class StructuredHTTPException(HTTPException):
    def __init__(
        self,
        status_code: int,
        message: str,
        data: BaseModel | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail=StructuredDetail(message=message, data=data).dict(),
            headers=headers,
        )


@lru_cache
def get_jack_client():
    return JackClient("MessagingServer")


@app.get("/init", response_model=InitResponse)
def init(client: JackClient = Depends(get_jack_client)):
    inputs = client.get_ports("system:.*", is_input=True)
    outputs = client.get_ports("system:.*", is_output=True)
    rate = cast(jack_server.SampleRate, client.samplerate)

    return InitResponse(inputs=len(inputs), outputs=len(outputs), rate=rate)


def check_client_name_not_system(client_name: str):
    if client_name == "system":
        raise StructuredHTTPException(
            status.HTTP_400_BAD_REQUEST, 'Client name can\'t be "system"'
        )


def get_port_or_raise(jack_client: JackClient, type: PortDirectionType, name: PortName):
    try:
        return jack_client.get_port_by_name(str(name))
    except jack.JackError:
        raise StructuredHTTPException(
            404, message="Port not found", data=PortNotFound(type=type, name=name)
        )


def _connect_ports(jack_client: JackClient, source: PortName, destination: PortName):
    jack_client.connect(str(source), str(destination))
    log.info(f"Connected ports: {source} -> {destination}")
    return ConnectResponse(source=source, destination=destination)


@app.put("/connect/send")
def connect_send(
    *,
    jack_client: JackClient = Depends(get_jack_client),
    client_name: str,
    port_idx: int,
):
    # TO mixer
    check_client_name_not_system(client_name)
    source_name = PortName(client=client_name, type="receive", idx=port_idx)
    get_port_or_raise(jack_client, type="source", name=source_name)

    destination_name = PortName(client="system", type="playback", idx=port_idx)
    destination = get_port_or_raise(
        jack_client, type="destination", name=destination_name
    )

    if connections := jack_client.get_all_connections(destination):
        raise StructuredHTTPException(
            status.HTTP_409_CONFLICT,
            message="Port already has connections",
            data=PlaybackPortAlreadyHasConnections(
                port_name=destination_name,
                connection_names=[p.name for p in connections],
            ),
        )
    return _connect_ports(jack_client, source_name, destination_name)


@app.patch("/connect/receive")
def connect_receive(
    *,
    jack_client: JackClient = Depends(get_jack_client),
    client_name: str,
    port_idx: int,
):
    # FROM mixer
    check_client_name_not_system(client_name)

    source_name = PortName(client="system", type="capture", idx=port_idx)
    get_port_or_raise(jack_client, type="source", name=source_name)

    destination_name = PortName(client=client_name, type="send", idx=port_idx)
    get_port_or_raise(jack_client, type="destination", name=destination_name)

    return _connect_ports(jack_client, source_name, destination_name)


class MessagingServer(uvicorn.Server):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(uvicorn.Config(app=app, workers=1, log_config=None))
        self.config.load()
        self.lifespan = self.config.lifespan_class(self.config)
        self._started = False

    async def start(self):
        self._started = True
        await self.startup()  # type: ignore

    async def stop(self):
        if self._started:
            self.should_exit = True
            await self.main_loop()
            await self.shutdown()


async def uvicorn_signal_handler(scope: anyio.CancelScope):
    with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
        async for _ in signals:
            scope.cancel()
            return

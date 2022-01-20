import signal
from functools import lru_cache
from typing import Any, cast

import anyio
import jack
import uvicorn  # type: ignore
from fastapi import Body, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

import jack_server
from jackson.logging import get_configured_logger
from jackson.services.jack_client import JackClient
from jackson.services.models import (
    ClientShould,
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
            detail={"message": message, "data": data.dict() if data else None},
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


def get_port_or_raise(jack_client: JackClient, type: PortDirectionType, name: PortName):
    try:
        return jack_client.get_port_by_name(str(name))
    except jack.JackError:
        raise StructuredHTTPException(
            404, message="Port not found", data=PortNotFound(type=type, name=name)
        )


@app.patch("/connect")
def connect(
    *,
    jack_client: JackClient = Depends(get_jack_client),
    source: PortName,
    destination: PortName,
    client_should: ClientShould = Body(...),
):
    # TODO: Validate source and destination
    get_port_or_raise(jack_client, type="source", name=source)
    destination_port = get_port_or_raise(
        jack_client, type="destination", name=destination
    )

    if client_should == "send" and (
        connections := jack_client.get_all_connections(destination_port)
    ):
        raise StructuredHTTPException(
            status.HTTP_409_CONFLICT,
            message="Port already has connections",
            data=PlaybackPortAlreadyHasConnections(
                port_name=destination, connection_names=[p.name for p in connections]
            ),
        )

    jack_client.connect(source, destination)
    return ConnectResponse(source=source, destination=destination)


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

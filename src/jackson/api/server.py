import signal
from functools import lru_cache
from typing import Any

import anyio
import jack
import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from jackson.api.models import (
    ConnectResponse,
    InitResponse,
    PlaybackPortAlreadyHasConnections,
    PortDirectionType,
    PortNotFound,
)
from jackson.jack_client import JackClient
from jackson.logging import get_configured_logger
from jackson.port_connection import ClientShould, PortName

app = FastAPI()
log = get_configured_logger(__name__, "HttpServer")
uvicorn_err_log = get_configured_logger("uvicorn.error", "HttpServer")
uvicorn_access_log = get_configured_logger("uvicorn.access", "HttpServer")


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
def init(jack_client: JackClient = Depends(get_jack_client)):
    inputs = jack_client.get_ports("system:.*", is_input=True)
    outputs = jack_client.get_ports("system:.*", is_output=True)
    rate = jack_client.samplerate

    return InitResponse(inputs=len(inputs), outputs=len(outputs), rate=rate)


def get_port_or_fail(jack_client: JackClient, type: PortDirectionType, name: PortName):
    try:
        return jack_client.get_port_by_name(name)
    except jack.JackError:
        raise StructuredHTTPException(
            404, message="Port not found", data=PortNotFound(type=type, name=name)
        )


@app.patch("/connect", response_model=ConnectResponse)
def connect(
    source: PortName,
    destination: PortName,
    client_should: ClientShould = Body(...),
    jack_client: JackClient = Depends(get_jack_client),
):
    # TODO: Validate (check if allowed) source and destination
    get_port_or_fail(jack_client, type="source", name=source)
    destination_port = get_port_or_fail(
        jack_client, type="destination", name=destination
    )

    if client_should == "send" and (
        connections := jack_client.get_all_connections(destination_port)
    ):
        raise StructuredHTTPException(
            status.HTTP_409_CONFLICT,
            message="Playback port already has connections",
            data=PlaybackPortAlreadyHasConnections(
                port_name=destination, connection_names=[p.name for p in connections]
            ),
        )

    jack_client.connect(
        source, destination
    )  # TODO: Check if ports already connected. It will prevent issues with multiple sessions
    return ConnectResponse(source=source, destination=destination)


class MessagingServer(uvicorn.Server):
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

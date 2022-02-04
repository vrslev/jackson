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
    FailedToConnectPorts,
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
        data: BaseModel | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail={
                "message": data.__class__.__name__,
                "data": data.dict() if data else None,
            },
            headers=headers,
        )


@lru_cache
def get_jack_client():
    return JackClient("MessagingServer")


@app.get("/init", response_model=InitResponse)
async def init(jack_client: JackClient = Depends(get_jack_client)):
    inputs = jack_client.get_ports("system:.*", is_input=True)
    outputs = jack_client.get_ports("system:.*", is_output=True)
    rate = jack_client.samplerate

    return InitResponse(inputs=len(inputs), outputs=len(outputs), rate=rate)


def get_port_or_fail(jack_client: JackClient, type: PortDirectionType, name: PortName):
    try:
        return jack_client.get_port_by_name(name)
    except jack.JackError:
        raise StructuredHTTPException(404, PortNotFound(type=type, name=name))


@app.patch("/connect", response_model=ConnectResponse)
async def connect(
    source: PortName,
    destination: PortName,
    client_should: ClientShould = Body(...),
    jack_client: JackClient = Depends(get_jack_client),
):
    # TODO: Validate (check if allowed) source and destination
    get_port_or_fail(jack_client, type="source", name=source)
    dest_port = get_port_or_fail(jack_client, type="destination", name=destination)

    if client_should == "send" and (
        connections := jack_client.get_all_connections(dest_port)
    ):
        raise StructuredHTTPException(
            status.HTTP_409_CONFLICT,
            PlaybackPortAlreadyHasConnections(
                port=destination,
                connections=[PortName.parse(p.name) for p in connections],
            ),
        )

    # TODO: Check if ports already connected. It will prevent issues with multiple sessions
    try:
        await jack_client.connect_retry(source, destination)
    except jack.JackError:
        raise StructuredHTTPException(
            status.HTTP_424_FAILED_DEPENDENCY,
            FailedToConnectPorts(source=source, destination=destination),
        )

    return ConnectResponse(source=source, destination=destination)


# @app.on_event("shutdown") # type: ignore
# def on_shutdown():
#     get_jack_client.cache_clear()


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

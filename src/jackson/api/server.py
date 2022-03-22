import signal
from dataclasses import dataclass, field
from types import FrameType
from typing import Callable, cast

import anyio
import fastapi
import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, status
from fastapi.exception_handlers import http_exception_handler
from pydantic import BaseModel

from jackson.connector import models
from jackson.connector import server as connector
from jackson.connector.server import ServerPortConnector
from jackson.logging import get_logger

app = FastAPI()
uvicorn_err_log = get_logger("uvicorn.error", "HttpServer")
uvicorn_access_log = get_logger("uvicorn.access", "HttpServer")


def get_port_connector() -> ServerPortConnector:
    return app.state.port_connector


@app.get("/init")
async def init(
    connector: ServerPortConnector = Depends(get_port_connector),
) -> models.InitResponse:
    return connector.init()


@app.patch("/connect")
async def connect(
    connector: ServerPortConnector = Depends(get_port_connector),
    connections: list[models.Connection] = Body(...),
) -> models.ConnectResponse:
    return await connector.connect(connections)


@app.exception_handler(connector.PortConnectorError)  # type: ignore
async def port_connector_error_handler(
    request: fastapi.Request, exc: connector.PortConnectorError
):
    status_map: dict[type[BaseModel], int] = {
        models.PortNotFound: 404,
        models.PlaybackPortAlreadyHasConnections: status.HTTP_409_CONFLICT,
        models.FailedToConnectPorts: status.HTTP_424_FAILED_DEPENDENCY,
    }
    http_exception = HTTPException(
        status_code=status_map[type(exc.data)],
        detail={"message": type(exc.data).__name__, "data": exc.data.dict()},
    )
    return await http_exception_handler(request=request, exc=http_exception)


@dataclass
class APIServer:
    get_port_connector: Callable[[], ServerPortConnector]
    port_connector: ServerPortConnector | None = field(default=None, init=False)
    server: uvicorn.Server = field(init=False)
    _started: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        config = uvicorn.Config(app=app, host="0.0.0.0", workers=1, log_config=None)
        self.server = uvicorn.Server(config)
        self.server.config.load()
        self.server.lifespan = self.server.config.lifespan_class(self.server.config)

    async def start(self) -> None:
        app.state.port_connector = self.get_port_connector()
        self._started = True
        await self.server.startup()  # type: ignore

    async def stop(self) -> None:
        if self._started:
            await self.server.shutdown()
        if self.port_connector:
            self.port_connector.close()  # TODO: Should it be here?

    def install_signal_handlers(self, scope: anyio.CancelScope) -> None:
        def handler(sig: int, frame: FrameType | None) -> None:
            scope.cancel()

            self.server.handle_exit(
                sig=cast(signal.Signals, sig),
                frame=frame,  # type: ignore
            )

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, handler)

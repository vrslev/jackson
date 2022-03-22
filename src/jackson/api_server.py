import signal
from types import FrameType
from typing import cast

import anyio
import fastapi
import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jackson.connector_server import (
    Connection,
    ConnectResponse,
    FailedToConnectPorts,
    InitResponse,
    PlaybackPortAlreadyHasConnections,
    PortConnectorError,
    PortNotFound,
    ServerPortConnector,
)
from jackson.logging import get_logger

app = FastAPI()
get_logger("uvicorn.error", "HttpServer")
get_logger("uvicorn.access", "HttpServer")


def get_port_connector() -> ServerPortConnector:
    return app.state.port_connector


@app.get("/init")
async def init(
    connector: ServerPortConnector = Depends(get_port_connector),
) -> InitResponse:
    return connector.init()


@app.patch("/connect")
async def connect(
    connector: ServerPortConnector = Depends(get_port_connector),
    connections: list[Connection] = Body(...),
) -> ConnectResponse:
    return await connector.connect(connections)


@app.exception_handler(PortConnectorError)  # type: ignore
async def port_connector_error_handler(
    request: fastapi.Request, exc: PortConnectorError
) -> JSONResponse:
    status_map: dict[type[BaseModel], int] = {
        PortNotFound: 404,
        PlaybackPortAlreadyHasConnections: status.HTTP_409_CONFLICT,
        FailedToConnectPorts: status.HTTP_424_FAILED_DEPENDENCY,
    }
    http_exception = HTTPException(
        status_code=status_map[type(exc.data)],
        detail={"message": type(exc.data).__name__, "data": exc.data.dict()},
    )
    return await http_exception_handler(request=request, exc=http_exception)


def _get_uvicorn_server() -> uvicorn.Server:
    config = uvicorn.Config(app=app, host="0.0.0.0", workers=1, log_config=None)
    server = uvicorn.Server(config)
    server.config.load()
    server.lifespan = server.config.lifespan_class(server.config)
    return server


def _install_signal_handlers(server: uvicorn.Server, scope: anyio.CancelScope) -> None:
    def handler(sig: int, frame: FrameType | None) -> None:
        scope.cancel()
        server.handle_exit(sig=cast(signal.Signals, sig), frame=frame)  # type: ignore

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handler)


def get_api_server(
    port_connector: ServerPortConnector, cancel_scope: anyio.CancelScope
) -> uvicorn.Server:
    app.state.port_connector = port_connector
    server = _get_uvicorn_server()
    _install_signal_handlers(server=server, scope=cancel_scope)
    return server

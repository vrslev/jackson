import signal
from types import FrameType

import anyio
import fastapi
import uvicorn
from fastapi import Body, FastAPI, HTTPException, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jackson.connector_server import (
    Connection,
    FailedToConnectPorts,
    PlaybackPortAlreadyHasConnections,
    PortConnectorError,
    PortNotFound,
    ServerPortConnector,
)


async def port_connector_error_handler(
    request: fastapi.Request, exc: PortConnectorError
) -> JSONResponse:
    status_map: dict[type[BaseModel], int] = {
        PortNotFound: 404,
        PlaybackPortAlreadyHasConnections: status.HTTP_409_CONFLICT,
        FailedToConnectPorts: status.HTTP_424_FAILED_DEPENDENCY,
    }
    http_exc = HTTPException(
        status_code=status_map[type(exc.data)],
        detail={"message": type(exc.data).__name__, "data": exc.data.dict()},
    )
    return await http_exception_handler(request=request, exc=http_exc)


def get_app(port_connector: ServerPortConnector) -> FastAPI:
    app = FastAPI(exception_handlers={PortConnectorError: port_connector_error_handler})

    @app.get("/init")
    async def _():
        return port_connector.init()

    @app.patch("/connect")
    async def _(connections: list[Connection] = Body(...)):
        return await port_connector.connect(connections)

    return app


def install_api_signal_handlers(
    server: uvicorn.Server, scope: anyio.CancelScope
) -> None:
    def handler(sig: int, frame: FrameType | None) -> None:
        scope.cancel()
        server.handle_exit(sig=sig, frame=frame)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handler)


def get_api_server(port_connector: ServerPortConnector) -> uvicorn.Server:
    app = get_app(port_connector)
    config = uvicorn.Config(app=app, host="0.0.0.0", workers=1, log_config=None)
    server = uvicorn.Server(config)
    server.config.load()
    server.lifespan = server.config.lifespan_class(server.config)
    return server

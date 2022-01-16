import logging
import signal
from copy import copy
from typing import cast

import anyio
import jack
import typer
import uvicorn  # type: ignore
import uvicorn.logging  # type: ignore
from fastapi import Depends, FastAPI, status
from uvicorn.config import LOGGING_CONFIG  # type: ignore

import jack_server
from jackson.services.jack_client import JackClient
from jackson.services.messaging.models import (
    ConnectResponse,
    InitResponse,
    PlaybackPortAlreadyHasConnectionsData,
    PortNotFound,
    PortType,
    StructuredHTTPException,
)
from jackson.services.util import generate_output_formatters

app = FastAPI()

_info, _err = generate_output_formatters("messaging-server")


async def get_jack_client():
    def info_stream_handler(message: str):
        typer.secho(_info(message))  # type: ignore

    def error_stream_handler(message: str):
        typer.secho(_err(message))  # type: ignore

    client = JackClient("MessagingServer", info_stream_handler, error_stream_handler)
    yield client
    client.block_streams()


@app.get("/init", response_model=InitResponse)
def init(client: JackClient = Depends(get_jack_client)):
    inputs = client.get_ports("system:.*", is_input=True)
    outputs = client.get_ports("system:.*", is_output=True)
    rate = cast(jack_server.SampleRate, client.samplerate)  # NOPE TODO: From settings

    return InitResponse(inputs=len(inputs), outputs=len(outputs), rate=rate)


def check_client_name_not_system(client_name: str):
    if client_name == "system":
        raise StructuredHTTPException(
            status.HTTP_400_BAD_REQUEST, 'Client name can\'t be "system"'
        )


def get_port_or_raise(client: JackClient, type: PortType, name: str):
    try:
        return client.get_port_by_name(name)
    except jack.JackError:
        raise StructuredHTTPException(
            404, message="Port not found", data=PortNotFound(type=type, name=name)
        )


@app.put("/connect/send")
def connect_send(
    *,
    jack_client: JackClient = Depends(get_jack_client),
    client_name: str,
    client_port_number: int,
    server_port_number: int,
):
    # TO mixer
    check_client_name_not_system(client_name)
    source_name = f"{client_name}:receive_{client_port_number}"
    source = get_port_or_raise(client=jack_client, type="source", name=source_name)

    destination_name = f"system:playback_{server_port_number}"
    destination = get_port_or_raise(
        client=jack_client, type="destination", name=destination_name
    )

    if connections := jack_client.get_all_connections(destination):
        raise StructuredHTTPException(
            status.HTTP_409_CONFLICT,
            message="Port already has connections",
            data=PlaybackPortAlreadyHasConnectionsData(
                port_name=destination_name,
                connection_names=[p.name for p in connections],
            ),
        )

    jack_client.connect(source, destination)
    return ConnectResponse(source=source_name, destination=destination_name)


@app.patch("/connect/receive")
def connect_receive(
    *,
    jack_client: JackClient = Depends(get_jack_client),
    client_name: str,
    client_port_number: int,
    server_port_number: int,
):
    # FROM mixer
    check_client_name_not_system(client_name)
    source_name = f"system:capture_{server_port_number}"
    source = get_port_or_raise(client=jack_client, type="source", name=source_name)

    destination_name = f"{client_name}:playback_{client_port_number}"
    destination = get_port_or_raise(
        client=jack_client, type="destination", name=destination_name
    )

    jack_client.connect(source, destination)
    return ConnectResponse(source=source_name, destination=destination_name)


_level_name_colors = {
    5: _info,
    logging.DEBUG: _info,
    logging.INFO: _info,
    logging.WARNING: _info,
    logging.ERROR: _err,
    logging.CRITICAL: _err,
}


class _UvicornDefaultFormatter(uvicorn.logging.DefaultFormatter):
    def formatMessage(self, record: logging.LogRecord) -> str:
        recordcopy = copy(record)
        func = _level_name_colors[recordcopy.levelno]
        recordcopy.message = func(recordcopy.getMessage())
        return super().formatMessage(recordcopy)


class _UvicornAccessFormatter(uvicorn.logging.AccessFormatter):
    def formatMessage(self, record: logging.LogRecord) -> str:
        recordcopy = copy(record)
        client_addr, method, full_path, http_version, status_code = recordcopy.args  # type: ignore
        status_code = self.get_status_code(int(status_code))  # type: ignore
        request_line = (
            f"{client_addr} {method} {full_path} HTTP/{http_version} {status_code}"
        )
        func = _level_name_colors[recordcopy.levelno]
        request_line = func(request_line)
        recordcopy.__dict__["request_line"] = request_line
        return uvicorn.logging.ColourizedFormatter.formatMessage(self, recordcopy)


def configure_logging():
    LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(message)s"
    LOGGING_CONFIG["formatters"]["default"]["()"] = _UvicornDefaultFormatter
    LOGGING_CONFIG["formatters"]["default"]["use_colors"] = False
    LOGGING_CONFIG["formatters"]["access"]["fmt"] = "%(request_line)s"
    LOGGING_CONFIG["formatters"]["access"]["()"] = _UvicornAccessFormatter


class MessagingServer(uvicorn.Server):
    def __init__(self, app: FastAPI) -> None:
        configure_logging()
        super().__init__(uvicorn.Config(app=app, workers=1))
        self.config.load()
        self.lifespan = self.config.lifespan_class(self.config)

    async def start(self):
        await self.startup()  # type: ignore

    async def stop(self):
        self.should_exit = True
        await self.main_loop()
        await self.shutdown()


async def uvicorn_signal_handler(scope: anyio.CancelScope):
    with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
        async for _ in signals:
            scope.cancel()
            return

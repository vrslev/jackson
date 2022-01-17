import logging
import signal
from functools import lru_cache

import anyio
import jack
import uvicorn  # type: ignore
from fastapi import Depends, FastAPI, status
from rich.logging import RichHandler

from jackson.services.jack_client import JackClient
from jackson.services.models import (
    ConnectResponse,
    InitResponse,
    PlaybackPortAlreadyHasConnectionsData,
    PortDirectionType,
    PortNotFound,
    StructuredHTTPException,
)
from jackson.services.util import generate_stream_handlers

app = FastAPI()


@lru_cache
def get_jack_client():
    return JackClient("MessagingServer", *generate_stream_handlers("messaging"))


@app.get("/init", response_model=InitResponse)
def init(client: JackClient = Depends(get_jack_client)):
    from jackson.settings import server_settings

    inputs = client.get_ports("system:.*", is_input=True)
    outputs = client.get_ports("system:.*", is_output=True)
    rate = server_settings.audio.sample_rate

    return InitResponse(inputs=len(inputs), outputs=len(outputs), rate=rate)


def check_client_name_not_system(client_name: str):
    if client_name == "system":
        raise StructuredHTTPException(
            status.HTTP_400_BAD_REQUEST, 'Client name can\'t be "system"'
        )


def get_port_or_raise(client: JackClient, type: PortDirectionType, name: str):
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
    port_idx: int,
):
    # TO mixer
    check_client_name_not_system(client_name)
    source_name = f"{client_name}:receive_{port_idx}"
    source = get_port_or_raise(client=jack_client, type="source", name=source_name)

    destination_name = f"system:playback_{port_idx}"
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
    logging.info(f"Connected ports: {source_name} -> {destination_name}")
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


class MessagingServer(uvicorn.Server):
    def __init__(self, app: FastAPI) -> None:
        logging.basicConfig(
            level="INFO",
            format="%(message)s",
            datefmt="[%X] [messaging]",
            handlers=[RichHandler()],
        )

        super().__init__(uvicorn.Config(app=app, workers=1, log_config=None))
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

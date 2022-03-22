from dataclasses import dataclass
from functools import partial

import anyio
import httpx
import jack_server
import typer
import yaml
from jack_server._server import SetByJack_
from typer.params import Option

from jackson import jacktrip
from jackson.jack_client import init_jack_client
from jackson.logging import configure_loggers
from jackson.manager import ClientManager, GetJackServer, ServerManager
from jackson.port_connection import (
    ConnectionMap,
    build_connection_map,
    count_receive_send_channels,
)
from jackson.settings import ClientSettings, ServerSettings


@dataclass(init=False)
class Server:
    manager: ServerManager

    def __init__(self, settings: ServerSettings) -> None:
        server = jack_server.Server(
            name=settings.audio.jack_server_name,
            driver=settings.audio.driver,
            device=settings.audio.device or SetByJack_,
            rate=settings.audio.sample_rate,
            period=settings.audio.buffer_size,
        )
        get_jacktrip = lambda: jacktrip.get_server(
            jack_server_name=settings.audio.jack_server_name,
            port=settings.server.jacktrip_port,
        )
        get_jack_client = partial(init_jack_client, settings.audio.jack_server_name)
        self.manager = ServerManager(
            jack_server=server,
            get_jacktrip=get_jacktrip,
            get_jack_client=get_jack_client,
        )


@dataclass(init=False)
class Client:
    manager: ClientManager

    def get_connection_map(
        self, inputs_limit: int, outputs_limit: int
    ) -> ConnectionMap:
        return build_connection_map(
            client_name=self.settings.name,
            receive=self.settings.ports.receive,
            send=self.settings.ports.send,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )

    def get_jacktrip(self, map: ConnectionMap) -> jacktrip.StreamingProcess:
        receive_count, send_count = count_receive_send_channels(map)
        return jacktrip.get_client(
            jack_server_name=self.settings.audio.jack_server_name,
            server_host=self.settings.server.host,
            server_port=self.settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=self.settings.name,
        )

    def __init__(self, settings: ClientSettings) -> None:
        self.settings = settings

        api_http_client = httpx.AsyncClient(base_url=settings.server.api_url)

        get_jack_server: GetJackServer = lambda rate, period: jack_server.Server(
            name=settings.audio.jack_server_name,
            driver=settings.audio.driver,
            device=settings.audio.device or SetByJack_,
            rate=rate,
            period=period,
        )

        get_jack_client = partial(init_jack_client, settings.audio.jack_server_name)

        self.manager = ClientManager(
            api_http_client=api_http_client,
            get_jack_server=get_jack_server,
            get_jack_client=get_jack_client,
            get_connection_map=self.get_connection_map,
            get_jacktrip=self.get_jacktrip,
        )


app = typer.Typer()


@app.command()
def server(config: typer.FileText = Option("server.yaml")) -> None:
    configure_loggers("server")
    settings = ServerSettings(**yaml.safe_load(config))
    server = Server(settings)
    anyio.run(server.manager.run, backend_options={"use_uvloop": True})


@app.command()
def client(config: typer.FileText = Option("client.yaml")) -> None:
    configure_loggers("client")
    settings = ClientSettings(**yaml.safe_load(config))
    client = Client(settings=settings)
    anyio.run(client.manager.run, backend_options={"use_uvloop": True})

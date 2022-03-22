from dataclasses import dataclass

import anyio
import httpx
import jack
import jack_server
import typer
import yaml
from attr import field
from jack_server._server import SetByJack_
from typer.params import Option

from jackson import jacktrip
from jackson.jack_client import get_jack_client
from jackson.logging import configure_loggers
from jackson.manager import ClientManager, ServerManager
from jackson.port_connection import (
    ConnectionMap,
    build_connection_map,
    count_receive_send_channels,
)
from jackson.settings import ClientSettings, ServerSettings


@dataclass
class Server:
    settings: ServerSettings
    manager: ServerManager = field(init=False)

    def get_jack_server(self) -> jack_server.Server:
        audio = self.settings.audio
        return jack_server.Server(
            name=audio.jack_server_name,
            driver=audio.driver,
            device=audio.device or SetByJack_,
            rate=audio.sample_rate,
            period=audio.buffer_size,
        )

    def get_jacktrip(self) -> jacktrip.StreamingProcess:
        return jacktrip.get_server(
            jack_server_name=self.settings.audio.jack_server_name,
            port=self.settings.server.jacktrip_port,
        )

    def get_jack_client(self) -> jack.Client:
        return get_jack_client(self.settings.audio.jack_server_name)

    def __post_init__(self) -> None:
        self.manager = ServerManager(
            jack_server=self.get_jack_server(),
            get_jacktrip=self.get_jacktrip,
            get_jack_client=self.get_jack_client,
        )


@dataclass
class Client:
    settings: ClientSettings
    manager: ClientManager = field(init=False)

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

    def get_jack_server(
        self, rate: jack_server.SampleRate, period: int
    ) -> jack_server.Server:
        return jack_server.Server(
            name=self.settings.audio.jack_server_name,
            driver=self.settings.audio.driver,
            device=self.settings.audio.device or SetByJack_,
            rate=rate,
            period=period,
        )

    def get_jack_client(self) -> jack.Client:
        return get_jack_client(self.settings.audio.jack_server_name)

    def __post_init__(self) -> None:
        self.manager = ClientManager(
            api_http_client=httpx.AsyncClient(base_url=self.settings.server.api_url),
            get_jack_server=self.get_jack_server,
            get_jack_client=self.get_jack_client,
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

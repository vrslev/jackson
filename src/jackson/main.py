from dataclasses import dataclass
from functools import partial
from typing import Callable, Coroutine

import anyio
import jack_server
import typer
import yaml
from jack_server._server import SetByJack_
from typer.params import Option

from jackson import jacktrip
from jackson.api.client import APIClient
from jackson.api.server import APIServer
from jackson.connector.client import ClientPortConnector
from jackson.jack_server import JackServerController
from jackson.logging import configure_loggers
from jackson.manager import (
    ClientManager,
    GetJack,
    GetPortConnector,
    ServerManager,
    StartClientJacktrip,
)
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
        jack = jack_server.Server(
            name=settings.audio.jack_server_name,
            driver=settings.audio.driver,
            device=settings.audio.device or SetByJack_,
            rate=settings.audio.sample_rate,
            period=settings.audio.buffer_size,
        )
        jack_controller = JackServerController(jack)
        api = APIServer(settings.audio.jack_server_name)
        start_jacktrip = lambda: jacktrip.run_server(
            jack_server_name=settings.audio.jack_server_name,
            port=settings.server.jacktrip_port,
        )
        self.manager = ServerManager(
            jack=jack_controller, api=api, start_jacktrip=start_jacktrip
        )


@dataclass(init=False)
class Client:
    manager: ClientManager

    def get_port_connector(
        self,
        settings: ClientSettings,
        connect_on_server: Callable[[ConnectionMap], Coroutine[None, None, None]],
        inputs_limit: int,
        outputs_limit: int,
    ) -> ClientPortConnector:
        map = build_connection_map(
            client_name=settings.name,
            receive=settings.ports.receive,
            send=settings.ports.send,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )
        return ClientPortConnector(
            jack_server_name=settings.audio.jack_server_name,
            connection_map=map,
            connect_on_server=connect_on_server,
        )

    async def start_jacktrip(
        self, settings: ClientSettings, map: ConnectionMap
    ) -> None:
        receive_count, send_count = count_receive_send_channels(map)
        return await jacktrip.run_client(
            jack_server_name=settings.audio.jack_server_name,
            server_host=settings.server.host,
            server_port=settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=settings.name,
        )

    def __init__(self, settings: ClientSettings) -> None:
        api = APIClient(base_url=settings.server.api_url)
        get_jack: GetJack = lambda rate, period: JackServerController(
            jack_server.Server(
                name=settings.audio.jack_server_name,
                driver=settings.audio.driver,
                device=settings.audio.device or SetByJack_,
                rate=rate,
                period=period,
            )
        )
        get_port_connector: GetPortConnector = partial(
            self.get_port_connector, settings
        )
        start_jacktrip: StartClientJacktrip = partial(self.start_jacktrip, settings)
        self.manager = ClientManager(
            api=api,
            get_jack=get_jack,
            get_port_connector=get_port_connector,
            start_jacktrip=start_jacktrip,
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

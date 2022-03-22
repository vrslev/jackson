import io

import anyio
import click
import httpx
import jack_server
import yaml
from jack_server._server import SetByJack_

from jackson import jacktrip
from jackson.jack_client import get_jack_client
from jackson.logging import configure_logging
from jackson.manager import Client, GetJackServer, Server
from jackson.settings import ClientSettings, ServerSettings, load_client_settings


def get_server_manager(settings: ServerSettings) -> Server:
    jack_server_ = jack_server.Server(
        name=settings.audio.jack_server_name,
        driver=settings.audio.driver,
        device=settings.audio.device or SetByJack_,
        rate=settings.audio.sample_rate,
        period=settings.audio.buffer_size,
    )
    jack_client = get_jack_client(settings.audio.jack_server_name)
    jacktrip_ = jacktrip.get_server(
        jack_server_name=settings.audio.jack_server_name,
        port=settings.server.jacktrip_port,
    )
    return Server(jack_server=jack_server_, jack_client=jack_client, jacktrip=jacktrip_)


def get_client_manager(settings: ClientSettings) -> Client:
    get_jack_server: GetJackServer = lambda rate, period: jack_server.Server(
        name=settings.audio.jack_server_name,
        driver=settings.audio.driver,
        device=settings.audio.device or SetByJack_,
        rate=rate,
        period=period,
    )
    get_jack_client_ = lambda: get_jack_client(settings.audio.jack_server_name)

    def get_jacktrip(receive_count: int, send_count: int) -> jacktrip.StreamingProcess:
        return jacktrip.get_client(
            jack_server_name=settings.audio.jack_server_name,
            server_host=settings.server.host,
            server_port=settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=settings.name,
        )

    return Client(
        api_http_client=httpx.AsyncClient(base_url=settings.server.api_url),
        connection_map=settings.connection_map,
        get_jack_server=get_jack_server,
        get_jack_client=get_jack_client_,
        get_jacktrip=get_jacktrip,
    )


@click.group()
def cli():
    ...


@cli.command()
@click.option("--config", default="server.yaml", type=click.File())
def server(config: io.TextIOWrapper) -> None:
    configure_logging("server")
    server = get_server_manager(ServerSettings(**yaml.safe_load(config)))
    anyio.run(server.run, backend_options={"use_uvloop": True})


@cli.command()
@click.option("--config", default="client.yaml", type=click.File())
def client(config: io.TextIOWrapper) -> None:
    configure_logging("client")
    client = get_client_manager(load_client_settings(yaml.safe_load(config)))
    anyio.run(client.run, backend_options={"use_uvloop": True})

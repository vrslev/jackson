import io

import anyio
import click
import httpx
import jack_server
import yaml
from jack_server._server import SetByJack_

from jackson import jacktrip
from jackson.api_client import APIClient
from jackson.logging import configure_logging, jacktrip_log
from jackson.manager import Client, Server, run_manager
from jackson.settings import ClientSettings, ServerSettings


def get_server(settings: ServerSettings) -> Server:
    jack_server_ = jack_server.Server(
        name=settings.audio.jack_server_name,
        driver=settings.audio.driver,
        device=settings.audio.device or SetByJack_,
        rate=settings.audio.sample_rate,
        period=settings.audio.buffer_size,
    )
    jacktrip_ = jacktrip.get_server(
        jack_server_name=settings.audio.jack_server_name,
        port=settings.server.jacktrip_port,
        log=jacktrip_log,
    )
    return Server(jack_server=jack_server_, jacktrip=jacktrip_)


def get_client(settings: ClientSettings) -> Client:
    def get_jack_server(rate: jack_server.SampleRate, period: int):
        return jack_server.Server(
            name=settings.audio.jack_server_name,
            driver=settings.audio.driver,
            device=settings.audio.device or SetByJack_,
            rate=rate,
            period=period,
        )

    def get_jacktrip(receive_count: int, send_count: int):
        return jacktrip.get_client(
            jack_server_name=settings.audio.jack_server_name,
            server_host=settings.server.host,
            server_port=settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=settings.name,
            log=jacktrip_log,
        )

    api = APIClient(httpx.AsyncClient(base_url=settings.server.api_url))
    return Client(
        api=api,
        connection_map=settings.connection_map,
        get_jack_server=get_jack_server,
        get_jacktrip=get_jacktrip,
    )


@click.group()
def cli():
    ...


@cli.command
@click.option("--config", default="server.yaml", type=click.File())
def server(config: io.TextIOWrapper) -> None:
    configure_logging("server")
    server = get_server(ServerSettings(**yaml.safe_load(config)))
    anyio.run(lambda: run_manager(server), backend_options={"use_uvloop": True})


@cli.command
@click.option("--config", default="client.yaml", type=click.File())
def client(config: io.TextIOWrapper) -> None:
    configure_logging("client")
    client = get_client(ClientSettings.load(yaml.safe_load(config)))
    anyio.run(lambda: run_manager(client), backend_options={"use_uvloop": True})

import anyio
import httpx
import jack_server
import typer
import yaml
from jack_server._server import SetByJack_
from typer.params import Option

from jackson import jacktrip
from jackson.jack_client import get_jack_client
from jackson.logging import configure_logging
from jackson.manager import Client, GetJackServer, Server
from jackson.port_connection import ConnectionMap, build_connection_map
from jackson.settings import ClientSettings, ServerSettings


def get_server_manager(settings: ServerSettings) -> Server:
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
    )
    get_jack_client_ = lambda: get_jack_client(settings.audio.jack_server_name)
    return Server(
        jack_server=jack_server_, jacktrip=jacktrip_, get_jack_client=get_jack_client_
    )


def get_client_manager(settings: ClientSettings) -> Client:
    get_jack_server: GetJackServer = lambda rate, period: jack_server.Server(
        name=settings.audio.jack_server_name,
        driver=settings.audio.driver,
        device=settings.audio.device or SetByJack_,
        rate=rate,
        period=period,
    )
    get_jack_client_ = lambda: get_jack_client(settings.audio.jack_server_name)

    def get_connection_map(inputs_limit: int, outputs_limit: int) -> ConnectionMap:
        return build_connection_map(
            client_name=settings.name,
            receive=settings.ports.receive,
            send=settings.ports.send,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )

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
        get_jack_server=get_jack_server,
        get_jack_client=get_jack_client_,
        get_connection_map=get_connection_map,
        get_jacktrip=get_jacktrip,
    )


app = typer.Typer()


@app.command()
def server(config: typer.FileText = Option("server.yaml")) -> None:
    configure_logging("server")
    server = get_server_manager(ServerSettings(**yaml.safe_load(config)))
    anyio.run(server.run, backend_options={"use_uvloop": True})


@app.command()
def client(config: typer.FileText = Option("client.yaml")) -> None:
    configure_logging("client")
    client = get_client_manager(ClientSettings(**yaml.safe_load(config)))
    anyio.run(client.run, backend_options={"use_uvloop": True})

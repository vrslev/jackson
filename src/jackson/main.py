import anyio
import typer
import yaml
from typer.params import Option

from jackson.logging import configure_loggers
from jackson.manager import Client, Server
from jackson.settings import ClientSettings, ServerSettings

app = typer.Typer()


@app.command()
def server(config: typer.FileText = Option("server.yaml")) -> None:
    configure_loggers("server")
    settings = ServerSettings(**yaml.safe_load(config))
    server = Server(settings)
    anyio.run(server.run, backend_options={"use_uvloop": True})


@app.command()
def client(
    config: typer.FileText = Option("client.yaml"),
    no_jack: bool = Option(False, "--no-jack"),
) -> None:
    configure_loggers("client")
    settings = ClientSettings(**yaml.safe_load(config), start_jack=not no_jack)
    client = Client(settings=settings)
    anyio.run(client.run, backend_options={"use_uvloop": True})

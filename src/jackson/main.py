import asyncer
import rich.traceback
import typer
from typer.params import Option

from jackson.manager import Client, Server
from jackson.settings import ClientSettings, ServerSettings

rich.traceback.install()

app = typer.Typer()


@app.command("server")
def server_command(config: typer.FileText = Option("config.server.yaml")):
    settings = ServerSettings.from_yaml(config)
    server = Server(settings)
    asyncer.runnify(server.run)()


@app.command("client")
def client_command(
    config: typer.FileText = Option("config.client.yaml"),
    no_jack: bool = Option(False, "--no-jack"),
):
    settings = ClientSettings.from_yaml(config)
    client = Client(settings=settings, start_jack=not no_jack)
    asyncer.runnify(client.run)()


if __name__ == "__main__":
    app()

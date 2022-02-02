import asyncer
import typer
from typer.params import Option

from jackson.manager import Client, Server
from jackson.settings import ClientSettings, ServerSettings

app = typer.Typer()


@app.command("server")
def server_command(config: typer.FileText = Option("config.server.yaml")):
    settings = ServerSettings.from_yaml(config)
    server = Server(settings)
    asyncer.runnify(server.run, backend_options={"use_uvloop": True})()


@app.command("client")
def client_command(
    config: typer.FileText = Option("config.client.yaml"),
    no_jack: bool = Option(False, "--no-jack"),
):
    settings = ClientSettings.from_yaml(config)
    client = Client(settings=settings, start_jack=not no_jack)
    asyncer.runnify(client.run, backend_options={"use_uvloop": True})()


if __name__ == "__main__":
    app()

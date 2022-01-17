import asyncer
import typer
from typer.params import Option

import jackson.settings
from jackson.manager import Client, Server
from jackson.settings import ClientSettings, ServerSettings

app = typer.Typer()


@app.command("server")
def server_command(config: typer.FileText = Option("config.server.yaml")):
    jackson.settings.server_settings = ServerSettings.from_yaml(config)
    server = Server(jackson.settings.server_settings)
    asyncer.runnify(server.run)()


@app.command("client")
def client_command(
    config: typer.FileText = Option("config.client.yaml"),
    no_jack: bool = Option(False, "--no-jack"),
):
    jackson.settings.client_settings = ClientSettings.from_yaml(config)
    client = Client(settings=jackson.settings.client_settings, start_jack=not no_jack)
    asyncer.runnify(client.run)()


if __name__ == "__main__":
    app()

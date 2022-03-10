import anyio
import typer
import yaml
from typer.params import Option

from jackson.logging import configure_loggers
from jackson.manager import Client, Server
from jackson.settings import ClientSettings, ServerSettings

app = typer.Typer()


@app.command()
def server(
    config: typer.FileText = Option("config.server.yaml"),
    no_workers_output: bool = Option(False, "--no-workers-output"),
):
    configure_loggers("server")

    settings = ServerSettings(**yaml.safe_load(config))
    server = Server(settings)

    if no_workers_output:
        import jackson.api.server
        import jackson.jack_server
        import jackson.jacktrip

        jackson.api.server.uvicorn_access_log.disabled = True
        jackson.jack_server.log.disabled = True
        jackson.jacktrip.log.disabled = True

    anyio.run(server.run)


@app.command()
def client(
    config: typer.FileText = Option("config.client.yaml"),
    no_jack: bool = Option(False, "--no-jack"),
):
    configure_loggers("client")

    settings = ClientSettings(**yaml.safe_load(config))
    client = Client(settings=settings, start_jack=not no_jack)

    anyio.run(client.run, backend_options={"use_uvloop": True})


if __name__ == "__main__":
    app()

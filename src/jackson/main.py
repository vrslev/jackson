import asyncer
import typer
from typer.params import Option

app = typer.Typer()


@app.command("server")
def server_command(
    config: typer.FileText = Option("config.server.yaml"),
    no_workers_output: bool = Option(False, "--no-workers-output"),
):
    import jackson.logging

    jackson.logging.MODE = "server"

    from jackson.manager import Server
    from jackson.settings import ServerSettings

    settings = ServerSettings.from_yaml(config)
    server = Server(settings)

    if no_workers_output:
        import jackson.api.server
        import jackson.jack_server
        import jackson.jacktrip

        jackson.api.server.uvicorn_access_log.disabled = True
        jackson.jack_server.log.disabled = True
        jackson.jacktrip.log.disabled = True

    asyncer.runnify(server.run)()


@app.command("client")
def client_command(
    config: typer.FileText = Option("config.client.yaml"),
    no_jack: bool = Option(False, "--no-jack"),
):
    import jackson.logging

    jackson.logging.MODE = "client"

    from jackson.manager import Client
    from jackson.settings import ClientSettings

    settings = ClientSettings.from_yaml(config)
    client = Client(settings=settings, start_jack=not no_jack)
    asyncer.runnify(client.run, backend_options={"use_uvloop": True})()


if __name__ == "__main__":
    app()

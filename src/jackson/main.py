import anyio
import asyncer
import typer
from typer.params import Option

import jack_server
from jackson.services import jacktrip
from jackson.services.port_connector import PortConnector
from jackson.services.util import generate_stream_handlers
from jackson.settings import ClientSettings, ServerSettings


async def start_server(settings: ServerSettings):
    info_stream_handler, error_stream_handler = generate_stream_handlers("jack")
    jack = jack_server.Server(
        driver=settings.audio.driver,
        device=settings.audio.device,
        rate=settings.audio.sample_rate,
        info_stream_handler=info_stream_handler,
        error_stream_handler=error_stream_handler,
    )
    # port_connector = PortConnector(settings.server.ports)

    async with asyncer.create_task_group() as task_group:
        try:
            try:
                jack.start()
            except (
                jack_server.ServerNotStartedError,
                jack_server.ServerNotOpenedError,
            ):
                raise typer.Exit(1)
            # port_connector.init()

            # task_group.soonify(port_connector.start_queue)()
            task_group.soonify(jacktrip.start_server)(port=settings.jacktrip_port)

            while True:
                await anyio.sleep(1)

        finally:
            with anyio.CancelScope(shield=True):
                # port_connector.deinit()
                jack.stop()


async def start_client(settings: ClientSettings, start_jack: bool):
    info_stream_handler, error_stream_handler = generate_stream_handlers("jack")
    jack = jack_server.Server(
        driver=settings.audio.driver,
        device=settings.audio.device,
        rate=48000,
        # rate=settings.sample_rate, # TODO: Use sample rate and receive channels and send channels from /init
        info_stream_handler=info_stream_handler,
        error_stream_handler=error_stream_handler,
    )
    port_connector = PortConnector(settings.ports)

    async with asyncer.create_task_group() as task_group:
        try:
            if start_jack:
                jack.start()
            port_connector.init()

            task_group.soonify(port_connector.start_queue)()
            task_group.soonify(jacktrip.start_client)(
                url=settings.server.jacktrip_url,
                receive_channels=16,
                send_channels=2,
                remote_name=settings.name,
            )

            while True:
                await anyio.sleep(1)

        finally:
            with anyio.CancelScope(shield=True):
                port_connector.deinit()
                if start_jack:
                    jack.stop()


app = typer.Typer()


@app.command("server")
def server_command(config: typer.FileText = Option("config.server.yaml")):
    settings = ServerSettings.from_yaml(config)
    asyncer.runnify(start_server)(settings=settings)


@app.command("client")
def client_command(
    config: typer.FileText = Option("config.client.yaml"),
    no_jack: bool = Option(False, "--no-jack"),
):
    settings = ClientSettings.from_yaml(config)
    asyncer.runnify(start_client)(settings=settings, start_jack=not no_jack)


if __name__ == "__main__":
    app()

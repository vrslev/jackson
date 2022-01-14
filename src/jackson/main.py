import anyio
import asyncer
import typer
from typer.params import Option

import jack_server
from jackson.services import jacktrip
from jackson.services.channel_connector import ChannelConnector
from jackson.services.util import generate_stream_handler
from jackson.settings import Settings


async def start_server(settings: Settings):
    jack = jack_server.Server(
        driver=settings.server.backend,
        device=settings.server.device,
        rate=48000,
        stream_handler=generate_stream_handler("jack"),
    )
    channel_connector = ChannelConnector(settings.server.channels)

    async with asyncer.create_task_group() as task_group:
        try:
            jack.start()
            channel_connector.init()

            task_group.soonify(channel_connector.start_queue)()
            task_group.soonify(jacktrip.start_server)(
                server_port=settings.server.port,
                remote_name=settings.server.remote_name,
                local_address=settings.server.address,
            )

            while True:
                await anyio.sleep(1)

        finally:
            with anyio.CancelScope(shield=True):
                channel_connector.deinit()
                jack.stop()


async def start_client(settings: Settings):
    jack = jack_server.Server(
        driver=settings.client.backend,
        device=settings.client.device,
        rate=48000,
        stream_handler=generate_stream_handler("jack"),
    )
    channel_connector = ChannelConnector(channels=settings.client.channels)

    async with asyncer.create_task_group() as task_group:
        try:
            jack.start()
            channel_connector.init()

            task_group.soonify(channel_connector.start_queue)()
            task_group.soonify(jacktrip.start_client)(
                server_address=settings.server.address,
                server_port=settings.server.port,
                client_port=settings.client.port,
                receive_channels=16,
                send_channels=2,
                remote_name=settings.client.remote_name,
            )

            while True:
                await anyio.sleep(1)

        finally:
            with anyio.CancelScope(shield=True):
                channel_connector.deinit()
                jack.stop()


app = typer.Typer()


class Context(typer.Context):
    obj: Settings


@app.callback()
def main_callback(ctx: Context, config: typer.FileText = Option("config.yaml")):
    ctx.obj = Settings.load(config)


@app.command("server")
def server_command(ctx: Context):
    asyncer.runnify(start_server)(settings=ctx.obj)


@app.command("client")
def client_command(ctx: Context):
    asyncer.runnify(start_client)(settings=ctx.obj)


if __name__ == "__main__":
    app()

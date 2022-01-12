import asyncer
import typer
from typer.params import Option

from jackson.services import jackd, jacktrip
from jackson.services.channel_connector import ChannelConnector
from jackson.utils import Settings, check_jack_jacktrip_on_machine


async def start_server(settings: Settings):
    async with asyncer.create_task_group() as task_group:
        task_group.soonify(jackd.start)(
            backend=settings.server.backend, device=settings.server.device
        )
        channel_connector = ChannelConnector(settings.server.channels)

        async with channel_connector.init():
            task_group.soonify(channel_connector.start)()
            task_group.soonify(jacktrip.start_server)(
                server_port=settings.server.port,
                remote_name=settings.server.remote_name,
            )


async def start_client(settings: Settings):
    async with asyncer.create_task_group() as task_group:
        task_group.soonify(jackd.start)(
            backend=settings.client.backend, device=settings.client.device
        )
        channel_connector = ChannelConnector(channels=settings.client.channels)

        async with channel_connector.init():
            task_group.soonify(channel_connector.start)()
            task_group.soonify(jacktrip.start_client)(
                server_address=settings.server.address,
                server_port=settings.server.port,
                client_port=settings.client.port,
                receive_channels=16,
                send_channels=2,
                remote_name=settings.client.remote_name,
            )


app = typer.Typer()


class Context(typer.Context):
    obj: Settings


@app.callback()
def main_callback(ctx: Context, config: typer.FileText = Option("config.yaml")):
    ctx.obj = Settings.load(config)
    check_jack_jacktrip_on_machine()


@app.command("server")
def server_command(ctx: Context):
    asyncer.runnify(start_server)(settings=ctx.obj)


@app.command("client")
def client_command(ctx: Context):
    asyncer.runnify(start_client)(settings=ctx.obj)


if __name__ == "__main__":
    app()

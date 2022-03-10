import time

import anyio
import jack
import typer

from jackson.logging import JackClientFilter, get_logger, silent_jack_stream_handler

log = get_logger(__name__, "JackClient")
log.addFilter(JackClientFilter())


def _block_streams():
    jack.set_info_function(silent_jack_stream_handler)
    jack.set_error_function(silent_jack_stream_handler)


def _set_stream_handlers():
    jack.set_info_function(log.info)
    jack.set_error_function(log.error)


def _init_or_sleep(name: str, *, server_name: str) -> jack.Client | None:
    try:
        log.info(f"[yellow]Connecting to {server_name}...[/yellow]")
        client = jack.Client(name=name, no_start_server=True, servername=server_name)
        log.info(f"[green]Connected to {server_name}![/green]")
    except jack.JackOpenError:
        time.sleep(0.1)
    else:
        _set_stream_handlers()
        return client


def init_jack_client(name: str, *, server_name: str) -> jack.Client:
    _block_streams()

    for _ in range(100):
        if client := _init_or_sleep(name=name, server_name=server_name):
            return client

    log.error(f"[red]Can't connect to {server_name}[/red]")
    raise typer.Exit(1)


async def connect_ports_retry(
    client: jack.Client, source: str, destination: str
) -> None:
    """Connect ports for sure.

    Several issues could come up while connecting JACK ports.

    1. "Cannot connect ports owned by inactive clients: "MyName" is not active"
        This means that client is not initialized yet.

    2. "Unknown destination port in attempted (dis)connection src_name  dst_name"
        I.e. port is not initialized yet.
    """

    exc = None

    for _ in range(100):
        try:
            connections = client.get_all_connections(
                client.get_port_by_name(str(source))
            )
            if any(p.name == destination for p in connections):
                return

            client.connect(str(source), str(destination))
            log.info(
                f"Connected ports: [bold green]{source}[/bold green] ->"
                + f" [bold green]{destination}[/bold green]"
            )
            return

        except jack.JackError as e:
            exc = e
            await anyio.sleep(0.1)

    assert exc
    raise exc

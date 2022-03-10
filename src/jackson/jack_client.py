import time
from typing import cast

import jack
import jack_server
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


class JackClient(jack.Client):
    def _init_or_fail(self, name: str, server_name: str):
        for _ in range(100):
            try:
                log.info(f"[yellow]Connecting to {server_name}...[/yellow]")
                super().__init__(
                    name=name, no_start_server=True, servername=server_name
                )
                log.info(f"[green]Connected to {server_name}![/green]")
                return
            except jack.JackOpenError:
                time.sleep(0.1)

        log.error(f"[red]Can't connect to {server_name}[/red]")
        raise typer.Exit(1)

    def __init__(self, name: str, *, server_name: str) -> None:
        # Attribute exists so we don't call client.deactivate() on shutdown
        # if it wasn't activated. Otherwise causes segfault.
        self._activated = False

        _block_streams()
        self._init_or_fail(name=name, server_name=server_name)
        _set_stream_handlers()

    def activate(self) -> None:
        super().activate()
        self._activated = True

    def deactivate(self, ignore_errors: bool = True) -> None:
        if self._activated:
            super().deactivate(ignore_errors=ignore_errors)
        _block_streams()

    def connect(self, source: str, destination: str) -> None:
        super().connect(source, destination)
        log.info(
            f"Connected ports: [bold green]{source}[/bold green] ->"
            + f" [bold green]{destination}[/bold green]"
        )

    @property
    def samplerate(self) -> jack_server.SampleRate:
        return cast(jack_server.SampleRate, super().samplerate)

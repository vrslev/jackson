import time
from typing import cast

import jack
import jack_server
import typer

from jackson.logging import (
    JackClientFilter,
    get_configured_logger,
    silent_jack_stream_handler,
)
from jackson.port_connection import PortName

log = get_configured_logger(__name__, "JackClient")
log.addFilter(JackClientFilter())


class JackClient(jack.Client):
    def __init__(self, name: str) -> None:
        # Attribute exists so we don't call client.deactivate() on shutdown
        # if it wasn't activated. Otherwise causes segfault.
        self._activated = False

        self._block_streams()

        for _ in range(100):
            try:
                log.info("[yellow]Connecting to Jack...[/yellow]")
                super().__init__(name=name, no_start_server=True)
                log.info("[green]Connected to Jack![/green]")
                break
            except jack.JackOpenError:
                time.sleep(0.1)

        else:
            log.error("[red]Can't connect to Jack[/red]")
            raise typer.Exit(1)

        self._set_stream_handlers()

    def _block_streams(self):
        jack.set_info_function(silent_jack_stream_handler)
        jack.set_error_function(silent_jack_stream_handler)

    def _set_stream_handlers(self):
        jack.set_info_function(log.info)
        jack.set_error_function(log.error)

    def activate(self) -> None:
        super().activate()
        self._activated = True

    def deactivate(self, ignore_errors: bool = True) -> None:
        if self._activated:
            super().deactivate(ignore_errors=ignore_errors)

        self._block_streams()

    def connect(self, source: PortName, destination: PortName) -> None:  # type: ignore
        src_name = str(source)
        dest_name = str(destination)

        super().connect(src_name, dest_name)

        log.info(
            f"Connected ports: [bold green]{src_name}[/bold green] ->"
            + f" [bold green]{dest_name}[/bold green]"
        )

    def get_port_by_name(self, name: PortName) -> jack.Port:  # type: ignore
        return super().get_port_by_name(str(name))

    @property
    def samplerate(self) -> jack_server.SampleRate:
        return cast(jack_server.SampleRate, super().samplerate)

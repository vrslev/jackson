import time
from typing import cast

import anyio
import jack
import jack_server
import typer

from jackson.logging import JackClientFilter, get_logger, silent_jack_stream_handler
from jackson.port_connection import PortName

log = get_logger(__name__, "JackClient")
log.addFilter(JackClientFilter())


class JackClient(jack.Client):
    def _init_or_fail(self, name: str):
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

    def __init__(self, name: str) -> None:
        # Attribute exists so we don't call client.deactivate() on shutdown
        # if it wasn't activated. Otherwise causes segfault.
        self._activated = False

        self._block_streams()
        self._init_or_fail(name=name)
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
        src_name, dest_name = str(source), str(destination)
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

    async def connect_retry(self, source: PortName, destination: PortName) -> None:
        """Connect ports for sure.

        Several issues could come up while connecting JACK ports.

        1. "Cannot connect ports owned by inactive clients: "MyName" is not active"
            This means that client is not initialized yet.

        2. "Unknown destination port in attempted (dis)connection src_name  dst_name"
            I.e. port is not initialized yet.
        """

        exc = None
        dest_name = str(destination)

        for _ in range(100):
            try:
                connections = self.get_all_connections(self.get_port_by_name(source))
                if any(p.name == dest_name for p in connections):
                    return

                self.connect(source, destination)
                return

            except jack.JackError as e:
                exc = e
                await anyio.sleep(0.1)

        assert exc
        raise exc

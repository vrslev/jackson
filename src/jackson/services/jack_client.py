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
from jackson.services.port_connection import PortName

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
                log.info("Connecting to Jack...")
                super().__init__(name=name, no_start_server=True)
                log.info("Connected to Jack!")
                break
            except jack.JackOpenError:
                time.sleep(0.1)

        else:
            log.error("Can't connect to Jack")
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
        source_name = str(source)
        destination_name = str(destination)
        super().connect(source_name, destination_name)
        log.info(f"Connected ports: {source_name} -> {destination_name}")

    @property
    def samplerate(self) -> jack_server.SampleRate:
        return cast(jack_server.SampleRate, super().samplerate)

import time

import jack
import typer

from jackson.logging import get_configured_logger, silent_jack_stream_handler

log = get_configured_logger(__name__, "jack-client")


class JackClient(jack.Client):
    def __init__(self, name: str) -> None:
        # Attribute exists so we don't call client.deactivate()
        # on shutdown if it wasn't activated
        self._activated = False

        self.block_streams()

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

        self.set_stream_handlers()

    def set_stream_handlers(self):
        jack.set_info_function(log.info)
        jack.set_error_function(log.error)

    def block_streams(self):
        jack.set_info_function(silent_jack_stream_handler)
        jack.set_error_function(silent_jack_stream_handler)

    def activate(self) -> None:
        super().activate()
        self._activated = True

    def deactivate(self, ignore_errors: bool = True) -> None:
        if self._activated:
            super().deactivate(ignore_errors=ignore_errors)

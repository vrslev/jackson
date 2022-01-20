import typer

import jack_server
from jackson.logging import (
    JackServerFilter,
    get_configured_logger,
    silent_jack_stream_handler,
)

log = get_configured_logger(__name__, "JackServer")
log.addFilter(JackServerFilter())


class JackServer(jack_server.Server):
    def __init__(
        self, *, driver: str, device: str, rate: jack_server.SampleRate | None = None
    ):
        super().__init__(driver=driver, device=device, rate=rate)

    def start(self):
        jack_server.set_info_function(log.info)
        jack_server.set_error_function(log.error)

        try:
            super().start()
        except (jack_server.ServerNotStartedError, jack_server.ServerNotOpenedError):
            raise typer.Exit(1)

    def stop(self):
        jack_server.set_info_function(silent_jack_stream_handler)
        jack_server.set_error_function(silent_jack_stream_handler)

        super().stop()

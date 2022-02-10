import jack_server
import typer

from jackson.logging import JackServerFilter, get_logger, silent_jack_stream_handler

log = get_logger(__name__, "JackServer")
log.addFilter(JackServerFilter())


class JackServer(jack_server.Server):
    def __init__(
        self, *, driver: str, device: str | None, rate: jack_server.SampleRate
    ):
        super().__init__(driver=driver, device=device, rate=rate, sync=True)

    def _start_or_exit(self):
        try:
            super().start()
        except (jack_server.ServerNotOpenedError, jack_server.ServerNotStartedError):
            raise typer.Exit(1)

    def start(self):
        jack_server.set_info_function(log.info)
        jack_server.set_error_function(log.error)
        self._start_or_exit()

    def stop(self):
        jack_server.set_info_function(silent_jack_stream_handler)
        jack_server.set_error_function(silent_jack_stream_handler)
        super().stop()

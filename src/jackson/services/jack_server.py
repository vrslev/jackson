import typer

import jack_server
from jackson.services.util import generate_stream_handlers


class JackServer(jack_server.Server):
    def __init__(self, *, driver: str, device: str, rate: jack_server.SampleRate):
        super().__init__(driver=driver, device=device, rate=rate)
        self._info, self._err = generate_stream_handlers("jack")

    def start(self):
        jack_server.set_info_function(self._info)
        jack_server.set_error_function(self._err)

        try:
            super().start()
        except (jack_server.ServerNotStartedError, jack_server.ServerNotOpenedError):
            raise typer.Exit(1)

    def stop(self):
        super().stop()
        jack_server.set_info_function(None)
        jack_server.set_error_function(None)

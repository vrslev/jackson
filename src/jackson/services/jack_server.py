from typing import Callable

import jack_server


class Server(jack_server.Server):
    def __init__(
        self,
        *,
        driver: str,
        device: str,
        rate: jack_server.SampleRate,
        info_stream_handler: Callable[[str], None],
        error_stream_handler: Callable[[str], None],
    ):
        super().__init__(driver=driver, device=device, rate=rate)
        self._info = info_stream_handler
        self._err = error_stream_handler

    def start(self):
        jack_server.set_info_function(self._info)
        jack_server.set_error_function(self._err)
        super().start()

    def stop(self):
        super().stop()
        jack_server.set_info_function(None)
        jack_server.set_error_function(None)

import time
from typing import Callable

import jack
import typer


class JackClient(jack.Client):
    def __init__(
        self,
        name: str,
        info_stream_handler: Callable[[str], None],
        error_stream_handler: Callable[[str], None],
    ) -> None:
        # Attribute exists so we don't call client.deactivate()
        # on shutdown if it wasn't activated
        self._activated = False

        self._info = info_stream_handler
        self._err = error_stream_handler
        self.block_streams()

        for _ in range(100):
            try:
                self._info("Connecting to Jack...")
                super().__init__(name=name, no_start_server=True)
                self._info("Connected to Jack!")
                break
            except jack.JackOpenError:
                time.sleep(0.1)

        else:
            self._err("Can't connect to Jack")
            raise typer.Exit(1)

        self.set_stream_handlers()

    def set_stream_handlers(self):
        jack.set_error_function(self._info)
        jack.set_info_function(self._err)

    def block_streams(self):
        _dont_print: Callable[[str], None] = lambda message: None
        jack.set_error_function(_dont_print)
        jack.set_info_function(_dont_print)

    def activate(self) -> None:
        super().activate()
        self._activated = True

    def deactivate(self, ignore_errors: bool = True) -> None:
        if self._activated:
            super().deactivate(ignore_errors=ignore_errors)

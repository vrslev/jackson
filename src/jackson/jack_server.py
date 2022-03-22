from dataclasses import dataclass

import jack_server

from jackson.logging import MessageFilter, get_logger


class JackServerFilter(MessageFilter):
    messages = {
        "JackMachSemaphore::Destroy failed to kill semaphore",
        "JackMachSemaphoreServer::Execute",
        "self-connect-mode is",
        "Input channel = ",
        "JACK output port = ",
        "CoreAudio driver is running...",
    }


log = get_logger(__name__, "JackServer")
log.addFilter(JackServerFilter())


def set_jack_server_stream_handlers() -> None:
    jack_server.set_info_function(log.info)
    jack_server.set_error_function(log.error)


def block_jack_server_streams() -> None:
    jack_server.set_info_function(None)
    jack_server.set_error_function(None)


@dataclass
class JackServerController:
    server: jack_server.Server

    def start(self) -> None:
        set_jack_server_stream_handlers()
        self.server.start()

    def stop(self) -> None:
        block_jack_server_streams()
        self.server.stop()

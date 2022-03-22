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


def _set_stream_handlers() -> None:
    jack_server.set_info_function(log.info)
    jack_server.set_error_function(log.error)


def start_jack_server(server: jack_server.Server) -> None:
    _set_stream_handlers()
    server.start()


def block_jack_server_streams() -> None:
    jack_server.set_info_function(None)
    jack_server.set_error_function(None)

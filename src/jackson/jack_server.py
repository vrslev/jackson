import jack_server

from jackson.logging import MessageFilter, get_logger, silent_jack_stream_handler


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


def set_jack_server_stream_handlers():
    jack_server.set_info_function(log.info)
    jack_server.set_error_function(log.error)


def block_jack_server_streams():
    jack_server.set_info_function(silent_jack_stream_handler)
    jack_server.set_error_function(silent_jack_stream_handler)

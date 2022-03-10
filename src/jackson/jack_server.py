import jack_server

from jackson.logging import JackServerFilter, get_logger, silent_jack_stream_handler

log = get_logger(__name__, "JackServer")
log.addFilter(JackServerFilter())


def set_jack_server_stream_handlers():
    jack_server.set_info_function(log.info)
    jack_server.set_error_function(log.error)


def block_jack_server_streams():
    jack_server.set_info_function(silent_jack_stream_handler)
    jack_server.set_error_function(silent_jack_stream_handler)

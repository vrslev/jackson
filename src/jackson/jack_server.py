import jack_server

from jackson.logging import set_jack_server_stream_handlers


def start_jack_server(server: jack_server.Server) -> None:
    set_jack_server_stream_handlers()
    server.start()

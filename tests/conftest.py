import jack_server
import pytest

from jackson.jack_server import set_jack_server_stream_handlers


@pytest.fixture(scope="session")
def jack_server_log():
    """Log handlers set for session. Otherwise segfaults."""
    set_jack_server_stream_handlers()


@pytest.fixture
@pytest.mark.usefixtures("jack_server_log")
def jack_server_():
    server = jack_server.Server(name="default", driver="dummy")
    yield server
    server.stop()
    del server

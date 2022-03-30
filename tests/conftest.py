import jack_server
import pytest


@pytest.fixture(autouse=True)
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def jack_server_():
    server = jack_server.Server(name="default", driver="dummy")
    server.start()
    yield server
    server.stop()
    del server

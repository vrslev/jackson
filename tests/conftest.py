import _pytest.fixtures
import jack
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


@pytest.fixture
def jack_client(jack_server_: jack_server.Server):
    client = jack.Client("helper", no_start_server=True, servername=jack_server_.name)
    yield client
    client.deactivate()
    client.close = lambda: None  # type: ignore
    del client


@pytest.fixture(params=("send", "receive"))
def client_should(request: _pytest.fixtures.SubRequest):
    return request.param

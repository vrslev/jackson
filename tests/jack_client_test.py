from typing import Any

import anyio
import jack
import jack_server
import pytest

import jackson.jack_client
from jackson.jack_client import _connect_ports_and_log, retry_connect_ports


@pytest.fixture
def jack_client(jack_server_: jack_server.Server):
    client = jack.Client("helper", no_start_server=True, servername=jack_server_.name)
    yield client
    client.deactivate()
    client.close = lambda: None  # type: ignore
    del client


def test_connect_ports_and_log(jack_client: jack.Client):
    ports = "system:capture_1", "system:playback_1"
    _connect_ports_and_log(jack_client, *ports)
    _connect_ports_and_log(jack_client, *ports)
    jack_client.disconnect(*ports)


async def test_retry_connect_ports(monkeypatch: pytest.MonkeyPatch):
    retry = 0
    fail = True

    client_: Any = object()
    src: Any = object()
    dest: Any = object()

    def mock_connect(client: Any, source: Any, destination: Any):
        assert client == client_
        assert source == src
        assert destination == dest

        nonlocal retry
        retry += 1

        if fail:
            raise jack.JackError(retry)

    async def mock_sleep(duration: int):
        pass

    monkeypatch.setattr(jackson.jack_client, "_connect_ports_and_log", mock_connect)
    monkeypatch.setattr(anyio, "sleep", mock_sleep)

    with pytest.raises(jack.JackError, match="10"):
        await retry_connect_ports(client_, src, dest)

    retry = 0
    fail = False

    await retry_connect_ports(client_, src, dest)

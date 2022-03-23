import logging

import jack_server
import pytest

from jackson.jack_server import (
    JackServerFilter,
    block_jack_server_streams,
    log,
    start_jack_server,
)


@pytest.fixture
def jack_server_():
    server = jack_server.Server(name="default", driver="dummy")
    yield server
    server.stop()


def test_start_jack_server(
    jack_server_: jack_server.Server, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.INFO, logger=log.name):
        start_jack_server(jack_server_)

    assert (text := caplog.text)

    for message in JackServerFilter.messages:
        assert message not in text


def test_block_jack_server_streams(
    jack_server_: jack_server.Server, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.INFO, logger=log.name):
        block_jack_server_streams()
        jack_server_.start()

    assert not caplog.text

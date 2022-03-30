from types import SimpleNamespace
from typing import Any

import pytest

from jackson.connector_server import (
    PlaybackPortAlreadyHasConnections,
    PortConnectorError,
    _validate_playback_port_is_free,
)
from jackson.port_connection import PortName


@pytest.mark.parametrize("connected", [[], [SimpleNamespace(name="system:capture_1")]])
def test_validate_playback_port_is_free_ok(connected: list[Any]):
    _validate_playback_port_is_free(
        source=PortName.parse("system:capture_1"),
        destination=PortName.parse("system:playback_1"),
        connected_ports=connected,
    )


@pytest.mark.parametrize(
    "connected",
    [
        [SimpleNamespace(name="system:capture_2")],
        [
            SimpleNamespace(name="system:capture_1"),
            SimpleNamespace(name="system:capture_2"),
        ],
    ],
)
def test_validate_playback_port_is_free_fails(connected: list[Any]):
    dest = PortName.parse("system:playback_1")
    with pytest.raises(PortConnectorError) as exc:
        _validate_playback_port_is_free(
            source=PortName.parse("system:capture_1"),
            destination=dest,
            connected_ports=connected,
        )

    assert exc.value.data == PlaybackPortAlreadyHasConnections(
        port=dest, connections=[PortName.parse(p.name) for p in connected]
    )

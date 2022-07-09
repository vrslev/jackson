import jack
import jack_server
import pytest

from jackson.connector_server import (
    Connection,
    PlaybackPortAlreadyHasConnections,
    PortConnectorError,
    PortDirectionType,
    PortNotFound,
    ServerPortConnector,
    validate_playback_port_is_free,
)
from jackson.port_connection import ClientShould, PortName


@pytest.mark.parametrize("connected", [[], ["system:capture_1"]])
def test_validate_playback_port_is_free_ok(connected: list[str]):
    validate_playback_port_is_free(
        source=PortName.parse("system:capture_1"),
        destination=PortName.parse("system:playback_1"),
        connected_to_dest=connected,
    )


@pytest.mark.parametrize(
    "connected", [["system:capture_2"], ["system:capture_1", "system:capture_2"]]
)
def test_validate_playback_port_is_free_fails(connected: list[str]):
    dest = PortName.parse("system:playback_1")
    with pytest.raises(PortConnectorError) as exc:
        validate_playback_port_is_free(
            source=PortName.parse("system:capture_1"),
            destination=dest,
            connected_to_dest=connected,
        )

    assert exc.value.data == PlaybackPortAlreadyHasConnections(
        port=dest, connections=[PortName.parse(p) for p in connected]
    )


@pytest.fixture
def server_port_connector(jack_client: jack.Client):
    return ServerPortConnector(jack_client)


def test_init(
    server_port_connector: ServerPortConnector, jack_server_: jack_server.Server
):
    response = server_port_connector.init()
    assert response.inputs == response.outputs == 2
    assert response.rate == jack_server_.driver.rate
    assert response.buffer_size == jack_server_.driver.period


def test_get_existing_port(server_port_connector: ServerPortConnector):
    name = "system:playback_1"
    port = server_port_connector._get_existing_port(
        type="source", name=PortName.parse(name)
    )
    assert port.name == name


@pytest.mark.parametrize("type", ["source", "destination"])
def test_get_existing_port_fails(
    server_port_connector: ServerPortConnector, type: PortDirectionType
):
    name = PortName.parse("system:send_1")
    with pytest.raises(PortConnectorError) as exc:
        server_port_connector._get_existing_port(type=type, name=name)
    assert exc.value.data == PortNotFound(type=type, name=name)


def test_validate_connection(
    server_port_connector: ServerPortConnector, client_should: ClientShould
):
    conn = Connection(
        source=PortName.parse("system:capture_1"),
        destination=PortName.parse("system:playback_1"),
        client_should=client_should,
    )
    server_port_connector._validate_connection(conn)
    server_port_connector._make_connection(conn)
    conn.source = PortName.parse("system:capture_2")

    func = lambda: server_port_connector._validate_connection(conn)
    if client_should == "receive":
        return func()

    exc = pytest.raises(PortConnectorError, func)
    assert exc.value.data == PlaybackPortAlreadyHasConnections(
        port=conn.destination, connections=[PortName.parse("system:capture_1")]
    )

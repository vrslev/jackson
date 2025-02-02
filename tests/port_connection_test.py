import pytest

from jackson.port_connection import (
    ClientShould,
    PortConnection,
    PortName,
    _build_connection,
    _build_specific_connections,
    _validate_bridge_limit,
    build_connection_map,
)


@pytest.fixture()
def client_name():
    return "Lev"


@pytest.fixture
def send_connection(client_name: str):
    return PortConnection(
        client_should="send",
        source=PortName.parse("system:capture_2"),
        local_bridge=PortName.parse("JackTrip:send_3"),
        remote_bridge=PortName(client=client_name, type="receive", idx=3),
        destination=PortName.parse("system:playback_11"),
    )


@pytest.fixture
def receive_connection(client_name: str):
    return PortConnection(
        client_should="receive",
        source=PortName.parse("system:capture_1"),
        remote_bridge=PortName(client=client_name, type="send", idx=2),
        local_bridge=PortName.parse("JackTrip:receive_2"),
        destination=PortName.parse("system:playback_3"),
    )


def test_port_name_str():
    assert str(PortName(client="system", type="playback", idx=1)) == "system:playback_1"


def test_port_name_parse_passes():
    assert PortName.parse("my_app:playback_1") == PortName(
        client="my_app", type="playback", idx=1
    )


def test_port_name_parse_fails():
    with pytest.raises(AssertionError):
        PortName.parse("my_app:playback_1_2")


def test_port_connection_methods_send(send_connection: PortConnection):
    c = send_connection
    assert c.get_local_connection() == (c.source, c.local_bridge)
    assert c.get_remote_connection() == (c.remote_bridge, c.destination)


def test_port_connection_methods_receive(receive_connection: PortConnection):
    c = receive_connection
    assert c.get_remote_connection() == (c.source, c.remote_bridge)
    assert c.get_local_connection() == (c.local_bridge, c.destination)


def test_validate_bridge_limit_passes():
    _validate_bridge_limit(1, 1, "receive")


def test_validate_bridge_limit_fails(client_should: ClientShould):
    with pytest.raises(RuntimeError, match=client_should):
        _validate_bridge_limit(1, 2, client_should)


def test_build_connection_send(send_connection: PortConnection, client_name: str):
    assert send_connection == _build_connection(
        client_name=client_name,
        client_should="send",
        local=send_connection.source.idx,
        remote=send_connection.destination.idx,
        bridge=send_connection.local_bridge.idx,
    )


def test_build_connection_receive(receive_connection: PortConnection, client_name: str):
    assert receive_connection == _build_connection(
        client_name=client_name,
        client_should="receive",
        local=receive_connection.destination.idx,
        remote=receive_connection.source.idx,
        bridge=receive_connection.local_bridge.idx,
    )


def test_build_specific_connections_send(client_name: str, client_should: ClientShould):
    x, y = _build_specific_connections(
        client_name=client_name,
        client_should=client_should,
        ports={1: 2, 3: 4},
    )
    assert x.remote_bridge.client == y.remote_bridge.client == client_name
    assert x.client_should == y.client_should == client_should
    assert x.local_bridge.idx == 1
    assert y.local_bridge.idx == 2


def test_build_connection_map(client_name: str):
    result = build_connection_map(
        client_name=client_name, receive={1: 11, 2: 12}, send={3: 13, 4: 14}
    )
    local_idxs = set[int]()
    remote_idxs = set[int]()

    for local_bridge, connection in result.items():
        assert local_bridge == connection.local_bridge

        for port in connection.get_local_connection():
            if port.client == "system":
                local_idxs.add(port.idx)
                break

        for port in connection.get_remote_connection():
            if port.client == "system":
                remote_idxs.add(port.idx)

    assert local_idxs == {1, 2, 3, 4}
    assert remote_idxs == {11, 12, 13, 14}

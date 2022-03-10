from typing import Iterable, Literal, cast

from pydantic import BaseModel

from jackson import jacktrip

PortType = Literal["send", "receive", "capture", "playback"]


class PortName(BaseModel, frozen=True):
    client: str
    type: PortType
    idx: int

    def __str__(self) -> str:
        return f"{self.client}:{self.type}_{self.idx}"

    @classmethod
    def parse(cls, port_name: str):
        *_, type_and_idx = port_name.split(":")

        type, idx, *extra = type_and_idx.split("_")
        assert not extra

        client = port_name.replace(f":{type_and_idx}", "")

        return cls(client=client, type=cast(PortType, type), idx=int(idx))


ClientShould = Literal["send", "receive"]


class PortConnection(BaseModel, frozen=True):
    client_should: ClientShould
    source: PortName
    local_bridge: PortName
    remote_bridge: PortName
    destination: PortName

    def get_local_connection(self):
        if self.client_should == "send":
            return self.source, self.local_bridge
        else:
            return self.local_bridge, self.destination

    def get_remote_connection(self):
        if self.client_should == "send":
            return self.remote_bridge, self.destination
        else:
            return self.source, self.remote_bridge


def _build_connection(
    client_name: str,
    client_should: ClientShould,
    limit: int,
    local: int,
    remote: int,
    bridge: int,
) -> PortConnection:
    if bridge > limit:
        raise RuntimeError(f"Limit of available {client_should} ports exceeded.")

    if client_should == "send":
        source_idx, destination_idx = local, remote
        local_bridge_type, remote_bridge_type = "send", "receive"
    else:
        source_idx, destination_idx = remote, local
        local_bridge_type, remote_bridge_type = "receive", "send"

    return PortConnection(
        client_should=client_should,
        source=PortName(client="system", type="capture", idx=source_idx),
        local_bridge=PortName(
            client=jacktrip.JACK_CLIENT_NAME, type=local_bridge_type, idx=bridge
        ),
        remote_bridge=PortName(client=client_name, type=remote_bridge_type, idx=bridge),
        destination=PortName(client="system", type="playback", idx=destination_idx),
    )


def _build_specific_connections(
    client_name: str, client_should: ClientShould, limit: int, ports: dict[int, int]
) -> Iterable[PortConnection]:
    for idx, (local, remote) in enumerate(ports.items()):
        bridge = idx + 1
        yield _build_connection(
            client_name=client_name,
            client_should=client_should,
            limit=limit,
            local=local,
            remote=remote,
            bridge=bridge,
        )


def _build_connections_gen(
    client_name: str,
    receive: dict[int, int],
    send: dict[int, int],
    inputs_limit: int,
    outputs_limit: int,
) -> Iterable[PortConnection]:
    yield from _build_specific_connections(
        client_name=client_name, client_should="send", limit=inputs_limit, ports=send
    )
    yield from _build_specific_connections(
        client_name=client_name,
        client_should="receive",
        limit=outputs_limit,
        ports=receive,
    )


_RegisteredJackTripPort = PortName
ConnectionMap = dict[_RegisteredJackTripPort, PortConnection]


def build_connection_map(
    client_name: str,
    receive: dict[int, int],
    send: dict[int, int],
    inputs_limit: int,
    outputs_limit: int,
) -> ConnectionMap:
    """Build connection map between server and client. Is it being built on client side."""
    gen = _build_connections_gen(
        client_name=client_name,
        receive=receive,
        send=send,
        inputs_limit=inputs_limit,
        outputs_limit=outputs_limit,
    )
    return {conn.local_bridge: conn for conn in gen}


def count_receive_send_channels(connection_map: ConnectionMap) -> tuple[int, int]:
    # Required for JackTrip
    receive, send = 0, 0

    for connection in connection_map.values():
        if connection.client_should == "send":
            send += 1
        else:
            receive += 1

    return receive, send

from typing import Literal, cast

from pydantic import BaseModel

from jackson.settings import ClientPorts

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

        type_, idx, *extra = type_and_idx.split("_")
        assert not extra

        client = port_name.replace(f":{type_and_idx}", "")

        return cls(client=client, type=cast(PortType, type_), idx=int(idx))


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


def _validate_channel_limit(client_should: ClientShould, bridge: int, limit: int):
    if bridge > limit:
        raise RuntimeError(f"Limit of available {client_should} ports exceeded.")


def _get_send_connection(client: str, source: int, destination: int, bridge: int):
    return PortConnection(
        client_should="send",
        source=PortName(client="system", type="capture", idx=source),
        local_bridge=PortName(client="JackTrip", type="send", idx=bridge),
        remote_bridge=PortName(client=client, type="receive", idx=bridge),
        destination=PortName(client="system", type="playback", idx=destination),
    )


def _get_receive_connection(client: str, source: int, destination: int, bridge: int):
    return PortConnection(
        client_should="receive",
        source=PortName(client="system", type="capture", idx=source),
        remote_bridge=PortName(client=client, type="send", idx=bridge),
        local_bridge=PortName(client="JackTrip", type="receive", idx=bridge),
        destination=PortName(client="system", type="playback", idx=destination),
    )


def _build_validate_connections(
    client: str, client_should: ClientShould, ports: dict[int, int], limit: int
):
    prev_bridge = 0

    for source, destination in ports.items():
        bridge = prev_bridge + 1
        prev_bridge = bridge
        _validate_channel_limit(client_should=client_should, bridge=bridge, limit=limit)

        if client_should == "send":
            func = _get_send_connection
        else:
            func = _get_receive_connection

        yield func(client=client, source=source, destination=destination, bridge=bridge)


def _build_connections(
    client_name: str, ports: ClientPorts, inputs_limit: int, outputs_limit: int
):
    yield from _build_validate_connections(
        client_name, "send", ports.send, inputs_limit
    )
    yield from _build_validate_connections(
        client_name, "receive", ports.receive, outputs_limit
    )


_RegisteredJackTripPort = PortName
ConnectionMap = dict[_RegisteredJackTripPort, PortConnection]


def build_connection_map(
    client_name: str, ports: ClientPorts, inputs_limit: int, outputs_limit: int
) -> ConnectionMap:
    """Build connection map between server and client. Is it being built on client side."""
    gen = _build_connections(
        client_name=client_name,
        ports=ports,
        inputs_limit=inputs_limit,
        outputs_limit=outputs_limit,
    )
    return {conn.local_bridge: conn for conn in gen}

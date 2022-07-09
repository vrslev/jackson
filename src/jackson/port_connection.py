from typing import Iterable, Literal, NewType, cast

from pydantic import BaseModel

from jackson import jacktrip

PortType = Literal["send", "receive", "capture", "playback"]


class PortName(BaseModel, frozen=True):
    """Parsed JACK port name."""

    client: str
    type: PortType
    idx: int

    def __str__(self) -> str:
        return f"{self.client}:{self.type}_{self.idx}"

    @classmethod
    def parse(cls, port_name: str):
        """Parse jack.Port().name into PortName."""
        *_, type_and_idx = port_name.split(":")
        type, idx, *extra = type_and_idx.split("_")
        assert not extra
        client = port_name.replace(f":{type_and_idx}", "")
        return cls(client=client, type=cast(PortType, type), idx=int(idx))


ClientShould = Literal["send", "receive"]


class PortConnection(BaseModel, frozen=True):
    """Connection of local and remote ports through bridge (JackTrip)."""

    client_should: ClientShould
    source: PortName
    local_bridge: PortName
    remote_bridge: PortName
    destination: PortName

    def get_local_connection(self) -> tuple[PortName, PortName]:
        """Get local source and destination ports."""
        if self.client_should == "send":
            return self.source, self.local_bridge
        else:
            return self.local_bridge, self.destination

    def get_remote_connection(self) -> tuple[PortName, PortName]:
        """Get remote source and destination ports."""
        if self.client_should == "send":
            return self.remote_bridge, self.destination
        else:
            return self.source, self.remote_bridge


RegisteredJackTripPort = NewType("RegisteredJackTripPort", PortName)
ConnectionMap = dict[RegisteredJackTripPort, PortConnection]


def _build_connection(
    *,
    client_name: str,
    local_bridge_client_name: str = jacktrip.JACK_CLIENT_NAME,
    client_should: ClientShould,
    local: int,
    remote: int,
    bridge: int,
) -> PortConnection:
    """
    Build port connection based on client role, name and port indexes
    assuming that JackTrip is used.
    """
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
            client=local_bridge_client_name, type=local_bridge_type, idx=bridge
        ),
        remote_bridge=PortName(client=client_name, type=remote_bridge_type, idx=bridge),
        destination=PortName(client="system", type="playback", idx=destination_idx),
    )


def _build_specific_connections(
    client_name: str, client_should: ClientShould, ports: dict[int, int]
) -> Iterable[PortConnection]:
    """Build port connection for `client_should`."""
    for idx, (local, remote) in enumerate(ports.items(), start=1):
        yield _build_connection(
            client_name=client_name,
            client_should=client_should,
            local=local,
            remote=remote,
            bridge=idx,
        )


def build_connection_map(
    client_name: str,
    receive: dict[int, int],
    send: dict[int, int],
) -> ConnectionMap:
    """Build connection map based on port indexes. Takes in account limits and client name."""

    def gen():
        yield from _build_specific_connections(
            client_name=client_name, client_should="send", ports=send
        )
        yield from _build_specific_connections(
            client_name=client_name, client_should="receive", ports=receive
        )

    return {RegisteredJackTripPort(conn.local_bridge): conn for conn in gen()}


def _validate_bridge_limit(
    limit: int, bridge_idx: int, client_should: ClientShould
) -> None:
    """Validate that receive or send count don't exceed given limit."""
    if bridge_idx > limit:
        raise RuntimeError(f"Limit of available {client_should} ports exceeded.")


def count_receive_send_channels(
    connection_map: ConnectionMap, inputs_limit: int, outputs_limit: int
) -> tuple[int, int]:
    """Count number of used receive and send ports for bridge limit allocation (JackTrip)."""

    receive, send = 0, 0

    for connection in connection_map.values():
        if connection.client_should == "send":
            send += 1
        else:
            receive += 1

    _validate_bridge_limit(limit=inputs_limit, bridge_idx=send, client_should="send")
    _validate_bridge_limit(
        limit=outputs_limit, bridge_idx=receive, client_should="receive"
    )

    return receive, send

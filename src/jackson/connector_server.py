from dataclasses import dataclass
from typing import Literal, cast

import jack
from jack_server import SampleRate
from pydantic import BaseModel

from jackson.jack_client import retry_connect_ports
from jackson.port_connection import ClientShould, PortName


class InitResponse(BaseModel):
    inputs: int
    outputs: int
    rate: SampleRate
    buffer_size: int


class Connection(BaseModel):
    source: PortName
    destination: PortName
    client_should: ClientShould


class ConnectResponse(BaseModel):
    pass


PortDirectionType = Literal["source", "destination"]


class PortNotFound(BaseModel):
    type: PortDirectionType
    name: PortName


class PlaybackPortAlreadyHasConnections(BaseModel):
    port: PortName
    connections: list[PortName]


class FailedToConnectPorts(BaseModel):
    source: PortName
    destination: PortName


@dataclass
class PortConnectorError(Exception):
    data: BaseModel


def _validate_playback_port_is_free(
    source: PortName, destination: PortName, connected_ports: list[PortName]
) -> None:
    if not connected_ports or connected_ports == [source]:
        return
    raise PortConnectorError(
        PlaybackPortAlreadyHasConnections(port=destination, connections=connected_ports)
    )


@dataclass
class ServerPortConnector:
    client: jack.Client

    def init(self) -> InitResponse:
        inputs = self.client.get_ports("system:.*", is_input=True)
        outputs = self.client.get_ports("system:.*", is_output=True)

        return InitResponse(
            inputs=len(inputs),
            outputs=len(outputs),
            rate=cast(SampleRate, self.client.samplerate),
            buffer_size=self.client.blocksize,
        )

    def _get_existing_port(self, type: PortDirectionType, name: PortName) -> jack.Port:
        try:
            return self.client.get_port_by_name(str(name))
        except jack.JackError:
            raise PortConnectorError(PortNotFound(type=type, name=name))

    def _validate_connection(self, conn: Connection) -> None:
        _src = self._get_existing_port("source", conn.source)
        dest = self._get_existing_port("destination", conn.destination)

        if conn.client_should == "receive":
            return

        connected_port_names = [
            PortName.parse(p.name) for p in self.client.get_all_connections(dest)
        ]
        _validate_playback_port_is_free(
            source=conn.source,
            destination=conn.destination,
            connected_ports=connected_port_names,
        )

    async def _connect_ports(self, source: PortName, destination: PortName) -> None:
        try:
            await retry_connect_ports(self.client, str(source), str(destination))
        except jack.JackError:
            raise PortConnectorError(
                FailedToConnectPorts(source=source, destination=destination),
            )

    async def connect(self, connections: list[Connection]) -> ConnectResponse:
        for conn in connections:
            self._validate_connection(conn)
            await self._connect_ports(conn.source, conn.destination)
        return ConnectResponse()

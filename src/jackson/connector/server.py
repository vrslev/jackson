from dataclasses import dataclass
from typing import cast

import jack
from jack_server import SampleRate
from pydantic import BaseModel

from jackson.connector import models
from jackson.jack_client import block_jack_client_streams, connect_ports_retry
from jackson.port_connection import PortName


@dataclass
class PortConnectorError(Exception):
    data: BaseModel


def _validate_playback_port_is_free(
    name: PortName, connected_ports: list[jack.Port]
) -> None:
    if not connected_ports:
        return

    names = [PortName.parse(p.name) for p in connected_ports]
    data = models.PlaybackPortAlreadyHasConnections(port=name, connections=names)
    raise PortConnectorError(data)


@dataclass
class ServerPortConnector:
    client: jack.Client

    def init(self) -> models.InitResponse:
        inputs = self.client.get_ports("system:.*", is_input=True)
        outputs = self.client.get_ports("system:.*", is_output=True)

        return models.InitResponse(
            inputs=len(inputs),
            outputs=len(outputs),
            rate=cast(SampleRate, self.client.samplerate),
            buffer_size=self.client.blocksize,
        )

    def _get_existing_port(
        self, type: models.PortDirectionType, name: PortName
    ) -> jack.Port:
        try:
            return self.client.get_port_by_name(str(name))
        except jack.JackError:
            raise PortConnectorError(models.PortNotFound(type=type, name=name))

    def _get_ports_from_connection(
        self, conn: models.Connection
    ) -> tuple[jack.Port, jack.Port]:
        source = self._get_existing_port(type="source", name=conn.source)
        destination = self._get_existing_port(type="destination", name=conn.destination)
        return source, destination

    def _validate_connection(self, conn: models.Connection) -> None:
        _, dest = self._get_ports_from_connection(conn)

        if conn.client_should == "send":
            _validate_playback_port_is_free(
                name=conn.destination,
                connected_ports=self.client.get_all_connections(dest),
            )

    async def _connect_ports(self, source: PortName, destination: PortName) -> None:
        try:
            await connect_ports_retry(self.client, str(source), str(destination))
        except jack.JackError:
            raise PortConnectorError(
                models.FailedToConnectPorts(source=source, destination=destination),
            )

    async def connect(
        self, connections: list[models.Connection]
    ) -> models.ConnectResponse:
        for conn in connections:
            self._validate_connection(conn)
            await self._connect_ports(conn.source, conn.destination)
        return models.ConnectResponse()

    def close(self) -> None:
        block_jack_client_streams()

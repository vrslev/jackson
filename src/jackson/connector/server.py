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


def init(client: jack.Client):
    inputs = client.get_ports("system:.*", is_input=True)
    outputs = client.get_ports("system:.*", is_output=True)

    return models.InitResponse(
        inputs=len(inputs),
        outputs=len(outputs),
        rate=cast(SampleRate, client.samplerate),
        buffer_size=client.blocksize,
    )


def _get_existing_port(
    client: jack.Client, type: models.PortDirectionType, name: PortName
) -> jack.Port:
    try:
        return client.get_port_by_name(str(name))
    except jack.JackError:
        raise PortConnectorError(models.PortNotFound(type=type, name=name))


def _get_ports_from_connection(
    client: jack.Client, conn: models.Connection
) -> tuple[jack.Port, jack.Port]:
    source = _get_existing_port(client, type="source", name=conn.source)
    destination = _get_existing_port(client, type="destination", name=conn.destination)
    return source, destination


def _validate_playback_port_is_free(
    name: PortName, connected_ports: list[jack.Port]
) -> None:
    if not connected_ports:
        return

    names = [PortName.parse(p.name) for p in connected_ports]
    data = models.PlaybackPortAlreadyHasConnections(port=name, connections=names)
    raise PortConnectorError(data)


def _validate_connection(client: jack.Client, conn: models.Connection) -> None:
    _, dest = _get_ports_from_connection(client, conn=conn)

    if conn.client_should == "send":
        _validate_playback_port_is_free(
            name=conn.destination, connected_ports=client.get_all_connections(dest)
        )


async def _connect_ports(
    client: jack.Client, source: PortName, destination: PortName
) -> None:
    try:
        await connect_ports_retry(client, str(source), str(destination))
    except jack.JackError:
        raise PortConnectorError(
            models.FailedToConnectPorts(source=source, destination=destination),
        )


async def connect(client: jack.Client, connections: list[models.Connection]):
    for conn in connections:
        _validate_connection(client, conn=conn)
        await _connect_ports(client, conn.source, conn.destination)
    return models.ConnectResponse()


@dataclass
class ServerPortConnector:
    client: jack.Client

    def init(self) -> models.InitResponse:
        return init(self.client)

    async def connect(
        self, connections: list[models.Connection]
    ) -> models.ConnectResponse:
        return await connect(self.client, connections)

    def close(self) -> None:
        block_jack_client_streams()

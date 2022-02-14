from typing import Literal

import jack_server
from pydantic import BaseModel

from jackson.port_connection import PortName


class InitResponse(BaseModel):
    inputs: int
    outputs: int
    rate: jack_server.SampleRate
    buffer_size: int


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


class ConnectResponse(BaseModel):
    source: PortName
    destination: PortName

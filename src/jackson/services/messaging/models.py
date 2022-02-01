from typing import Literal

import jack_server
from pydantic import BaseModel

from jackson.services.port_connection import PortName


class InitResponse(BaseModel):
    inputs: int
    outputs: int
    rate: jack_server.SampleRate


PortDirectionType = Literal["source", "destination"]


class PortNotFound(BaseModel):
    type: PortDirectionType
    name: PortName


class PlaybackPortAlreadyHasConnections(BaseModel):
    port_name: PortName
    connection_names: list[str]


class ConnectResponse(BaseModel):
    source: PortName
    destination: PortName

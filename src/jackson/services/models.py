from typing import Literal, cast

from pydantic import BaseModel

import jack_server

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

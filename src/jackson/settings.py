from ipaddress import IPv4Address
from typing import IO

import yaml
from pydantic import BaseModel, BaseSettings

import jack_server

_SourcePortName = str
_DestinationPortName = str
PortMap = dict[_SourcePortName, _DestinationPortName]


class _ServerSettings(BaseModel):
    address: IPv4Address
    ports: PortMap
    audio_driver: str
    audio_device: str


class _ClientSettings(BaseModel):
    name: str
    ports: PortMap
    audio_driver: str
    audio_device: str


class Settings(BaseSettings):
    sample_rate: jack_server.SampleRate
    server: _ServerSettings
    client: _ClientSettings

    @classmethod
    def load(cls, file: IO[str]):
        content = yaml.safe_load(file)
        return cls(**content)

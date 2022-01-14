from ipaddress import IPv4Address
from typing import IO

import yaml
from pydantic import BaseModel, BaseSettings

_SourcePort = str
_DestinationPort = str
ChannelMap = dict[_SourcePort, _DestinationPort]


class _ServerSettings(BaseModel):
    address: IPv4Address
    port: int
    channels: ChannelMap
    backend: str
    device: str


class _ClientSettings(BaseModel):
    remote_name: str
    port: int
    channels: ChannelMap
    backend: str
    device: str


class Settings(BaseSettings):
    server: _ServerSettings
    client: _ClientSettings

    @classmethod
    def load(cls, file: IO[str]):
        content = yaml.safe_load(file)
        return cls(**content)

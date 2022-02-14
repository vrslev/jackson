from ipaddress import IPv4Address
from typing import IO

import jack_server
import yaml
from pydantic import BaseModel, BaseSettings


class _YamlBaseSettings(BaseSettings):
    @classmethod
    def from_yaml(cls, file: IO[str]):
        content = yaml.safe_load(file)
        return cls(**content)


class _BaseAudio(BaseModel):
    driver: str
    device: str | None


class _ServerAudio(_BaseAudio):
    sample_rate: jack_server.SampleRate
    buffer_size: int  # In samples


class _BaseServer(BaseModel):
    jacktrip_port: int
    api_port: int


class _ServerServer(_BaseServer):
    pass


class ServerSettings(_YamlBaseSettings):
    audio: _ServerAudio
    server: _ServerServer


class _ClientAudio(_BaseAudio):
    pass


class _ClientServer(_BaseServer):
    host: IPv4Address


class ClientPorts(BaseModel):
    receive: dict[int, int]
    send: dict[int, int]


class ClientSettings(_YamlBaseSettings):
    name: str
    audio: _ClientAudio
    server: _ClientServer
    ports: ClientPorts

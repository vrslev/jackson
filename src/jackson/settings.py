from ipaddress import IPv4Address
from typing import IO, cast

import yaml
from pydantic import BaseModel, BaseSettings

import jack_server

_SourcePortName = str
_DestinationPortName = str
PortMap = dict[_SourcePortName, _DestinationPortName]


class _YamlBaseSettings(BaseSettings):
    @classmethod
    def from_yaml(cls, file: IO[str]):
        content = yaml.safe_load(file)
        return cls(**content)


class _BaseAudio(BaseModel):
    driver: str
    device: str


class _ServerAudio(_BaseAudio):
    sample_rate: jack_server.SampleRate


class _BaseServer(BaseModel):
    jacktrip_port: int
    messaging_port: int


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


server_settings = cast(ServerSettings, None)
client_settings = cast(ClientSettings, None)

from ipaddress import IPv4Address
from typing import IO

import yaml
from pydantic import BaseModel, BaseSettings


class _YamlBaseSettings(BaseSettings):
    @classmethod
    def from_yaml(cls, file: IO[str]):
        content = yaml.safe_load(file)
        return cls(**content)


class _Audio(BaseModel):
    driver: str
    device: str


class _ServerAudio(_Audio):
    pass


class _BaseServer(BaseModel):
    jacktrip_port: int
    messaging_port: int


class _ServerServer(_BaseServer):
    pass


class ServerSettings(_YamlBaseSettings):
    audio: _ServerAudio
    server: _ServerServer


class _ClientAudio(_Audio):
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

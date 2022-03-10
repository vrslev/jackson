from ipaddress import IPv4Address

import jack_server
from pydantic import BaseModel, BaseSettings


class _BaseAudio(BaseModel):
    driver: str
    device: str | None


class _ServerAudio(_BaseAudio):
    sample_rate: jack_server.SampleRate
    buffer_size: int  # In samples


class _BaseServer(BaseModel):
    jacktrip_port: int
    api_port: int


class ServerSettings(BaseSettings):
    audio: _ServerAudio
    server: _BaseServer


class _ClientServer(_BaseServer):
    host: IPv4Address


class ClientPorts(BaseModel):
    receive: dict[int, int]
    send: dict[int, int]


class ClientSettings(BaseSettings):
    name: str
    audio: _BaseAudio
    server: _ClientServer
    ports: ClientPorts

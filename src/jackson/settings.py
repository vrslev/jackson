from ipaddress import IPv4Address
from typing import Any

from jack_server import SampleRate
from pydantic import AnyHttpUrl, BaseModel

from jackson.port_connection import ConnectionMap, build_connection_map


class _ServerAudio(BaseModel):
    driver: str
    device: str | None
    jack_server_name: str = "JacksonServer"
    sample_rate: SampleRate
    buffer_size: int  # In samples


class _ServerServer(BaseModel):
    jacktrip_port: int
    api_port: int


class ServerSettings(BaseModel):
    audio: _ServerAudio
    server: _ServerServer


class _ClientAudio(BaseModel):
    driver: str
    device: str | None
    jack_server_name: str = "JacksonClient"


class _ClientServer(BaseModel):
    jacktrip_port: int
    api_port: int
    host: IPv4Address

    @property
    def api_url(self) -> str:
        return AnyHttpUrl.build(
            scheme="http", host=str(self.host), port=str(self.api_port)
        )


class _ClientPorts(BaseModel):
    receive: dict[int, int]
    send: dict[int, int]


class _FileClientSettings(BaseModel):
    name: str
    audio: _ClientAudio
    server: _ClientServer
    ports: _ClientPorts


class ClientSettings(BaseModel):
    name: str
    audio: _ClientAudio
    server: _ClientServer
    connection_map: ConnectionMap

    @staticmethod
    def load(content: Any) -> "ClientSettings":
        f = _FileClientSettings(**content)
        map = build_connection_map(
            client_name=f.name, receive=f.ports.receive, send=f.ports.send
        )
        return ClientSettings(
            name=f.name, audio=f.audio, server=f.server, connection_map=map
        )

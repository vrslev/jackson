from ipaddress import IPv4Address
from typing import Any

import jack_server
from pydantic import AnyHttpUrl, BaseModel, root_validator


class _BaseAudio(BaseModel):
    driver: str
    device: str | None
    jack_server_name: str


_DEFAULT_SERVER_JACK_SERVER_NAME = "JacksonServer"


class _ServerAudio(_BaseAudio):
    jack_server_name: str = _DEFAULT_SERVER_JACK_SERVER_NAME
    sample_rate: jack_server.SampleRate
    buffer_size: int  # In samples


class _BaseServer(BaseModel):
    jacktrip_port: int
    api_port: int


class ServerSettings(BaseModel):
    audio: _ServerAudio
    server: _BaseServer


class _ClientAudio(_BaseAudio):
    jack_server_name: str = "JacksonClient"


class _ClientServer(_BaseServer):
    host: IPv4Address

    @property
    def api_url(self) -> str:
        return AnyHttpUrl.build(
            scheme="http", host=str(self.host), port=str(self.api_port)
        )


class ClientPorts(BaseModel):
    receive: dict[int, int]
    send: dict[int, int]


class ClientSettings(BaseModel):
    name: str
    audio: _ClientAudio
    server: _ClientServer
    ports: ClientPorts
    start_jack: bool

    @root_validator
    def validate_all(cls, values: dict[str, Any]):
        if not values["start_jack"]:
            values["audio"].jack_server_name = _DEFAULT_SERVER_JACK_SERVER_NAME
        return values

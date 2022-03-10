from ipaddress import IPv4Address

import jack_server
from pydantic import BaseModel, BaseSettings


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


class ServerSettings(BaseSettings):
    audio: _ServerAudio
    server: _BaseServer


class _ClientAudio(_BaseAudio):
    jack_server_name: str = "JacksonClient"


class _ClientServer(_BaseServer):
    host: IPv4Address


class ClientPorts(BaseModel):
    receive: dict[int, int]
    send: dict[int, int]


class ClientSettings(BaseSettings):
    name: str
    audio: _ClientAudio
    server: _ClientServer
    ports: ClientPorts
    start_jack: bool

    def get_jack_server_name(self) -> str:
        return (
            self.audio.jack_server_name
            if self.start_jack
            else _DEFAULT_SERVER_JACK_SERVER_NAME
        )

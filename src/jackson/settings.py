from typing import IO, TYPE_CHECKING

import yaml
from pydantic import AnyUrl, BaseModel, BaseSettings, UrlError

import jack_server

if TYPE_CHECKING:
    from pydantic.networks import Parts
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


class ServerSettings(_YamlBaseSettings):
    audio: _ServerAudio
    jacktrip_port: int
    messaging_port: int


class _ClientAudio(_BaseAudio):
    pass


class UrlPortError(UrlError):
    code = "url.port"
    msg_template = "missing URL port"


# from pydantic import BaseConfig
# from pydantic.fields import ModelField
# from pydantic.networks import url_regex
# from pydantic.validators import constr_length_validator, str_validator


class UrlWithPort(AnyUrl):
    host: str
    port: str

    # @classmethod
    # def validate(
    #     cls, value: Any, field: ModelField, config: BaseConfig
    # ) -> "UrlWithPort":
    #     if value.__class__ == cls:
    #         return value
    #     url: str = str_validator(value)
    #     m = url_regex().match(url)
    #     assert m, "URL regex failed unexpectedly"

    #     original_parts = cast("Parts", m.groupdict())
    #     host, tld, host_type, rebuild = cls.validate_host(parts)

    @classmethod
    def validate_parts(cls, parts: "Parts") -> "Parts":
        parts["scheme"] = ""
        parts = super().validate_parts(parts)
        if not parts.get("port"):
            raise UrlPortError()
        return parts


class _ClientServer(BaseModel):
    jacktrip_url: UrlWithPort
    messaging_url: UrlWithPort


class ClientPorts(BaseModel):
    receive: dict[int, int]
    send: dict[int, int]


class ClientSettings(_YamlBaseSettings):
    name: str
    audio: _ClientAudio
    server: _ClientServer
    ports: ClientPorts


# class _ServerSettings(BaseModel):
#     address: IPv4Address
#     ports: PortMap
#     audio_driver: str
#     audio_device: str


# class _ClientSettings(BaseModel):
#     name: str
#     ports: PortMap
#     audio_driver: str
#     audio_device: str


# class Settings(BaseSettings):
#     sample_rate: jack_server.SampleRate
#     server: _ServerSettings
#     client: _ClientSettings

#     @classmethod
#     def load(cls, file: IO[str]):
#         content = yaml.safe_load(file)
#         return cls(**content)

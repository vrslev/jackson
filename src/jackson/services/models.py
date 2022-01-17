from typing import Any, Literal, cast

from fastapi import HTTPException
from pydantic import BaseModel

import jack_server


class InitResponse(BaseModel):
    inputs: int
    outputs: int
    rate: jack_server.SampleRate


class StructuredDetail(BaseModel):
    message: str
    data: BaseModel | None


class StructuredHTTPException(HTTPException):
    def __init__(
        self,
        status_code: int,
        message: str,
        data: BaseModel | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            detail=StructuredDetail(message=message, data=data),
            headers=headers,
        )


PortDirectionType = Literal["source", "destination"]


class PortNotFound(BaseModel):
    type: PortDirectionType
    name: str


class PlaybackPortAlreadyHasConnectionsData(BaseModel):
    port_name: str
    connection_names: list[str]


class ConnectResponse(BaseModel):
    source: str
    destination: str


PortType = Literal["send", "receive", "capture", "playback"]


class PortName(BaseModel, frozen=True):
    client: str
    type: PortType
    idx: int

    def __str__(self) -> str:
        return f"{self.client}:{self.type}_{self.idx}"

    @classmethod
    def parse(cls, port_name: str):
        *_, type_and_idx = port_name.split(":")

        type_, idx, *extra = type_and_idx.split("_")
        assert not extra

        client = port_name.replace(f":{type_and_idx}", "")

        return cls(client=client, type=cast(PortType, type_), idx=int(idx))

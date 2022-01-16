from typing import Any, Literal

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


PortType = Literal["source", "destination"]


class PortNotFound(BaseModel):
    type: PortType
    name: str


class PlaybackPortAlreadyHasConnectionsData(BaseModel):
    port_name: str
    connection_names: list[str]


class ConnectResponse(BaseModel):
    source: str
    destination: str

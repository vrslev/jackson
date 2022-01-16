from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel


class InitResponse(BaseModel):
    inputs: int
    outputs: int


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

    def exc(self):
        return StructuredHTTPException(404, message="Source port not found", data=self)


class PortAlreadyHasConnectionsData(BaseModel):
    type: PortType
    name: str
    connection_names: list[str]

    def exc(self):
        return StructuredHTTPException(
            status.HTTP_409_CONFLICT, message="Port already has connections", data=self
        )


class ConnectResponse(BaseModel):
    source: str
    destination: str

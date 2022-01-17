from ipaddress import IPv4Address
from typing import Any

import httpx
from pydantic import AnyHttpUrl, BaseModel
from pydantic.dataclasses import dataclass

from jackson.services.models import (
    ConnectResponse,
    InitResponse,
    PlaybackPortAlreadyHasConnections,
    PortName,
    PortNotFound,
)


@dataclass
class ServerError(Exception):
    message: str
    data: Any

    def __str__(self) -> str:
        return f"{self.message}: {self.data.dict()}"


def build_exception(
    name: str, detail: dict[str, Any], data_model: type[BaseModel]
) -> Exception:
    cls_ = dataclass(type(name, (ServerError,), {"message": None, "data": None}))
    exc = cls_(message=detail["message"], data=data_model(**detail["data"]))
    return exc  # type: ignore


class MessagingClient:
    def __init__(self, host: IPv4Address, port: int) -> None:
        base_url = AnyHttpUrl.build(scheme="http", host=str(host), port=str(port))
        self.client = httpx.AsyncClient(base_url=base_url)
        self.exception_handlers: dict[str, tuple[str, type[BaseModel]]] = {
            "Port already has connections": (
                "PlaybackPortAlreadyHasConnectionsError",
                PlaybackPortAlreadyHasConnections,
            ),
            "Port not found": ("PortNotFoundError", PortNotFound),
        }

    async def init(self):
        response = await self.client.get("/init")  # type: ignore
        return InitResponse(**response.json())

    def handler_detail(self, detail: dict[str, Any]):
        resp = self.exception_handlers.get(detail["message"])
        if resp is None:
            raise NotImplementedError

        name, model = resp
        raise build_exception(name=name, detail=detail, data_model=model)

    async def connect_send(self, client_name: str, destination_idx: int):
        """
        CONFIG
        ports:
            send:
                3: 2


        ON CLIENT
        system:capture_3 -> JackTrip:send_2

        ON SERVER
        JackTrip:receive_2 -> system:playback_2
        """
        response = await self.client.put(  # type: ignore
            "/connect/send",
            params={"client_name": client_name, "port_idx": destination_idx},
        )
        data = response.json()
        if "detail" in data:
            self.handler_detail(data["detail"])
        return ConnectResponse(**data)

    async def connect_receive(
        self, client_name: str, destination_idx: int
    ) -> ConnectResponse:
        raise NotImplementedError

    async def connect(self, client_name: str, source: PortName, destination: PortName):
        if source.client == "system":
            return await self.connect_send(
                client_name=client_name, destination_idx=destination.idx
            )
        elif destination.client == "system":
            return
            return await self.connect_receive(
                client_name=client_name, destination_idx=destination.idx
            )
        raise NotImplementedError

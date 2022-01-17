from ipaddress import IPv4Address
from typing import Any

import httpx
from pydantic import AnyHttpUrl, BaseModel
from pydantic.dataclasses import dataclass

from jackson.logging import get_configured_logger
from jackson.services.models import (
    ConnectResponse,
    InitResponse,
    PlaybackPortAlreadyHasConnections,
    PortName,
    PortNotFound,
)

log = get_configured_logger(__name__, "messaging-client")


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

    def handle_exceptions(self, data: dict[str, Any]):
        if "detail" not in data:
            return

        resp = self.exception_handlers.get(data["detail"]["message"])
        if resp is None:
            raise NotImplementedError

        name, model = resp
        raise build_exception(name=name, detail=data["detail"], data_model=model)

    async def connect_send(self, client_name: str, destination_idx: int):
        """
        CONFIG
        send:
            3: 2

        ON CLIENT
        system:capture_3 -> JackTrip:send_2

        ON SERVER
        Lev:receive_2 -> system:playback_2
        """
        response = await self.client.put(  # type: ignore
            "/connect/send",
            params={"client_name": client_name, "port_idx": destination_idx},
        )
        data = response.json()
        self.handle_exceptions(data)

        parsed_data = ConnectResponse(**data)
        log.info(
            f"Connected ports on server: {parsed_data.source} -> {parsed_data.destination}"
        )

    async def connect_receive(self, client_name: str, source_idx: int):
        """
        CONFIG
        receive:
            2: 3

        ON CLIENT
        JackTrip:receive_3 -> system:playback_2

        ON SERVER
        system:capture_3 -> Lev:send_3
        """
        response = await self.client.patch(  # type: ignore
            "/connect/receive",
            params={"client_name": client_name, "port_idx": source_idx},
        )
        data = response.json()
        self.handle_exceptions(data)

        parsed_data = ConnectResponse(**data)
        log.info(
            f"Connected ports on server: {parsed_data.source} -> {parsed_data.destination}"
        )

    async def connect(self, client_name: str, source: PortName, destination: PortName):
        if source.client == "system":
            return await self.connect_send(
                client_name=client_name, destination_idx=destination.idx
            )

        elif destination.client == "system":
            return await self.connect_receive(
                client_name=client_name, source_idx=source.idx
            )

        raise NotImplementedError

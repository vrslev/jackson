from ipaddress import IPv4Address
from typing import Any

import httpx
from pydantic import AnyHttpUrl, BaseModel
from pydantic.dataclasses import dataclass

from jackson.logging import get_configured_logger
from jackson.services.models import (
    ClientShould,
    ConnectResponse,
    InitResponse,
    PlaybackPortAlreadyHasConnections,
    PortName,
    PortNotFound,
)

log = get_configured_logger(__name__, "HttpClient")


@dataclass
class ServerError(Exception):
    message: str
    data: Any

    def __str__(self) -> str:
        return f"{self.message}: {self.data.dict()}"


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
        if "detail" not in data or "message" not in data["detail"]:
            return

        detail = data["detail"]
        res = self.exception_handlers.get(detail["message"])
        if res is None:
            raise NotImplementedError

        name, model = res

        cls_ = dataclass(type(name, (ServerError,), {"message": None, "data": None}))
        exc = cls_(message=detail["message"], data=model(**detail["data"]))
        raise exc  # type: ignore

    async def connect(
        self,
        source: PortName,
        destination: PortName,
        client_should: ClientShould,
    ):
        response = await self.client.patch(  # type: ignore
            "/connect",
            json={
                "source": source.dict(),
                "destination": destination.dict(),
                "client_should": client_should,
            },
        )
        data = response.json()
        self.handle_exceptions(data)

        parsed_data = ConnectResponse(**data)
        log.info(
            f"Connected ports on server: {parsed_data.source} -> {parsed_data.destination}"
        )

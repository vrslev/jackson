from dataclasses import dataclass
from functools import partial
from ipaddress import IPv4Address
from typing import Any, Callable, Coroutine, TypeVar

import anyio
import httpx
from pydantic import AnyHttpUrl, BaseModel

from jackson.api.models import (
    ConnectResponse,
    FailedToConnectPorts,
    InitResponse,
    PlaybackPortAlreadyHasConnections,
    PortName,
    PortNotFound,
)
from jackson.logging import get_logger
from jackson.port_connection import ClientShould

log = get_logger(__name__, "HttpClient")


@dataclass
class ServerError(Exception):
    message: str
    data: BaseModel

    def __str__(self) -> str:
        return f"{self.message} ({self.data})"


_T = TypeVar("_T", bound=BaseModel)


class MessagingClient:
    def __init__(self, host: IPv4Address, port: int) -> None:
        base_url = AnyHttpUrl.build(scheme="http", host=str(host), port=str(port))
        self.client = httpx.AsyncClient(base_url=base_url)
        self.known_errors: tuple[type[BaseModel], ...] = (
            PlaybackPortAlreadyHasConnections,
            PortNotFound,
            FailedToConnectPorts,
        )

    def _handle_exceptions(self, data: dict[str, Any]):
        if "detail" not in data:
            return

        if "message" not in data["detail"]:
            raise RuntimeError(data)

        detail = data["detail"]

        model = None
        for m in self.known_errors:
            if m.__name__ == detail["message"]:
                model = m
                break

        if model is None:
            raise RuntimeError(data)

        raise ServerError(message=detail["message"], data=model(**detail["data"]))

    def _handle_response(self, response: httpx.Response, model: type[_T]) -> _T:
        data = response.json()
        self._handle_exceptions(data)
        return model(**data)

    async def _retry(
        self,
        func: Callable[[], Coroutine[None, None, httpx.Response]],
        times: int,
        delay: float,
    ) -> httpx.Response:
        response = None

        for _ in range(times):
            response = await func()
            if response.status_code == 404:  # type: ignore
                await anyio.sleep(delay)
                continue
            else:
                return response

        assert response
        return response

    async def init(self):
        response = await self.client.get("/init")  # type: ignore
        return self._handle_response(response, InitResponse)

    def _build_connect_payload(
        self, source: PortName, destination: PortName, client_should: ClientShould
    ):
        return {
            "source": source.dict(),
            "destination": destination.dict(),
            "client_should": client_should,
        }

    async def connect(
        self, source: PortName, destination: PortName, client_should: ClientShould
    ):
        payload = self._build_connect_payload(source, destination, client_should)
        _connect = partial(self.client.patch, "/connect", json=payload)  # type: ignore
        response = await self._retry(_connect, times=3, delay=0.5)
        data = self._handle_response(response, ConnectResponse)
        log.info(
            f"Connected ports on server: [bold cyan]{data.source}[/bold cyan]"
            + f" -> [bold cyan]{data.destination}[/bold cyan]"
        )

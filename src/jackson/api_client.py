from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Coroutine, Iterable, TypeVar

import anyio
import httpx
from pydantic import BaseModel

from jackson.connector_server import (
    Connection,
    ConnectResponse,
    FailedToConnectPorts,
    InitResponse,
    PlaybackPortAlreadyHasConnections,
    PortNotFound,
)
from jackson.port_connection import ConnectionMap


@dataclass
class ServerError(Exception):
    message: str
    data: BaseModel

    def __str__(self) -> str:
        return f"{self.message} ({self.data})"


known_errors: tuple[type[BaseModel], ...] = (
    PlaybackPortAlreadyHasConnections,
    PortNotFound,
    FailedToConnectPorts,
)
T = TypeVar("T")


def _is_structured_exception(data: dict[str, Any]) -> bool:
    return "message" in data["detail"] and "data" in data["detail"]


def _find_model_by_name(name: str) -> type[BaseModel] | None:
    for model in known_errors:
        if model.__name__ == name:
            return model


def _handle_exceptions(data: dict[str, Any]) -> None:
    if "detail" not in data:
        return

    if not _is_structured_exception(data):
        raise RuntimeError(data)

    name = data["detail"]["message"]

    if not (model := _find_model_by_name(name)):
        raise RuntimeError(data)

    raise ServerError(message=name, data=model(**data["detail"]["data"]))


def handle_response(response: httpx.Response, model: type[T]) -> T:
    data = response.json()
    _handle_exceptions(data)
    return model(**data)


def get_required_remote_connections(map: ConnectionMap) -> Iterable[dict[str, Any]]:
    for connection in map.values():
        src, dest = connection.get_remote_connection()
        yield Connection(
            source=src, destination=dest, client_should=connection.client_should
        ).dict()


async def retry_connect_func(
    func: Callable[[], Coroutine[None, None, httpx.Response]]
) -> httpx.Response:
    response = None

    for _ in range(3):
        if (response := await func()).status_code != 404:
            return response
        await anyio.sleep(0.5)

    assert response
    return response


@dataclass
class APIClient:
    client: httpx.AsyncClient

    async def init(self) -> InitResponse:
        response = await self.client.get("/init")  # pyright: ignore
        return handle_response(response, InitResponse)

    async def connect(self, connection_map: ConnectionMap) -> None:
        payload = list(get_required_remote_connections(connection_map))
        func = partial(self.client.patch, "/connect", json=payload)  # pyright: ignore
        response = await retry_connect_func(func)
        handle_response(response, ConnectResponse)

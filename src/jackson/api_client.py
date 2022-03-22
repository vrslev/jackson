from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Coroutine, Iterable

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


_known_errors: tuple[type[BaseModel], ...] = (
    PlaybackPortAlreadyHasConnections,
    PortNotFound,
    FailedToConnectPorts,
)


def _is_structured_exception(data: dict[str, Any]) -> bool:
    return "message" in data["detail"] and "data" in data["detail"]


def _find_model_by_name(name: str) -> type[BaseModel] | None:
    for model in _known_errors:
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


def _handle_response(response: httpx.Response) -> Any:
    data = response.json()
    _handle_exceptions(data)
    return data


def _get_connections(map: ConnectionMap) -> Iterable[dict[str, Any]]:
    for connection in map.values():
        src, dest = connection.get_remote_connection()
        yield Connection(
            source=src, destination=dest, client_should=connection.client_should
        ).dict()


async def _retry_connect(
    func: Callable[[], Coroutine[None, None, httpx.Response]]
) -> httpx.Response:
    response = None

    for _ in range(3):
        response = await func()
        if response.status_code == 404:
            await anyio.sleep(0.5)
        else:
            return response

    assert response
    return response


@dataclass
class APIClient:
    client: httpx.AsyncClient

    async def init(self) -> InitResponse:
        response = await self.client.get("/init")  # type: ignore
        return InitResponse(**_handle_response(response))

    async def connect(self, connection_map: ConnectionMap) -> None:
        payload = list(_get_connections(connection_map))
        func = partial(self.client.patch, "/connect", json=payload)  # type: ignore
        response = await _retry_connect(func)
        ConnectResponse(**_handle_response(response))

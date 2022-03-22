from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Coroutine, Iterable

import anyio
import httpx
from pydantic import BaseModel

from jackson.connector.server import (
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


def _handle_exceptions(data: dict[str, Any]) -> None:
    if "detail" not in data:
        return

    if "message" not in data["detail"]:
        raise RuntimeError(data)

    message = data["detail"]["message"]
    detail_data = data["detail"]["data"]

    model = None
    for m in _known_errors:
        if m.__name__ == message:
            model = m
            break

    if model is None:
        raise RuntimeError(data)

    raise ServerError(message=message, data=model(**detail_data))


def _handle_response(response: httpx.Response) -> Any:
    data = response.json()
    _handle_exceptions(data)
    return data


async def _retry_request(
    func: Callable[[], Coroutine[None, None, httpx.Response]],
    times: int = 3,
    delay: float = 0.5,
) -> httpx.Response:
    response = None

    for _ in range(times):
        response = await func()
        if response.status_code == 404:
            await anyio.sleep(delay)
            continue
        else:
            return response

    assert response
    return response


def _get_connections(map: ConnectionMap) -> Iterable[dict[str, Any]]:
    for connection in map.values():
        src, dest = connection.get_remote_connection()
        yield Connection(
            source=src, destination=dest, client_should=connection.client_should
        ).dict()


@dataclass(init=False)
class APIClient:
    client: httpx.AsyncClient

    def __init__(self, base_url: str) -> None:
        self.client = httpx.AsyncClient(base_url=base_url)

    async def init(self) -> InitResponse:
        response = await self.client.get("/init")  # type: ignore
        return InitResponse(**_handle_response(response))

    async def connect(self, connection_map: ConnectionMap) -> None:
        payload = list(_get_connections(connection_map))
        func = partial(self.client.patch, "/connect", json=payload)  # type: ignore

        response = await _retry_request(func)
        ConnectResponse(**_handle_response(response))

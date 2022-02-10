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


_known_errors: tuple[type[BaseModel], ...] = (
    PlaybackPortAlreadyHasConnections,
    PortNotFound,
    FailedToConnectPorts,
)


def _handle_exceptions(data: dict[str, Any]):
    if "detail" not in data:
        return

    if "message" not in data["detail"]:
        raise RuntimeError(data)

    detail = data["detail"]

    model = None
    for m in _known_errors:
        if m.__name__ == detail["message"]:
            model = m
            break

    if model is None:
        raise RuntimeError(data)

    raise ServerError(message=detail["message"], data=model(**detail["data"]))


_T = TypeVar("_T", bound=BaseModel)


def _handle_response(response: httpx.Response, model: type[_T]) -> _T:
    data = response.json()
    _handle_exceptions(data)
    return model(**data)


# pyright: reportUnknownMemberType = false
# pyright: reportUnknownArgumentType = false


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


def _build_connect_payload(
    source: PortName, destination: PortName, client_should: ClientShould
):
    return {
        "source": source.dict(),
        "destination": destination.dict(),
        "client_should": client_should,
    }


def _log_connection(source: PortName, destination: PortName):
    log.info(
        f"Connected ports on server: [bold cyan]{source}[/bold cyan]"
        + f" -> [bold cyan]{destination}[/bold cyan]"
    )


class MessagingClient(httpx.AsyncClient):
    status_code: int

    def __init__(self, host: IPv4Address, port: int) -> None:
        base_url = AnyHttpUrl.build(scheme="http", host=str(host), port=str(port))
        super().__init__(base_url=base_url)

    async def init(self):
        response = await self.get("/init")
        return _handle_response(response, InitResponse)

    async def connect(
        self, source: PortName, destination: PortName, client_should: ClientShould
    ):
        payload = _build_connect_payload(source, destination, client_should)
        func = partial(self.patch, "/connect", json=payload)

        response = await _retry_request(func)
        data = _handle_response(response, ConnectResponse)
        _log_connection(data.source, data.destination)

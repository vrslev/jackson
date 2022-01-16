from ipaddress import IPv4Address

import httpx
from pydantic import AnyHttpUrl

from jackson.services.messaging.models import InitResponse


class MessagingClient:
    def __init__(self, host: IPv4Address, port: int) -> None:
        base_url = AnyHttpUrl.build(scheme="http", host=str(host), port=str(port))
        self.client = httpx.AsyncClient(base_url=base_url)

    async def init(self):
        response = await self.client.get("/init")  # type: ignore
        return InitResponse(**response.json())

    async def connect(self, source: str, destination: str):
        # response = await self.client.get("/connect")
        ...
        # return ConnectResponse(**response.json())

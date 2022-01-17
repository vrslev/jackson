from ipaddress import IPv4Address

import httpx
from pydantic import AnyHttpUrl

from jackson.services.models import InitResponse


class MessagingClient:
    def __init__(self, host: IPv4Address, port: int) -> None:
        base_url = AnyHttpUrl.build(scheme="http", host=str(host), port=str(port))
        self.client = httpx.AsyncClient(base_url=base_url)

    async def init(self):
        response = await self.client.get("/init")  # type: ignore
        return InitResponse(**response.json())

    # async def connect_receive(
    #     self, client_name: str, client_port_number: int, server_port_number: int
    # ):...
    async def connect(self, source: str, destination: str):
        print(source, destination)

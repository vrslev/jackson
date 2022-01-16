import httpx

from jackson.services.messaging.models import InitResponse


class MessagingClient:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.AsyncClient(base_url=base_url)

    async def init(self):
        response = await self.client.get("/init")  # type: ignore
        return InitResponse(**response.json())

    async def connect(self, source: str, destination: str):
        # response = await self.client.get("/connect")
        ...
        # return ConnectResponse(**response.json())

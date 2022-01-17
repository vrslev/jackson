from ipaddress import IPv4Address

import httpx
from pydantic import AnyHttpUrl

from jackson.services.models import ConnectResponse, InitResponse, PortName


class MessagingClient:
    def __init__(self, host: IPv4Address, port: int) -> None:
        base_url = AnyHttpUrl.build(scheme="http", host=str(host), port=str(port))
        self.client = httpx.AsyncClient(base_url=base_url)

    async def init(self):
        response = await self.client.get("/init")  # type: ignore
        return InitResponse(**response.json())

    async def connect_send(self, client_name: str, destination_idx: int):
        """
        CONFIG
        ports:
            send:
                3: 2


        ON CLIENT
        system:capture_3 -> JackTrip:send_2

        ON SERVER
        JackTrip:receive_2 -> system:playback_2
        """
        response = await self.client.put(  # type: ignore
            "/connect/send",
            params={"client_name": client_name, "port_idx": destination_idx},
        )
        # print(response.json())
        return ConnectResponse(**response.json())

    async def connect_receive(
        self, client_name: str, destination_idx: int
    ) -> ConnectResponse:
        raise NotImplementedError

    async def connect(self, client_name: str, source: PortName, destination: PortName):
        if source.client == "system":
            return await self.connect_send(
                client_name=client_name, destination_idx=destination.idx
            )
        elif destination.client == "system":
            return
            return await self.connect_receive(
                client_name=client_name, destination_idx=destination.idx
            )
        raise NotImplementedError

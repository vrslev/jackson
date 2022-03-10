import asyncio
from dataclasses import dataclass, field
from typing import Callable, Coroutine

import anyio

from jackson.jack_client import JackClient
from jackson.logging import get_logger
from jackson.port_connection import ConnectionMap

log = get_logger(__name__, "PortConnector")


@dataclass
class PortConnector:
    jack_server_name: str
    connection_map: ConnectionMap
    connect_on_server: Callable[[ConnectionMap], Coroutine[None, None, None]]
    callback_queue: asyncio.Queue[Callable[[], Coroutine[None, None, None]]] = field(
        default_factory=asyncio.Queue
    )
    jack_client: JackClient = field(init=False)

    def __post_init__(self):
        self.jack_client = JackClient(
            "PortConnector", server_name=self.jack_server_name
        )
        self.jack_client.set_client_registration_callback(
            self._client_registration_callback
        )
        self.jack_client.activate()

    async def _connect(self):
        await self.connect_on_server(self.connection_map)

        for connection in self.connection_map.values():
            src, dest = connection.get_local_connection()
            await self.jack_client.connect_retry(str(src), str(dest))

    def _client_registration_callback(self, name: str, register: bool):
        if not register:
            return
        if name != "JackTrip":
            return

        self.callback_queue.put_nowait(self._connect)

    def stop_jack_client(self):
        if self.jack_client:
            self.jack_client.deactivate()

    async def run_queue(self):
        async with anyio.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.start_soon(callback)

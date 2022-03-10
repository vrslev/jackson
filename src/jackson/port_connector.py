from dataclasses import dataclass, field
from typing import Callable, Coroutine

import anyio

from jackson.jack_client import JackClient
from jackson.port_connection import ConnectionMap


@dataclass
class PortConnector:
    jack_server_name: str
    connection_map: ConnectionMap
    connect_on_server: Callable[[ConnectionMap], Coroutine[None, None, None]]
    ready: anyio.Event = field(default_factory=anyio.Event, init=False)
    client_activated = False
    client: JackClient = field(init=False)

    def __post_init__(self):
        self.client = JackClient("PortConnector", server_name=self.jack_server_name)
        self.client.set_client_registration_callback(self.client_registration_callback)
        self.client.activate()
        self.client_activated = True

    def client_registration_callback(self, name: str, register: bool):
        if register and name == "JackTrip":
            self.ready.set()

    async def connect_local(self):
        for connection in self.connection_map.values():
            src, dest = connection.get_local_connection()
            await self.client.connect_retry(str(src), str(dest))

    async def connect(self):
        await self.connect_on_server(self.connection_map)
        await self.connect_local()

    def deactivate(self):
        if self.client_activated:
            self.client.deactivate()
            self.client_activated = False

    async def wait_and_run(self):
        await self.ready.wait()
        await self.connect()
        self.deactivate()

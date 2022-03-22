from dataclasses import dataclass, field
from typing import Callable, Coroutine

import anyio
import jack

from jackson.jack_client import connect_ports_retry
from jackson.port_connection import ConnectionMap

ConnectOnServer = Callable[[ConnectionMap], Coroutine[None, None, None]]


@dataclass
class ClientPortConnector:
    client: jack.Client
    connection_map: ConnectionMap
    connect_on_server: ConnectOnServer
    ready: anyio.Event = field(default_factory=anyio.Event, init=False)
    client_activated: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.client.set_client_registration_callback(self._client_registration_callback)
        self.client.activate()
        self.client_activated = True

    def _client_registration_callback(self, name: str, register: bool) -> None:
        if register and name == "JackTrip":
            self.ready.set()

    async def _connect_locally(self) -> None:
        for connection in self.connection_map.values():
            src, dest = connection.get_local_connection()
            await connect_ports_retry(self.client, str(src), str(dest))

    async def _connect(self) -> None:
        await self.connect_on_server(self.connection_map)
        await self._connect_locally()

    async def wait_and_run(self) -> None:
        await self.ready.wait()
        await self._connect()
        self.deactivate()

    def deactivate(self) -> None:
        if self.client_activated:
            self.client.deactivate()
            self.client_activated = False

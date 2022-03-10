import asyncio
from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Coroutine, Protocol

import anyio
import jack

from jackson.jack_client import JackClient
from jackson.logging import get_logger
from jackson.port_connection import (
    ClientShould,
    ConnectionMap,
    PortConnection,
    PortName,
)

log = get_logger(__name__, "PortConnector")


class _ConnectOnServer(Protocol):
    async def __call__(
        self, source: PortName, destination: PortName, client_should: ClientShould
    ) -> None:
        ...


@dataclass
class PortConnector:
    jack_server_name: str
    connection_map: ConnectionMap
    connect_on_server: _ConnectOnServer
    callback_queue: asyncio.Queue[Callable[[], Coroutine[None, None, None]]] = field(
        default_factory=asyncio.Queue
    )
    jack_client: JackClient | None = field(default=None, init=False)

    def start_jack_client(self):
        self.jack_client = JackClient(
            "PortConnector", server_name=self.jack_server_name
        )
        self.jack_client.set_port_registration_callback(
            self._port_registration_callback
        )
        self.jack_client.activate()

    def stop_jack_client(self):
        if self.jack_client:
            self.jack_client.deactivate()

    def _log_registration(self, name: str, registered: bool):
        if registered:
            log.info(f"Registered port: [green]{name}[/green]")
        else:
            log.info(f"Unregistered port: [red]{name}[/red]")

    def _should_connect(self, name: PortName, registered: bool):
        return registered and name in self.connection_map

    async def _connect_on_both_ends(self, connection: PortConnection):
        assert self.jack_client
        await self.connect_on_server(
            *connection.get_remote_connection(), connection.client_should
        )
        src, dest = connection.get_local_connection()
        self.jack_client.connect(str(src), str(dest))

    def _schedule_connecting(self, name: PortName):
        func = partial(self._connect_on_both_ends, self.connection_map[name])
        self.callback_queue.put_nowait(func)

    def _port_registration_callback(self, port: jack.Port, registered: bool):
        self._log_registration(port.name, registered)
        port_name = PortName.parse(port.name)

        if self._should_connect(port_name, registered):
            self._schedule_connecting(port_name)

    async def run_queue(self):
        async with anyio.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.start_soon(callback)

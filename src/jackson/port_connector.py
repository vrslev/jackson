import asyncio
from functools import partial
from typing import Callable, Coroutine

import asyncer
import jack

from jackson.api.client import MessagingClient
from jackson.jack_client import JackClient
from jackson.logging import get_logger
from jackson.port_connection import ConnectionMap, PortConnection, PortName

log = get_logger(__name__, "PortConnector")


class PortConnector:
    def __init__(
        self, *, connection_map: ConnectionMap, messaging_client: MessagingClient
    ) -> None:
        self.messaging_client = messaging_client
        self.connection_map = connection_map
        self.callback_queue: asyncio.Queue[
            Callable[[], Coroutine[None, None, None]]
        ] = asyncio.Queue()

    def start_jack_client(self):
        self.jack_client = JackClient("PortConnector")
        self.jack_client.set_port_registration_callback(
            self._port_registration_callback
        )
        self.jack_client.activate()

    def _log_port_registration(self, name: str, registered: bool):
        if registered:
            log.info(f"Registered port: [green]{name}[/green]")
        else:
            log.info(f"Unregistered port: [red]{name}[/red]")

    def _port_should_connect(self, name: PortName, registered: bool):
        return registered and name in self.connection_map

    async def _connect_on_both_ends(self, connection: PortConnection):
        await self.messaging_client.connect(
            *connection.get_remote_connection(), connection.client_should
        )
        self.jack_client.connect(*connection.get_local_connection())

    def _schedule_port_connection(self, name: PortName):
        conn = self.connection_map[name]
        func = partial(self._connect_on_both_ends, connection=conn)
        self.callback_queue.put_nowait(func)

    def _port_registration_callback(self, port: jack.Port, registered: bool):
        self._log_port_registration(port.name, registered)
        port_name = PortName.parse(port.name)

        if self._port_should_connect(port_name, registered):
            self._schedule_port_connection(port_name)

    async def run_queue(self):
        async with asyncer.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.soonify(callback)()

    def stop(self):
        self.jack_client.deactivate()

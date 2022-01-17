import asyncio
from typing import Any, Callable, Coroutine

import asyncer
import jack

from jackson.logging import generate_stream_handlers
from jackson.services.jack_client import JackClient
from jackson.services.messaging.client import MessagingClient
from jackson.services.models import PortName
from jackson.settings import ClientPorts


class PortConnector:
    def __init__(
        self, client_name: str, ports: ClientPorts, messaging_client: MessagingClient
    ) -> None:
        self.client_name = client_name
        self.set_send_ports(ports.send)
        self._set_receive_ports(ports.receive)

        self.callback_queue: asyncio.Queue[
            Callable[[], Coroutine[Any, Any, None]]
        ] = asyncio.Queue()
        self._info, self._err = generate_stream_handlers("port-connector")
        self.messaging_client = messaging_client
        self.jack_client = None

    def set_send_ports(self, send_ports: dict[int, int]):
        self.send_ports: dict[PortName, PortName] = {}

        for local_source_idx, remote_destination_idx in send_ports.items():
            src = PortName(client="system", type="capture", idx=local_source_idx)
            dest = PortName(client="JackTrip", type="send", idx=remote_destination_idx)
            self.send_ports[src] = dest

        self.reverse_send_ports = {v: k for k, v in self.send_ports.items()}

    def _set_receive_ports(self, receive_ports: dict[int, int]):
        self.receive_ports: dict[PortName, PortName] = {}

        for local_destination_idx, remote_source_idx in receive_ports.items():
            src = PortName(client="JackTrip", type="receive", idx=local_destination_idx)
            dest = PortName(client="system", type="playback", idx=remote_source_idx)
            self.receive_ports[src] = dest

    async def _connect_ports(self, source: PortName, destination: PortName):
        assert self.jack_client
        await self.messaging_client.connect(self.client_name, source, destination)
        self.jack_client.connect(str(source), str(destination))
        self._info(f"Connected ports: {source} -> {destination}")

    def _resolve_source_destination(self, port: jack.Port):
        port_name = PortName.parse(port.name)

        if port.is_input and port_name in self.reverse_send_ports:
            source = self.reverse_send_ports[port_name]
            destination = port_name
            return source, destination

        elif port.is_output and port_name in self.receive_ports:
            source = port_name
            destination = self.receive_ports[port_name]
            return source, destination

    def port_registration_callback(self, port: jack.Port, register: bool):
        if not register:
            self._info(f"Unregistered port: {port.name}")
            return  # We don't want to do anything if port unregistered

        self._info(f"Registered port: {port.name}")
        resp = self._resolve_source_destination(port)
        if not resp:
            return

        async def task():
            await self._connect_ports(*resp)

        self.callback_queue.put_nowait(task)

    def init(self):
        self.jack_client = JackClient(
            "PortConnector",
            info_stream_handler=self._info,
            error_stream_handler=self._err,
        )
        self.jack_client.set_port_registration_callback(self.port_registration_callback)
        self.jack_client.activate()

    def deinit(self):
        if self.jack_client:
            self.jack_client.deactivate()
            self.jack_client.block_streams()

    async def start_queue(self):
        async with asyncer.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.soonify(callback)()

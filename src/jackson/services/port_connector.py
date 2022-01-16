import asyncio
import time
from typing import Any, Callable, Coroutine

import asyncer
import jack

from jackson.services.messaging.client import MessagingClient
from jackson.services.util import generate_stream_handlers
from jackson.settings import ClientPorts


class JackClient(jack.Client):
    def __init__(
        self,
        name: str,
        info_stream_handler: Callable[[str], None],
        error_stream_handler: Callable[[str], None],
    ) -> None:
        # Attribute exists so we don't call client.deactivate()
        # on shutdown if it wasn't activated
        self._activated = False

        jack.set_error_function(info_stream_handler)
        jack.set_info_function(error_stream_handler)

        for _ in range(200):
            try:
                info_stream_handler("Connecting to Jack...")
                super().__init__(name=name, no_start_server=True)
                info_stream_handler("Connected to Jack!")
                break
            except jack.JackOpenError:
                time.sleep(0.1)

        else:
            # TODO: Pretty exit
            raise RuntimeError("Can't connect to Jack")

    def activate(self) -> None:
        super().activate()
        self._activated = True

    def deactivate(self, ignore_errors: bool = True) -> None:
        if self._activated:
            super().deactivate(ignore_errors=ignore_errors)

        _dont_print: Callable[[str], None] = lambda message: None
        jack.set_error_function(
            _dont_print
        )  # TODO: Does it belong here? What if uvicorn server doesn't want to activate
        jack.set_info_function(_dont_print)


class PortConnector:
    def __init__(self, ports: ClientPorts, messaging_client: MessagingClient) -> None:
        self.ports = ports
        self.set_send_ports(ports.send)
        self._set_receive_ports(ports.receive)

        self.callback_queue: asyncio.Queue[
            Callable[[], Coroutine[Any, Any, None]]
        ] = asyncio.Queue()
        self._info, self._err = generate_stream_handlers("port-connector")
        self.messaging_client = messaging_client

    def set_send_ports(self, send_ports: dict[int, int]):
        self.send_ports: dict[str, str] = {}

        for local_source_idx, remote_destination_idx in send_ports.items():
            src = f"system:capture_{local_source_idx}"
            dest = f"JackTrip:send_{remote_destination_idx}"
            self.send_ports[src] = dest

    def _set_receive_ports(self, receive_ports: dict[int, int]):
        self.receive_ports: dict[str, str] = {}

        for local_destination_idx, remote_source_idx in receive_ports.items():
            src = f"JackTrip:receive_{local_destination_idx}"
            dest = f"system:playback_{remote_source_idx}"
            self.receive_ports[src] = dest

    async def _connect_ports(self, source: str, destination: str):
        await self.messaging_client.connect(source, destination)
        self.jack_client.connect(source, destination)
        self._info(f"Connected ports: {source} -> {destination}")

    def _resolve_source_destination(self, port: jack.Port):
        port_name = port.name

        if port.is_input and port_name in self.receive_ports:
            source = self.receive_ports[port_name]
            destination = port_name
            return source, destination

        elif port.is_output and port_name in self.send_ports:
            source = port_name
            destination = self.send_ports[port_name]
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
        # self._connect_initial_ports() # TODO: Connect initial ports or not?
        self.jack_client.set_port_registration_callback(self.port_registration_callback)
        self.jack_client.activate()

    def deinit(self):
        self.jack_client.deactivate()

    async def start_queue(self):
        async with asyncer.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.soonify(callback)()

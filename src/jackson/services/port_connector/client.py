import asyncio
import time
from typing import Any, Callable, Coroutine

import asyncer
import httpx
import jack

import jackson.services.port_connector.client as messaging_client
from jackson.services.port_connector.models import InitResponse
from jackson.services.util import generate_stream_handlers
from jackson.settings import ClientPorts


class MessagingClient:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.AsyncClient(base_url=base_url)

    async def init(self):
        response = await self.client.get("/init")
        return InitResponse(**response.json())

    async def connect(self, source: str, destination: str):
        response = await self.client.get("/connect")
        ...
        # return ConnectResponse(**response.json())


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
        jack.set_error_function(_dont_print)
        jack.set_info_function(_dont_print)


def _get_port_name(port: str | jack.Port):
    return port.name if isinstance(port, jack.Port) else port


class PortConnector:
    def __init__(self, ports: ClientPorts) -> None:
        self.ports = ports
        self._destination_ports = set(ports.values())
        self._reverse_port_map = {v: k for k, v in ports.items()}

        self.callback_queue: asyncio.Queue[
            Callable[[], Coroutine[Any, Any, None]]
        ] = asyncio.Queue()
        self._info, self._err = generate_stream_handlers("port-connector")

    async def build_destination_ports(self):
        ...

    async def _connect_ports(
        self, source: str | jack.Port, destination: str | jack.Port
    ):
        source_name = _get_port_name(source)
        destination_name = _get_port_name(destination)
        await messaging_client.connect(source=source_name, destination=destination_name)

        self.jack_client.connect(source=source_name, destination=destination_name)
        self._info(f"Connected ports: {source_name} -> {destination_name}")

    def _resolve_source_destination(self, port: jack.Port):
        port_name = port.name

        if port.is_input:
            if port_name not in self._destination_ports:
                return

            source = self._reverse_port_map[port_name]
            destination = port
            return source, destination

        elif port.is_output:
            if port_name not in self.ports:
                # keys are source ports
                return

            source = port
            destination = self.ports[port_name]
            return source, destination

    def port_registration_callback(self, port: jack.Port, register: bool):
        if register:
            self._info(f"Registered port: {port.name}")
        else:
            self._info(f"Unregistered port: {port.name}")
            return  # We don't want to do anything if port unregistered

        resp = self._resolve_source_destination(port)
        if not resp:
            return

        source, destination = resp

        async def task():
            await self._connect_ports(source, destination)

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

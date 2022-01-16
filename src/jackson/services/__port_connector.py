# type: ignore
import asyncio
import time
from typing import Any, Callable, Coroutine

import asyncer
import jack

import jackson.services.port_connector.client as messaging_client
from jackson.services.util import generate_stream_handlers
from jackson.settings import ClientPorts


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
        # Attribute exists so we don't call client.deactivate()
        # on shutdown if it wasn't activated
        self._client_activated = False

    # async def build_destination_ports(self):...
    async def _connect_ports(
        self, source: str | jack.Port, destination: str | jack.Port
    ):
        source_name = _get_port_name(source)
        destination_name = _get_port_name(destination)
        await messaging_client.connect(source=source_name, destination=destination_name)

        self.client.connect(source=source_name, destination=destination_name)
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
        jack.set_error_function(self._info)
        jack.set_info_function(self._info)

        for _ in range(200):
            try:
                self._info("Connecting to Jack...")
                self.client = jack.Client("PortConnector", no_start_server=True)
                self._info("Connected to Jack!")
                break
            except jack.JackOpenError:
                time.sleep(0.1)

        else:
            # TODO: Pretty exit
            raise RuntimeError("Can't connect to Jack")

        # self._connect_initial_ports() # TODO: Connect initial ports or not?
        self.client.set_port_registration_callback(self.port_registration_callback)
        self.client.activate()
        self._client_activated = True

    def deinit(self):
        if self._client_activated:
            self.client.deactivate()

        _dont_print: Callable[[str], None] = lambda message: None
        jack.set_error_function(_dont_print)
        jack.set_info_function(_dont_print)

    async def start_queue(self):
        async with asyncer.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.soonify(callback)()

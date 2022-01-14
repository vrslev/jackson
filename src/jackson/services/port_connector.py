import asyncio
import time
from typing import Callable

import jack

from jackson.services.util import generate_stream_handler
from jackson.settings import PortMap


def _get_port_name(port: str | jack.Port):
    return port.name if isinstance(port, jack.Port) else port


class PortConnector:
    def __init__(self, ports: PortMap) -> None:
        self.ports = ports
        self._destination_ports = set(ports.values())
        self._reverse_port_map = {v: k for k, v in ports.items()}

        self.callback_queue: asyncio.Queue[Callable[[], None]] = asyncio.Queue()
        self._print = generate_stream_handler("port-connector")

    def _connect_ports(
        self, source: str | jack.Port, destination: str | jack.Port, *, enqueue: bool
    ):
        def task():
            self.client.connect(source=source, destination=destination)
            self._print(
                "Connected ports: "
                + f"{_get_port_name(source)} -> {_get_port_name(destination)}"
            )

        if enqueue:
            self.callback_queue.put_nowait(task)
        else:
            task()

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
            self._print(f"Registered port: {port.name}")
        else:
            self._print(f"Unregistered port: {port.name}")
            return  # We don't want to do anything if port unregistered

        if resp := self._resolve_source_destination(port):
            self._connect_ports(*resp, enqueue=True)

    def _connect_initial_ports(self):
        for port in self.client.get_ports():
            if self.client.get_all_connections(port):
                continue

            resp = self._resolve_source_destination(port)
            if not resp:
                continue

            try:
                for port in resp:
                    name = _get_port_name(port)
                    self.client.get_port_by_name(name)
            except jack.JackError:
                pass
            else:
                self._connect_ports(*resp, enqueue=False)

    def init(self):
        jack.set_error_function(self._print)
        jack.set_info_function(self._print)

        for _ in range(200):
            try:
                self._print("Connecting to Jack...")
                self.client = jack.Client("PortConnector", no_start_server=True)
                self._print("Connected to Jack!")
                break
            except jack.JackOpenError:
                time.sleep(0.1)

        else:
            raise RuntimeError("Can't connect to Jack")

        self._connect_initial_ports()
        self.client.set_port_registration_callback(self.port_registration_callback)
        self.client.activate()

    def deinit(self):
        self.client.deactivate()

        _dont_print: Callable[[str], None] = lambda message: None
        jack.set_error_function(_dont_print)
        jack.set_info_function(_dont_print)

    async def start_queue(self):
        while True:
            callback = await self.callback_queue.get()
            callback()

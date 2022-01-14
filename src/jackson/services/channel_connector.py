import asyncio
import time
from typing import Callable

import jack

from jackson.services.util import generate_stream_handler
from jackson.settings import ChannelMap


def _get_port_name(port: str | jack.Port):
    return port.name if isinstance(port, jack.Port) else port


class ChannelConnector:
    def __init__(self, channels: ChannelMap) -> None:
        self.channels = channels
        self._destination_ports = set(channels.values())
        self._reverse_channels_map = {v: k for k, v in channels.items()}

        self.callback_queue: asyncio.Queue[Callable[[], None]] = asyncio.Queue()
        self._print = generate_stream_handler("channel-connector")

    def _connect_channels(
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

    def _resolve_source_destination_ports(self, port: jack.Port):
        port_name = port.name

        if port.is_input:
            if port_name not in self._destination_ports:
                return

            source = self._reverse_channels_map[port_name]
            destination = port
            return source, destination

        elif port.is_output:
            if port_name not in self.channels:
                # keys are source ports
                return

            source = port
            destination = self.channels[port_name]
            return source, destination

    def port_registration_callback(self, port: jack.Port, register: bool):
        if register:
            self._print(f"Registered port: {port.name}")
        else:
            self._print(f"Unregistered port: {port.name}")
            return  # We don't want to do anything if port unregistered

        if resp := self._resolve_source_destination_ports(port):
            self._connect_channels(*resp, enqueue=True)

    def _connect_initial_channels(self):
        for port in self.client.get_ports():
            if not self.client.get_all_connections(port):
                if resp := self._resolve_source_destination_ports(port):
                    self._connect_channels(*resp, enqueue=False)
                else:
                    continue

    def init(self):
        jack.set_error_function(self._print)
        jack.set_info_function(self._print)

        for _ in range(200):
            try:
                self._print("Connecting to Jack...")
                self.client = jack.Client("ChannelConnector", no_start_server=True)
                self._print("Connected to Jack!")
                break
            except jack.JackOpenError:
                time.sleep(0.1)

        else:
            raise RuntimeError("Can't connect to Jack")

        self._connect_initial_channels()
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

import asyncio
import contextlib
import functools
from typing import Callable

import anyio
import jack
import typer

from jackson.utils import ChannelMap, get_random_color

_color = get_random_color()


def _print_colored(message: str):
    typer.secho(f"[channel-connector] {message}", fg=_color)  # type: ignore


class ChannelConnector:
    def __init__(self, channels: ChannelMap) -> None:
        self.channels = channels
        self._destination_ports = set(channels.values())
        self._reverse_channels_map = {v: k for k, v in channels.items()}
        self.callback_queue: asyncio.Queue[Callable[[], None]] = asyncio.Queue()

    def _schedule_channel_connection(
        self, source: str | jack.Port, destination: str | jack.Port
    ):
        self.callback_queue.put_nowait(
            functools.partial(
                self.client.connect, source=source, destination=destination
            )
        )

    def _resolve_source_destination_ports(self, port: jack.Port):
        if port.is_input:
            if port.name not in self._destination_ports:
                return

            source = self._reverse_channels_map[port.name]
            destination = port
            return source, destination

        elif port.is_output:
            if port.name not in self.channels:
                # keys are source ports
                return

            source = port
            destination = self.channels[port.name]
            return source, destination

    def port_registration_callback(self, port: jack.Port, register: bool):
        _print_colored(f"Registered port: {port.name}")

        if not register:
            return

        resp = self._resolve_source_destination_ports(port)
        if not resp:
            return

        source, destination = resp
        _print_colored(f"Resolved channels: {source} -> {destination}")
        self._schedule_channel_connection(source, destination)

    @contextlib.asynccontextmanager
    async def init_worker(self):
        jack.set_error_function(_print_colored)
        jack.set_info_function(_print_colored)

        for _ in range(200):
            try:
                _print_colored("Connecting to Jack...")
                self.client = jack.Client("ChannelConnector", no_start_server=True)
                _print_colored("Connected to Jack!")
                break
            except jack.JackOpenError:
                await anyio.sleep(0.1)

        else:
            raise RuntimeError("Can't connect to Jack")

        self.client.set_port_registration_callback(self.port_registration_callback)
        self.client.activate()
        yield

    async def start_queue(self):
        while True:
            callback = await self.callback_queue.get()
            callback()

from dataclasses import dataclass, field
from typing import Protocol

import anyio
import jack_server
from anyio.abc import TaskGroup
from jack_server._server import SetByJack_

from jackson import jacktrip
from jackson.api.client import APIClient
from jackson.api.server import APIServer, uvicorn_signal_handler
from jackson.jack_server import (
    block_jack_server_streams,
    set_jack_server_stream_handlers,
)
from jackson.port_connection import build_connection_map, count_receive_send_channels
from jackson.port_connector import PortConnector
from jackson.settings import ClientSettings, ServerSettings


class BaseManager(Protocol):
    async def start(self, tg: TaskGroup):
        ...

    async def stop(self):
        ...

    async def run(self):
        async with anyio.create_task_group() as task_group:
            try:
                await self.start(task_group)
                await anyio.sleep_forever()
            finally:
                with anyio.CancelScope(shield=True):
                    await self.stop()


@dataclass
class Server(BaseManager):
    settings: ServerSettings
    jack: jack_server.Server = field(init=False)
    api: APIServer = field(init=False)

    def __post_init__(self):
        set_jack_server_stream_handlers()
        self.jack = jack_server.Server(
            name=self.settings.audio.jack_server_name,
            driver=self.settings.audio.driver,
            device=self.settings.audio.device or SetByJack_,
            rate=self.settings.audio.sample_rate,
            period=self.settings.audio.buffer_size,
        )
        self.api = APIServer(self.settings.audio.jack_server_name)

    async def start(self, tg: TaskGroup):
        self.jack.start()

        tg.start_soon(
            lambda: jacktrip.run_server(
                jack_server_name=self.settings.audio.jack_server_name,
                port=self.settings.server.jacktrip_port,
            )
        )
        tg.start_soon(self.api.start)
        tg.start_soon(lambda: uvicorn_signal_handler(tg.cancel_scope))

    async def stop(self):
        await self.api.stop()
        block_jack_server_streams()
        self.jack.stop()


@dataclass
class Client(BaseManager):
    settings: ClientSettings
    jack: jack_server.Server | None = field(default=None, init=False)
    api: APIClient = field(init=False)
    port_connector: PortConnector | None = field(default=None, init=False)

    def __post_init__(self):
        self.api = APIClient(
            host=self.settings.server.host, port=self.settings.server.api_port
        )

    def start_jack(self, rate: jack_server.SampleRate, period: int):
        if not self.settings.start_jack:
            return

        set_jack_server_stream_handlers()
        self.jack = jack_server.Server(
            name=self.settings.get_jack_server_name(),
            driver=self.settings.audio.driver,
            device=self.settings.audio.device or SetByJack_,
            rate=rate,
            period=period,
        )
        self.jack.start()

    def start_port_connector(self, inputs_limit: int, outputs_limit: int):
        map = build_connection_map(
            client_name=self.settings.name,
            receive=self.settings.ports.receive,
            send=self.settings.ports.send,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )
        self.port_connector = PortConnector(
            jack_name=self.settings.get_jack_server_name(),
            connection_map=map,
            connect_on_server=self.api.connect,
        )

    async def start_jacktrip(self, receive_count: int, send_count: int):
        return await jacktrip.run_client(
            jack_server_name=self.settings.get_jack_server_name(),
            server_host=self.settings.server.host,
            server_port=self.settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=self.settings.name,
        )

    async def start(self, tg: TaskGroup):
        response = await self.api.init()

        self.start_jack(rate=response.rate, period=response.buffer_size)
        self.start_port_connector(
            inputs_limit=response.inputs, outputs_limit=response.outputs
        )

        assert self.port_connector
        tg.start_soon(self.port_connector.wait_and_run)

        receive_count, send_count = count_receive_send_channels(
            self.port_connector.connection_map
        )
        tg.start_soon(lambda: self.start_jacktrip(receive_count, send_count))

    async def stop(self):
        await self.api.client.aclose()

        if self.port_connector:
            self.port_connector.deactivate()

        if self.settings.start_jack and self.jack:
            block_jack_server_streams()
            self.jack.stop()

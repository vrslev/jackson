from abc import ABC, abstractmethod

import anyio
import asyncer
import jack_server
from asyncer._main import TaskGroup

from jackson import jacktrip
from jackson.api.client import MessagingClient
from jackson.api.server import MessagingServer
from jackson.api.server import app as messaging_app
from jackson.api.server import uvicorn_signal_handler
from jackson.jack_server import JackServer
from jackson.port_connection import build_connection_map, count_receive_send_channels
from jackson.port_connector import PortConnector
from jackson.settings import ClientSettings, ServerSettings


class _BaseManager(ABC):
    @abstractmethod
    async def start(self, task_group: TaskGroup):
        ...

    @abstractmethod
    async def stop(self):
        ...

    async def run(self):
        async with asyncer.create_task_group() as task_group:
            try:
                await self.start(task_group)
                await anyio.sleep_forever()
            finally:
                with anyio.CancelScope(shield=True):
                    await self.stop()


class Server(_BaseManager):
    def __init__(self, settings: ServerSettings):
        self.settings = settings
        self.jack_server = JackServer(
            driver=self.settings.audio.driver,
            device=self.settings.audio.device,
            rate=self.settings.audio.sample_rate,
        )
        self.messaging_server = MessagingServer(messaging_app)

    async def start(self, task_group: TaskGroup):
        self.jack_server.start()

        task_group.soonify(jacktrip.run_server)(port=self.settings.server.jacktrip_port)
        task_group.soonify(self.messaging_server.start)()
        task_group.soonify(uvicorn_signal_handler)(task_group.cancel_scope)

    async def stop(self):
        await self.messaging_server.stop()
        self.jack_server.stop()


class Client(_BaseManager):
    def __init__(self, settings: ClientSettings, start_jack: bool) -> None:
        self.settings = settings
        self.start_jack = start_jack
        self.jack_server = None
        self.port_connector = None

        self.messaging_client = MessagingClient(
            host=settings.server.host, port=settings.server.messaging_port
        )

    def start_jack_server(self, rate: jack_server.SampleRate):
        self.jack_server = JackServer(
            driver=self.settings.audio.driver,
            device=self.settings.audio.device,
            rate=rate,
        )
        self.jack_server.start()

    def setup_port_connector(self, inputs_limit: int, outputs_limit: int):
        map = build_connection_map(
            client_name=self.settings.name,
            ports=self.settings.ports,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )
        self.port_connector = PortConnector(
            connection_map=map, messaging_client=self.messaging_client
        )
        self.port_connector.start_jack_client()

    async def start_jacktrip(self):
        assert self.port_connector
        receive_count, send_count = count_receive_send_channels(
            self.port_connector.connection_map
        )

        return await jacktrip.run_client(
            server_host=self.settings.server.host,
            server_port=self.settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=self.settings.name,
        )

    async def start(self, task_group: TaskGroup):
        init_resp = await self.messaging_client.init()

        if self.start_jack:
            self.start_jack_server(init_resp.rate)

        self.setup_port_connector(init_resp.inputs, init_resp.outputs)
        assert self.port_connector

        task_group.soonify(self.port_connector.run_queue)()
        task_group.soonify(self.start_jacktrip)()

    async def stop(self):
        await self.messaging_client.client.aclose()

        if self.port_connector:
            self.port_connector.stop_jack_client()

        if self.start_jack and self.jack_server:
            self.jack_server.stop()

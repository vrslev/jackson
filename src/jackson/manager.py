from abc import ABC, abstractmethod

import anyio
import asyncer
import jack_server
from asyncer._main import TaskGroup

from jackson.services import jacktrip
from jackson.services.jack_server import JackServer
from jackson.services.messaging.client import MessagingClient
from jackson.services.messaging.server import MessagingServer
from jackson.services.messaging.server import app as messaging_app
from jackson.services.messaging.server import uvicorn_signal_handler
from jackson.services.port_connector import PortConnector
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

    async def start_jacktrip(self):
        return await jacktrip.start_server(port=self.settings.server.jacktrip_port)

    async def start(self, task_group: TaskGroup):
        self.jack_server.start()

        task_group.soonify(self.start_jacktrip)()
        task_group.soonify(self.messaging_server.start)()
        task_group.soonify(uvicorn_signal_handler)(task_group.cancel_scope)

    async def stop(self):
        await self.messaging_server.stop()
        self.jack_server.stop()


class Client(_BaseManager):
    def __init__(self, settings: ClientSettings, start_jack: bool) -> None:
        self.settings = settings
        self.start_jack = start_jack
        self.messaging_client = MessagingClient(
            host=settings.server.host, port=settings.server.messaging_port
        )
        self.jack_server = None
        self.port_connector = None

    def start_jack_server(self, rate: jack_server.SampleRate):
        self.jack_server = JackServer(
            driver=self.settings.audio.driver,
            device=self.settings.audio.device,
            rate=rate,
        )
        self.jack_server.start()

    def init_port_connector(self, inputs_limit: int, outputs_limit: int):
        self.port_connector = PortConnector(
            client_name=self.settings.name,
            ports=self.settings.ports,
            messaging_client=self.messaging_client,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )

    async def start_port_connector_queue(self):
        assert self.port_connector
        return await self.port_connector.run_queue()

    async def start_jacktrip(self):
        assert self.port_connector
        (
            receive_count,
            send_count,
        ) = self.port_connector.get_receive_send_channels_counts()

        return await jacktrip.start_client(
            server_host=self.settings.server.host,
            server_port=self.settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=self.settings.name,
        )

    async def start(self, task_group: TaskGroup):
        init_response = await self.messaging_client.init()

        if self.start_jack:
            self.start_jack_server(init_response.rate)

        self.init_port_connector(init_response.inputs, init_response.outputs)

        task_group.soonify(self.start_port_connector_queue)()
        task_group.soonify(self.start_jacktrip)()

    async def stop(self):
        await self.messaging_client.client.aclose()

        if self.port_connector:
            self.port_connector.deinit()

        if self.jack_server and self.start_jack:
            self.jack_server.stop()

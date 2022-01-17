from abc import ABC, abstractmethod

import anyio
import asyncer
from asyncer._main import TaskGroup

import jack_server
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
                while True:
                    await anyio.sleep(1)
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
        self.port_connector = PortConnector(settings.ports, self.messaging_client)

    def start_jack_server(self, rate: jack_server.SampleRate):
        self.jack_server = JackServer(
            driver=self.settings.audio.driver,
            device=self.settings.audio.device,
            rate=rate,
        )
        self.jack_server.start()

    async def start_jacktrip(self, receive_channels: int, send_channels: int):
        return await jacktrip.start_client(
            host=self.settings.server.host,
            port=self.settings.server.jacktrip_port,
            receive_channels=receive_channels,
            send_channels=send_channels,
            remote_name=self.settings.name,
        )

    async def start(self, task_group: TaskGroup):
        init_response = await self.messaging_client.init()
        print(init_response)
        if self.start_jack:
            self.start_jack_server(init_response.rate)

        self.port_connector.init()
        task_group.soonify(self.port_connector.start_queue)()

        task_group.soonify(self.start_jacktrip)(
            receive_channels=init_response.outputs,
            send_channels=init_response.inputs,  # TODO: This is not always true
        )

    async def stop(self):
        await self.messaging_client.client.aclose()
        self.port_connector.deinit()

        if self.jack_server and self.start_jack:
            self.jack_server.stop()

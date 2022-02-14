from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import anyio
import asyncer
import jack_server
from asyncer._main import TaskGroup

from jackson import jacktrip
from jackson.api.client import APIClient
from jackson.api.server import APIServer
from jackson.api.server import app as api_app
from jackson.api.server import uvicorn_signal_handler
from jackson.jack_server import JackServer
from jackson.port_connection import build_connection_map, count_receive_send_channels
from jackson.port_connector import PortConnector
from jackson.settings import ClientSettings, ServerSettings


class BaseManager(ABC):
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


@dataclass
class Server(BaseManager):
    settings: ServerSettings
    jack_server_: JackServer = field(init=False)
    api_server: APIServer = field(init=False)
    jack_server_name: str = field(default="JacksonServer", init=False)

    def __post_init__(self):
        self.jack_server_ = JackServer(
            name=self.jack_server_name,
            driver=self.settings.audio.driver,
            device=self.settings.audio.device,
            rate=self.settings.audio.sample_rate,
            period=self.settings.audio.buffer_size,
        )
        api_app.state.jack_server_name = self.jack_server_name
        self.api_server = APIServer(api_app)

    async def start(self, task_group: TaskGroup):
        self.jack_server_.start()

        task_group.soonify(jacktrip.run_server)(
            jack_server_name=self.jack_server_name,
            port=self.settings.server.jacktrip_port,
        )
        task_group.soonify(self.api_server.start)()
        task_group.soonify(uvicorn_signal_handler)(task_group.cancel_scope)

    async def stop(self):
        await self.api_server.stop()
        self.jack_server_.stop()


@dataclass
class Client(BaseManager):
    settings: ClientSettings
    start_jack: bool
    jack_server_: JackServer | None = field(default=None, init=False)
    port_connector: PortConnector | None = field(default=None, init=False)
    api_client: APIClient = field(init=False)
    jack_server_name: str = field(default="JacksonClient", init=False)

    def __post_init__(self):
        self.api_client = APIClient(
            host=self.settings.server.host, port=self.settings.server.api_port
        )

    def start_jack_server(self, rate: jack_server.SampleRate, period: int):
        self.jack_server_ = JackServer(
            name=self.jack_server_name,
            driver=self.settings.audio.driver,
            device=self.settings.audio.device,
            rate=rate,
            period=period,
        )
        self.jack_server_.start()

    def setup_port_connector(self, inputs_limit: int, outputs_limit: int):
        map = build_connection_map(
            client_name=self.settings.name,
            ports=self.settings.ports,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )

        self.port_connector = PortConnector(
            jack_server_name=self.jack_server_name,
            connection_map=map,
            connect_on_server=self.api_client.connect,
        )
        self.port_connector.start_jack_client()

    async def start_jacktrip(self):
        assert self.port_connector

        receive_count, send_count = count_receive_send_channels(
            self.port_connector.connection_map
        )

        return await jacktrip.run_client(
            jack_server_name=self.jack_server_name,
            server_host=self.settings.server.host,
            server_port=self.settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=self.settings.name,
        )

    async def start(self, task_group: TaskGroup):
        init_resp = await self.api_client.init()

        if self.start_jack:
            self.start_jack_server(rate=init_resp.rate, period=init_resp.buffer_size)

        self.setup_port_connector(init_resp.inputs, init_resp.outputs)
        assert self.port_connector

        task_group.soonify(self.port_connector.run_queue)()
        task_group.soonify(self.start_jacktrip)()

    async def stop(self):
        await self.api_client.aclose()

        if self.port_connector:
            self.port_connector.stop_jack_client()

        if self.start_jack and self.jack_server_:
            self.jack_server_.stop()

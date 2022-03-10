from abc import ABC, abstractmethod
from dataclasses import dataclass, field

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


class BaseManager(ABC):
    @abstractmethod
    async def start(self, task_group: TaskGroup):
        ...

    @abstractmethod
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


DEFAULT_SERVER_JACK_SERVER = "JacksonServer"  # TODO: Move to settings
DEFAULT_CLIENT_JACK_SERVER = "JacksonClient"


@dataclass
class Server(BaseManager):
    settings: ServerSettings
    jack: jack_server.Server = field(init=False)
    jack_name: str = field(default=DEFAULT_SERVER_JACK_SERVER, init=False)
    api: APIServer = field(init=False)

    def __post_init__(self):
        set_jack_server_stream_handlers()
        self.jack = jack_server.Server(
            name=self.jack_name,
            driver=self.settings.audio.driver,
            device=self.settings.audio.device or SetByJack_,
            rate=self.settings.audio.sample_rate,
            period=self.settings.audio.buffer_size,
        )
        self.api = APIServer(self.jack_name)

    async def start(self, task_group: TaskGroup):
        self.jack.start()

        task_group.start_soon(
            lambda: jacktrip.run_server(
                jack_server_name=self.jack_name,
                port=self.settings.server.jacktrip_port,
            )
        )
        task_group.start_soon(self.api.start)
        task_group.start_soon(lambda: uvicorn_signal_handler(task_group.cancel_scope))

    async def stop(self):
        await self.api.stop()
        block_jack_server_streams()
        self.jack.stop()


@dataclass
class Client(BaseManager):
    settings: ClientSettings
    start_jack: bool
    jack: jack_server.Server | None = field(default=None, init=False)
    jack_name: str = field(default=DEFAULT_CLIENT_JACK_SERVER, init=False)
    api: APIClient = field(init=False)
    port_connector: PortConnector | None = field(default=None, init=False)

    def __post_init__(self):
        self.api = APIClient(
            host=self.settings.server.host, port=self.settings.server.api_port
        )

    def start_jack_server(self, rate: jack_server.SampleRate, period: int):
        set_jack_server_stream_handlers()
        self.jack = jack_server.Server(
            name=self.jack_name,
            driver=self.settings.audio.driver,
            device=self.settings.audio.device or SetByJack_,
            rate=rate,
            period=period,
        )
        self.jack.start()

    def get_port_connector(self, inputs_limit: int, outputs_limit: int):
        map = build_connection_map(
            client_name=self.settings.name,
            ports=self.settings.ports,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )

        return PortConnector(
            jack_server_name=self.jack_name,
            connection_map=map,
            connect_on_server=self.api.connect,
        )

    async def start_jacktrip(self):
        assert self.port_connector
        receive_count, send_count = count_receive_send_channels(
            self.port_connector.connection_map
        )

        return await jacktrip.run_client(
            jack_server_name=self.jack_name,
            server_host=self.settings.server.host,
            server_port=self.settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=self.settings.name,
        )

    async def start(self, task_group: TaskGroup):
        init_resp = await self.api.init()

        if self.start_jack:
            self.start_jack_server(rate=init_resp.rate, period=init_resp.buffer_size)
        else:
            self.jack_name = DEFAULT_SERVER_JACK_SERVER

        self.port_connector = self.get_port_connector(
            init_resp.inputs, init_resp.outputs
        )

        task_group.start_soon(self.port_connector.wait_and_run)
        task_group.start_soon(self.start_jacktrip)

    async def stop(self):
        await self.api.client.aclose()

        if self.port_connector:
            self.port_connector.deactivate()

        if self.start_jack and self.jack:
            block_jack_server_streams()
            self.jack.stop()

from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Coroutine, Protocol

import anyio
import jack
import jack_server
from anyio.abc import TaskGroup

from jackson.api.client import APIClient
from jackson.api.server import APIServer
from jackson.connector.client import ClientPortConnector
from jackson.connector.server import ServerPortConnector
from jackson.jack_client import block_jack_client_streams
from jackson.jack_server import (
    block_jack_server_streams,
    set_jack_server_stream_handlers,
)
from jackson.port_connection import ConnectionMap


class BaseManager(Protocol):
    async def start(self, tg: TaskGroup) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            try:
                await self.start(tg)
                await anyio.sleep_forever()
            finally:
                with anyio.CancelScope(shield=True):
                    await self.stop()


@dataclass
class ServerManager(BaseManager):
    jack_server: jack_server.Server
    start_jacktrip: Callable[[], Coroutine[None, None, None]]
    get_jack_client: Callable[[], jack.Client]
    jack_client: jack.Client | None = field(default=None, init=False)
    api: APIServer | None = field(default=None, init=False)

    async def start(self, tg: TaskGroup) -> None:
        set_jack_server_stream_handlers()
        self.jack_server.start()
        tg.start_soon(self.start_jacktrip)
        self.jack_client = self.get_jack_client()

        self.api = APIServer(port_connector=ServerPortConnector(self.jack_client))
        self.api.install_signal_handlers(tg.cancel_scope)
        tg.start_soon(self.api.start)

    async def stop(self) -> None:
        if self.api:
            await self.api.stop()
        if self.jack_client:
            block_jack_client_streams()
        block_jack_server_streams()
        self.jack_server.stop()


class GetJackServer(Protocol):
    def __call__(self, rate: jack_server.SampleRate, period: int) -> jack_server.Server:
        ...


class GetConnectionMap(Protocol):
    def __call__(self, inputs_limit: int, outputs_limit: int) -> ConnectionMap:
        ...


class StartClientJacktrip(Protocol):
    async def __call__(self, map: ConnectionMap) -> None:
        ...


@dataclass
class ClientManager(BaseManager):
    api: APIClient
    get_jack_server: GetJackServer
    get_jack_client: Callable[[], jack.Client]
    get_connection_map: GetConnectionMap
    start_jacktrip: StartClientJacktrip
    jack_server_: jack_server.Server | None = field(default=None, init=False)
    jack_client: jack.Client | None = field(default=None, init=False)
    port_connector: ClientPortConnector | None = field(default=None, init=False)

    async def start(self, tg: TaskGroup) -> None:
        response = await self.api.init()

        self.jack_server_ = self.get_jack_server(
            rate=response.rate, period=response.buffer_size
        )
        self.jack_server_.start()

        self.jack_client = self.get_jack_client()
        self.port_connector = ClientPortConnector(
            client=self.jack_client,
            connection_map=self.get_connection_map(
                inputs_limit=response.inputs,
                outputs_limit=response.outputs,
            ),
            connect_on_server=self.api.connect,
        )
        tg.start_soon(self.port_connector.wait_and_run)

        tg.start_soon(partial(self.start_jacktrip, self.port_connector.connection_map))

    async def stop(self) -> None:
        await self.api.client.aclose()

        if self.port_connector:
            self.port_connector.deactivate()

        if self.jack_client:
            block_jack_client_streams()

        if self.jack_server_:
            self.jack_server_.stop()

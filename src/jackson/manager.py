from dataclasses import dataclass, field
from functools import partial, singledispatch
from typing import Any, Callable, Coroutine, Protocol

import anyio
import httpx
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
        await cleanup_stack(self.api, self.jack_client, self.jack_server)


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
    api_http_client: httpx.AsyncClient
    get_jack_server: GetJackServer
    get_jack_client: Callable[[], jack.Client]
    get_connection_map: GetConnectionMap
    start_jacktrip: StartClientJacktrip
    jack_server_: jack_server.Server | None = field(default=None, init=False)
    jack_client: jack.Client | None = field(default=None, init=False)
    port_connector: ClientPortConnector | None = field(default=None, init=False)

    async def start(self, tg: TaskGroup) -> None:
        api = APIClient(client=self.api_http_client)
        response = await api.init()

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
            connect_on_server=api.connect,
        )
        tg.start_soon(self.port_connector.wait_and_run)

        tg.start_soon(partial(self.start_jacktrip, self.port_connector.connection_map))

    async def stop(self) -> None:
        await cleanup_stack(
            self.api_http_client,
            self.port_connector,
            self.jack_client,
            self.jack_server_,
        )


@singledispatch
async def cleanup(v: Any) -> None:
    ...


@cleanup.register(APIServer)
async def _(v: APIServer):
    await v.stop()


@cleanup.register(jack.Client)
async def _(v: jack.Client):
    block_jack_client_streams()


@cleanup.register(jack_server.Server)
async def _(v: jack_server.Server):
    block_jack_server_streams()
    v.stop()


@cleanup.register(httpx.AsyncClient)
async def _(v: httpx.AsyncClient):
    await v.aclose()


@cleanup.register(ClientPortConnector)
async def _(v: ClientPortConnector):
    v.deactivate()


@cleanup.register(type(None))
async def _(v: None):
    pass


async def cleanup_stack(*stack: Any) -> None:
    for v in stack:
        await cleanup(v)

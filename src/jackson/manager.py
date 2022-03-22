from dataclasses import dataclass, field
from functools import singledispatch
from typing import Any, Callable, Coroutine, Protocol

import anyio
import httpx
import jack
import jack_server
import uvicorn
from anyio.abc import TaskGroup

from jackson.api.client import APIClient
from jackson.api.server import get_api_server
from jackson.connector.client import ClientPortConnector
from jackson.connector.server import ServerPortConnector
from jackson.jack_client import block_jack_client_streams
from jackson.jack_server import (
    block_jack_server_streams,
    set_jack_server_stream_handlers,
)
from jackson.jacktrip import StreamingProcess
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


GetJackClient = Callable[[], Coroutine[None, None, jack.Client]]


@dataclass
class ServerManager(BaseManager):
    jack_server: jack_server.Server
    get_jacktrip: Callable[[], StreamingProcess]
    get_jack_client: GetJackClient
    jacktrip: StreamingProcess | None = field(default=None, init=False)
    jack_client: jack.Client | None = field(default=None, init=False)
    api: uvicorn.Server | None = field(default=None, init=False)

    async def start(self, tg: TaskGroup) -> None:
        set_jack_server_stream_handlers()
        self.jack_server.start()

        self.jacktrip = self.get_jacktrip()
        tg.start_soon(self.jacktrip.start)

        self.jack_client = await self.get_jack_client()
        self.api = get_api_server(
            port_connector=ServerPortConnector(self.jack_client),
            cancel_scope=tg.cancel_scope,
        )
        tg.start_soon(self.api.startup)  # type: ignore

    async def stop(self) -> None:
        await cleanup_stack(self.api, self.jacktrip, self.jack_client, self.jack_server)


class GetJackServer(Protocol):
    def __call__(self, rate: jack_server.SampleRate, period: int) -> jack_server.Server:
        ...


class GetConnectionMap(Protocol):
    def __call__(self, inputs_limit: int, outputs_limit: int) -> ConnectionMap:
        ...


class GetClientJacktrip(Protocol):
    def __call__(self, map: ConnectionMap) -> StreamingProcess:
        ...


@dataclass
class ClientManager(BaseManager):
    api_http_client: httpx.AsyncClient
    get_jack_server: GetJackServer
    get_jack_client: GetJackClient
    get_connection_map: GetConnectionMap
    get_jacktrip: GetClientJacktrip
    jacktrip: StreamingProcess | None = field(default=None, init=False)
    jack_server_: jack_server.Server | None = field(default=None, init=False)
    jack_client: jack.Client | None = field(default=None, init=False)
    port_connector: ClientPortConnector | None = field(default=None, init=False)

    async def start(self, tg: TaskGroup) -> None:
        api = APIClient(client=self.api_http_client)
        response = await api.init()

        self.jack_server_ = self.get_jack_server(
            rate=response.rate, period=response.buffer_size
        )
        set_jack_server_stream_handlers()
        self.jack_server_.start()

        self.jack_client = await self.get_jack_client()
        map = self.get_connection_map(
            inputs_limit=response.inputs, outputs_limit=response.outputs
        )
        self.port_connector = ClientPortConnector(
            client=self.jack_client, connection_map=map, connect_on_server=api.connect
        )
        tg.start_soon(self.port_connector.wait_and_run)

        self.jacktrip = self.get_jacktrip(map)
        tg.start_soon(self.jacktrip.start)

    async def stop(self) -> None:
        await cleanup_stack(
            self.api_http_client,
            self.port_connector,
            self.jack_client,
            self.jacktrip,
            self.jack_server_,
        )


@singledispatch
async def cleanup(v: Any) -> None:
    ...


@cleanup.register(type(None))
async def _(v: None):
    pass


@cleanup.register(uvicorn.Server)
async def _(v: uvicorn.Server):
    await v.shutdown()


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


@cleanup.register(StreamingProcess)
async def _(v: StreamingProcess):
    await v.stop()


async def cleanup_stack(*stack: Any) -> None:
    for v in stack:
        await cleanup(v)

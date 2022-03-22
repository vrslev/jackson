from dataclasses import dataclass, field
from functools import singledispatch
from typing import Any, Callable, Protocol

import anyio
import httpx
import jack
import jack_server
import uvicorn
from anyio.abc import TaskGroup

from jackson.api_client import APIClient
from jackson.api_server import get_api_server
from jackson.connector_client import ClientPortConnector
from jackson.connector_server import ServerPortConnector
from jackson.jack_client import block_jack_client_streams
from jackson.jack_server import block_jack_server_streams, start_jack_server
from jackson.jacktrip import StreamingProcess
from jackson.port_connection import ConnectionMap, count_receive_send_channels


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
class Server(BaseManager):
    jack_server: jack_server.Server
    jack_client: jack.Client
    jacktrip: StreamingProcess
    api: uvicorn.Server | None = field(default=None, init=False)

    async def start(self, tg: TaskGroup) -> None:
        start_jack_server(self.jack_server)

        tg.start_soon(self.jacktrip.start)

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


class GetClientJacktrip(Protocol):
    def __call__(self, receive_count: int, send_count: int) -> StreamingProcess:
        ...


@dataclass
class Client(BaseManager):
    api_http_client: httpx.AsyncClient
    connection_map: ConnectionMap
    get_jack_server: GetJackServer
    get_jack_client: Callable[[], jack.Client]
    get_jacktrip: GetClientJacktrip
    jack_server_: jack_server.Server | None = field(default=None, init=False)
    jack_client: jack.Client | None = field(default=None, init=False)
    jacktrip: StreamingProcess | None = field(default=None, init=False)

    async def start(self, tg: TaskGroup) -> None:
        api = APIClient(client=self.api_http_client)
        response = await api.init()

        self.jack_server_ = self.get_jack_server(
            rate=response.rate, period=response.buffer_size
        )
        start_jack_server(self.jack_server_)

        self.jack_client = self.get_jack_client()
        port_connector = ClientPortConnector(
            client=self.jack_client,
            connection_map=self.connection_map,
            connect_on_server=api.connect,
        )
        tg.start_soon(port_connector.wait_and_run)

        receive_count, send_count = count_receive_send_channels(
            connection_map=self.connection_map,
            inputs_limit=response.inputs,
            outputs_limit=response.outputs,
        )
        self.jacktrip = self.get_jacktrip(
            receive_count=receive_count, send_count=send_count
        )
        tg.start_soon(self.jacktrip.start)

    async def stop(self) -> None:
        await cleanup_stack(
            self.api_http_client,
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
    v.deactivate()


@cleanup.register(jack_server.Server)
async def _(v: jack_server.Server):
    block_jack_server_streams()
    v.stop()


@cleanup.register(httpx.AsyncClient)
async def _(v: httpx.AsyncClient):
    await v.aclose()


@cleanup.register(StreamingProcess)
async def _(v: StreamingProcess):
    await v.stop()


async def cleanup_stack(*stack: Any) -> None:
    for v in stack:
        await cleanup(v)

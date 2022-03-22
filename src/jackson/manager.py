from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Coroutine, Protocol

import anyio
import jack_server
from anyio.abc import TaskGroup

from jackson.api.client import APIClient
from jackson.api.server import APIServer
from jackson.connector.client import ClientPortConnector, ConnectOnServer
from jackson.jack_server import JackServerController
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
    jack: JackServerController
    api: APIServer
    start_jacktrip: Callable[[], Coroutine[None, None, None]]

    async def start(self, tg: TaskGroup) -> None:
        self.jack.start()
        tg.start_soon(self.start_jacktrip)
        self.api.install_signal_handlers(tg.cancel_scope)
        tg.start_soon(self.api.start)

    async def stop(self) -> None:
        await self.api.stop()
        self.jack.stop()


class GetJack(Protocol):
    def __call__(
        self, rate: jack_server.SampleRate, period: int
    ) -> JackServerController:
        ...


class GetPortConnector(Protocol):
    def __call__(
        self, connect_on_server: ConnectOnServer, inputs_limit: int, outputs_limit: int
    ) -> ClientPortConnector:
        ...


class StartClientJacktrip(Protocol):
    async def __call__(self, map: ConnectionMap) -> None:
        ...


@dataclass
class ClientManager(BaseManager):
    api: APIClient
    get_jack: GetJack
    get_port_connector: GetPortConnector
    start_jacktrip: StartClientJacktrip
    jack: JackServerController | None = field(default=None, init=False)
    port_connector: ClientPortConnector | None = field(default=None, init=False)

    async def start(self, tg: TaskGroup) -> None:
        response = await self.api.init()

        self.jack = self.get_jack(rate=response.rate, period=response.buffer_size)
        self.jack.start()

        self.port_connector = self.get_port_connector(
            connect_on_server=self.api.connect,
            inputs_limit=response.inputs,
            outputs_limit=response.outputs,
        )
        tg.start_soon(self.port_connector.wait_and_run)

        tg.start_soon(partial(self.start_jacktrip, self.port_connector.connection_map))

    async def stop(self) -> None:
        await self.api.client.aclose()

        if self.port_connector:
            self.port_connector.deactivate()

        if self.jack:
            self.jack.stop()

from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Coroutine, Protocol

import anyio
import jack_server
from anyio.abc import TaskGroup
from jack_server._server import SetByJack_

from jackson import jacktrip
from jackson.api.client import APIClient
from jackson.api.server import APIServer
from jackson.connector.client import ClientPortConnector, ConnectOnServer
from jackson.jack_server import JackServerController
from jackson.port_connection import (
    ConnectionMap,
    build_connection_map,
    count_receive_send_channels,
)
from jackson.settings import ClientSettings, ServerSettings


class BaseManager(Protocol):
    async def start(self, tg: TaskGroup) -> None:
        ...

    async def stop(self) -> None:
        ...


class BaseInstance(Protocol):
    manager: BaseManager

    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            try:
                await self.manager.start(tg)
                await anyio.sleep_forever()
            finally:
                with anyio.CancelScope(shield=True):
                    await self.manager.stop()


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


@dataclass(init=False)
class Server(BaseInstance):
    manager: ServerManager

    def __init__(self, settings: ServerSettings) -> None:
        jack = jack_server.Server(
            name=settings.audio.jack_server_name,
            driver=settings.audio.driver,
            device=settings.audio.device or SetByJack_,
            rate=settings.audio.sample_rate,
            period=settings.audio.buffer_size,
        )
        jack_controller = JackServerController(jack)
        api = APIServer(settings.audio.jack_server_name)
        start_jacktrip = lambda: jacktrip.run_server(
            jack_server_name=settings.audio.jack_server_name,
            port=settings.server.jacktrip_port,
        )
        self.manager = ServerManager(
            jack=jack_controller, api=api, start_jacktrip=start_jacktrip
        )


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


@dataclass(init=False)
class Client(BaseInstance):
    manager: ClientManager

    def get_port_connector(
        self,
        settings: ClientSettings,
        connect_on_server: Callable[[ConnectionMap], Coroutine[None, None, None]],
        inputs_limit: int,
        outputs_limit: int,
    ) -> ClientPortConnector:
        map = build_connection_map(
            client_name=settings.name,
            receive=settings.ports.receive,
            send=settings.ports.send,
            inputs_limit=inputs_limit,
            outputs_limit=outputs_limit,
        )
        return ClientPortConnector(
            jack_server_name=settings.audio.jack_server_name,
            connection_map=map,
            connect_on_server=connect_on_server,
        )

    async def start_jacktrip(
        self, settings: ClientSettings, map: ConnectionMap
    ) -> None:
        receive_count, send_count = count_receive_send_channels(map)
        return await jacktrip.run_client(
            jack_server_name=settings.audio.jack_server_name,
            server_host=settings.server.host,
            server_port=settings.server.jacktrip_port,
            receive_channels=receive_count,
            send_channels=send_count,
            remote_name=settings.name,
        )

    def __init__(self, settings: ClientSettings) -> None:
        api = APIClient(base_url=settings.server.api_url)
        get_jack: GetJack = lambda rate, period: JackServerController(
            jack_server.Server(
                name=settings.audio.jack_server_name,
                driver=settings.audio.driver,
                device=settings.audio.device or SetByJack_,
                rate=rate,
                period=period,
            )
        )
        get_port_connector: GetPortConnector = partial(
            self.get_port_connector, settings
        )
        start_jacktrip: StartClientJacktrip = partial(self.start_jacktrip, settings)
        self.manager = ClientManager(
            api=api,
            get_jack=get_jack,
            get_port_connector=get_port_connector,
            start_jacktrip=start_jacktrip,
        )

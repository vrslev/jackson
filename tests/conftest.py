import logging
from asyncio import Queue
from typing import Literal

import anyio
import pytest
from _pytest.logging import LogCaptureFixture
from asyncer._main import TaskGroup

from jackson.jack_client import JackClient
from jackson.manager import Client, Server
from jackson.port_connection import PortConnection, PortName
from jackson.settings import ClientSettings, ServerSettings

ConnectionMapQueue = Queue[dict[PortName, PortConnection]]
ExitQueue = Queue[Literal["server", "client"]]


def ports_are_connected(client: JackClient, source: PortName, destination: PortName):
    connected = False
    src_port = client.get_port_by_name(source)

    for port in client.get_all_connections(src_port):
        if port.name == str(destination):
            connected = True

    return connected


def validate_connections(connection_map: dict[PortName, PortConnection]):
    client = JackClient("ConnectionsTester")
    missing_connections: list[tuple[PortName, PortName]] | None = None

    while missing_connections is None or len(missing_connections) == len(
        connection_map
    ):
        missing_connections = []

        for port_conn in connection_map.values():
            src_name, dest_name = port_conn.get_remote_connection()
            if not ports_are_connected(client, src_name, dest_name):
                missing_connections.append((src_name, dest_name))

        if not missing_connections:
            break

    if missing_connections:
        raise RuntimeError(f"There are missing connections: {missing_connections}")


class CustomServer(Server):
    def __init__(
        self,
        settings: ServerSettings,
        exit_queue: ExitQueue,
        connection_map_queue: ConnectionMapQueue,
    ):
        super().__init__(settings)
        self.exit_queue = exit_queue
        self.connection_map_queue = connection_map_queue

    async def check_connections(self):
        connection_map = await self.connection_map_queue.get()
        validate_connections(connection_map)
        await self.exit_queue.put("server")

    async def start(self, task_group: TaskGroup):
        await super().start(task_group)
        task_group.soonify(self.check_connections)()


class CustomClient(Client):
    def __init__(
        self,
        settings: ClientSettings,
        start_jack: bool,
        exit_queue: ExitQueue,
        connection_map_queue: ConnectionMapQueue,
    ) -> None:
        super().__init__(settings, start_jack)
        self.count = 0
        self.exit_queue = exit_queue
        self.connection_map_queue = connection_map_queue

    def patch_connect_ports_on_both_ends(self):
        assert self.port_connector

        # pyright: reportPrivateUsage = false
        prev_func = self.port_connector._connect_on_both_ends

        async def connect_ports_on_both_ends_override(connection: PortConnection):
            await prev_func(connection)
            self.count += 1

        self.port_connector._connect_on_both_ends = connect_ports_on_both_ends_override

    def init_port_connector(self, inputs_limit: int, outputs_limit: int):
        super().setup_port_connector(inputs_limit, outputs_limit)
        self.patch_connect_ports_on_both_ends()

    async def check_connections(self):
        assert self.port_connector

        while not self.count == len(self.port_connector.connection_map):
            await anyio.sleep(0.0001)

        await self.connection_map_queue.put(self.port_connector.connection_map)
        validate_connections(self.port_connector.connection_map)
        self.exit_queue.put_nowait("client")

    async def start(self, task_group: TaskGroup):
        await super().start(task_group)
        task_group.soonify(self.check_connections)()

    async def run(self, server: CustomServer):
        while not server.api_server._started:
            await anyio.sleep(0.0001)
        return await super().run()


@pytest.fixture(scope="function")
def exit_queue() -> ExitQueue:
    return Queue()


@pytest.fixture(scope="function")
def connection_map_queue() -> ConnectionMapQueue:
    return Queue()


@pytest.fixture(scope="function")
def server(exit_queue: ExitQueue, connection_map_queue: ConnectionMapQueue):
    with open("tests/config.server.test.yaml") as f:
        settings = ServerSettings.from_yaml(f)
    return CustomServer(settings, exit_queue, connection_map_queue)


@pytest.fixture
def client_settings():
    with open("tests/config.client.test.yaml") as f:
        return ClientSettings.from_yaml(f)


@pytest.fixture(scope="function")
def client(
    client_settings: ClientSettings,
    exit_queue: ExitQueue,
    connection_map_queue: ConnectionMapQueue,
):
    return CustomClient(
        client_settings,
        start_jack=False,
        exit_queue=exit_queue,
        connection_map_queue=connection_map_queue,
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def caplog_config(caplog: LogCaptureFixture):
    caplog.set_level(logging.INFO)

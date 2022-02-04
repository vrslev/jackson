from asyncio import Queue
from typing import Literal

import anyio
import asyncer
import rich
from asyncer._main import TaskGroup

import jackson.logging
from jackson.jack_client import JackClient
from jackson.port_connection import PortConnection, PortName

jackson.logging.MODE = "test"


from jackson.manager import Client, Server
from jackson.settings import ClientSettings, ServerSettings

connection_map_queue: Queue[dict[PortName, PortConnection]] = Queue()
exit_queue: Queue[Literal["server", "client"]] = Queue()


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


class TestingServer(Server):
    async def check_connections(self):
        connection_map = await connection_map_queue.get()
        validate_connections(connection_map)
        await exit_queue.put("server")

    async def start(self, task_group: TaskGroup):
        await super().start(task_group)
        task_group.soonify(self.check_connections)()


class TestingClient(Client):
    count: int = 0

    def patch_connect_ports_on_both_ends(self):
        assert self.port_connector

        # pyright: reportPrivateUsage = false
        prev_func = self.port_connector._connect_ports_on_both_ends

        async def connect_ports_on_both_ends_override(connection: PortConnection):
            await prev_func(connection)
            self.count += 1

        self.port_connector._connect_ports_on_both_ends = (
            connect_ports_on_both_ends_override
        )

    def init_port_connector(self, inputs_limit: int, outputs_limit: int):
        super().init_port_connector(inputs_limit, outputs_limit)
        self.patch_connect_ports_on_both_ends()

    async def check_connections(self):
        assert self.port_connector

        while not self.count == len(self.port_connector.connection_map):
            await anyio.sleep(0.0001)

        await connection_map_queue.put(self.port_connector.connection_map)
        validate_connections(self.port_connector.connection_map)
        exit_queue.put_nowait("client")

    async def start(self, task_group: TaskGroup):
        await super().start(task_group)
        task_group.soonify(self.check_connections)()


def get_server():
    with open("tests/config.server.test.yaml") as f:
        settings = ServerSettings.from_yaml(f)
    return TestingServer(settings)


def get_client():
    with open("tests/config.client.test.yaml") as f:
        settings = ClientSettings.from_yaml(f)
    return TestingClient(settings, start_jack=False)


async def async_main():
    server = get_server()
    client = get_client()

    async with asyncer.create_task_group() as task_group:
        task_group.soonify(server.run)()

        while not server.messaging_server._started:
            await anyio.sleep(0.0001)

        task_group.soonify(client.run)()

        server_ok = False
        client_ok = False

        while True:
            value = await exit_queue.get()
            if value == "server":
                server_ok = True
            else:
                client_ok = True

            if server_ok and client_ok:
                task_group.cancel_scope.cancel()
                return 0


def main():
    code = asyncer.runnify(async_main)()
    if code == 0:
        rich.print("[bold green]Test passed![/bold green]")


if __name__ == "__main__":
    main()

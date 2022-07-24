from collections.abc import Awaitable, Callable

import anyio
import jack

from jackson.jack_client import connect_ports_and_log
from jackson.jacktrip import JACK_CLIENT_NAME
from jackson.port_connection import ConnectionMap


def ports_already_connected(client: jack.Client, source: str, destination: str) -> bool:
    source_port = client.get_port_by_name(source)
    connections = client.get_all_connections(source_port)
    return any(p.name == destination for p in connections)


async def connect_server_and_client_ports(
    client: jack.Client,
    connect_on_server: Callable[[ConnectionMap], Awaitable[None]],
    connection_map: ConnectionMap,
) -> None:
    def on_register(name: str, register: bool) -> None:
        if register and name == JACK_CLIENT_NAME:
            ready.set()

    ready = anyio.Event()
    client.set_client_registration_callback(on_register)
    client.activate()

    await ready.wait()
    await connect_on_server(connection_map)

    for conn in connection_map.values():
        src, dest = conn.get_local_connection()
        src_str, dest_str = str(src), str(dest)

        if not ports_already_connected(client, src_str, dest_str):
            connect_ports_and_log(client, src_str, dest_str)

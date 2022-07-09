from typing import Callable, Coroutine

import anyio
import jack

from jackson.jack_client import connect_ports_safe
from jackson.jacktrip import JACK_CLIENT_NAME
from jackson.port_connection import ConnectionMap


async def connect_server_and_client_ports(
    client: jack.Client,
    connect_on_server: Callable[[ConnectionMap], Coroutine[None, None, None]],
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
        connect_ports_safe(client, str(src), str(dest))

from typing import Callable, Coroutine

import anyio
import jack

from jackson.jack_client import retry_connect_ports
from jackson.jacktrip import JACK_CLIENT_NAME
from jackson.port_connection import ConnectionMap


async def connect_server_and_client_ports(
    client: jack.Client,
    connection_map: ConnectionMap,
    connect_on_server: Callable[[ConnectionMap], Coroutine[None, None, None]],
) -> None:
    def cb(name: str, register: bool) -> None:
        if register and name == JACK_CLIENT_NAME:
            ready.set()

    ready = anyio.Event()
    client.set_client_registration_callback(cb)
    client.activate()
    await ready.wait()

    async def connect_locally() -> None:
        for conn in connection_map.values():
            src, dest = conn.get_local_connection()
            await retry_connect_ports(client, str(src), str(dest))

    async with anyio.create_task_group() as tg:
        tg.start_soon(lambda: connect_on_server(connection_map))
        tg.start_soon(connect_locally)

import asyncio
from functools import partial
from typing import Callable, Coroutine

import asyncer
import jack

from jackson.api.client import MessagingClient
from jackson.jack_client import JackClient
from jackson.logging import get_logger
from jackson.port_connection import PortConnection, PortName
from jackson.settings import ClientPorts

log = get_logger(__name__, "PortConnector")


class PortConnector:
    def __init__(
        self,
        *,
        client_name: str,
        ports: ClientPorts,
        messaging_client: MessagingClient,
        inputs_limit: int,
        outputs_limit: int,
    ) -> None:
        self.client_name = client_name
        self.messaging_client = messaging_client
        self.callback_queue: asyncio.Queue[
            Callable[[], Coroutine[None, None, None]]
        ] = asyncio.Queue()

        self._build_connection_map(ports, inputs_limit, outputs_limit)
        self._setup_jack_client()

    def _build_connection_map(
        self, ports_from_config: ClientPorts, inputs_limit: int, outputs_limit: int
    ):
        connections: list[PortConnection] = []
        prev_send_port_idx = 0
        prev_receive_port_idx = 0

        # Resolve send ports
        for src_idx, dest_idx in ports_from_config.send.items():
            bridge_idx = prev_send_port_idx + 1
            prev_send_port_idx = bridge_idx
            if bridge_idx > inputs_limit:
                raise RuntimeError("Limit of available send ports exceeded.")

            conn = PortConnection(
                client_should="send",
                source=PortName(client="system", type="capture", idx=src_idx),
                local_bridge=PortName(client="JackTrip", type="send", idx=bridge_idx),
                remote_bridge=PortName(
                    client=self.client_name, type="receive", idx=bridge_idx
                ),
                destination=PortName(client="system", type="playback", idx=dest_idx),
            )
            connections.append(conn)

        # Resolve receive ports
        for dest_idx, src_idx in ports_from_config.receive.items():
            bridge_idx = prev_receive_port_idx + 1
            prev_receive_port_idx = bridge_idx
            if bridge_idx > outputs_limit:
                raise RuntimeError("Limit of available receive ports exceeded.")

            conn = PortConnection(
                client_should="receive",
                source=PortName(client="system", type="capture", idx=src_idx),
                remote_bridge=PortName(
                    client=self.client_name, type="send", idx=bridge_idx
                ),
                local_bridge=PortName(
                    client="JackTrip", type="receive", idx=bridge_idx
                ),
                destination=PortName(client="system", type="playback", idx=dest_idx),
            )
            connections.append(conn)

        RegisteredJackTripPort = PortName
        self.connection_map: dict[RegisteredJackTripPort, PortConnection] = {
            conn.local_bridge: conn for conn in connections
        }

    def _setup_jack_client(self):
        self.jack_client = JackClient("PortConnector")
        self.jack_client.set_port_registration_callback(
            self._port_registration_callback
        )
        self.jack_client.activate()

    def _log_port_registration(self, name: str, registered: bool):
        if registered:
            log.info(f"Registered port: [green]{name}[/green]")
        else:
            log.info(f"Unregistered port: [red]{name}[/red]")

    def _port_should_connect(self, name: PortName, registered: bool):
        return registered and name in self.connection_map

    def _schedule_port_connection(self, name: PortName):
        conn = self.connection_map[name]
        func = partial(self._connect_on_both_ends, connection=conn)
        self.callback_queue.put_nowait(func)

    def _port_registration_callback(self, port: jack.Port, registered: bool):
        self._log_port_registration(port.name, registered)
        port_name = PortName.parse(port.name)

        if self._port_should_connect(port_name, registered):
            self._schedule_port_connection(port_name)

    async def _connect_on_both_ends(self, connection: PortConnection):
        await self.messaging_client.connect(
            *connection.get_remote_connection(), connection.client_should
        )
        self.jack_client.connect(*connection.get_local_connection())

    def count_receive_send_channels(self):  # Required for JackTrip
        receive, send = 0, 0

        for connection in self.connection_map.values():
            if connection.client_should == "send":
                send += 1
            else:
                receive += 1

        return receive, send

    async def run_queue(self):
        async with asyncer.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.soonify(callback)()

    def stop(self):
        self.jack_client.deactivate()

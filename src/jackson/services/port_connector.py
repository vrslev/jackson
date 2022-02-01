import asyncio
from functools import partial
from typing import Any, Callable, Coroutine

import asyncer
import jack

from jackson.logging import get_configured_logger
from jackson.services import jacktrip
from jackson.services.jack_client import JackClient
from jackson.services.messaging.client import MessagingClient
from jackson.services.port_connection import PortConnection, PortName
from jackson.settings import ClientPorts

log = get_configured_logger(__name__, "PortConnector")


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
        self._build_connection_map(ports, inputs_limit, outputs_limit)

        self.callback_queue: asyncio.Queue[
            Callable[[], Coroutine[Any, Any, None]]
        ] = asyncio.Queue()
        self.messaging_client = messaging_client

        self.jack_client = JackClient("PortConnector")
        self.jack_client.set_port_registration_callback(
            self._port_registration_callback
        )
        self.jack_client.activate()

    def _build_connection_map(
        self, ports_from_config: ClientPorts, inputs_limit: int, outputs_limit: int
    ):
        connections: list[PortConnection] = []

        # Resolve send ports
        for source_idx, destination_idx in ports_from_config.send.items():
            bridge_idx = jacktrip.get_first_available_send_port(inputs_limit)
            conn = PortConnection(
                client_should="send",
                source=PortName(client="system", type="capture", idx=source_idx),
                local_bridge=PortName(client="JackTrip", type="send", idx=bridge_idx),
                remote_bridge=PortName(
                    client=self.client_name, type="receive", idx=bridge_idx
                ),
                destination=PortName(
                    client="system", type="playback", idx=destination_idx
                ),
            )
            connections.append(conn)

        # Resolve receive ports
        for destination_idx, source_idx in ports_from_config.receive.items():
            bridge_idx = jacktrip.get_first_available_receive_port(outputs_limit)
            conn = PortConnection(
                client_should="receive",
                source=PortName(client="system", type="capture", idx=source_idx),
                remote_bridge=PortName(
                    client=self.client_name, type="send", idx=bridge_idx
                ),
                local_bridge=PortName(
                    client="JackTrip", type="receive", idx=bridge_idx
                ),
                destination=PortName(
                    client="system", type="playback", idx=destination_idx
                ),
            )
            connections.append(conn)

        RegisteredJackTripPort = str
        self.connection_map: dict[RegisteredJackTripPort, PortConnection] = {}
        for conn in connections:
            self.connection_map[str(conn.local_bridge)] = conn

    def count_receive_send_channels(self):
        # Required for JackTrip
        receive, send = 0, 0
        for connection in self.connection_map.values():
            if connection.client_should == "send":
                send += 1
            else:
                receive += 1
        return receive, send

    async def _connect_ports_on_both_ends(self, connection: PortConnection):
        await self.messaging_client.connect(
            *connection.get_remote_connection(),
            client_should=connection.client_should,
        )
        self.jack_client.connect(*connection.get_local_connection())

    def _port_registration_callback(self, port: jack.Port, register: bool):
        port_name = port.name

        if not register:
            log.info(f"Unregistered port: {port_name}")
            return  # We don't want to do anything if port unregistered

        log.info(f"Registered port: {port_name}")

        if port_name not in self.connection_map:
            return

        conn = self.connection_map[port_name]
        self.callback_queue.put_nowait(partial(self._connect_ports_on_both_ends, conn))

    async def run_queue(self):
        async with asyncer.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.soonify(callback)()

    def deinit(self):
        self.jack_client.deactivate()

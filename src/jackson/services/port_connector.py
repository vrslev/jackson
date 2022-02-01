import asyncio
from typing import Any, Callable, Coroutine

import asyncer
import jack
from pydantic import BaseModel

from jackson.logging import get_configured_logger
from jackson.services import jacktrip
from jackson.services.jack_client import JackClient
from jackson.services.messaging.client import MessagingClient
from jackson.services.models import ClientShould, PortName
from jackson.settings import ClientPorts

log = get_configured_logger(__name__, "PortConnector")


class PortConnection(BaseModel, frozen=True):
    client_should: ClientShould
    source: PortName
    local_bridge: PortName
    remote_bridge: PortName
    destination: PortName

    def get_local_connection(self):
        if self.client_should == "send":
            return self.source, self.local_bridge
        else:
            return self.local_bridge, self.destination

    def get_remote_connection(self):
        if self.client_should == "send":
            return self.remote_bridge, self.destination
        else:
            return self.source, self.remote_bridge


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
        self.init_connections(ports, inputs_limit, outputs_limit)

        self.callback_queue: asyncio.Queue[
            Callable[[], Coroutine[Any, Any, None]]
        ] = asyncio.Queue()
        self.messaging_client = messaging_client
        self.jack_client = None

    def init_connections(
        self, ports_from_config: ClientPorts, inputs_limit: int, outputs_limit: int
    ):
        connections: list[PortConnection] = []
        self.resolve_send_ports(connections, ports_from_config.send, inputs_limit)
        self.resolve_receive_ports(
            connections, ports_from_config.receive, outputs_limit
        )
        self.build_connection_map(connections)

    def resolve_send_ports(
        self, connections: list[PortConnection], send_ports: dict[int, int], limit: int
    ):
        for source_idx, destination_idx in send_ports.items():
            bridge_idx = jacktrip.get_first_available_send_port(limit)
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

    def resolve_receive_ports(
        self,
        connections: list[PortConnection],
        receive_ports: dict[int, int],
        limit: int,
    ):
        for destination_idx, source_idx in receive_ports.items():
            bridge_idx = jacktrip.get_first_available_receive_port(limit)
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

    def build_connection_map(self, connections: list[PortConnection]):
        RegisteredJackTripPort = str
        self.connection_map: dict[RegisteredJackTripPort, PortConnection] = {}
        for conn in connections:
            self.connection_map[str(conn.local_bridge)] = conn

    def get_receive_send_channels_counts(self):
        receive, send = 0, 0
        for connection in self.connection_map.values():
            if connection.client_should == "send":
                send += 1
            else:
                receive += 1
        return receive, send

    async def _connect_ports(self, connection: PortConnection):
        assert self.jack_client

        remote_source, remote_destination = connection.get_remote_connection()

        await self.messaging_client.connect(
            source=remote_source,
            destination=remote_destination,
            client_should=connection.client_should,
        )

        local_source, local_destination = connection.get_local_connection()
        self.jack_client.connect(local_source, local_destination)

    def port_registration_callback(self, port: jack.Port, register: bool):
        port_name = port.name
        if not register:
            log.info(f"Unregistered port: {port_name}")
            return  # We don't want to do anything if port unregistered

        log.info(f"Registered port: {port_name}")

        if port_name not in self.connection_map:
            return

        conn = self.connection_map[port_name]

        async def task():
            await self._connect_ports(conn)

        self.callback_queue.put_nowait(task)

    def init(self):
        self.jack_client = JackClient("PortConnector")
        self.jack_client.set_port_registration_callback(self.port_registration_callback)
        self.jack_client.activate()

    def deinit(self):
        if self.jack_client:
            self.jack_client.deactivate()

    async def start_queue(self):
        async with asyncer.create_task_group() as task_group:
            while True:
                callback = await self.callback_queue.get()
                task_group.soonify(callback)()

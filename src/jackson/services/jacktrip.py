import contextlib
import itertools
import shlex
from ipaddress import IPv4Address
from typing import Callable

import anyio
import asyncer
import typer
from anyio.abc import ByteReceiveStream, Process
from anyio.streams.text import TextReceiveStream

from jackson.logging import JackTripFilter, get_configured_logger

log = get_configured_logger(__name__, "JackTrip")
log.addFilter(JackTripFilter())


class _Program:
    def __init__(self, cmd: list[str]) -> None:
        self.cmd = cmd
        self.name = cmd[0]

    async def _restream_stream(
        self, stream: ByteReceiveStream | None, handler: Callable[[str], None]
    ):
        if not stream:
            return

        async for text in TextReceiveStream(stream):
            for line in text.splitlines():
                handler(line.strip())

    @contextlib.asynccontextmanager
    async def _start(self):
        log.info(f"Starting {self.name}... ({shlex.join(self.cmd)})")

        async with await anyio.open_process(self.cmd) as process:
            async with asyncer.create_task_group() as task_group:
                task_group.soonify(self._restream_stream)(
                    stream=process.stderr, handler=log.error
                )
                task_group.soonify(self._restream_stream)(
                    stream=process.stdout, handler=log.info
                )
                yield process

    async def _close(self, process: Process):
        if process.returncode is None:
            process.terminate()
        await process.wait()
        code = process.returncode

        # Otherwise RuntimeError('Event loop is closed') is being called
        process._process._transport.close()  # type: ignore

        log.info(f"Exited with code {code}")
        return code

    async def run_forever(self):
        async with self._start() as process:
            try:
                await process.wait()

            except anyio.get_cancelled_exc_class():
                with anyio.CancelScope(shield=True):
                    return await self._close(process)

            else:
                if (code := await self._close(process)) == 0:
                    await self.run_forever()
                else:
                    raise typer.Exit(code or 0)


async def start_server(*, port: int, udprt: bool = True):
    cmd: list[str] = [
        "jacktrip",
        "--jacktripserver",
        "--bindport",
        str(port),
        "--nojackportsconnect",
    ]

    if udprt:
        cmd.append("--udprt")

    await _Program(cmd).run_forever()


async def start_client(
    *,
    host: IPv4Address,
    port: int,
    receive_channels: int,
    send_channels: int,
    remote_name: str,
    client_name: str = "JackTrip",
    udprt: bool = True,
):
    """
    Args:
        remote_name — The name by which a server identifies a client
        client_name — The name of JACK Client
    """
    cmd: list[str] = [
        "jacktrip",
        "--pingtoserver",
        str(host),
        "--receivechannels",
        str(receive_channels),
        "--sendchannels",
        str(send_channels),
        "--peerport",
        str(port),
        "--clientname",
        client_name,
        "--remotename",
        remote_name,
        "--nojackportsconnect",
    ]

    if udprt:
        cmd.append("--udprt")

    await _Program(cmd).run_forever()


# def resolve_number_of_send_channels(send_ports: dict[int, int]):
#     return max(send_ports.keys()) if send_ports else 0


_BridgePort = int
_reserved_send_ports: set[_BridgePort] = set()
_reserved_receive_ports: set[_BridgePort] = set()


def _get_first_available_bridge_port(set_: set[_BridgePort]) -> int:  # type: ignore
    for idx in itertools.count(start=1):
        if idx in set_:
            continue
        set_.add(idx)
        return idx


def get_first_available_bridge_send_port():
    return _get_first_available_bridge_port(_reserved_send_ports)


def get_first_available_bridge_receive_port():
    return _get_first_available_bridge_port(_reserved_receive_ports)

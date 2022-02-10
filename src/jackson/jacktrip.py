import contextlib
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
        log.info(
            f"Starting [bold blue]{self.name}[/bold blue]..."
            + f" [italic]({shlex.join(self.cmd)})[/italic]"
        )

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
                code = await self._close(process)
                if code == 0:
                    await self.run_forever()
                else:
                    raise typer.Exit(code or 0)


async def _run_jacktrip(cmd: list[str]):
    await _Program(cmd).run_forever()


def _build_server_cmd(*, port: int):
    return [
        "jacktrip",
        "--jacktripserver",
        "--bindport",
        str(port),
        "--nojackportsconnect",
        "--udprt",
    ]


async def run_server(*, port: int):
    cmd = _build_server_cmd(port=port)
    await _run_jacktrip(cmd)


def _build_client_cmd(
    *,
    server_host: IPv4Address,
    server_port: int,
    receive_channels: int,
    send_channels: int,
    remote_name: str,
):
    return [
        "jacktrip",
        "--pingtoserver",
        str(server_host),
        "--receivechannels",
        str(receive_channels or 1),
        # JackTrip doesn't allow one-way channel broadcasting
        "--sendchannels",
        str(send_channels or 1),
        "--peerport",
        str(server_port),
        "--clientname",
        "JackTrip",
        "--remotename",
        remote_name,
        "--nojackportsconnect",
        "--udprt",
    ]


async def run_client(
    *,
    server_host: IPv4Address,
    server_port: int,
    receive_channels: int,
    send_channels: int,
    remote_name: str,
):
    cmd = _build_client_cmd(
        server_host=server_host,
        server_port=server_port,
        receive_channels=receive_channels,
        send_channels=send_channels,
        remote_name=remote_name,
    )
    await _run_jacktrip(cmd)

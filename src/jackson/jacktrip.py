import contextlib
import os
import shlex
from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Callable

import anyio
import typer
from anyio.abc import ByteReceiveStream, Process
from anyio.streams.text import TextReceiveStream

from jackson.logging import JackTripFilter, get_logger

log = get_logger(__name__, "JackTrip")
log.addFilter(JackTripFilter())

JACK_CLIENT_NAME = "JackTrip"


async def _restream_stream(
    stream: ByteReceiveStream | None, handler: Callable[[str], None]
):
    if not stream:
        return

    async for text in TextReceiveStream(stream):
        for line in text.splitlines():
            handler(line.strip())


async def _close_process(process: Process):
    if process.returncode is None:
        process.terminate()

    await process.wait()
    code = process.returncode

    # Otherwise RuntimeError('Event loop is closed') is being called
    process._process._transport.close()  # type: ignore

    log.info(f"Exited with code {code}")
    return code


def _log_starting(cmd: list[str]) -> None:
    log.info(
        f"Starting [bold blue]{cmd[0]}[/bold blue]..."
        + f" [italic]({shlex.join(cmd)})[/italic]"
    )


@dataclass
class _Program:
    cmd: list[str]
    env: dict[str, str]

    @contextlib.asynccontextmanager
    async def _start(self):
        _log_starting(self.cmd)

        env = dict(os.environ)
        env.update(self.env)

        async with await anyio.open_process(self.cmd, env=env) as process:
            async with anyio.create_task_group() as tg:
                tg.start_soon(lambda: _restream_stream(process.stderr, log.error))
                tg.start_soon(lambda: _restream_stream(process.stdout, log.error))
                yield process

    async def run_forever(self):
        async with self._start() as process:
            try:
                await process.wait()

            except anyio.get_cancelled_exc_class():
                with anyio.CancelScope(shield=True):
                    await _close_process(process)

            else:  # Exited by itself
                code = await _close_process(process)
                if code == 0:
                    await self.run_forever()
                else:
                    raise typer.Exit(code or 0)


async def _run_jacktrip(cmd: list[str], jack_server_name: str):
    cmd.insert(0, "jacktrip")
    env = {"JACK_DEFAULT_SERVER": jack_server_name}
    await _Program(cmd=cmd, env=env).run_forever()


def _build_server_cmd(*, port: int):
    return [
        "--jacktripserver",
        "--bindport",
        str(port),
        "--nojackportsconnect",
        "--udprt",
    ]


async def run_server(*, jack_server_name: str, port: int):
    cmd = _build_server_cmd(port=port)
    await _run_jacktrip(cmd, jack_server_name)


def _build_client_cmd(
    *,
    server_host: IPv4Address,
    server_port: int,
    receive_channels: int,
    send_channels: int,
    remote_name: str,
):
    return [
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
        JACK_CLIENT_NAME,
        "--remotename",
        remote_name,
        "--nojackportsconnect",
        "--udprt",
    ]


async def run_client(
    *,
    jack_server_name: str,
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
    await _run_jacktrip(cmd, jack_server_name)

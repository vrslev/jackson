import contextlib
import shlex
from ipaddress import IPv4Address
from shutil import which
from typing import IO, Callable

import anyio
import asyncer
import typer
import yaml
from anyio.abc import ByteReceiveStream, Process
from anyio.streams.text import TextReceiveStream
from pydantic import BaseModel, BaseSettings

_available_colors: set[str] = set()


def get_random_color():
    global _available_colors

    if not _available_colors:
        _available_colors = {
            typer.colors.GREEN,
            typer.colors.YELLOW,
            typer.colors.BLUE,
            typer.colors.MAGENTA,
            typer.colors.CYAN,
        }

    return _available_colors.pop()


def _generate_stream_handler(proc: str, color: str):
    def printer(message: str):
        typer.secho(f"[{proc}] {message}", fg=color)  # type: ignore

    return printer


async def _restream_stream(
    stream: ByteReceiveStream | None, handler: Callable[[str], None]
):
    if not stream:
        return

    async for text in TextReceiveStream(stream):
        for line in text.splitlines():
            handler(line.strip())


async def _close_process(process: Process, printer: Callable[[str], None]):
    if process.returncode is None:
        process.terminate()
    await process.wait()
    code = process.returncode

    # Otherwise RuntimeError('Event loop is closed') is being called
    process._process._transport.close()  # type: ignore

    printer(f"Exited with code {code}")
    if code != 0:
        raise typer.Exit(code or 0)
    return code


@contextlib.asynccontextmanager
async def start_process(cmd: list[str]):
    proc = cmd[0]
    handler = _generate_stream_handler(proc, get_random_color())
    handler(f"Starting {proc}... ({shlex.join(cmd)})")

    async with await anyio.open_process(cmd) as process:  # type: ignore
        async with asyncer.create_task_group() as task_group:
            task_group.soonify(_restream_stream)(stream=process.stderr, handler=handler)
            task_group.soonify(_restream_stream)(stream=process.stdout, handler=handler)
            yield process, handler


async def run_process(cmd: list[str]):
    async with start_process(cmd) as (process, handler):
        try:
            await process.wait()
        finally:
            with anyio.CancelScope(shield=True):
                return await _close_process(process, handler)


async def run_forever(cmd: list[str]):
    async with start_process(cmd) as (process, handler):
        try:
            await process.wait()
        except anyio.get_cancelled_exc_class():
            with anyio.CancelScope(shield=True):
                return await _close_process(process, handler)
        else:
            code = await _close_process(process, handler)
            if code == 0:
                await run_forever(cmd)


_SourcePort = str
_DestinationPort = str
ChannelMap = dict[_SourcePort, _DestinationPort]


class _ClientSettings(BaseModel):
    remote_name: str
    port: int
    channels: ChannelMap
    backend: str
    device: str


class _ServerSettings(_ClientSettings):
    address: IPv4Address


class Settings(BaseSettings):
    server: _ServerSettings
    client: _ClientSettings

    @classmethod
    def load(cls, file: IO[str]):
        content = yaml.safe_load(file)
        return cls(**content)


def check_jack_jacktrip_on_machine():
    if not which("jackd"):
        raise RuntimeError("Install jackd before running")
    if not which("jacktrip"):
        raise RuntimeError("Install jacktrip before running")

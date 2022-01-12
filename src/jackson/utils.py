from ipaddress import IPv4Address
from shutil import which
from typing import IO, Callable

import anyio
import asyncer
import typer
import yaml
from anyio.abc import ByteReceiveStream
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


def _handle_exit(code: int | None, printer: Callable[[str], None]):
    if code is None:
        printer(f"Exited")
    else:
        printer(f"Exited with code {code}")
        if code > 0:
            raise typer.Exit(code)


async def run_process(cmd: list[str]):
    proc = cmd[0]
    handler = _generate_stream_handler(proc, get_random_color())

    async with await anyio.open_process(cmd) as process:  # type: ignore
        try:
            async with asyncer.create_task_group() as task_group:
                task_group.soonify(_restream_stream)(
                    stream=process.stderr, handler=handler
                )
                task_group.soonify(_restream_stream)(
                    stream=process.stdout, handler=handler
                )
            code = await process.wait()
            _handle_exit(code, handler)
            return code

        except anyio.get_cancelled_exc_class():
            if process.returncode is None:
                process.terminate()
            _handle_exit(process.returncode, handler)
            raise


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

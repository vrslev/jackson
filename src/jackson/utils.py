import asyncio
import shlex
from ipaddress import IPv4Address
from shutil import which
from typing import IO, Callable

import typer
import yaml
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


async def _read_and_print_stream(
    stream: asyncio.StreamReader | None, handler: Callable[[str], None]
):
    if not stream:
        return

    while True:
        if line := await stream.readline():
            handler(line.decode().strip())
        else:
            break


def _get_print_handler(proc_name: str, color: str):
    def printer(message: str):
        typer.secho(f"[{proc_name}] {message}", fg=color)  # type: ignore

    return printer


async def execute(cmd: list[str]):
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    printer = _get_print_handler(proc_name=cmd[0], color=get_random_color())
    printer(f"Starting {cmd[0]}... [{shlex.join(cmd)}]")

    async def read_streams():
        await asyncio.gather(
            _read_and_print_stream(stream=process.stdout, handler=printer),
            _read_and_print_stream(stream=process.stderr, handler=printer),
        )

    try:
        await read_streams()
        return await process.wait()
    finally:
        try:
            process.terminate()
        except ProcessLookupError:
            pass

        if process.returncode is not None:
            printer(f"Exited with code {process.returncode}")
        else:
            printer("Exited")


async def run_forever(cmd: list[str]):
    while True:
        code = await execute(cmd)
        if code > 0:
            raise typer.Exit(code)


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

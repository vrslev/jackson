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


def _get_random_color():
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


def generate_stream_handler(proc: str):
    color = _get_random_color()

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


class Program:
    def __init__(self, cmd: list[str]) -> None:
        self.cmd = cmd
        self.proc = cmd[0]

    @contextlib.asynccontextmanager
    async def _start(self):
        self.printer = generate_stream_handler(self.proc)
        self.printer(f"Starting {self.proc}... ({shlex.join(self.cmd)})")

        async with await anyio.open_process(self.cmd) as process:  # type: ignore
            async with asyncer.create_task_group() as task_group:
                task_group.soonify(_restream_stream)(
                    stream=process.stderr, handler=self.printer
                )
                task_group.soonify(_restream_stream)(
                    stream=process.stdout, handler=self.printer
                )
                yield process

    async def _close(self, process: Process):
        if process.returncode is None:
            process.terminate()
        await process.wait()
        code = process.returncode

        # Otherwise RuntimeError('Event loop is closed') is being called
        process._process._transport.close()  # type: ignore

        self.printer(f"Exited with code {code}")
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

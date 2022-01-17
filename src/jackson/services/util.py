import contextlib
import shlex
from functools import partial
from typing import Callable

import anyio
import asyncer
import typer
from anyio.abc import ByteReceiveStream, Process
from anyio.streams.text import TextReceiveStream
from rich.console import Console
from rich.style import Style


def generate_stream_handlers(proc: str):
    console = Console(log_path=False, log_time_format=f"[%X] [{proc}]")
    return console.log, partial(console.log, style=Style(bold=True))


class Program:
    def __init__(self, cmd: list[str]) -> None:
        self.cmd = cmd
        self.proc = cmd[0]
        self._info, self._err = generate_stream_handlers(self.proc)

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
        self._info(f"Starting {self.proc}... ({shlex.join(self.cmd)})")

        async with await anyio.open_process(self.cmd) as process:  # type: ignore
            async with asyncer.create_task_group() as task_group:
                task_group.soonify(self._restream_stream)(
                    stream=process.stderr, handler=self._err
                )
                task_group.soonify(self._restream_stream)(
                    stream=process.stdout, handler=self._info
                )
                yield process

    async def _close(self, process: Process):
        if process.returncode is None:
            process.terminate()
        await process.wait()
        code = process.returncode

        # Otherwise RuntimeError('Event loop is closed') is being called
        process._process._transport.close()  # type: ignore

        self._info(f"Exited with code {code}")
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

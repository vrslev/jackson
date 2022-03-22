import contextlib
import logging
import os
import shlex
from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import AsyncGenerator, Callable

import anyio
from anyio.abc import ByteReceiveStream, Process
from anyio.streams.text import TextReceiveStream

from jackson.logging import MessageFilter, get_logger


class JackTripFilter(MessageFilter):
    messages = {
        "WEAK-JACK: initializing",
        "WEAK-JACK: OK.",
        "mThreadPool default maxThreadCount",
        "mThreadPool maxThreadCount previously set",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        if all(c == "-" for c in record.msg):
            return False

        if all(c == "=" for c in record.msg):
            return False

        return super().filter(record)


log = get_logger(__name__, "JackTrip")
log.addFilter(JackTripFilter())

JACK_CLIENT_NAME = "JackTrip"


async def _restream_stream(
    stream: ByteReceiveStream | None, handler: Callable[[str], None]
) -> None:
    if not stream:
        return

    async for text in TextReceiveStream(stream):
        for line in text.splitlines():
            handler(line.strip())


@dataclass
class StreamingProcess:
    cmd: list[str]
    env: dict[str, str]
    process: Process | None = None

    @contextlib.asynccontextmanager
    async def _open_process_and_stream(self) -> AsyncGenerator[Process, None]:
        log.info(
            f"Starting [bold blue]{self.cmd[0]}[/bold blue]..."
            + f" [italic]({shlex.join(self.cmd)})[/italic]"
        )

        env = dict(os.environ)
        env.update(self.env)

        async with await anyio.open_process(self.cmd, env=env) as process:
            async with anyio.create_task_group() as tg:
                tg.start_soon(lambda: _restream_stream(process.stderr, log.error))
                tg.start_soon(lambda: _restream_stream(process.stdout, log.error))
                yield process

    async def start(self) -> None:
        async with self._open_process_and_stream() as self.process:
            try:
                await self.process.wait()
            except anyio.get_cancelled_exc_class():
                with anyio.CancelScope(shield=True):
                    await self.stop()
            else:
                code = await self.stop()
                raise RuntimeError(f"JackTrip exited with code {code}")

    async def stop(self) -> int | None:
        assert self.process

        if self.process.returncode is None:
            self.process.terminate()

        await self.process.wait()
        code = self.process.returncode

        # Otherwise RuntimeError('Event loop is closed') is being called
        self.process._process._transport.close()  # type: ignore

        log.info(f"Exited with code {code}")
        return code


def _get_jacktrip(cmd: list[str], jack_server_name: str) -> StreamingProcess:
    cmd.insert(0, "jacktrip")
    env = {"JACK_DEFAULT_SERVER": jack_server_name}
    return StreamingProcess(cmd=cmd, env=env)


def _build_server_cmd(*, port: int) -> list[str]:
    return [
        "--jacktripserver",
        "--bindport",
        str(port),
        "--nojackportsconnect",
        "--udprt",
    ]


def get_server(*, jack_server_name: str, port: int) -> StreamingProcess:
    cmd = _build_server_cmd(port=port)
    return _get_jacktrip(cmd, jack_server_name)


def _build_client_cmd(
    *,
    server_host: IPv4Address,
    server_port: int,
    receive_channels: int,
    send_channels: int,
    remote_name: str,
) -> list[str]:
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


def get_client(
    *,
    jack_server_name: str,
    server_host: IPv4Address,
    server_port: int,
    receive_channels: int,
    send_channels: int,
    remote_name: str,
) -> StreamingProcess:
    cmd = _build_client_cmd(
        server_host=server_host,
        server_port=server_port,
        receive_channels=receive_channels,
        send_channels=send_channels,
        remote_name=remote_name,
    )
    return _get_jacktrip(cmd, jack_server_name)

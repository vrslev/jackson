import contextlib
import logging
import os
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from ipaddress import IPv4Address

import anyio
from anyio.abc import ByteReceiveStream, Process
from anyio.streams.text import TextReceiveStream

JACK_CLIENT_NAME = "JackTrip"


async def _restream_stream(
    stream: ByteReceiveStream | None, handler: Callable[[str], None]
) -> None:
    assert stream
    async for text in TextReceiveStream(stream):
        for line in text.splitlines():
            handler(line.strip())


@dataclass
class StreamingProcess:
    cmd: list[str]
    env: dict[str, str]
    log: logging.Logger

    process: Process | None = field(default=None, init=False)
    is_stopping: bool = field(default=False, init=False)

    @contextlib.asynccontextmanager
    async def _open_process_and_stream(self) -> AsyncGenerator[Process, None]:
        env = dict(os.environ)
        env.update(self.env)

        async with await anyio.open_process(self.cmd, env=env) as process:
            async with anyio.create_task_group() as tg:
                tg.start_soon(lambda: _restream_stream(process.stderr, self.log.error))
                yield process

    async def start(self) -> None:
        self.is_stopping = False

        async with self._open_process_and_stream() as self.process:
            try:
                await self.process.wait()
            except anyio.get_cancelled_exc_class():
                with anyio.CancelScope(shield=True):
                    await self.stop()
                    pass
            else:
                code = await self.stop()
                raise SystemExit(code)

    async def stop(self) -> None:
        if not self.process or self.is_stopping:
            return

        self.is_stopping = True

        if self.process.returncode is None:
            self.process.terminate()

        await self.process.wait()

        # Otherwise RuntimeError('Event loop is closed') might be called
        self.process._process._transport.close()  # pyright: ignore


def _get_jacktrip(
    cmd: list[str], jack_server_name: str, log: logging.Logger
) -> StreamingProcess:
    cmd_ = cmd.copy()
    cmd_.insert(0, "jacktrip")
    env = {"JACK_DEFAULT_SERVER": jack_server_name}
    return StreamingProcess(cmd=cmd_, env=env, log=log)


def _build_server_cmd(*, port: int) -> list[str]:
    return [
        "--jacktripserver",
        "--bindport",
        str(port),
        "--nojackportsconnect",
        "--udprt",
    ]


def get_server(
    *, jack_server_name: str, port: int, log: logging.Logger
) -> StreamingProcess:
    cmd = _build_server_cmd(port=port)
    return _get_jacktrip(cmd, jack_server_name, log)


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
    log: logging.Logger,
) -> StreamingProcess:
    cmd = _build_client_cmd(
        server_host=server_host,
        server_port=server_port,
        receive_channels=receive_channels,
        send_channels=send_channels,
        remote_name=remote_name,
    )
    return _get_jacktrip(cmd, jack_server_name, log)

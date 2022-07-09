from typing import Callable

import anyio
import jack

from jackson.logging import MessageFilter, get_logger


class JackClientFilter(MessageFilter):
    messages = {
        "CheckRes error",
        "JackSocketClientChannel read fail",
        "Cannot read socket fd = ",
    }


log = get_logger(__name__, "JackClient")
log.addFilter(JackClientFilter())


def get_jack_client(server_name: str) -> jack.Client:
    block_jack_client_streams()
    client = jack.Client(name="Helper", no_start_server=True, servername=server_name)
    _set_jack_client_streams()
    return client


def _set_jack_client_streams() -> None:
    jack.set_info_function(log.info)
    jack.set_error_function(log.error)


def _silent_stream_handler(_: str) -> None:
    pass


def block_jack_client_streams() -> None:
    jack.set_info_function(_silent_stream_handler)
    jack.set_error_function(_silent_stream_handler)


def _connect_ports_and_log(client: jack.Client, source: str, destination: str) -> None:
    port = client.get_port_by_name(source)
    if any(p.name == destination for p in client.get_all_connections(port)):
        return
    client.connect(source, destination)
    log.info(
        f"Connected ports: [bold green]{source}[/bold green] ->"
        + f" [bold green]{destination}[/bold green]"
    )


async def _retry(
    func: Callable[[], None], exc_type: type[Exception], times: int
) -> None:
    exc = None

    for _ in range(times):
        try:
            return func()
        except exc_type as current_exc:
            exc = current_exc
            await anyio.sleep(0.1)

    assert exc
    raise exc


async def retry_connect_ports(
    client: jack.Client, source: str, destination: str
) -> None:
    """Try to connect ports 10 times or fail.

    Several issues could come up while connecting JACK ports:
    - "Cannot connect ports owned by inactive clients: "MyName" is not active"
      This means that JackTrip client is not initialized yet.
    - "Unknown destination port in attempted (dis)connection src_name  dst_name"
      I. e. port is not initialized yet.
    """
    func = lambda: _connect_ports_and_log(
        client, source=source, destination=destination
    )
    await _retry(func=func, exc_type=jack.JackError, times=10)

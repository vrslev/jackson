from jackson.services.util import Program
from jackson.settings import UrlWithPort


async def start_server(*, port: int, udprt: bool = True):
    cmd: list[str] = [
        "jacktrip",
        "--jacktripserver",
        "--bindport",
        str(port),
        "--nojackportsconnect",
    ]

    if udprt:
        cmd.append("--udprt")

    await Program(cmd).run_forever()


async def start_client(
    *,
    url: UrlWithPort,
    receive_channels: int,
    send_channels: int,
    client_name: str = "JackTrip",
    remote_name: str,
    udprt: bool = True,
):
    """
    Args:

    client_name — The name of JACK Client
    remote_name — The name by which a server identifies a client
    """
    cmd: list[str] = [
        "jacktrip",
        "--pingtoserver",
        url.host,
        "--receivechannels",
        str(receive_channels),
        "--sendchannels",
        str(send_channels),
        "--peerport",
        url.port,
        "--clientname",
        client_name,
        "--remotename",
        remote_name,
        "--nojackportsconnect",
    ]

    if udprt:
        cmd.append("--udprt")

    await Program(cmd).run_forever()

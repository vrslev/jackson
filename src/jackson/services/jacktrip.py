from ipaddress import IPv4Address

from jackson.services.util import Program


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
    host: IPv4Address,
    port: int,
    receive_channels: int,
    send_channels: int,
    remote_name: str,
    client_name: str = "JackTrip",
    udprt: bool = True,
):
    """
    Args:

    remote_name — The name by which a server identifies a client
    client_name — The name of JACK Client
    """
    cmd: list[str] = [
        "jacktrip",
        "--pingtoserver",
        str(host),
        "--receivechannels",
        str(receive_channels),
        "--sendchannels",
        str(send_channels),
        "--peerport",
        str(port),
        "--clientname",
        client_name,
        "--remotename",
        remote_name,
        "--nojackportsconnect",
    ]

    if udprt:
        cmd.append("--udprt")

    await Program(cmd).run_forever()

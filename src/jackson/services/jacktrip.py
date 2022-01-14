from ipaddress import IPv4Address

from jackson.services.util import Program


async def start_server(
    *, local_address: IPv4Address, queue: str = "auto", udprt: bool = True
):
    cmd: list[str] = [
        "jacktrip",
        "--jacktripserver",
        "--queue",
        queue,
        "--localaddress",
        str(local_address),
        "--nojackportsconnect",
    ]

    if udprt:
        cmd.append("--udprt")

    await Program(cmd).run_forever()


async def start_client(
    *,
    server_address: IPv4Address,
    receive_channels: int,
    send_channels: int,
    queue: str = "auto",
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
        str(server_address),
        "--receivechannels",
        str(receive_channels),
        "--sendchannels",
        str(send_channels),
        "--queue",
        queue,
        "--clientname",
        client_name,
        "--remotename",
        remote_name,
        "--nojackportsconnect",
    ]

    if udprt:
        cmd.append("--udprt")

    await Program(cmd).run_forever()

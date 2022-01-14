from ipaddress import IPv4Address

from jackson.services.util import Program


async def start_server(
    *,
    server_port: int,
    queue: str = "auto",
    no_jack_ports_connect: bool = True,
    udprt: bool = True,
    local_address: IPv4Address,
):
    cmd: list[str] = [
        "jacktrip",
        "--jacktripserver",
        "--queue",
        queue,
        "--bindport",
        str(server_port),
        "--localaddress",
        str(local_address),
    ]

    if no_jack_ports_connect:
        cmd.append("--nojackportsconnect")

    if udprt:
        cmd.append("--udprt")

    await Program(cmd).run_forever()


async def start_client(
    *,
    server_address: IPv4Address,
    server_port: int,
    client_port: int,
    receive_channels: int,
    send_channels: int,
    queue: str = "auto",
    client_name: str = "JackTrip",
    remote_name: str,
    no_jack_ports_connect: bool = True,
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
        "--bindport",
        str(client_port),
        "--peerport",
        str(server_port),
        "--clientname",
        client_name,
        "--remotename",
        remote_name,
    ]

    if no_jack_ports_connect:
        cmd.append("--nojackportsconnect")

    if udprt:
        cmd.append("--udprt")

    await Program(cmd).run_forever()

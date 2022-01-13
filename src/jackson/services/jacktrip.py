from ipaddress import IPv4Address

from jackson.utils import Program


async def start_server(
    *,
    server_port: int,
    queue: str = "auto",
    client_name: str = "JackTrip",  # TODO: Check if this is required
    remote_name: str,  # TODO: Check if this is required too
    no_jack_ports_connect: bool = True,
    udprt: bool = True,
):
    """Client name - name that is appears in Jack Server"""

    cmd: list[str] = [
        "jacktrip",
        "--jacktripserver",
        "--queue",
        queue,
        "--bindport",
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

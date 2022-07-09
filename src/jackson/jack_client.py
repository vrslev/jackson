import jack

from jackson.logging import jack_client_log as log


def ports_already_connected(client: jack.Client, source: str, destination: str) -> bool:
    source_port = client.get_port_by_name(source)
    connections = client.get_all_connections(source_port)
    return any(p.name == destination for p in connections)


def connect_ports_safe(client: jack.Client, source: str, destination: str) -> None:
    if ports_already_connected(client, source, destination):
        return

    client.connect(source, destination)
    log.info(
        f"Connected ports: [bold green]{source}[/bold green] ->"
        + f" [bold green]{destination}[/bold green]"
    )

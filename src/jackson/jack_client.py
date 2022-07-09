import jack

from jackson.logging import jack_client_log as log


def connect_ports_and_log(client: jack.Client, source: str, destination: str) -> None:
    client.connect(source, destination)
    log.info(
        f"Connected ports: [bold green]{source}[/bold green] ->"
        + f" [bold green]{destination}[/bold green]"
    )

import jack
from fastapi import Depends, FastAPI, status

from jackson.services.port_connector.models import (
    ConnectResponse,
    InitResponse,
    PlaybackPortAlreadyHasConnectionsData,
    PortNotFound,
    PortType,
    StructuredHTTPException,
)

app = FastAPI()


async def get_jack_client():
    return jack.Client("messaging-server")


@app.get("/init", response_model=InitResponse)
def init(client: jack.Client = Depends(get_jack_client)):
    inputs = client.get_ports("system:.*", is_input=True)
    outputs = client.get_ports("system:.*", is_output=True)

    return InitResponse(inputs=len(inputs), outputs=len(outputs))


def check_client_name_not_system(client_name: str):
    if client_name == "system":
        raise StructuredHTTPException(
            status.HTTP_400_BAD_REQUEST, 'Client name can\'t be "system"'
        )


def get_port_or_raise(client: jack.Client, type: PortType, name: str):
    try:
        return client.get_port_by_name(name)
    except jack.JackError:
        raise StructuredHTTPException(
            404, message="Port not found", data=PortNotFound(type=type, name=name)
        )


@app.put("/connect/send")
def connect_send(
    *,
    jack_client: jack.Client = Depends(get_jack_client),
    client_name: str,
    client_port_number: int,
    server_port_number: int,
):
    # TO mixer
    check_client_name_not_system(client_name)
    source_name = f"{client_name}:receive_{client_port_number}"
    source = get_port_or_raise(client=jack_client, type="source", name=source_name)

    destination_name = f"system:playback_{server_port_number}"
    destination = get_port_or_raise(
        client=jack_client, type="destination", name=destination_name
    )

    if connections := jack_client.get_all_connections(destination):
        raise StructuredHTTPException(
            status.HTTP_409_CONFLICT,
            message="Port already has connections",
            data=PlaybackPortAlreadyHasConnectionsData(
                port_name=destination_name,
                connection_names=[p.name for p in connections],
            ),
        )

    jack_client.connect(source, destination)
    return ConnectResponse(source=source_name, destination=destination_name)


@app.patch("/connect/receive")
def connect_receive(
    *,
    jack_client: jack.Client = Depends(get_jack_client),
    client_name: str,
    client_port_number: int,
    server_port_number: int,
):
    # FROM mixer
    check_client_name_not_system(client_name)
    source_name = f"system:capture_{server_port_number}"
    source = get_port_or_raise(client=jack_client, type="source", name=source_name)

    destination_name = f"{client_name}:playback_{client_port_number}"
    destination = get_port_or_raise(
        client=jack_client, type="destination", name=destination_name
    )

    jack_client.connect(source, destination)
    return ConnectResponse(source=source_name, destination=destination_name)


if __name__ == "__main__":
    import uvicorn  # type: ignore

    uvicorn.run(app)  # type: ignore

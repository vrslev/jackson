from typing import Literal

import jack
from fastapi import Depends, FastAPI, status

from jackson.services.messaging.models import (
    ConnectResponse,
    InitResponse,
    PortAlreadyHasConnectionsData,
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


ServerShould = Literal["send", "receive"]


def resolve_ports_to_connect(
    *,
    server_should: ServerShould,
    client_name: str,
    server_port_number: int,
    client_port_number: int,
):
    if server_should == "send":
        source = f"system:capture_{server_port_number}"
        destination = f"{client_name}:send_{client_port_number}"
    else:
        source = f"{client_name}:receive_{client_port_number}"
        destination = f"system:playback_{server_port_number}"

    return source, destination


def get_port_or_raise(client: jack.Client, type: PortType, name: str):
    try:
        return client.get_port_by_name(name)
    except jack.JackError:
        raise PortNotFound(type=type, name=name).exc()


def validate_port_has_no_connections(
    client: jack.Client, port: jack.Port, type: PortType, name: str
):
    connections = client.get_all_connections(port)
    if not connections:
        return

    raise PortAlreadyHasConnectionsData(
        type=type, name=name, connection_names=[p.name for p in connections]
    ).exc()


@app.put("/connect", response_model=ConnectResponse)
def connect(
    *,
    client: jack.Client = Depends(get_jack_client),
    client_name: str,
    server_should: ServerShould,
    server_port_number: int,
    client_port_number: int,
):
    check_client_name_not_system(client_name)
    source_name, destination_name = resolve_ports_to_connect(
        server_should=server_should,
        client_name=client_name,
        server_port_number=server_port_number,
        client_port_number=client_port_number,
    )

    source = get_port_or_raise(client=client, type="source", name=source_name)
    if server_should == "send":
        # TODO: What is multiple clients connected....
        validate_port_has_no_connections(
            client=client, port=source, type="source", name=source_name
        )

    destination = get_port_or_raise(
        client=client, type="destination", name=destination_name
    )
    if server_should == "receive":
        validate_port_has_no_connections(
            client=client, port=destination, type="destination", name=destination_name
        )

    client.connect(source_name, destination_name)
    return ConnectResponse(source=source_name, destination=destination_name)


if __name__ == "__main__":
    import uvicorn  # type: ignore

    uvicorn.run(app)  # type: ignore

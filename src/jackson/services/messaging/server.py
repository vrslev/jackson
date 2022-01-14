import jack
from fastapi import FastAPI

from jackson.services.messaging.models import InitResponse

app = FastAPI()


@app.get("/init", response_model=InitResponse)
def init():
    client = jack.Client("http-server")
    inputs = client.get_ports("system:.*", is_input=True)
    outputs = client.get_ports("system:.*", is_output=True)
    return InitResponse(inputs=len(inputs), outputs=len(outputs))


@app.get("/connect")
def connect(source: str, destination: str):
    s = source.startswith("system")
    d = destination.startswith("system")
    assert s or d
    assert not (s and d)

    from_system = s

    client = jack.Client("http-server")

    if from_system:
        client.connect(source, destination)
    else:
        port = client.get_port_by_name(destination)
        if client.get_all_connections(port):
            raise PermissionError("Somebody already sends information to this port.")

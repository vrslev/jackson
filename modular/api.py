from typing import Any, cast

import jack
import uvicorn

from jackson.api_server import get_app
from jackson.connector_server import ServerPortConnector

jack_client = jack.Client("Helper", no_start_server=True, servername="JacksonServer")
connector = ServerPortConnector(jack_client)
app = get_app(connector)
uvicorn.run(cast(Any, app), host="0.0.0.0")

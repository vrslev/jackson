from typing import Literal

from jackson.services.jack_server._server import Driver as Driver
from jackson.services.jack_server._server import Parameter as Parameter
from jackson.services.jack_server._server import Server as Server


async def start(*, driver: str, device: str, rate: Literal[44100, 48000]):
    server = Server(driver=driver, device=device, rate=rate)
    try:
        server.start()
    finally:
        server.stop()

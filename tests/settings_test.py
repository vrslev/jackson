from ipaddress import IPv4Address

from jackson.port_connection import build_connection_map
from jackson.settings import (
    ClientSettings,
    _ClientAudio,
    _ClientPorts,
    _ClientServer,
    _FileClientSettings,
)


def test_client_server_settings_api_url():
    s = _ClientServer(jacktrip_port=0, api_port=8000, host=IPv4Address("127.0.0.1"))
    assert s.api_url == "http://127.0.0.1:8000"


def test_load_client_settings():
    f = _FileClientSettings(
        name="Lev",
        audio=_ClientAudio(driver="dummy", device=None),
        server=_ClientServer(
            jacktrip_port=0, api_port=0, host=IPv4Address("127.0.0.1")
        ),
        ports=_ClientPorts(receive={1: 11, 2: 12}, send={3: 13, 4: 14}),
    )

    settings = ClientSettings.load(f.dict())
    assert settings.name == f.name
    assert settings.audio == f.audio
    assert settings.server == f.server
    assert settings.connection_map == build_connection_map(
        client_name=settings.name, receive=f.ports.receive, send=f.ports.send
    )

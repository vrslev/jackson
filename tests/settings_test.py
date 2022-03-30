from ipaddress import IPv4Address

from jackson.port_connection import build_connection_map
from jackson.settings import (
    _ClientAudio,
    _ClientPorts,
    _ClientServer,
    _FileClientSettings,
    load_client_settings,
)


def test_load_client_settings():
    fsettings = _FileClientSettings(
        name="Lev",
        audio=_ClientAudio(driver="dummy", device=None),
        server=_ClientServer(
            jacktrip_port=0, api_port=0, host=IPv4Address("127.0.0.1")
        ),
        ports=_ClientPorts(receive={1: 11, 2: 12}, send={3: 13, 4: 14}),
    )

    settings = load_client_settings(fsettings.dict())
    assert settings.name == fsettings.name
    assert settings.audio == fsettings.audio
    assert settings.server == fsettings.server
    assert settings.connection_map == build_connection_map(
        client_name=settings.name,
        receive=fsettings.ports.receive,
        send=fsettings.ports.send,
    )

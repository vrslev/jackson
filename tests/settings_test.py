from ipaddress import IPv4Address

import pytest

from jackson.settings import ClientPorts, ClientSettings, _ClientAudio, _ClientServer


@pytest.fixture
def client_settings():
    return ClientSettings(
        name="Me",
        audio=_ClientAudio(driver="somedriver", device=None),
        server=_ClientServer(
            jacktrip_port=4464, api_port=8000, host=IPv4Address("127.0.0.1")
        ),
        ports=ClientPorts(receive={}, send={}),
        start_jack=False,
    )


@pytest.mark.parametrize(
    ("start_jack", "name"),
    ((True, "JacksonClient"), (False, "JacksonServer")),
)
def test_client_setttings_start_jack(
    client_settings: ClientSettings, start_jack: bool, name: str
):
    client_settings.start_jack = start_jack
    client_settings.audio.jack_server_name = "JacksonClient"
    settings = ClientSettings.parse_obj(client_settings)
    assert settings.audio.jack_server_name == name

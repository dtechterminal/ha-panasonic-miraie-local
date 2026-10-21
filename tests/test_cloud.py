import pytest
from custom_components.ac_mitm.cloud import Bootstrap, InvalidAuth


class Response:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self, **kwargs):
        return self.data


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


@pytest.mark.asyncio
async def test_bootstrap_falls_back_to_home_key_and_discards_account_secrets():
    session = Session(
        [
            Response({"accessToken": "fixture-token"}),
            Response(
                [
                    {
                        "udpControlKey": "01" * 32,
                        "udpControlIV": "02" * 16,
                        "spaces": [
                            {
                                "devices": [
                                    {
                                        "deviceId": "fixture-ac",
                                        "category": "AC",
                                        "deviceName": "Study",
                                    }
                                ]
                            }
                        ],
                    }
                ]
            ),
            Response(
                [
                    {
                        "deviceId": "fixture-ac",
                        "macAddress": "00:00:00:00:00:01",
                        "modelNumber": "fixture-model",
                        "manualCode": "do-not-store",
                    }
                ]
            ),
        ]
    )
    bootstrap = Bootstrap(session)
    assert await bootstrap.login("fixture@example.invalid", "fixture-password") == {
        "fixture-ac": "Study"
    }
    data = await bootstrap.credentials("fixture-ac")
    assert data["key"] == "01" * 32 and data["iv"] == "02" * 16
    assert not any(key in data for key in ["username", "password", "accessToken", "manualCode"])
    assert bootstrap.token is None and bootstrap.devices == {}


@pytest.mark.asyncio
async def test_auth_failure_never_includes_server_secret_response():
    bootstrap = Bootstrap(Session([Response({"password": "sensitive"}, 401)]))
    with pytest.raises(InvalidAuth) as caught:
        await bootstrap.login("fixture@example.invalid", "fixture-password")
    assert "sensitive" not in str(caught.value)

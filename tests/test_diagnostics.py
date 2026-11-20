import asyncio
import types

import ha_stubs

from custom_components.ac_mitm.diagnostics import (
    REDACT,
    async_get_config_entry_diagnostics,
    redact,
)


def test_redact_hides_secrets_at_any_depth_and_keeps_the_status():
    status = {
        "ps": "on",
        "rmtmp": "25.0",
        "key": "aa" * 32,
        "nested": {"iv": "bb" * 16, "mac": "AA:BB", "acvs": 0},
        "list": [{"token": "t"}, {"cnv": 40}],
    }
    out = redact(status)
    assert out["ps"] == "on" and out["rmtmp"] == "25.0"
    assert out["key"] == out["nested"]["iv"] == out["nested"]["mac"] == "**REDACTED**"
    assert out["nested"]["acvs"] == 0
    assert out["list"] == [{"token": "**REDACTED**"}, {"cnv": 40}]
    assert status["key"] == "aa" * 32, "the original is untouched"


def test_redact_covers_what_an_entry_stores():
    for key in ("key", "iv", "device_id", "mac", "host", "password", "token"):
        assert key in REDACT


def test_diagnostics_show_the_raw_status_without_secrets():
    coordinator = ha_stubs.FakeCoordinator({"rmtmp": "128.25", "acec": "on", "mac": "AA:BB"})
    hass = types.SimpleNamespace(data={"ac_mitm": {"entry": {"coordinator": coordinator}}})
    entry = types.SimpleNamespace(
        entry_id="entry", data={"device_id": "x", "key": "aa", "iv": "bb", "port": 5001}
    )
    out = asyncio.run(async_get_config_entry_diagnostics(hass, entry))
    assert out["status"]["rmtmp"] == "128.25" and out["status"]["acec"] == "on"
    assert out["status"]["mac"] == "**REDACTED**"
    assert out["entry"] == {
        "device_id": "**REDACTED**",
        "key": "**REDACTED**",
        "iv": "**REDACTED**",
        "port": 5001,
    }
    assert out["last_update_success"] is True

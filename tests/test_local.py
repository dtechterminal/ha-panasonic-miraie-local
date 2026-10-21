import json

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.ac_mitm.api import AcMitmApiError
from custom_components.ac_mitm.native import NativeApi, verify_local
from custom_components.ac_mitm.protocol import (
    Protocol,
    ProtocolError,
    command_settings,
    matches,
    tlv,
)

CONFIG = {"device_id": "fixture-ac", "key": "01" * 32, "iv": "02" * 16}


def reply(state, device_id="fixture-ac"):
    raw = json.dumps(state).encode()
    raw += b"\0" * (-len(raw) % 16)
    enc = Cipher(
        algorithms.AES(bytes.fromhex(CONFIG["key"])), modes.CBC(bytes.fromhex(CONFIG["iv"]))
    ).encryptor()
    return tlv(0, device_id.encode()) + tlv(2, enc.update(raw) + enc.finalize())


def request_settings(wire):
    size = int.from_bytes(wire[1:3], "big")
    assert wire[0] == 0 and wire[3 : 3 + size] == b"fixture-ac"
    offset = 3 + size
    assert wire[offset] == 1
    raw = wire[offset + 3 :]
    dec = Cipher(
        algorithms.AES(bytes.fromhex(CONFIG["key"])), modes.CBC(bytes.fromhex(CONFIG["iv"]))
    ).decryptor()
    return json.loads((dec.update(raw) + dec.finalize()).rstrip(b"\0"))


def test_request_framing_and_zero_padding():
    data = request_settings(Protocol(**CONFIG).encode({"actmp": "25"}))
    assert data == {"ki": 1, "cnt": "an", "sid": "1", "actmp": "25"}


@pytest.mark.parametrize(
    "wire",
    [
        b"\0",
        tlv(0, b"fixture-ac") + tlv(2, b"short"),
        tlv(0, b"fixture-ac") + tlv(0, b"fixture-ac"),
    ],
)
def test_rejects_malformed_frames(wire):
    with pytest.raises(ProtocolError):
        Protocol(**CONFIG).decode(wire)


def test_rejects_other_device_even_with_same_home_key():
    with pytest.raises(ProtocolError):
        Protocol(**CONFIG).decode(reply({"ps": "off", "actmp": "24"}, "another-ac"))


def test_rejects_incomplete_status():
    with pytest.raises(ProtocolError):
        Protocol(**CONFIG).decode(reply({"ps": "off"}))


def test_numeric_fields_and_ack_comparison():
    settings = command_settings("acvs", "0", {"achs": "3", "cnv": "40"})
    assert settings == {"acvs": 0, "achs": 3, "cnv": 40}
    assert all(isinstance(v, int) for v in settings.values())
    assert matches({"actmp": "24.0", "cnv": "40"}, {"actmp": 24, "cnv": 40})
    assert not matches({"actmp": "24"}, {"actmp": 25})


@pytest.mark.parametrize(
    "action,value,extra",
    [
        ("topic", "x", None),
        ("acvs", "0.5", None),
        ("achs", 6, None),
        ("cnv", 42, None),
        ("ps", "toggle", None),
        ("actmp", 35, None),
        ("ps", "on", {"ps": "off"}),
    ],
)
def test_invalid_commands(action, value, extra):
    with pytest.raises((ProtocolError, ValueError)):
        command_settings(action, value, extra)


class Device:
    def __init__(self, intermediate=False, drop_first=False, reject_change=False):
        self.state = {"ps": "off", "actmp": "24", "acfs": "auto"}
        self.intermediate = intermediate
        self.drop_first = drop_first
        self.reject_change = reject_change
        self.requests = []

    async def exchange(self, wire):
        settings = request_settings(wire)
        self.requests.append(settings)
        if self.drop_first:
            self.drop_first = False
            return []
        old = dict(self.state)
        for key, value in settings.items():
            if key not in ["ki", "cnt", "sid"]:
                if not (self.reject_change and key == "actmp" and float(value) != 24):
                    self.state[key] = value
        if self.intermediate and any(k not in ["ki", "cnt", "sid"] for k in settings):
            return [reply(old)]
        return [reply(self.state)]


@pytest.mark.asyncio
async def test_dropped_datagram_retries_and_intermediate_ack_settles():
    device = Device(intermediate=True, drop_first=True)
    api = NativeApi(CONFIG, device)
    await api.async_command("actmp", "25", extra={"acfs": "low"})
    assert device.state["actmp"] == "25" and device.state["acfs"] == "low"
    assert len(device.requests) >= 3


@pytest.mark.asyncio
async def test_setup_verifies_real_change_and_restores_power_and_temperature():
    device = Device()
    api = NativeApi(CONFIG, device)
    result = await verify_local(api)
    temperatures = [r["actmp"] for r in device.requests if "actmp" in r]
    assert temperatures == ["25.0", "24.0"]
    assert result["ac"]["ps"] == "off"
    assert float(result["ac"]["actmp"]) == 24
    assert not any("ps" in r for r in device.requests)


@pytest.mark.asyncio
async def test_setup_does_not_report_success_for_ignored_commands_and_restores():
    device = Device(reject_change=True)
    api = NativeApi(CONFIG, device)
    with pytest.raises(AcMitmApiError):
        await verify_local(api)
    assert any(r.get("actmp") == "24.0" for r in device.requests)
    assert float(device.state["actmp"]) == 24

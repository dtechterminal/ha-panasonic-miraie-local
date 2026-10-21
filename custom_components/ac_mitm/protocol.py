"""Panasonic native UDP framing, independent of Home Assistant."""

from __future__ import annotations

import json

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class ProtocolError(Exception):
    """A packet or command is invalid."""


def tlv(kind: int, value: bytes) -> bytes:
    return bytes([kind]) + len(value).to_bytes(2, "big") + value


class Protocol:
    def __init__(self, device_id: str, key: str, iv: str):
        self.device_id = device_id.encode("ascii")
        self.key = bytes.fromhex(key)
        self.iv = bytes.fromhex(iv)
        if len(self.key) != 32 or len(self.iv) != 16 or not self.device_id:
            raise ProtocolError("Invalid device identifier or AES key/IV length")

    def encode(self, settings: dict | None = None) -> bytes:
        raw = json.dumps(
            {"ki": 1, "cnt": "an", "sid": "1", **(settings or {})}, separators=(",", ":")
        ).encode()
        raw += b"\0" * (-len(raw) % 16)
        enc = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).encryptor()
        return tlv(0, self.device_id) + tlv(1, enc.update(raw) + enc.finalize())

    def decrypt(self, wire: bytes) -> bytes:
        fields = {}
        offset = 0
        while offset < len(wire):
            if offset + 3 > len(wire):
                raise ProtocolError("Truncated TLV header")
            kind, size = wire[offset], int.from_bytes(wire[offset + 1 : offset + 3], "big")
            offset += 3
            if kind in fields or offset + size > len(wire):
                raise ProtocolError("Invalid TLV field")
            fields[kind] = wire[offset : offset + size]
            offset += size
        if fields.get(0) != self.device_id or not fields.get(2) or len(fields[2]) % 16:
            raise ProtocolError("Unexpected device or ciphertext")
        dec = Cipher(algorithms.AES(self.key), modes.CBC(self.iv)).decryptor()
        return (dec.update(fields[2]) + dec.finalize()).rstrip(b"\0")

    def decode(self, wire: bytes) -> dict:
        try:
            result = json.loads(self.decrypt(wire))
        except (ValueError, UnicodeError) as err:
            raise ProtocolError("Invalid decrypted status") from err
        if not isinstance(result, dict) or "ps" not in result or "actmp" not in result:
            raise ProtocolError("Incomplete AC status")
        return result


def command_settings(action: str, value, extra: dict | None = None) -> dict:
    allowed = {"ps", "acmd", "actmp", "acfs", "acvs", "achs", "acpm", "acem", "acec", "acdc", "cnv"}
    if (
        action not in allowed
        or not isinstance(extra or {}, dict)
        or set(extra or {}) - allowed
        or action in (extra or {})
    ):
        raise ProtocolError("Unsupported command")
    settings = {action: value, **(extra or {})}
    for key in ("acvs", "achs", "cnv"):
        if key in settings:
            number = float(settings[key])
            if not number.is_integer():
                raise ProtocolError("Position/capacity must be an integer")
            settings[key] = int(number)
            if key != "cnv" and not 0 <= settings[key] <= 5:
                raise ProtocolError("Swing position must be 0–5")
    if "cnv" in settings and settings["cnv"] not in [0, 40, 55, 70, 80, 90, 100, 110]:
        raise ProtocolError("Unsupported capacity")
    if "ps" in settings and settings["ps"] not in ["on", "off"]:
        raise ProtocolError("Invalid power state")
    if "actmp" in settings and not 16 <= float(settings["actmp"]) <= 30:
        raise ProtocolError("Temperature must be 16–30°C")
    return settings


def matches(state: dict, settings: dict) -> bool:
    for key, value in settings.items():
        if key not in state:
            return False
        try:
            if float(state[key]) == float(value):
                continue
        except (ValueError, TypeError):
            pass
        if str(state[key]).lower() != str(value).lower():
            return False
    return True

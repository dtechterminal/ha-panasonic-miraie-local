"""Native local-only AC API. This module never contacts Panasonic servers."""

from __future__ import annotations

import asyncio
import time

from .api import AcMitmApiError
from .protocol import Protocol, ProtocolError, command_settings, matches
from .transport import UdpTransport


class NativeApi:
    def __init__(self, config: dict, transport: UdpTransport):
        self.config = config
        self.transport = transport
        self.protocol = Protocol(config["device_id"], config["key"], config["iv"])
        self.lock = asyncio.Lock()
        self.state = {}

    async def _exchange(self, settings: dict | None = None) -> dict:
        for attempt in range(3):
            try:
                packets = await self.transport.exchange(
                    self.protocol.encode(settings), expected=settings
                )
            except (OSError, TimeoutError, ValueError) as err:
                raise AcMitmApiError(
                    "Local UDP transport failed; check device IP and HA network access"
                ) from err
            states = []
            for wire in packets:
                try:
                    states.append(self.protocol.decode(wire))
                except (ProtocolError, ValueError):
                    continue
            if states:
                self.state = states[-1]
                return self.state
            if attempt < 2:
                await asyncio.sleep(0.25)
        raise AcMitmApiError(
            "No valid local status reply; check IP, UDP 5001/5002, VLAN and local key"
        )

    def _snapshot(self) -> dict:
        return {
            "ac": {**self.state, "_transport": "local_udp", "onlineStatus": "true"},
            "local": {
                "enabled": True,
                "available": True,
                "transport": "local_udp",
                "receiver": getattr(self.transport, "last_receiver", None),
                "model": self.config.get("model"),
                "firmware": self.config.get("firmware"),
                "last_update": time.time(),
            },
            "sessions": [],
        }

    async def async_get_state(self) -> dict:
        async with self.lock:
            await self._exchange()
            return self._snapshot()

    async def async_command(self, action, value, topic=None, extra=None) -> dict:
        try:
            settings = command_settings(action, value, extra)
        except (ProtocolError, ValueError, TypeError) as err:
            raise AcMitmApiError("Invalid AC command") from err
        async with self.lock:
            state = await self._exchange(settings)
            deadline = asyncio.get_running_loop().time() + 3
            while not matches(state, settings):
                if asyncio.get_running_loop().time() >= deadline:
                    raise AcMitmApiError(
                        "AC acknowledged the packet but did not apply all requested settings"
                    )
                await asyncio.sleep(0.15)
                state = await self._exchange()
            return {"ok": True, "transport": "local_udp", **self._snapshot()}


async def verify_local(api: NativeApi) -> dict:
    """Prove a local setting change, then restore it without changing power."""
    snapshot = await api.async_get_state()
    temperature = float(snapshot["ac"]["actmp"])
    target = temperature + 1 if temperature <= 29 else temperature - 1
    try:
        await api.async_command("actmp", str(target))
        changed = await api.async_get_state()
        if float(changed["ac"]["actmp"]) != target:
            raise AcMitmApiError("Local setting change was not confirmed")
    finally:
        await api.async_command("actmp", str(temperature))
    snapshot = await api.async_get_state()
    if float(snapshot["ac"]["actmp"]) != float(temperature):
        raise AcMitmApiError("Local verification failed")
    return snapshot

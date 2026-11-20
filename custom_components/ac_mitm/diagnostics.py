"""Diagnostics: the AC's last status exactly as it reported it, with secrets removed."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Never shown: the local key and IV, identifiers, and account details.
REDACT = frozenset(
    {
        "key",
        "iv",
        "device_id",
        "deviceId",
        "mac",
        "host",
        "password",
        "token",
        "access_token",
        "refresh_token",
        "username",
        "email",
        "mobile",
        "user_id",
        "userId",
        "home_id",
        "homeId",
        "topic",
    }
)


def redact(data: Any, keys: frozenset[str] = REDACT) -> Any:
    """A copy of data with every value under a sensitive key replaced, at any depth."""
    if isinstance(data, dict):
        return {k: "**REDACTED**" if k in keys else redact(v, keys) for k, v in data.items()}
    if isinstance(data, list):
        return [redact(v, keys) for v in data]
    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    data = coordinator.data or {}
    return {
        "entry": redact(dict(entry.data)),
        "status": redact(dict(data.get("ac") or {})),
        "local": redact(dict(data.get("local") or {})),
        "last_update_success": coordinator.last_update_success,
    }

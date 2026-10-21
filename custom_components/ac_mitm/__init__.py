"""Native local control for Panasonic India MirAIe air conditioners."""

from __future__ import annotations

import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AcMitmApi
from .const import DOMAIN
from .coordinator import AcMitmCoordinator
from .native import NativeApi
from .transport import UdpTransport

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up native UDP control or a legacy local bridge."""
    session = async_get_clientsession(hass)
    shared = hass.data.setdefault(DOMAIN, {})
    if entry.data.get("device_id"):
        lock = shared.setdefault("_udp_lock", asyncio.Lock())
        api = NativeApi(dict(entry.data), UdpTransport(dict(entry.data), lock))
    else:
        api = AcMitmApi.from_entry(entry, session)
    coordinator = AcMitmCoordinator(hass, api, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"api": api, "coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, ["climate", "switch", "select"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, ["climate", "switch", "select"]
    )
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded

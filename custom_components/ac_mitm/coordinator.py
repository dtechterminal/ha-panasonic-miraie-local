"""Shared polling for the Panasonic native local control bridge."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AcMitmApiError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class AcMitmCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api, entry):
        super().__init__(
            hass,
            _LOGGER,
            name="Panasonic AC Local",
            config_entry=entry,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self.entry_id = entry.entry_id

    async def _async_update_data(self):
        try:
            return await self.api.async_get_state()
        except AcMitmApiError as error:
            raise UpdateFailed(str(error)) from error

    async def async_command(self, action, value, **kwargs):
        """Immediately publish confirmed readback instead of waiting for poll debounce."""
        result = await self.api.async_command(action, value, **kwargs)
        if isinstance(result, dict) and result.get("ac"):
            self.async_set_updated_data({**(self.data or {}), **result})
        else:
            await self.async_request_refresh()
        return result

    @property
    def device_info(self):
        local = (self.data or {}).get("local") or {}
        return {
            "identifiers": {(DOMAIN, self.entry_id)},
            "name": "Panasonic AC (Local)",
            "manufacturer": "Panasonic",
            "model": local.get("model") or "MirAIe AC",
            "sw_version": local.get("firmware"),
        }

    @property
    def device_available(self):
        data = self.data or {}
        local = data.get("local") or {}
        return (
            self.last_update_success
            and bool(data.get("ac"))
            and (not local.get("enabled") or local.get("available", False))
        )

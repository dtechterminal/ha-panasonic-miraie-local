"""Native local controls for the AC's optional operating features."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AcMitmApiError
from .const import DOMAIN, KEY_COIL_CLEANING, KEY_DISPLAY, KEY_ECONOMY, KEY_POWERFUL


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AcLocalSwitch(data["coordinator"], data["api"], entry.entry_id, key, name)
            for key, name in [
                (KEY_DISPLAY, "Display"),
                (KEY_POWERFUL, "Powerful"),
                (KEY_ECONOMY, "Economy"),
                (KEY_COIL_CLEANING, "Coil cleaning"),
            ]
        ]
    )


class AcLocalSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, api, entry_id, key, name):
        super().__init__(coordinator)
        self.api = api
        self.key = key
        self._attr_name = name
        self._attr_unique_id = entry_id + "_" + key

    @property
    def device_info(self):
        return self.coordinator.device_info

    @property
    def available(self):
        return self.coordinator.device_available and self.key in (self.coordinator.data or {}).get(
            "ac", {}
        )

    @property
    def is_on(self):
        value = ((self.coordinator.data or {}).get("ac") or {}).get(self.key)
        return str(value).lower() in ("on", "true", "1")

    async def _set(self, value):
        try:
            extra = None
            exclusive = [KEY_POWERFUL, KEY_ECONOMY, KEY_COIL_CLEANING]
            if value == "on" and self.key in exclusive:
                extra = {key: "off" for key in exclusive if key != self.key}
                extra["cnv"] = 0
            await self.coordinator.async_command(self.key, value, extra=extra)
        except AcMitmApiError as error:
            raise HomeAssistantError(str(error)) from error

    async def async_turn_on(self, **kwargs):
        await self._set("on")

    async def async_turn_off(self, **kwargs):
        await self._set("off")

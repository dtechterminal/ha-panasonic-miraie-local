"""Native local convertible capacity limits advertised by this AC model."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AcMitmApiError
from .const import DOMAIN, KEY_CAPACITY, KEY_ECONOMY, KEY_POWERFUL

OPTIONS = {
    "Auto": 0,
    "40%": 40,
    "55%": 55,
    "70%": 70,
    "80%": 80,
    "90%": 90,
    "100%": 100,
    "110%": 110,
}


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AcCapacity(data["coordinator"], data["api"], entry.entry_id)])


class AcCapacity(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Capacity"
    _attr_options = list(OPTIONS)

    def __init__(self, coordinator, api, entry_id):
        super().__init__(coordinator)
        self.api = api
        self._attr_unique_id = entry_id + "_" + KEY_CAPACITY

    @property
    def device_info(self):
        return self.coordinator.device_info

    @property
    def available(self):
        return self.coordinator.device_available and KEY_CAPACITY in (
            self.coordinator.data or {}
        ).get("ac", {})

    @property
    def current_option(self):
        value = ((self.coordinator.data or {}).get("ac") or {}).get(KEY_CAPACITY)
        try:
            return next((name for name, number in OPTIONS.items() if number == int(value)), None)
        except (ValueError, TypeError):
            return None

    async def async_select_option(self, option):
        try:
            await self.coordinator.async_command(
                KEY_CAPACITY, OPTIONS[option], extra={KEY_ECONOMY: "off", KEY_POWERFUL: "off"}
            )
        except AcMitmApiError as error:
            raise HomeAssistantError(str(error)) from error

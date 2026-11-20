"""Native local selects: the convertible capacity limit and each vane's exact position."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AcMitmApiError
from .const import (
    DOMAIN,
    KEY_CAPACITY,
    KEY_ECONOMY,
    KEY_POWERFUL,
    KEY_SWING_HORIZONTAL,
    KEY_SWING_VERTICAL,
)
from .features import VANE_OPTIONS, vane_option, vane_value

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
    coordinator, api = data["coordinator"], data["api"]
    async_add_entities(
        [
            AcCapacity(coordinator, api, entry.entry_id),
            AcVane(coordinator, api, entry.entry_id, KEY_SWING_VERTICAL, "Vertical vane"),
            AcVane(coordinator, api, entry.entry_id, KEY_SWING_HORIZONTAL, "Horizontal vane"),
        ]
    )


class _AcSelect(CoordinatorEntity, SelectEntity):
    """A select backed by one key of the AC's status; unavailable when the AC omits it."""

    _attr_has_entity_name = True
    key = ""

    def __init__(self, coordinator, api, entry_id):
        super().__init__(coordinator)
        self.api = api
        self._attr_unique_id = entry_id + "_" + self.key

    @property
    def device_info(self):
        return self.coordinator.device_info

    @property
    def _value(self):
        return ((self.coordinator.data or {}).get("ac") or {}).get(self.key)

    @property
    def available(self):
        return self.coordinator.device_available and self.key in (
            self.coordinator.data or {}
        ).get("ac", {})

    async def _send(self, value, extra=None):
        try:
            await self.coordinator.async_command(self.key, value, extra=extra)
        except AcMitmApiError as error:
            raise HomeAssistantError(str(error)) from error


class AcCapacity(_AcSelect):
    _attr_name = "Capacity"
    _attr_options = list(OPTIONS)
    key = KEY_CAPACITY

    @property
    def current_option(self):
        try:
            return next(
                (name for name, number in OPTIONS.items() if number == int(self._value)), None
            )
        except (ValueError, TypeError):
            return None

    async def async_select_option(self, option):
        await self._send(OPTIONS[option], extra={KEY_ECONOMY: "off", KEY_POWERFUL: "off"})


class AcVane(_AcSelect):
    """One vane: swing, or a fixed position 1-5."""

    _attr_options = list(VANE_OPTIONS)
    _attr_icon = "mdi:arrow-oscillating"

    def __init__(self, coordinator, api, entry_id, key, name):
        self.key = key
        self._attr_name = name
        super().__init__(coordinator, api, entry_id)

    @property
    def current_option(self):
        return vane_option(self._value)

    async def async_select_option(self, option):
        await self._send(vane_value(option))

"""Native local controls for AC capacity and flap positions."""

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

SWING_OPTIONS = {
    "Auto / Swing": 0,
    "Position 1": 1,
    "Position 2": 2,
    "Position 3": 3,
    "Position 4": 4,
    "Position 5": 5,
}


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    async_add_entities([
        AcCapacity(coordinator, api, entry.entry_id),
        AcSwingPosition(
            coordinator,
            entry.entry_id,
            KEY_SWING_VERTICAL,
            "Vertical flap position",
        ),
        AcSwingPosition(
            coordinator,
            entry.entry_id,
            KEY_SWING_HORIZONTAL,
            "Horizontal flap position",
        ),
    ])


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
        value = ((self.coordinator.data or {}).get("ac") or {}).get(
            KEY_CAPACITY
        )
        try:
            return next(
                name
                for name, number in OPTIONS.items()
                if number == int(value)
            )
        except (ValueError, TypeError, StopIteration):
            return None

    async def async_select_option(self, option):
        try:
            await self.coordinator.async_command(
                KEY_CAPACITY,
                OPTIONS[option],
                extra={
                    KEY_ECONOMY: "off",
                    KEY_POWERFUL: "off",
                },
            )
        except AcMitmApiError as error:
            raise HomeAssistantError(str(error)) from error


class AcSwingPosition(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_options = list(SWING_OPTIONS)

    def __init__(self, coordinator, entry_id, key, name):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{key}_position"

    @property
    def device_info(self):
        return self.coordinator.device_info

    @property
    def available(self):
        ac = (self.coordinator.data or {}).get("ac") or {}
        return self.coordinator.device_available and self.key in ac

    @property
    def current_option(self):
        ac = (self.coordinator.data or {}).get("ac") or {}
        value = ac.get(self.key)

        try:
            position = int(float(value))
        except (TypeError, ValueError):
            return None

        return next(
            (
                label
                for label, number in SWING_OPTIONS.items()
                if number == position
            ),
            None,
        )

    async def async_select_option(self, option):
        try:
            await self.coordinator.async_command(
                self.key,
                SWING_OPTIONS[option],
            )
        except AcMitmApiError as error:
            raise HomeAssistantError(str(error)) from error
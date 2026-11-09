"""Climate entity for a Panasonic AC controlled locally."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .api import AcMitmApi, AcMitmApiError
from .const import (
    DOMAIN,
    KEY_ECONOMY,
    KEY_FAN,
    KEY_FILTER_CLEANING,
    KEY_FILTER_DUST,
    KEY_MODE,
    KEY_ONLINE,
    KEY_POWER,
    KEY_POWERFUL,
    KEY_ROOM_TEMP,
    KEY_SWING_HORIZONTAL,
    KEY_SWING_VERTICAL,
    KEY_TARGET_TEMP,
)
from .coordinator import AcMitmCoordinator

_LOGGER = logging.getLogger(__name__)

HVAC_MODE_MAP = {
    "off": HVACMode.OFF,
    "auto": HVACMode.AUTO,
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "dry": HVACMode.DRY,
    "fan": HVACMode.FAN_ONLY,
}

MODE_TO_MIRAIe = {v: k for k, v in HVAC_MODE_MAP.items()}

FAN_MODE_MAP = {
    "auto": "auto",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "quiet": "quiet",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the native local climate entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    api: AcMitmApi = data["api"]
    coordinator = data["coordinator"]

    async_add_entities([AcMitmClimate(coordinator, api, entry)])


class AcMitmClimate(ClimateEntity, CoordinatorEntity[AcMitmCoordinator]):
    """AC entity backed by native UDP state and confirmed commands."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
    _attr_target_temperature_step = 1
    _attr_min_temp = 16
    _attr_max_temp = 30
    # HA 2026.11 renamed the temperature members to native_*; the old names remain
    # for older HA and are what it reads there
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_fan_modes = list(FAN_MODE_MAP)
    _attr_hvac_modes = list(HVAC_MODE_MAP.values())
    # "both" is the AC's only all-vanes swing; a separate "on" read back as "both"
    _attr_swing_modes = ["off", "vertical", "horizontal", "both"]

    def __init__(self, coordinator, api: AcMitmApi, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._api = api
        self._entry = entry
        self._attr_unique_id = entry.entry_id

    # -- state -----------------------------------------------------------

    @property
    def _ac(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return data.get("ac") or {}

    @property
    def available(self) -> bool:
        return self.coordinator.device_available

    @property
    def device_info(self):
        return self.coordinator.device_info

    def _float(self, key: str) -> float | None:
        try:
            return float(self._ac.get(key))
        except (TypeError, ValueError):
            return None

    @property
    def native_current_temperature(self) -> float | None:
        return self._float(KEY_ROOM_TEMP)

    @property
    def native_target_temperature(self) -> float | None:
        return self._float(KEY_TARGET_TEMP)

    current_temperature = native_current_temperature
    target_temperature = native_target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        if str(self._ac.get(KEY_POWER, "off")).lower() in ("off", "0", "false"):
            return HVACMode.OFF
        return HVAC_MODE_MAP.get(str(self._ac.get(KEY_MODE, "")).lower(), HVACMode.AUTO)

    @property
    def fan_mode(self) -> str | None:
        value = self._ac.get(KEY_FAN)
        if value is None:
            return None
        return FAN_MODE_MAP.get(str(value).lower(), str(value).lower())

    @property
    def swing_mode(self) -> str | None:
        vertical = str(self._ac.get(KEY_SWING_VERTICAL))
        horizontal = str(self._ac.get(KEY_SWING_HORIZONTAL))
        if vertical == "0" and horizontal == "0":
            return "both"
        if vertical == "0":
            return "vertical"
        if horizontal == "0":
            return "horizontal"
        return "off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "control_transport": self._ac.get("_transport"),
            "local_available": (data.get("local") or {}).get("available"),
            "device_online": self._ac.get(KEY_ONLINE),
            "powerful_mode": self._ac.get(KEY_POWERFUL) == "on",
            "economy_mode": self._ac.get(KEY_ECONOMY) == "on",
            "filter_dust_level": self._ac.get(KEY_FILTER_DUST),
            "filter_cleaning_required": self._ac.get(KEY_FILTER_CLEANING),
        }

    # -- commands --------------------------------------------------------

    async def _send(self, action: str, value: Any, extra: dict | None = None) -> None:
        topic = self._ac.get("_topic")
        try:
            await self.coordinator.async_command(action, value, topic=topic, extra=extra)
        except AcMitmApiError as err:
            _LOGGER.error("Local AC command %s=%s failed: %s", action, value, err)
            raise HomeAssistantError(str(err)) from err
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._send(KEY_POWER, "off")
            return
        miraie_mode = MODE_TO_MIRAIe.get(hvac_mode)
        if miraie_mode:
            await self._send(KEY_MODE, miraie_mode, extra={KEY_POWER: "on"})

    async def async_set_temperature(self, **kwargs) -> None:
        """Set the target temperature."""
        hvac_mode = kwargs.get("hvac_mode")
        temperature = kwargs.get("temperature")
        if temperature is None:
            if hvac_mode is not None:
                await self.async_set_hvac_mode(hvac_mode)
            return
        extra = None
        if hvac_mode is not None and hvac_mode != HVACMode.OFF:
            extra = {KEY_MODE: MODE_TO_MIRAIe[hvac_mode], KEY_POWER: "on"}
        await self._send(KEY_TARGET_TEMP, str(temperature), extra=extra)
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        value = FAN_MODE_MAP.get(str(fan_mode).lower(), str(fan_mode).lower())
        await self._send(KEY_FAN, value)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode."""
        positions = {
            "off": ("3", "3"),
            "vertical": ("0", "3"),
            "horizontal": ("3", "0"),
            "both": ("0", "0"),
        }
        vertical, horizontal = positions[str(swing_mode).lower()]
        await self._send(KEY_SWING_VERTICAL, vertical, extra={KEY_SWING_HORIZONTAL: horizontal})

    async def async_turn_on(self) -> None:
        """Turn the AC on."""
        await self._send(KEY_POWER, "on")

    async def async_turn_off(self) -> None:
        """Turn the AC off."""
        await self._send(KEY_POWER, "off")

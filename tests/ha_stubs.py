"""Small stand-ins for the Home Assistant classes the entity modules import.

Importing this lets tests run the select, switch and diagnostics modules without Home Assistant
installed. It only fills names that are missing, so a real Home Assistant wins when present.
"""

import asyncio
import sys
import types


class HomeAssistantError(Exception):
    pass


class CoordinatorEntity:
    def __init__(self, coordinator=None, *args, **kwargs):
        self.coordinator = coordinator


class SelectEntity:
    pass


class SwitchEntity:
    pass


def _module(name, **attrs):
    module = sys.modules.setdefault(name, types.ModuleType(name))
    for key, value in attrs.items():
        if not hasattr(module, key):
            setattr(module, key, value)
    return module


for _name in ("homeassistant", "homeassistant.components", "homeassistant.helpers"):
    _module(_name)
_module("homeassistant.components.select", SelectEntity=SelectEntity)
_module("homeassistant.components.switch", SwitchEntity=SwitchEntity)
_module("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
_module("homeassistant.helpers.update_coordinator", CoordinatorEntity=CoordinatorEntity)
_module("homeassistant.config_entries", ConfigEntry=object)
_module("homeassistant.core", HomeAssistant=object)

HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError


class FakeCoordinator:
    """Holds an AC status and applies commands to it, as a confirmed readback would."""

    def __init__(self, status, error=None):
        self.data = {"ac": dict(status), "local": {"enabled": True, "available": True}}
        self.device_available = True
        self.device_info = {}
        self.last_update_success = True
        self.sent = []
        self.error = error

    async def async_command(self, action, value, **kwargs):
        if self.error:
            raise self.error
        extra = kwargs.get("extra")
        self.sent.append((action, value, extra))
        self.data["ac"][action] = value
        self.data["ac"].update(extra or {})


def setup_entities(platform, coordinator):
    """Run a platform's async_setup_entry and return its entities by name."""
    hass = types.SimpleNamespace(
        data={"ac_mitm": {"entry": {"coordinator": coordinator, "api": None}}}
    )
    entry = types.SimpleNamespace(entry_id="entry", data={})
    added = []
    asyncio.run(platform.async_setup_entry(hass, entry, added.extend))
    return {getattr(entity, "_attr_name", None): entity for entity in added}

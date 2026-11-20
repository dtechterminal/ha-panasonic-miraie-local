import asyncio

import pytest

import ha_stubs

from custom_components.ac_mitm import switch
from custom_components.ac_mitm.protocol import ProtocolError, command_settings


@pytest.mark.parametrize("value", ["on", "off"])
def test_nanoe_is_a_command(value):
    assert command_settings("acng", value) == {"acng": value}


@pytest.mark.parametrize("key", ["acpm", "acem", "acec", "acdc", "acng"])
@pytest.mark.parametrize("value", ["yes", "1", 1, True, ""])
def test_feature_switches_take_only_on_or_off(key, value):
    with pytest.raises(ProtocolError):
        command_settings(key, value)


def test_the_exclusive_modes_still_send_their_off_values():
    settings = command_settings("acpm", "on", {"acem": "off", "acec": "off", "cnv": 0})
    assert settings == {"acpm": "on", "acem": "off", "acec": "off", "cnv": 0}


def test_nanoe_switch_exists_and_is_available_only_when_reported():
    with_nanoe = ha_stubs.setup_entities(switch, ha_stubs.FakeCoordinator({"acng": "on"}))
    assert with_nanoe["nanoe"].is_on and with_nanoe["nanoe"].available
    without = ha_stubs.setup_entities(switch, ha_stubs.FakeCoordinator({"ps": "on"}))
    assert not without["nanoe"].available


def test_turning_nanoe_on_does_not_touch_the_exclusive_modes():
    coordinator = ha_stubs.FakeCoordinator({"acng": "off", "acpm": "on", "cnv": 70})
    asyncio.run(ha_stubs.setup_entities(switch, coordinator)["nanoe"].async_turn_on())
    assert coordinator.sent == [("acng", "on", None)]
    assert coordinator.data["ac"]["acpm"] == "on" and coordinator.data["ac"]["cnv"] == 70


def test_existing_switches_keep_their_unique_ids():
    found = ha_stubs.setup_entities(switch, ha_stubs.FakeCoordinator({}))
    assert found["Coil cleaning"]._attr_unique_id == "entry_acec"
    assert found["Economy"]._attr_unique_id == "entry_acem"
    assert found["nanoe"]._attr_unique_id == "entry_acng"

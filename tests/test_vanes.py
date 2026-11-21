import asyncio

import pytest

import ha_stubs

from custom_components.ac_mitm import select
from custom_components.ac_mitm.api import AcMitmApiError
from custom_components.ac_mitm.features import VANE_OPTIONS, vane_option, vane_value
from custom_components.ac_mitm.protocol import command_settings


@pytest.mark.parametrize(
    "value, option",
    [(0, "Swing"), ("0", "Swing"), (1, "1"), ("3", "3"), (5.0, "5"), ("5", "5")],
)
def test_vane_option_reads_every_position_the_ac_reports(value, option):
    assert vane_option(value) == option


@pytest.mark.parametrize("value", [None, "", "x", -1, 6, "2.5", float("nan")])
def test_vane_option_is_none_for_anything_else(value):
    assert vane_option(value) is None


def test_vane_value_round_trips_every_option():
    for option in VANE_OPTIONS:
        assert vane_option(vane_value(option)) == option


def test_vane_value_rejects_unknown_options():
    with pytest.raises(ValueError):
        vane_value("up")


@pytest.mark.parametrize("key", ["acvs", "achs"])
@pytest.mark.parametrize("option", VANE_OPTIONS)
def test_every_vane_option_makes_a_valid_command(key, option):
    assert command_settings(key, vane_value(option)) == {key: vane_value(option)}


def test_each_vane_shows_its_position_and_unique_id():
    found = ha_stubs.setup_entities(
        select, ha_stubs.FakeCoordinator({"acvs": "0", "achs": "4", "cnv": 40})
    )
    assert found["Vertical vane"].current_option == "Swing"
    assert found["Horizontal vane"].current_option == "4"
    assert found["Capacity"].current_option == "40%"
    assert found["Vertical vane"]._attr_unique_id == "entry_acvs"
    assert found["Horizontal vane"]._attr_unique_id == "entry_achs"
    assert found["Capacity"]._attr_unique_id == "entry_cnv", "existing entity ids must not move"


def test_choosing_a_vane_position_sends_only_that_vane():
    coordinator = ha_stubs.FakeCoordinator({"acvs": "0", "achs": "3"})
    vertical = ha_stubs.setup_entities(select, coordinator)["Vertical vane"]
    asyncio.run(vertical.async_select_option("2"))
    assert coordinator.sent == [("acvs", 2, None)]
    assert vertical.current_option == "2"
    assert coordinator.data["ac"]["achs"] == "3"


def test_capacity_still_turns_economy_and_powerful_off():
    coordinator = ha_stubs.FakeCoordinator({"cnv": 0})
    asyncio.run(ha_stubs.setup_entities(select, coordinator)["Capacity"].async_select_option("70%"))
    assert coordinator.sent == [("cnv", 70, {"acem": "off", "acpm": "off"})]


def test_a_vane_the_ac_does_not_report_is_unavailable():
    found = ha_stubs.setup_entities(select, ha_stubs.FakeCoordinator({"acvs": "1"}))
    assert found["Vertical vane"].available
    assert not found["Horizontal vane"].available


def test_a_refused_command_reaches_home_assistant_as_an_error():
    coordinator = ha_stubs.FakeCoordinator({"acvs": "0"}, error=AcMitmApiError("not applied"))
    vertical = ha_stubs.setup_entities(select, coordinator)["Vertical vane"]
    with pytest.raises(ha_stubs.HomeAssistantError):
        asyncio.run(vertical.async_select_option("5"))

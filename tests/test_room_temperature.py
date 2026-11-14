import pytest

from custom_components.ac_mitm.protocol import room_temperature


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        # Firmware 3.02 packs "<prefix>.<whole °C>" (seen on CS-CU-NU18BKY5WX)
        ({"V": "3.02", "rmtmp": "128.25"}, 25.0),
        ({"V": "3.02", "rmtmp": "134.24"}, 24.0),
        ({"V": "3.02", "rmtmp": "01.26"}, 26.0),
        ({"V": "3.02", "rmtmp": "61.28"}, 28.0),
        ({"V": "3.02", "rmtmp": "132.26"}, 26.0),
        ({"V": "3.10", "rmtmp": "2.29"}, 29.0),
        # No reading yet (unit off or just started)
        ({"V": "3.02", "rmtmp": "00.0"}, None),
        # Malformed or missing
        ({"V": "3.02", "rmtmp": "garbage"}, None),
        ({"V": "3.02", "rmtmp": "12.ab"}, None),
        ({"V": "3.02"}, None),
        # Older firmware or no version: plain value, unchanged behaviour
        ({"V": "2.10", "rmtmp": "26.0"}, 26.0),
        ({"V": "2.10", "rmtmp": "26.5"}, 26.5),
        ({"rmtmp": "27.0"}, 27.0),
        ({"V": "unknown", "rmtmp": "27.0"}, 27.0),
    ],
)
def test_room_temperature(state, expected):
    assert room_temperature(state) == expected

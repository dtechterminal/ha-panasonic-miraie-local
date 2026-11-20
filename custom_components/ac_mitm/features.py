"""Vane positions as plain values, independent of Home Assistant."""

from __future__ import annotations

from typing import Any

# The AC's vertical (acvs) and horizontal (achs) vanes each take 0 for swing and 1-5 for a
# fixed position. The climate entity's swing modes only reach 0 and 3; these reach every one.
VANE_OPTIONS = ["Swing", "1", "2", "3", "4", "5"]


def vane_option(value: Any) -> str | None:
    """The option for a vane value the AC reported, or None when it isn't 0-5."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number.is_integer() or not 0 <= number <= 5:
        return None
    return VANE_OPTIONS[int(number)]


def vane_value(option: str) -> int:
    """The value to send for a vane option. Raises ValueError for an unknown option."""
    return VANE_OPTIONS.index(option)

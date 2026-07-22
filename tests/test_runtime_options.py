from __future__ import annotations

import pytest

from bus_schedule_engine.time_utils import parse_runtime_options


def test_parse_runtime_options_returns_sorted_inclusive_bounds() -> None:
    assert parse_runtime_options("65,55,60,65") == (55, 65)
    assert parse_runtime_options("55; 65") == (55, 65)
    assert parse_runtime_options("55-65") == (55, 65)


def test_parse_runtime_options_recovers_excel_decimal_comma_conversion() -> None:
    assert parse_runtime_options(55.65) == (55, 65)


@pytest.mark.parametrize("value", ["55.5,65", "55.65", 55.5, "", 0, -1])
def test_parse_runtime_options_rejects_decimals_and_non_positive_integers(value) -> None:
    with pytest.raises(ValueError):
        parse_runtime_options(value)

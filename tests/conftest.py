from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from bus_schedule_engine.models import Direction, RouteType, ScenarioParameters, Trip

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_APPTEST_FROM_FILE = AppTest.from_file


def _repo_relative_app_test(script_path, *args, **kwargs):
    path = Path(script_path)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    return _ORIGINAL_APPTEST_FROM_FILE(path, *args, **kwargs)


# Streamlit now resolves AppTest relative paths against the calling test file.
# Keep the repository's historical test semantics explicit and version-independent.
AppTest.from_file = _repo_relative_app_test


@pytest.fixture
def make_parameters() -> Callable[..., ScenarioParameters]:
    def factory(**overrides) -> ScenarioParameters:
        values = {
            "route_id": "T-01",
            "route_name": "Tuyến kiểm thử",
            "route_type": RouteType.INTRA_PROVINCIAL,
            "trip_runtime_minutes": 30,
            "total_daily_trips": 4,
            "terminal_1_name": "Bến 1",
            "terminal_1_first_departure": 6 * 3600,
            "terminal_1_last_departure": 7 * 3600,
            "terminal_2_name": "Bến 2",
            "terminal_2_first_departure": 6 * 3600 + 10 * 60,
            "terminal_2_last_departure": 7 * 3600 + 10 * 60,
            "vehicle_capacity_passengers": 60,
            "target_load_factor": 0.85,
            "maximum_load_factor": 0.90,
            "time_block_minutes": 60,
            "minimum_layover_minutes": 5,
        }
        values.update(overrides)
        return ScenarioParameters(**values)

    return factory


@pytest.fixture
def make_valid_trips() -> Callable[[ScenarioParameters], list[Trip]]:
    def factory(parameters: ScenarioParameters) -> list[Trip]:
        definitions = [
            (
                "T1",
                parameters.terminal_1_name,
                Direction.TERMINAL_1_TO_2,
                parameters.terminal_1_first_departure,
            ),
            (
                "T2",
                parameters.terminal_2_name,
                Direction.TERMINAL_2_TO_1,
                parameters.terminal_2_first_departure,
            ),
            (
                "T3",
                parameters.terminal_1_name,
                Direction.TERMINAL_1_TO_2,
                parameters.terminal_1_last_departure,
            ),
            (
                "T4",
                parameters.terminal_2_name,
                Direction.TERMINAL_2_TO_1,
                parameters.terminal_2_last_departure,
            ),
        ]
        return [
            Trip(
                scenario="B",
                trip_id=trip_id,
                departure_terminal=terminal,
                direction=direction,
                departure_seconds=departure,
                arrival_seconds=departure + parameters.trip_runtime_minutes * 60,
            )
            for trip_id, terminal, direction, departure in definitions
        ]

    return factory

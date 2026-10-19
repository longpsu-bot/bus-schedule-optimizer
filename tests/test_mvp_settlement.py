from copy import deepcopy

import pytest

from bus_schedule_engine.mvp.planning import compile_plan
from bus_schedule_engine.mvp.quality import waiting
from bus_schedule_engine.mvp.runner import _settings


def direction():
    return {
        "first": 0,
        "last": 120,
        "trip_count": 9,
        "baseline": list(range(0, 121, 15)),
        "demand": [
            {"start": 0, "end": 30, "passengers": 90},
            {"start": 30, "end": 120, "passengers": 30},
        ],
        "protected_windows": [],
    }


PLAN = [{"end": 45, "gaps": 3}, {"end": 120, "gaps": 5}]


def test_passenger_settlement_changes_legal_integer_rhythm_and_integrated_setting():
    d = direction()
    original = deepcopy(d)
    control = compile_plan(d, PLAN, {})
    assert waiting(control["departures"], d["demand"])["wait"] == 7.5
    settings = _settings({"compilation_lookahead": 256})
    result = compile_plan(d, PLAN, settings)
    assert result["departures"] == [0, 10, 20, 30, 48, 66, 84, 102, 120]
    assert waiting(result["departures"], d["demand"])["wait"] == 6
    assert result["settlement_previews"] > 1
    assert result["settlement_lookahead_complete"]
    assert settings["candidate_budget"] == 25
    assert result == compile_plan(d, PLAN, settings)
    assert d == original


def test_explicit_protection_and_transition_are_respected_by_settlement():
    d = direction()
    d["protected_windows"] = [{"start": 30, "end": 120, "max_gap": 15}]
    result = compile_plan(d, PLAN, {"compilation_lookahead": 256})
    assert result["departures"] == list(range(0, 121, 15))
    d["protected_windows"] = []
    result = compile_plan(d, PLAN, {"compilation_lookahead": 256, "maximum_transition_jump": 3})
    assert result["departures"] == list(range(0, 121, 15))


def test_small_preview_limit_is_disclosed_and_retains_valid_incumbent():
    result = compile_plan(direction(), PLAN, {"compilation_lookahead": 1})
    assert result["status"] == "COMPILED"
    assert 1 <= result["settlement_previews"] <= 2
    assert not result["settlement_lookahead_complete"]
    assert len(result["departures"]) == 9
    assert result["departures"][-1] == 120


def test_settlement_responds_to_demand_without_changing_plan_or_endpoints():
    d = direction()
    d["demand"] = [
        {"start": 0, "end": 90, "passengers": 30},
        {"start": 90, "end": 120, "passengers": 90},
    ]
    result = compile_plan(d, PLAN, {"compilation_lookahead": 256})
    assert [r["headway_minutes"] for r in result["regimes"]] == [25, 9]
    assert result["departures"][0] == 0 and result["departures"][-1] == 120
    assert len(result["departures"]) == 9
    assert all(r["gap_count"] >= 2 for r in result["regimes"])


def test_boundary_solve_and_previews_share_deterministic_work_budget(monkeypatch):
    from bus_schedule_engine.mvp import planning

    instances = []
    original = planning.solver

    def observed_solver(settings):
        instance = original(settings)
        instances.append(instance)
        return instance

    monkeypatch.setattr(planning, "solver", observed_solver)
    result = compile_plan(
        direction(), PLAN, {"compilation_lookahead": 256, "solver_work_limit": 0.01}
    )
    assert result["status"] == "COMPILED"
    assert len(instances) == 2
    used = instances[0].response_proto.deterministic_time
    assert used > 0
    assert instances[1].parameters.max_deterministic_time + used <= 0.01 + 1e-12


@pytest.mark.parametrize("value", [-1, True, 1.5, 257])
def test_preview_budget_is_validated(value):
    with pytest.raises(ValueError, match="compilation_lookahead"):
        _settings({"compilation_lookahead": value})

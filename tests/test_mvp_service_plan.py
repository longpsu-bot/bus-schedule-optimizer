import json
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from bus_schedule_engine.mvp.circulation import assign_fleet, validate_chains
from bus_schedule_engine.mvp.input import validate_bundle
from bus_schedule_engine.mvp.planning import compile_plan
from bus_schedule_engine.mvp.quality import evaluate, select_candidate
from bus_schedule_engine.mvp.runner import export_result, run_bundle


def bundle():
    return {
        "route_id": "synthetic",
        "provenance": {"source": "hand-checked fixture"},
        "demand_basis": "independent_arrivals",
        "fleet_ceiling": 2,
        "layover_minutes": {"outbound": 5, "inbound": 5},
        "directions": {
            d: {
                "first": 360 + offset,
                "last": 420 + offset,
                "trip_count": 4,
                "runtime_minutes": 15,
                "baseline": [360 + offset, 380 + offset, 400 + offset, 420 + offset],
                "demand": [{"start": 360 + offset, "end": 420 + offset, "passengers": 60}],
                "protected_windows": [{"start": 360 + offset, "end": 420 + offset, "max_gap": 20}],
            }
            for d, offset in (("outbound", 0), ("inbound", 20))
        },
    }


def test_hand_checked_vertical_slice_and_exports(tmp_path):
    result = run_bundle(bundle(), {"candidate_budget": 5})
    assert result["status"] in {"FEASIBLE_RECOMMENDATION", "FEASIBLE_BUDGET_LIMITED"}
    selected = result["recommended"]
    assert selected["departures"] == {
        "outbound": [360, 380, 400, 420],
        "inbound": [380, 400, 420, 440],
    }
    assert selected["quality"]["required_fleet"] == 2
    assert selected["quality"]["waiting_minutes"] == pytest.approx(10)
    assert selected["quality"]["hard_constraints_pass"]
    assert all(r["headway_minutes"] == 20 for r in selected["regimes"])
    export_result(result, tmp_path)
    assert len(list(tmp_path.iterdir())) == 6
    assert (
        json.loads((tmp_path / "recommended_timetable.json").read_text())["departures"]
        == selected["departures"]
    )
    workbook = load_workbook(tmp_path / "recommended_timetable.xlsx", data_only=True)
    assert workbook.sheetnames == [
        "Outbound",
        "Inbound",
        "ServiceRegimes",
        "VehicleCirculation",
        "QualityComparison",
    ]
    assert [row[1] for row in workbook["Outbound"].iter_rows(min_row=2, values_only=True)] == [
        360,
        380,
        400,
        420,
    ]


@pytest.mark.parametrize(
    "field,value", [("fleet_ceiling", True), ("fleet_ceiling", 0), ("demand_basis", "unknown")]
)
def test_invalid_authority_is_blocked(field, value):
    data = bundle()
    data[field] = value
    assert run_bundle(data)["status"] == "BLOCKED_INPUT"


def test_missing_layover_and_directional_demand_are_not_inferred():
    data = bundle()
    del data["layover_minutes"]
    assert "layover_minutes" in run_bundle(data)["diagnostics"]["input_error"]
    data = bundle()
    data["directions"]["inbound"]["demand"] = []
    assert run_bundle(data)["status"] == "BLOCKED_INPUT"


def test_input_does_not_mutate_and_nonfinite_demand_blocks():
    data = bundle()
    before = deepcopy(data)
    validate_bundle(data)
    assert data == before
    data["directions"]["outbound"]["demand"][0]["passengers"] = float("nan")
    assert run_bundle(data)["status"] == "BLOCKED_INPUT"


def test_exact_wait_integrates_bucket_crossing_departures():
    data = validate_bundle(bundle())
    data["directions"]["outbound"]["demand"] = [{"start": 365, "end": 395, "passengers": 30}]
    q = evaluate(data, {"outbound": [360, 380, 400, 420], "inbound": [380, 400, 420, 440]}, [])
    # Integral over [365,380] to 380 and [380,395] to 400 = 300 / 30 = 10.
    assert q["directional_waiting_minutes"]["outbound"] == pytest.approx(10)


def test_metric_disagreement_does_not_deadlock_and_fleet_band_is_explicit():
    candidates = [
        {
            "id": "sse",
            "departures": {"outbound": [1], "inbound": [2]},
            "quality": {
                "hard_constraints_pass": True,
                "maximum_protected_gap": 10,
                "waiting_minutes": 5,
                "required_fleet": 4,
                "regime_count": 2,
                "transition_jump": 0,
                "terminal_wait": 0,
                "tail_gap": 10,
                "sse": 0,
                "te": 100,
            },
        },
        {
            "id": "te",
            "departures": {"outbound": [2], "inbound": [3]},
            "quality": {
                "hard_constraints_pass": True,
                "maximum_protected_gap": 10,
                "waiting_minutes": 5.09,
                "required_fleet": 3,
                "regime_count": 2,
                "transition_jump": 0,
                "terminal_wait": 0,
                "tail_gap": 10,
                "sse": 100,
                "te": 0,
            },
        },
    ]
    assert select_candidate(candidates, {})["id"] == "te"
    assert (
        select_candidate(candidates, {"wait_absolute_tolerance": 0, "wait_relative_tolerance": 0})[
            "id"
        ]
        == "sse"
    )
    candidates[1]["quality"]["hard_constraints_pass"] = False
    assert select_candidate(candidates, {})["id"] == "sse"


def test_exact_fleet_chains_respect_arrival_terminal_layover():
    data = validate_bundle(bundle())
    departures = {"outbound": [360, 380, 400, 420], "inbound": [380, 400, 420, 440]}
    fleet = assign_fleet(data, departures, 2)
    assert fleet["required_fleet"] == 2
    validate_chains(data, departures, fleet)
    broken = deepcopy(fleet)
    broken["trips"][0]["arrival"] += 100
    with pytest.raises(ValueError):
        validate_chains(data, departures, broken)


def test_initial_terminal_stock_is_enforced():
    data = bundle()
    data["initial_vehicles"] = {"outbound": 0, "inbound": 2}
    result = run_bundle(data, {"candidate_budget": 2})
    assert result["recommended"] is None


def test_fleet_ceiling_and_protection_are_hard():
    data = bundle()
    data["fleet_ceiling"] = 1
    assert run_bundle(data, {"candidate_budget": 2})["recommended"] is None
    data = validate_bundle(bundle())
    data["directions"]["outbound"]["protected_windows"][0]["max_gap"] = 19
    quality = evaluate(
        data, {"outbound": [360, 380, 400, 420], "inbound": [380, 400, 420, 440]}, []
    )
    assert not quality["hard_constraints_pass"]
    assert any("PROTECTED" in x for x in quality["failures"])


def test_capacity_point_eight_and_unavailable_are_explicit():
    data = validate_bundle(bundle())
    departures = {"outbound": [360, 380, 400, 420], "inbound": [380, 400, 420, 440]}
    assert evaluate(data, departures, [])["capacity"] is None
    data.update({"vehicle_capacity": 20, "maximum_load_factor": 0.8, "capacity_policy": "hard"})
    quality = evaluate(data, departures, [])
    assert quality["capacity"]["maximum_modeled_boardings"] == 20
    assert not quality["hard_constraints_pass"]


def test_compiler_settles_boundaries_without_one_gap_blocks():
    data = validate_bundle(bundle())
    direction = data["directions"]["outbound"]
    direction["trip_count"] = 7
    plan = [{"end": 391, "gaps": 3}, {"end": 420, "gaps": 3}]
    compiled = compile_plan(direction, plan, {"solver_seconds": 2})
    assert compiled["status"] == "COMPILED"
    assert compiled["departures"][0] == 360 and compiled["departures"][-1] == 420
    assert len(compiled["departures"]) == 7
    assert all(r["gap_count"] >= 2 for r in compiled["regimes"])
    assert len(set(compiled["departures"])) == 7


def test_determinism_budgets_and_independent_routes():
    settings = {"candidate_budget": 1, "max_revisions": 0}
    first = run_bundle(bundle(), settings)
    assert first == run_bundle(bundle(), settings)
    assert first["status"] == "FEASIBLE_BUDGET_LIMITED"
    assert first["diagnostics"]["evaluations"] == 1
    bad = bundle()
    del bad["fleet_ceiling"]
    assert run_bundle(bad)["status"] == "BLOCKED_INPUT"
    assert run_bundle(bundle(), settings)["recommended"] is not None


def test_only_authoritative_contradiction_proves_route_infeasible():
    data = bundle()
    data["directions"]["outbound"]["trip_count"] = 100
    result = run_bundle(data)
    assert result["status"] == "PROVEN_INFEASIBLE"
    assert "whole-minute" in result["diagnostics"]["proof"]
    data = bundle()
    data["fleet_ceiling"] = 1
    assert (
        run_bundle(data, {"candidate_budget": 1})["status"]
        == "SEARCH_INCOMPLETE_NO_FEASIBLE_CANDIDATE"
    )


def test_archived_metric_definitions_are_preserved():
    from bus_schedule_engine.mvp.quality import demand_fit_diagnostics

    # 4 departures in first bucket, 2 in second; demand shares 1/2 each.
    times = [0, 10, 20, 30, 40, 50]
    buckets = [
        {"start": 0, "end": 40, "passengers": 50},
        {"start": 40, "end": 60, "passengers": 50},
    ]
    diagnostics = demand_fit_diagnostics(times, buckets)
    assert diagnostics["sse"] == pytest.approx(1 / 18)
    assert diagnostics["te"] == pytest.approx(1)
    # Service density .02 on [0,50]; demand .0125 then .025. L1 integral .6.
    assert diagnostics["continuous_exposure"] == pytest.approx(1.8)


def test_demand_flatness_does_not_create_unnecessary_regimes():
    from bus_schedule_engine.mvp.planning import initial_plan

    d = {
        "first": 0,
        "last": 120,
        "trip_count": 13,
        "demand": [{"start": i, "end": i + 30, "passengers": 30} for i in range(0, 120, 30)],
    }
    assert initial_plan(d, {}) == [{"end": 120, "gaps": 12}]


def test_bounded_feedback_repairs_integer_incompatibility():
    data = bundle()
    data["fleet_ceiling"] = 8
    for d in data["directions"].values():
        d["trip_count"] = 9
        d["last"] = d["first"] + 65
        d["baseline"][-1] = d["last"]
        d["demand"] = [
            {"start": d["first"], "end": d["first"] + 30, "passengers": 70},
            {"start": d["first"] + 30, "end": d["last"], "passengers": 60},
        ]
        d["protected_windows"] = []
    result = run_bundle(data, {"candidate_budget": 10, "minimum_regime_minutes": 10})
    assert result["recommended"] is not None
    assert result["diagnostics"]["evaluations"] <= 10
    assert any(
        c["status"] == "FAMILY_INFEASIBLE"
        for c in result["diagnostics"]["feedback"][0]["compilation"].values()
    )
    assert any(f["operation"] != "initial" for f in result["diagnostics"]["feedback"])


def test_candidate_generation_itself_is_bounded():
    data = bundle()
    for d in data["directions"].values():
        d["trip_count"] = 13
        start = d["first"]
        d["last"] = start + 240
        d["baseline"] = list(range(start, start + 241, 20))
        d["demand"] = [
            {"start": start + 60 * i, "end": start + 60 * (i + 1), "passengers": p}
            for i, p in enumerate([20, 90, 40, 10])
        ]
        d["protected_windows"] = []
    result = run_bundle(data, {"candidate_budget": 3})
    assert result["diagnostics"]["distinct_plans_generated"] <= 3


def test_time_of_day_runtime_and_terminal_specific_layover():
    data = validate_bundle(bundle())
    data["directions"]["outbound"]["runtime_periods"] = [
        {"start": 360, "end": 390, "minutes": 15},
        {"start": 390, "end": 421, "minutes": 25},
    ]
    data["layover_minutes"]["inbound"] = 7
    times = {"outbound": [360, 380, 400, 420], "inbound": [380, 400, 420, 440]}
    fleet = assign_fleet(data, times)
    rows = {t["trip_id"]: t for t in fleet["trips"]}
    assert rows["outbound-001"]["arrival"] == 375
    assert rows["outbound-001"]["ready"] == 382
    assert rows["outbound-003"]["arrival"] == 425
    validate_chains(data, times, fleet)


def test_unknown_input_constraint_is_not_silently_ignored():
    data = bundle()
    data["terminal_occupancy_limit"] = 1
    assert run_bundle(data)["status"] == "BLOCKED_INPUT"


def test_hard_capacity_policy_requires_capacity():
    data = bundle()
    data.update(capacity_policy="hard", maximum_load_factor=0.8)
    result = run_bundle(data)
    assert result["status"] == "BLOCKED_INPUT"
    assert "vehicle_capacity" in result["diagnostics"]["input_error"]


def test_unknown_nested_protection_is_blocked():
    data = bundle()
    data["directions"]["outbound"]["protected_windows"][0]["maximum_gap_minutes"] = 1
    assert run_bundle(data)["status"] == "BLOCKED_INPUT"


@pytest.mark.parametrize("settings", [[1], "abc", True])
def test_malformed_settings_return_blocked_input(settings):
    assert run_bundle(bundle(), settings)["status"] == "BLOCKED_INPUT"


def test_total_budget_applies_to_baseline_too():
    result = run_bundle(bundle(), {"total_seconds": 1e-9})
    assert result["recommended"] is None
    assert result["diagnostics"]["baseline_status"] == "TIME_LIMIT"
    assert result["diagnostics"]["evaluations"] == 0


def test_service_density_responds_to_demand_and_reports_response():
    data = bundle()
    data["fleet_ceiling"] = 20
    for d in data["directions"].values():
        d["last"] = d["first"] + 120
        d["trip_count"] = 13
        d["baseline"] = list(range(d["first"], d["last"] + 1, 10))
        d["protected_windows"] = []
        d["demand"] = [
            {"start": d["first"], "end": d["first"] + 60, "passengers": 240},
            {"start": d["first"] + 60, "end": d["last"], "passengers": 15},
        ]
    candidate = run_bundle(data, {"candidate_budget": 1})["recommended"]
    assert candidate is not None
    out = [r for r in candidate["regimes"] if r["direction"] == "outbound"]
    assert out[0]["headway_minutes"] < out[-1]["headway_minutes"]
    response = candidate["quality"]["demand_response"]["outbound"]
    assert response["aligned_transitions"] == 1


def test_independent_regime_check_rejects_tampered_membership_count():
    data = validate_bundle(bundle())
    selected = run_bundle(data)["recommended"]
    regimes = deepcopy(selected["regimes"])
    regimes[0]["planned_departure_count"] += 1
    assert not evaluate(data, selected["departures"], regimes)["hard_constraints_pass"]

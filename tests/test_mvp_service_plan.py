import json
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from bus_schedule_engine.mvp.circulation import assign_fleet, validate_chains
from bus_schedule_engine.mvp.input import validate_bundle
from bus_schedule_engine.mvp.planning import compile_plan, revise_plan
from bus_schedule_engine.mvp.quality import change_justification, evaluate, select_candidate
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
    assert result["status"] == "NO_CHANGE_RECOMMENDED"
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
    assert {p.name for p in tmp_path.iterdir()} == {
        "recommended_timetable.json",
        "service_regimes.json",
        "vehicle_chains.json",
        "quality_report.json",
        "run_diagnostics.json",
        "recommended_timetable.xlsx",
        "operational_review.html",
    }
    assert (
        json.loads((tmp_path / "recommended_timetable.json").read_text())["departures"]
        == selected["departures"]
    )
    workbook = load_workbook(tmp_path / "recommended_timetable.xlsx", data_only=True)
    assert workbook.sheetnames[:5] == [
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
    assert first["status"] == "NO_CHANGE_RECOMMENDED"
    assert first["search_status"] == "FEASIBLE_RECOMMENDATION"
    assert first["diagnostics"]["search_exhausted"]
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
    assert result["diagnostics"]["evaluations"] <= 3
    assert result["diagnostics"]["maximum_pending_plans"] <= 4 * 3


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
    result = run_bundle(data, {"candidate_budget": 1})
    candidate = result["alternatives"][0]
    assert candidate["change_assessment"]["reason"] == "FLEET_INCREASE_NOT_AUTHORIZED"
    assert candidate is not None
    out = [r for r in candidate["regimes"] if r["direction"] == "outbound"]
    assert out[0]["headway_minutes"] < out[-1]["headway_minutes"]
    response = candidate["quality"]["demand_response"]["outbound"]
    assert response["aligned_transitions"] == 1


def test_independent_regime_check_rejects_tampered_membership_count():
    data = validate_bundle(bundle())
    selected = compile_plan(data["directions"]["outbound"], [{"end": 420, "gaps": 3}], {})
    inbound = compile_plan(data["directions"]["inbound"], [{"end": 440, "gaps": 3}], {})
    times = {"outbound": selected["departures"], "inbound": inbound["departures"]}
    selected["regimes"][0]["direction"] = "outbound"
    inbound["regimes"][0]["direction"] = "inbound"
    selected["regimes"] += inbound["regimes"]
    regimes = deepcopy(selected["regimes"])
    regimes[0]["planned_departure_count"] += 1
    assert not evaluate(data, times, regimes)["hard_constraints_pass"]


def policy_candidate(wait=10, fleet=2, valid=True, source="OPTIMIZED"):
    return {
        "id": source,
        "source": source,
        "departures": {"outbound": [0, 20, 40], "inbound": [20, 40, 60]},
        "quality": {
            "hard_constraints_pass": valid,
            "waiting_minutes": wait,
            "directional_waiting_minutes": dict.fromkeys(("outbound", "inbound"), wait),
            "required_fleet": fleet,
            "maximum_protected_gap": 20,
            "protected_windows": [],
            "regime_count": 2,
            "transition_jump": 0,
            "terminal_wait": 0,
            "tail_gap": 20,
        },
    }


@pytest.mark.parametrize(
    "wait,fleet,expected",
    [
        (10.01, 2, False),
        (10, 2, False),
        (10.1, 1, True),
        (10.21, 1, False),
        (9.8, 2, True),
        (9.99, 2, False),
        (9.8, 3, False),
    ],
)
def test_baseline_change_requires_material_service_or_equivalent_fleet_saving(
    wait, fleet, expected
):
    baseline = policy_candidate(source="BASELINE")
    candidate = policy_candidate(wait, fleet)
    evidence = change_justification(candidate, baseline, {})
    assert evidence["justified"] is expected
    assert select_candidate([candidate], {}, baseline) is (candidate if expected else baseline)


def test_directional_deterioration_cannot_hide_in_combined_average():
    baseline = policy_candidate(source="BASELINE")
    candidate = policy_candidate(9.8, 1)
    candidate["quality"]["directional_waiting_minutes"]["inbound"] = 11
    assert not change_justification(candidate, baseline, {})["justified"]


def test_noncompliant_baseline_requires_valid_replacement():
    baseline = policy_candidate(valid=False, source="BASELINE")
    candidate = policy_candidate(11, 2)
    assert select_candidate([candidate], {}, baseline) is candidate
    candidate["quality"]["hard_constraints_pass"] = False
    assert select_candidate([candidate], {}, baseline) is None


def test_irregular_baseline_retained_with_actual_exports(tmp_path):
    data = bundle()
    data["fleet_ceiling"] = 8
    for d in data["directions"].values():
        d["baseline"][1] -= 1
        d["protected_windows"] = []
    result = run_bundle(data, {"candidate_budget": 1})
    assert result["status"] == "NO_CHANGE_RECOMMENDED"
    assert result["recommended"]["source"] == "BASELINE"
    assert result["recommended"]["regimes"] == []
    assert result["recommended"]["quality"]["regime_count"] is None
    assert result["recommended"]["departures"] == {
        d: v["baseline"] for d, v in data["directions"].items()
    }
    validate_chains(
        validate_bundle(data),
        result["recommended"]["departures"],
        result["recommended"]["vehicle_chains"],
    )
    export_result(result, tmp_path)
    exported = json.loads((tmp_path / "recommended_timetable.json").read_text())
    assert exported["selected_source"] == "BASELINE"
    assert json.loads((tmp_path / "service_regimes.json").read_text()) == []
    wb = load_workbook(tmp_path / "recommended_timetable.xlsx", data_only=True)
    assert wb["QualityComparison"]["C3"].value == "BASELINE"
    assert [r[1] for r in wb["Outbound"].iter_rows(min_row=2, values_only=True)] == exported[
        "departures"
    ]["outbound"]


def test_baseline_fixed_count_and_hard_transition_are_checked():
    data = bundle()
    data["directions"]["outbound"]["trip_count"] = 5
    result = run_bundle(data, {"candidate_budget": 1})
    assert not result["baseline"]["hard_constraints_pass"]
    assert result.get("selected_source") != "BASELINE"
    data = bundle()
    data["directions"]["outbound"]["baseline"][1] -= 5
    data["directions"]["outbound"]["protected_windows"] = []
    result = run_bundle(data, {"candidate_budget": 1, "maximum_transition_jump": 1})
    assert "HARD_TRANSITION_JUMP" in result["baseline"]["failures"]
    assert result["selected_source"] == "OPTIMIZED"


def targeted_fixture():
    data = bundle()
    data["fleet_ceiling"] = 20
    for d in data["directions"].values():
        start = d["first"]
        d.update(
            last=start + 120,
            trip_count=9,
            baseline=list(range(start, start + 121, 15)),
            protected_windows=[],
        )
        d["demand"] = [
            {"start": start, "end": start + 60, "passengers": 600},
            {"start": start + 60, "end": start + 120, "passengers": 1},
        ]
    return validate_bundle(data)


def test_bucket_feedback_uses_absolute_exposure_and_integrates_exact_wait():
    data = targeted_fixture()
    times = {
        d: [v["first"] + t for t in [0, 30, 60, 70, 80, 90, 100, 110, 120]]
        for d, v in data["directions"].items()
    }
    q = evaluate(data, times, [])
    rows = q["demand_buckets"]
    assert rows[0]["waiting_integral"] == pytest.approx(9000)
    assert rows[0]["baseline_waiting_minutes"] == pytest.approx(7.5)
    assert rows[0]["waiting_difference_minutes"] == pytest.approx(7.5)
    assert rows[0]["maximum_intersecting_gap"] == 30
    assert sum(b["waiting_contribution_minutes"] for b in rows) == pytest.approx(
        q["waiting_minutes"]
    )
    assert q["service_feedback"][0]["problem"] == "EXCESS_WAIT_VS_BASELINE"
    assert q["service_feedback"][0]["severity"] == pytest.approx(4500)


def test_protected_and_capacity_feedback_identifies_responsible_gap():
    data = targeted_fixture()
    start = data["directions"]["outbound"]["first"]
    data["directions"]["outbound"]["protected_windows"] = [
        {"start": start, "end": start + 60, "max_gap": 15}
    ]
    data.update(vehicle_capacity=100, maximum_load_factor=0.8, capacity_policy="hard")
    times = {
        d: [v["first"] + t for t in [0, 30, 60, 70, 80, 90, 100, 110, 120]]
        for d, v in data["directions"].items()
    }
    q = evaluate(data, times, [])
    assert q["service_feedback"][0]["problem"] == "PROTECTED_SERVICE"
    item = next(
        f
        for f in q["service_feedback"]
        if f["problem"] == "CAPACITY_PROXY" and f["direction"] == "outbound"
    )
    assert (item["interval_start"], item["interval_end"]) == (start, start + 30)
    assert item["modeled_boardings"] == 300
    assert item["threshold"] == 80
    assert item["severity"] == 220
    assert q["capacity"]["actual_load_factor_certified"] is False


def test_low_demand_relative_error_does_not_dominate_revision_priority():
    data = targeted_fixture()
    times = {
        d: [v["first"] + t for t in [0, 20, 40, 60, 61, 62, 63, 64, 120]]
        for d, v in data["directions"].items()
    }
    q = evaluate(data, times, [])
    ordinary = [f for f in q["service_feedback"] if f["problem"] == "EXCESS_WAIT_VS_BASELINE"]
    assert ordinary[0]["interval_end"] - ordinary[0]["interval_start"] == 60
    assert ordinary[0]["interval_start"] == data["directions"][ordinary[0]["direction"]]["first"]
    assert ordinary[0]["severity"] > ordinary[-1]["severity"]


def test_targeted_reallocation_and_boundary_neighbors_improve_peak():
    data = targeted_fixture()["directions"]["outbound"]
    plan = [{"end": data["first"] + 60, "gaps": 4}, {"end": data["last"], "gaps": 4}]
    feedback = [
        {
            "direction": "outbound",
            "interval_start": data["first"],
            "interval_end": data["first"] + 60,
            "problem": "EXCESS_WAIT_VS_BASELINE",
            "priority": 2,
            "severity": 100,
        }
    ]
    neighbors = revise_plan(data, plan, feedback, {})
    assert neighbors[0][0] == "reallocate_trip"
    assert neighbors[0][1][0]["gaps"] == 5
    shifted = next(p for name, p in neighbors if name == "shift_boundary")
    assert shifted[0]["end"] < plan[0]["end"]
    old = compile_plan(data, plan, {})
    new = compile_plan(data, neighbors[0][1], {})
    assert old["status"] == new["status"] == "COMPILED"
    from bus_schedule_engine.mvp.quality import waiting

    assert (
        waiting(new["departures"], data["demand"])["wait"]
        < waiting(old["departures"], data["demand"])["wait"]
    )


def test_search_directional_fairness_and_operation_diversity():
    data = targeted_fixture()
    result = run_bundle(data)
    operations = [f["operation"] for f in result["diagnostics"]["feedback"]][1:]
    directions = [op.split(":")[0] for op in operations]
    assert directions.count("outbound") >= 4
    assert directions.count("inbound") >= 4
    assert abs(directions.count("outbound") - directions.count("inbound")) <= 1
    assert len({op.split(":")[1] for op in operations}) >= 2
    assert result["diagnostics"]["demand_guided_evaluations"] > 0
    assert result["diagnostics"]["evaluations"] == 25
    assert result == run_bundle(data)


def test_strict_proxy_exhaustion_is_incomplete_not_proven_infeasible():
    data = bundle()
    data.update(vehicle_capacity=20, maximum_load_factor=0.8, capacity_policy="hard")
    result = run_bundle(data)
    assert result["status"] == "SEARCH_INCOMPLETE_NO_FEASIBLE_CANDIDATE"
    assert result["diagnostics"]["global_optimality_proved"] is False
    assert result["baseline"]["capacity"]["within_policy"] is False
    assert result["diagnostics"]["remaining_service_violations"]


def test_material_protected_gap_improvement_can_justify_equivalent_service():
    baseline = policy_candidate(source="BASELINE")
    candidate = policy_candidate()
    baseline["quality"]["protected_windows"] = [{"maximum_gap": 20}]
    candidate["quality"]["protected_windows"] = [{"maximum_gap": 15}]
    assert (
        change_justification(candidate, baseline, {})["reason"]
        == "MATERIAL_PROTECTED_SERVICE_IMPROVEMENT"
    )
    candidate["quality"]["waiting_minutes"] = 11
    assert not change_justification(candidate, baseline, {})["justified"]


def test_uncertified_baseline_is_not_treated_as_proved_noncompliant():
    baseline = policy_candidate(valid=False, source="BASELINE")
    baseline["quality"]["operational_certification"] = "INCOMPLETE"
    assert not change_justification(policy_candidate(), baseline, {})["justified"]
    assert select_candidate([policy_candidate()], {}, baseline) is None


def test_fleet_pressure_feedback_targets_exact_peak_and_revisions():
    data = validate_bundle(bundle())
    data["fleet_ceiling"] = 1
    times = {d: v["baseline"] for d, v in data["directions"].items()}
    q = evaluate(data, times, [])
    item = next(f for f in q["service_feedback"] if f["problem"] == "FLEET_PRESSURE")
    assert item["severity"] == 1
    assert item["required_fleet"] == 2
    assert item["overlapping_trip_ids"]
    assert "SHIFT_BOUNDARY" in item["recommended_revision_types"]


def test_boundary_shift_alone_improves_a_known_peak():
    from bus_schedule_engine.mvp.quality import waiting

    direction = targeted_fixture()["directions"]["outbound"]
    direction["demand"] = [
        {"start": 360, "end": 390, "passengers": 600},
        {"start": 390, "end": 480, "passengers": 1},
    ]
    plan = [{"end": 405, "gaps": 4}, {"end": 480, "gaps": 4}]
    feedback = [
        {
            "interval_start": 360,
            "interval_end": 390,
            "problem": "EXCESS_WAIT_VS_BASELINE",
            "priority": 2,
            "severity": 600,
        }
    ]
    shifted = next(
        p for name, p in revise_plan(direction, plan, feedback, {}) if name == "shift_boundary"
    )
    old, new = compile_plan(direction, plan, {}), compile_plan(direction, shifted, {})
    assert old["status"] == new["status"] == "COMPILED"
    assert (
        waiting(new["departures"], direction["demand"])["wait"]
        < waiting(old["departures"], direction["demand"])["wait"]
    )


def test_custom_materiality_rejects_tiny_improvement_and_settings_are_validated():
    baseline = policy_candidate(source="BASELINE")
    assert not change_justification(
        policy_candidate(9.8), baseline, {"wait_materiality_minutes": 0.3}
    )["justified"]
    assert run_bundle(bundle(), {"wait_materiality_relative": -1})["status"] == "BLOCKED_INPUT"


def test_unproved_baseline_fleet_leaves_operator_decision_unresolved(monkeypatch):
    from bus_schedule_engine.mvp import runner

    original, calls = runner.assign_fleet, []

    def assignment(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            return {"status": "MINIMUM_FLEET_UNPROVED", "required_fleet": None, "trips": []}
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "assign_fleet", assignment)
    result = run_bundle(bundle(), {"candidate_budget": 1})
    assert result["recommended"] is None
    assert result["operator_decision"] == "UNRESOLVED"
    assert result["status"] == "BASELINE_COMPARISON_INCOMPLETE"
    assert result["search_status"] == "FEASIBLE_BUDGET_LIMITED"
    assert result["diagnostics"]["baseline_status"] == "INCOMPLETE"
    assert result["diagnostics"]["budget_limited"]


def test_protected_tail_precedes_high_demand_wait_in_revision_order():
    direction = targeted_fixture()["directions"]["outbound"]
    plan = [{"end": 420, "gaps": 4}, {"end": 480, "gaps": 4}]
    feedback = [
        {
            "interval_start": 360,
            "interval_end": 420,
            "problem": "EXCESS_WAIT_VS_BASELINE",
            "priority": 2,
            "severity": 5000,
        },
        {
            "interval_start": 420,
            "interval_end": 480,
            "problem": "PROTECTED_SERVICE",
            "priority": 0,
            "severity": 1,
        },
    ]
    name, changed = revise_plan(direction, plan, feedback, {})[0]
    assert name == "reallocate_trip"
    assert changed[1]["gaps"] == 5


def test_optimized_source_and_exact_regimes_exported(tmp_path):
    data = bundle()
    data["directions"]["outbound"]["baseline"][1] -= 5
    result = run_bundle(data, {"candidate_budget": 1})
    assert result["selected_source"] == "OPTIMIZED"
    assert result["decision"]["reason"] == "REPLACE_NONCOMPLIANT_BASELINE"
    export_result(result, tmp_path)
    assert (
        json.loads((tmp_path / "recommended_timetable.json").read_text())["selected_source"]
        == "OPTIMIZED"
    )
    assert len(json.loads((tmp_path / "service_regimes.json").read_text())) == 2


def test_explicit_zero_demand_does_not_hide_protected_service_benefit():
    data = bundle()
    data["fleet_ceiling"] = 8
    candidate_times = {}
    for direction, d in data["directions"].items():
        start = d["first"]
        d.update(
            last=start + 180,
            trip_count=10,
            baseline=[start + t for t in [0, 30, 60, 90, 100, 110, 120, 140, 160, 180]],
            demand=[{"start": start, "end": start + 180, "passengers": 0}],
            protected_windows=[{"start": start, "end": start + 60, "max_gap": 30}],
        )
        candidate_times[direction] = [start + t for t in [0, 20, 40, 60, 70, 80, 90, 120, 150, 180]]
    data = validate_bundle(data)
    baseline_times = {d: v["baseline"] for d, v in data["directions"].items()}
    baseline = {"quality": evaluate(data, baseline_times, [])}
    candidate = {"quality": evaluate(data, candidate_times, [])}
    assert baseline["quality"]["waiting_minutes"] is None
    assert baseline["quality"]["required_fleet"] == candidate["quality"]["required_fleet"] == 4
    assert (
        change_justification(candidate, baseline, {})["reason"]
        == "MATERIAL_PROTECTED_SERVICE_IMPROVEMENT"
    )
    unknown = policy_candidate(wait=None, source="BASELINE")
    assert not change_justification(policy_candidate(wait=None), unknown, {})["justified"]


def test_proven_baseline_service_failure_allows_replacement_even_if_fleet_unproved(monkeypatch):
    from bus_schedule_engine.mvp import runner

    original, calls = runner.assign_fleet, []

    def assignment(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            return {"status": "MINIMUM_FLEET_UNPROVED", "required_fleet": None, "trips": []}
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "assign_fleet", assignment)
    data = bundle()
    data["directions"]["outbound"]["baseline"][1] -= 5
    result = run_bundle(data, {"candidate_budget": 1})
    assert result["recommended"]["source"] == "OPTIMIZED"
    assert result["decision"]["reason"] == "REPLACE_NONCOMPLIANT_BASELINE"
    assert "outbound: PROTECTED_SERVICE" in result["baseline"]["proven_hard_failures"]
    assert result["diagnostics"]["baseline_status"] == "INCOMPLETE"

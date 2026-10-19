"""Joint scheduling regressions with hand-checkable two-terminal circulations."""

from copy import deepcopy

import pytest

from bus_schedule_engine.mvp.circulation import assign_fleet, validate_chains
from bus_schedule_engine.mvp.input import validate_bundle
from bus_schedule_engine.mvp.planning import compile_plan
from bus_schedule_engine.mvp.runner import _settings, run_bundle

PLAN = [{"end": 20, "gaps": 2}, {"end": 60, "gaps": 2}]
JOINT = {"directional_settlements": 4, "compilation_lookahead": 256}


def bundle():
    return {
        "route_id": "joint-synthetic",
        "provenance": {"source": "hand-checked alternating terminals, 15-minute trips"},
        "demand_basis": "independent_arrivals",
        "fleet_ceiling": 2,
        "layover_minutes": {"outbound": 0, "inbound": 0},
        "directions": {
            d: {
                "first": 0,
                "last": 60,
                "trip_count": 5,
                "baseline": [0, 15, 30, 45, 60],
                "runtime_minutes": 15,
                "demand": [
                    {"start": 0, "end": 20, "passengers": 90},
                    {"start": 20, "end": 60, "passengers": 10},
                ],
                "protected_windows": [{"start": 0, "end": 60, "max_gap": 20}],
            }
            for d in ("outbound", "inbound")
        },
    }


def test_kbest_keeps_distinct_legal_vectors_and_local_service_alternative():
    d = bundle()["directions"]["outbound"]
    settings = _settings(JOINT | {"minimum_regime_minutes": 0})
    compiled = compile_plan(d, PLAN, settings)
    vectors = [tuple(c["departures"]) for c in compiled["settlements"]]
    assert 2 <= len(vectors) <= 4
    assert len(vectors) == len(set(vectors))
    assert (0, 10, 20, 40, 60) in vectors
    assert (0, 15, 30, 45, 60) in vectors
    assert compiled["settlement_previews"] <= 256
    for c in compiled["settlements"]:
        assert len(c["departures"]) == 5
        assert c["departures"][0] == 0 and c["departures"][-1] == 60
        assert all(r["gap_count"] >= 2 for r in c["regimes"])
        assert max(b - a for a, b in zip(c["departures"], c["departures"][1:], strict=False)) <= 20
    assert compiled == compile_plan(d, PLAN, settings)


def test_directional_wait_winner_requires_four_vehicles_but_regular_pair_needs_two():
    data = validate_bundle(bundle())
    best = dict.fromkeys(data["directions"], [0, 10, 20, 40, 60])
    regular = dict.fromkeys(data["directions"], [0, 15, 30, 45, 60])
    assert assign_fleet(data, best)["required_fleet"] == 4
    fleet = assign_fleet(data, regular)
    # Two simultaneous first trips require >=2 vehicles; both alternate every 15 minutes.
    assert fleet["required_fleet"] == 2
    validate_chains(data, regular, fleet)


def test_joint_runner_recovers_feasible_pair_and_does_not_repeat_exact_pairs():
    settings = JOINT | {"minimum_regime_minutes": 0, "candidate_budget": 8}
    data = bundle()
    for d in data["directions"].values():
        d["baseline"] = [0, 10, 20, 40, 60]
    result = run_bundle(data, settings)
    assert result["recommended"]["quality"]["required_fleet"] == 2
    assert result["recommended"]["source"] == "OPTIMIZED"
    assert result["diagnostics"]["exact_pair_evaluations"] > 1
    assert result["diagnostics"]["duplicate_schedules"] > 0
    assert result["diagnostics"]["directional_compilation_cache_hits"] > 0
    pairs = [p for f in result["diagnostics"]["feedback"] for p in f.get("pairs", [])]
    assert any(p["quality"]["required_fleet"] == 4 for p in pairs if p.get("quality"))
    unique = [p for p in pairs if p["candidate_status"] != "DUPLICATE_TIMETABLE"]
    assert len(unique) == result["diagnostics"]["exact_pair_evaluations"]
    for p in unique:
        if p.get("candidate"):
            c = p["candidate"]
            validate_chains(validate_bundle(bundle()), c["departures"], c["vehicle_chains"])
    assert result == run_bundle(data, settings)


@pytest.mark.parametrize(
    "name,value",
    [
        ("directional_settlements", 0),
        ("directional_settlements", 5),
        ("pair_evaluation_budget", True),
        ("pair_evaluation_budget", 0),
        ("pairs_per_plan", 0),
        ("pairs_per_plan", 17),
    ],
)
def test_joint_resource_settings_are_validated(name, value):
    with pytest.raises(ValueError, match=name):
        _settings({name: value})


def test_pair_budget_is_separate_from_plan_budget_and_never_claims_infeasibility():
    result = run_bundle(
        bundle(), JOINT | {"pair_evaluation_budget": 1, "minimum_regime_minutes": 0}
    )
    assert result["diagnostics"]["exact_pair_evaluations"] == 1
    assert result["diagnostics"]["evaluations"] <= 25
    assert result["diagnostics"]["search_limit_reason"] == "PAIR_EVALUATION_BUDGET"
    assert result["status"] != "PROVEN_INFEASIBLE"
    assert result["diagnostics"]["unexamined_retained_pairs"] > 0


def test_pair_key_separates_runtime_layover_stock_protection_demand_and_ceiling():
    from bus_schedule_engine.mvp.joint import pair_key

    data = validate_bundle(bundle())
    times = {d: v["baseline"] for d, v in data["directions"].items()}
    original = pair_key(data, times, {}, {})
    for field in ("runtime", "layover", "stock", "protection", "demand", "ceiling"):
        changed = deepcopy(data)
        if field == "runtime":
            changed["directions"]["outbound"]["runtime_minutes"] = 16
        elif field == "layover":
            changed["layover_minutes"]["inbound"] = 1
        elif field == "stock":
            changed["initial_vehicles"] = {"outbound": 1, "inbound": 1}
        elif field == "protection":
            changed["directions"]["outbound"]["protected_windows"][0]["max_gap"] = 15
        elif field == "demand":
            changed["directions"]["outbound"]["demand"][0]["passengers"] = 91
        else:
            changed["fleet_ceiling"] = 3
        assert pair_key(changed, times, {}, {}) != original
    assert pair_key(data, times | {"outbound": [0, 10, 20, 40, 60]}, {}, {}) != original


def test_runtime_scenarios_have_independent_exact_calculations():
    a = bundle()
    b = deepcopy(a)
    for d in b["directions"].values():
        d["runtime_minutes"] = 16
    settings = JOINT | {"candidate_budget": 1, "minimum_regime_minutes": 0}
    p50, p75 = run_bundle(a, settings), run_bundle(b, settings)
    assert p50["baseline"]["required_fleet"] == 2
    assert p75["baseline"]["required_fleet"] == 4
    assert p50["diagnostics"]["exact_pair_evaluations"] > 0
    assert p75["diagnostics"]["exact_pair_evaluations"] > 0


def test_verified_incumbent_is_recomputed_and_recoverable_even_with_one_pair_budget():
    data = bundle()
    seed = {
        "departures": {d: v["baseline"] for d, v in data["directions"].items()},
        "regimes": [
            {
                "direction": d,
                "start_time": 0,
                "end_time": 60,
                "headway_minutes": 15,
                "gap_count": 4,
                "planned_departure_count": 5,
                "regime_type": "end_tail",
            }
            for d in data["directions"]
        ],
    }
    bad_baseline = [0, 10, 20, 40, 60]
    for d in data["directions"].values():
        d["baseline"] = bad_baseline
    result = run_bundle(
        data, JOINT | {"pair_evaluation_budget": 1, "minimum_regime_minutes": 0}, incumbents=[seed]
    )
    c = result["recommended"]
    assert c["id"] == "I001"
    assert c["quality"]["required_fleet"] == 2
    assert result["diagnostics"]["incumbents"][0]["quality"]["hard_constraints_pass"]
    validate_chains(validate_bundle(data), c["departures"], c["vehicle_chains"])
    # The same seed fails a distinct longer-runtime scenario: never trust its old fleet.
    for d in data["directions"].values():
        d["runtime_minutes"] = 16
    longer = run_bundle(
        data, JOINT | {"pair_evaluation_budget": 1, "minimum_regime_minutes": 0}, incumbents=[seed]
    )
    assert longer["recommended"] is None
    assert longer["diagnostics"]["incumbents"][0]["quality"]["required_fleet"] == 4


def test_local_deterioration_changes_equivalent_selection_without_hard_rejection():
    from bus_schedule_engine.mvp.joint import local_evidence
    from bus_schedule_engine.mvp.quality import evaluate, select_candidate

    data = validate_bundle(bundle())
    data["fleet_ceiling"] = 4
    for d in data["directions"].values():
        d["protected_windows"] = []
        del d["runtime_minutes"]
        d["runtime_periods"] = [
            {"start": 0, "end": 15, "minutes": 5},
            {"start": 15, "end": 20, "minutes": 20},
            {"start": 20, "end": 61, "minutes": 5},
        ]
    times = {d: v["baseline"] for d, v in data["directions"].items()}
    baseline = {"departures": times}
    candidates = []
    for label, vector in (("regular", [0, 15, 30, 45, 60]), ("wait_winner", [0, 10, 20, 40, 60])):
        deps = dict.fromkeys(data["directions"], vector)
        fleet = assign_fleet(data, deps)
        c = {
            "id": label,
            "departures": deps,
            "regimes": [],
            "vehicle_chains": fleet,
            "quality": evaluate(data, deps, [], fleet),
        }
        local_evidence(data, c, baseline, None, {})
        candidates.append(c)
    assert all(c["quality"]["hard_constraints_pass"] for c in candidates)
    assert [c["quality"]["required_fleet"] for c in candidates] == [4, 2]
    # The wider declared equivalence exposes the local-service tie breaker.
    settings = JOINT | {"wait_absolute_tolerance": 4}
    assert select_candidate(candidates, {"wait_absolute_tolerance": 4})["id"] == "wait_winner"
    assert select_candidate(candidates, settings)["id"] == "regular"
    assert select_candidate([candidates[1]], settings)["id"] == "wait_winner"


def test_no_retained_settlement_can_relax_explicit_protection_or_transitions():
    d = bundle()["directions"]["outbound"]
    d["protected_windows"] = [{"start": 0, "end": 60, "max_gap": 14}]
    settings = _settings(JOINT | {"minimum_regime_minutes": 0})
    assert compile_plan(d, PLAN, settings)["status"] == "NO_LEGAL_SETTLEMENT"
    d["protected_windows"][0]["max_gap"] = 20
    result = compile_plan(d, PLAN, settings | {"maximum_transition_jump": 0})
    assert [c["departures"] for c in result["settlements"]] == [[0, 15, 30, 45, 60]]


def test_initial_stock_is_enforced_in_joint_mode():
    data = bundle()
    data["initial_vehicles"] = {"outbound": 0, "inbound": 2}
    result = run_bundle(data, JOINT | {"candidate_budget": 1, "minimum_regime_minutes": 0})
    assert result["recommended"] is None
    pairs = result["diagnostics"]["feedback"][0]["pairs"]
    assert all(p["fleet_status"] == "INITIAL_STOCK_INFEASIBLE" for p in pairs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("gap_count", 3),
        ("gap_count", True),
        ("headway_minutes", "15"),
        ("direction", "other"),
        ("regime_type", None),
    ],
)
def test_malformed_incumbent_regimes_cannot_poison_exact_vector_cache(field, value):
    data = bundle()
    seed = {
        "departures": {d: v["baseline"] for d, v in data["directions"].items()},
        "regimes": [
            {
                "direction": d,
                "start_time": 0,
                "end_time": 60,
                "headway_minutes": 15,
                "gap_count": 4,
                "planned_departure_count": 5,
                "regime_type": "end_tail",
            }
            for d in data["directions"]
        ],
    }
    seed["regimes"][0][field] = value
    result = run_bundle(data, JOINT | {"minimum_regime_minutes": 0}, incumbents=[seed])
    assert result["status"] == "BLOCKED_INPUT"
    assert "incumbent" in result["diagnostics"]["input_error"]


def test_diversity_retains_best_protected_service_outcome():
    d = bundle()["directions"]["outbound"]
    d["baseline"] = [0, 18, 36, 48, 60]
    result = compile_plan(
        d,
        [{"end": 36, "gaps": 2}, {"end": 60, "gaps": 2}],
        _settings(JOINT | {"minimum_regime_minutes": 0}),
    )
    assert [0, 15, 30, 45, 60] in [c["departures"] for c in result["settlements"]]


def test_unexamined_pairs_excludes_a_previously_validated_incumbent_vector():
    data = bundle()
    seed = {
        "departures": dict.fromkeys(data["directions"], [0, 10, 20, 40, 60]),
        "regimes": [
            {
                "direction": d,
                "start_time": a,
                "end_time": b,
                "headway_minutes": h,
                "gap_count": 2,
                "planned_departure_count": n,
                "regime_type": "normal",
            }
            for d in data["directions"]
            for a, b, h, n in [(0, 20, 10, 2), (20, 60, 20, 3)]
        ],
    }
    result = run_bundle(
        data, JOINT | {"minimum_regime_minutes": 0, "pair_evaluation_budget": 1}, incumbents=[seed]
    )
    assert result["diagnostics"]["unexamined_retained_pairs"] == 15


def test_joint_compilation_checks_deadline_during_diversity_scoring(monkeypatch):
    from bus_schedule_engine.mvp import joint

    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        return 0 if calls == 1 else 100

    monkeypatch.setattr(joint, "monotonic", clock, raising=False)
    settings = _settings(JOINT | {"minimum_regime_minutes": 0})
    result = compile_plan(bundle()["directions"]["outbound"], PLAN, settings, deadline=50)
    assert result["status"] == "SOLVER_LIMIT"
    assert result["directional_scoring_complete"] is False


def test_equivalent_incumbent_regime_labels_are_canonical_before_vector_caching():
    data = bundle()
    seed = {
        "departures": {d: v["baseline"] for d, v in data["directions"].items()},
        "regimes": [
            {
                "direction": d,
                "start_time": a,
                "end_time": b,
                "headway_minutes": 15,
                "gap_count": 2,
                "planned_departure_count": n,
                "regime_type": "normal",
            }
            for d in data["directions"]
            for a, b, n in [(0, 30, 2), (30, 60, 3)]
        ],
    }
    result = run_bundle(
        data, JOINT | {"minimum_regime_minutes": 0, "pair_evaluation_budget": 1}, incumbents=[seed]
    )
    assert result["diagnostics"]["incumbents"][0]["quality"]["regime_count"] == 2
    assert result["diagnostics"]["exact_pair_evaluations"] == 1

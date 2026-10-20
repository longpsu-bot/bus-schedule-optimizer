"""Independent small matching witnesses and regime-generation regressions."""

from copy import deepcopy

import pytest

from bus_schedule_engine.mvp.circulation import assign_fleet, validate_chains
from bus_schedule_engine.mvp.input import validate_bundle
from bus_schedule_engine.mvp.planning import compile_plan
from bus_schedule_engine.mvp.runner import _settings, run_bundle


def allocation_case():
    return {
        "route_id": "fleet-allocation-witness",
        "provenance": {"source": "two terminals, simultaneous starts, 15-minute travel"},
        "demand_basis": "independent_arrivals",
        "fleet_ceiling": 2,
        "layover_minutes": {"outbound": 0, "inbound": 0},
        "directions": {
            d: {
                "first": 0,
                "last": 120,
                "trip_count": 9,
                "baseline": [0, 10, 20, 30, 40, 50, 60, 90, 120],
                "runtime_minutes": 15,
                "demand": [
                    {"start": 0, "end": 60, "passengers": 81},
                    {"start": 60, "end": 120, "passengers": 1},
                ],
                "protected_windows": [{"start": 0, "end": 120, "max_gap": 30}],
            }
            for d in ("outbound", "inbound")
        },
    }


def test_matching_feedback_exposes_residual_bridges_without_mutating_assignment():
    from bus_schedule_engine.mvp.fleet_feedback import fleet_pressure

    data = validate_bundle(allocation_case())
    times = {d: v["baseline"] for d, v in data["directions"].items()}
    fleet = assign_fleet(data, times)
    original = deepcopy(fleet)
    evidence = fleet_pressure(data, fleet)
    assert fleet["required_fleet"] == 4
    assert evidence["matching_size"] == 14
    assert evidence["fleet_deficit"] == 2
    assert len(evidence["chain_starts"]) == 4
    assert len(evidence["chain_ends"]) == 4
    # The dense early peak needs coordinated changes; no single forward edge suffices.
    assert not any(e["augmenting_bridge"] for e in evidence["missed_connections"])
    assert min(e["minutes_late"] for e in evidence["missed_connections"]) == 5
    assert evidence["feasibility_prediction"] is False
    assert fleet == original
    assert evidence == fleet_pressure(data, fleet)


def test_residual_bridge_can_lose_another_link_when_trip_time_changes():
    from bus_schedule_engine.mvp.fleet_feedback import fleet_pressure

    data = validate_bundle(allocation_case())
    times = {"outbound": [0, 30], "inbound": [16, 45]}
    fleet = assign_fleet(data, times)
    evidence = fleet_pressure(data, fleet)
    bridge = next(e for e in evidence["missed_connections"] if e["augmenting_bridge"])
    assert (bridge["from_trip"], bridge["to_trip"], bridge["minutes_late"]) == (
        "inbound-001",
        "outbound-002",
        1,
    )
    # Delaying O2 closes I1 -> O2 but breaks O2 -> I2, so fleet stays at two.
    assert assign_fleet(data, times | {"outbound": [0, 31]})["required_fleet"] == 2


def test_feedback_requires_exact_matching_and_does_not_overclaim_stock_evidence():
    from bus_schedule_engine.mvp.fleet_feedback import fleet_pressure

    data = validate_bundle(allocation_case())
    assert fleet_pressure(data, {"status": "SOLVER_LIMIT"})["status"] == "UNAVAILABLE"
    times = {d: v["baseline"] for d, v in data["directions"].items()}
    fleet = assign_fleet(data, times)
    data["initial_vehicles"] = {"outbound": 3, "inbound": 3}
    assert fleet_pressure(data, fleet)["residual_basis"] == "UNCONSTRAINED_MATCHING_ONLY"


def test_fixed_headway_plan_is_compiled_exactly_and_validates_input():
    direction = validate_bundle(allocation_case())["directions"]["outbound"]
    plan = [
        {"end": 60, "gaps": 4, "headway_minutes": 15},
        {"end": 120, "gaps": 4, "headway_minutes": 15},
    ]
    result = compile_plan(direction, plan, _settings({"compilation_lookahead": 256}))
    assert result["departures"] == list(range(0, 121, 15))
    invalid = deepcopy(plan)
    invalid[0]["headway_minutes"] = True
    assert compile_plan(direction, invalid, _settings(None))["status"] == "INVALID_PLAN"
    invalid[0]["headway_minutes"] = 14
    assert compile_plan(direction, invalid, _settings(None))["status"] == "FAMILY_INFEASIBLE"


def test_coordinated_regime_generation_reduces_exact_fleet_under_same_plan_budget():
    data = allocation_case()
    settings = {
        "candidate_budget": 2,
        "directional_settlements": 4,
        "compilation_lookahead": 256,
        "pairs_per_plan": 6,
        "boundary_settlement_minutes": 0,
        "maximum_regimes": 2,
    }
    control = run_bundle(data, settings)
    assert control["recommended"] is None
    guided = run_bundle(data, settings | {"fleet_guided": True})
    c = guided["recommended"]
    assert c is not None
    assert c["quality"]["required_fleet"] == 2
    # Two simultaneous first trips prove the lower bound. Two alternating chains attain it.
    assert c["departures"] == dict.fromkeys(data["directions"], list(range(0, 121, 15)))
    validate_chains(validate_bundle(data), c["departures"], c["vehicle_chains"])
    assert all(r["gap_count"] >= 2 and type(r["headway_minutes"]) is int for r in c["regimes"])
    assert c["quality"]["hard_constraints_pass"]
    diag = guided["diagnostics"]
    assert diag["evaluations"] == control["diagnostics"]["evaluations"] == 2
    assert diag["exact_pair_evaluations"] <= 160
    assert diag["fleet_guided_evaluations"] == 1
    assert diag["fleet_guided_fleet_improvements"] >= 1
    old_plans = [f["plans"] for f in control["diagnostics"]["feedback"]]
    assert diag["feedback"][1]["plans"] not in old_plans
    assert diag["feedback"][1]["fleet_guidance"]["directions_changed"] == 2
    assert guided == run_bundle(data, settings | {"fleet_guided": True})


@pytest.mark.parametrize("value", [1, "yes", None])
def test_fleet_feedback_setting_is_boolean(value):
    assert run_bundle(allocation_case(), {"fleet_guided": value})["status"] == "BLOCKED_INPUT"


def test_guided_feedback_deadline_and_hard_guardrails_are_preserved():
    from bus_schedule_engine.mvp.fleet_feedback import fleet_pressure, fleet_revisions

    data = validate_bundle(allocation_case())
    settings = _settings(
        {
            "directional_settlements": 4,
            "fleet_guided": True,
            "candidate_budget": 1,
            "boundary_settlement_minutes": 0,
        }
    )
    result = run_bundle(data, settings)
    c = result["diagnostics"]["feedback"][0]["pairs"][0]["candidate"]
    assert fleet_pressure(data, c["vehicle_chains"], deadline=0)["status"] == "UNAVAILABLE"
    assert fleet_revisions(data, c, settings, deadline=0)[1] == []
    original = deepcopy(c)
    evidence, proposals = fleet_revisions(data, c, settings)
    assert evidence["revision_generation_complete"]
    assert 0 < len(proposals) <= 12
    for p in proposals:
        for d, plan in p["plans"].items():
            assert sum(b["gaps"] for b in plan) == 8
            assert len(plan) <= settings["maximum_regimes"]
            assert plan[-1]["end"] == 120
            compiled = compile_plan(data["directions"][d], plan, settings)
            assert compiled["status"] == "COMPILED"
            assert (
                max(
                    b - a
                    for a, b in zip(
                        compiled["departures"], compiled["departures"][1:], strict=False
                    )
                )
                <= 30
            )
    assert c == original


def test_independent_maxflow_audit_checks_known_minima_and_detects_wrong_fleet():
    from bus_schedule_engine.mvp.route10_fleet_pilot import audit_fleet

    data = validate_bundle(allocation_case())
    times = {d: v["baseline"] for d, v in data["directions"].items()}
    fleet = assign_fleet(data, times)
    assert audit_fleet(data, times, fleet) == 4
    regular = dict.fromkeys(data["directions"], list(range(0, 121, 15)))
    assert audit_fleet(data, regular, assign_fleet(data, regular)) == 2
    wrong = deepcopy(fleet)
    wrong["required_fleet"] = 3
    with pytest.raises(ValueError, match="fleet"):
        audit_fleet(data, times, wrong)


def test_worse_parent_cannot_starve_nearer_feasible_regime_proposals():
    from bus_schedule_engine.mvp.fleet_feedback import fleet_revisions
    from bus_schedule_engine.mvp.quality import evaluate

    data = validate_bundle(allocation_case())
    settings = _settings(
        {
            "candidate_budget": 1,
            "directional_settlements": 4,
            "boundary_settlement_minutes": 0,
            "maximum_regimes": 2,
        }
    )
    worse = run_bundle(data, settings)["diagnostics"]["feedback"][0]["pairs"][0]["candidate"]
    times = {"outbound": list(range(0, 121, 15)), "inbound": [0, 18, 36, 50, 64, 78, 92, 106, 120]}
    regular = compile_plan(
        data["directions"]["outbound"], [{"end": 120, "gaps": 8, "headway_minutes": 15}], settings
    )
    inbound = compile_plan(
        data["directions"]["inbound"],
        [
            {"end": 36, "gaps": 2, "headway_minutes": 18},
            {"end": 120, "gaps": 6, "headway_minutes": 14},
        ],
        settings,
    )
    regimes = [
        r | {"direction": d}
        for d, c in (("outbound", regular), ("inbound", inbound))
        for r in c["regimes"]
    ]
    fleet = assign_fleet(data, times)
    nearer = {
        "id": "nearer",
        "departures": times,
        "regimes": regimes,
        "vehicle_chains": fleet,
        "quality": evaluate(data, times, regimes, fleet, settings),
    }
    assert nearer["quality"]["required_fleet"] == 3
    assert worse["quality"]["required_fleet"] == 4
    _, lower = fleet_revisions(data, nearer, settings)
    _, higher = fleet_revisions(data, worse, settings)
    assert lower and higher
    assert max(p["priority"] for p in lower) < min(p["priority"] for p in higher)

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from bus_schedule_engine.mvp.circulation import validate_chains
from bus_schedule_engine.mvp.input import runtime_at
from bus_schedule_engine.mvp.route10_pilot import (
    _strongest_trial,
    compare_timetable,
    planning_bundle,
    run_pilot,
    runtime_scenarios,
)


def source():
    times = {
        "outbound": [285, 300, 315, 330, 345] + list(range(360, 1241, 20)) + [1260],
        "inbound": [300, 315, 330, 345, 360, 375] + list(range(390, 1251, 20)) + [1260],
    }
    trips = [
        {
            "direction": d,
            "departure": t,
            "arrival": t + 20 + i % 5,
            "source_sheet": "synthetic",
            "source_cells": [f"D{i + 2}", f"E{i + 2}"],
        }
        for d, departures in times.items()
        for i, t in enumerate(departures)
    ]
    return {
        "source": {"sha256": "synthetic", "workbook": "synthetic.xlsx"},
        "route_identity": {"outbound": "A -> B", "inbound": "B -> A"},
        "demand_status": "SUPPORTED_BOARDING_PROXY",
        "demand": [
            {
                "direction": d,
                "interval_start": t,
                "interval_end": t + 30,
                "demand_passengers": 30,
                "source_cells": ["synthetic"],
            }
            for d in times
            for t in range(270, 1290, 30)
        ],
        "timetables": {
            s: {d: [{"departure": t} for t in departures] for d, departures in times.items()}
            for s in ("BASELINE", "EXTERNAL_CANDIDATE")
        },
        "vehicle_trips": trips,
    }


def test_nearest_rank_summaries_round_up_and_preserve_small_sample_provenance():
    s = source()
    # Five early outbound observations: nearest-rank p50=22, p75=23.
    scenarios = runtime_scenarios(s)
    assert scenarios[0]["runtime_periods"]["outbound"][0]["minutes"] == 22
    assert scenarios[1]["runtime_periods"]["outbound"][0]["minutes"] == 23
    evidence = scenarios[0]["period_evidence"]["outbound"][0]
    assert evidence["n"] == 5 and evidence["sparse"]
    assert len(evidence["observations"]) == 5
    assert scenarios[0]["authority"] == "REPORT_DERIVED_HYPOTHETICAL"


def test_common_period_boundaries_and_all_trip_arrivals_use_same_rule():
    s = source()
    for trip in s["vehicle_trips"]:
        if trip["direction"] == "outbound" and trip["departure"] >= 360:
            trip["arrival"] += 10
    original = deepcopy(s)
    scenario = runtime_scenarios(s)[0]
    data = planning_bundle(s, scenario)
    d = data["directions"]["outbound"]
    assert (
        scenario["runtime_periods"]["outbound"][0]["minutes"]
        != scenario["runtime_periods"]["outbound"][1]["minutes"]
    )
    assert runtime_at(d, 359) == scenario["runtime_periods"]["outbound"][0]["minutes"]
    assert runtime_at(d, 360) == scenario["runtime_periods"]["outbound"][1]["minutes"]
    assert runtime_at(d, 1260) == scenario["runtime_periods"]["outbound"][-1]["minutes"]
    for key in ("BASELINE", "EXTERNAL_CANDIDATE"):
        departures = {
            d: [t["departure"] for t in s["timetables"][key][d]] for d in data["directions"]
        }
        result = compare_timetable(data, key, departures, [])
        validate_chains(data, departures, result["vehicle_chains"])
        assert result["quality"]["hard_constraints_pass"]
        assert result["operational_status"] == "CONDITIONAL"
        assert result["quality"]["protected_service_certified"] is False
    assert s == original


def test_guardrail_is_explicit_experimental_and_not_inferred_peak_protection():
    s = source()
    scenario = runtime_scenarios(s)[0]
    plain = planning_bundle(s, scenario)
    guard = planning_bundle(s, scenario, headway_guardrail=25)
    assert all(not d["protected_windows"] for d in plain["directions"].values())
    assert guard["directions"]["outbound"]["protected_windows"] == [
        {"start": 285, "end": 1260, "max_gap": 25}
    ]
    assert "experimental" in guard["provenance"]["protection_basis"].lower()


def test_missing_recorded_runtime_coverage_and_sparse_periods_fail_explicitly():
    s = source()
    s["vehicle_trips"].pop()
    with pytest.raises(ValueError, match="coverage"):
        runtime_scenarios(s)
    s = source()
    # Retain identity coverage but move all early departures out of their period.
    for t in s["vehicle_trips"]:
        if t["direction"] == "outbound" and t["departure"] < 360:
            t["departure"] += 76
            t["arrival"] += 76
    s["timetables"]["EXTERNAL_CANDIDATE"]["outbound"] = [
        {"departure": t["departure"]} for t in s["vehicle_trips"] if t["direction"] == "outbound"
    ]
    with pytest.raises(ValueError, match="observations"):
        runtime_scenarios(s)


def test_missing_or_wrong_workbook_is_not_substituted(tmp_path):
    with pytest.raises(FileNotFoundError, match="Bus10_MienTay_DHQG_A.xlsx"):
        run_pilot(tmp_path / "Bus10_MienTay_DHQG_A.xlsx", tmp_path / "out")
    with pytest.raises(ValueError, match="SHA-256"):
        run_pilot(Path(__file__).parent / "fixtures/external_report.xlsx", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_strongest_trial_uses_measured_settlement_instead_of_resolving_with_fresh_budget():
    from test_mvp_settlement import PLAN, direction

    from bus_schedule_engine.mvp.planning import compile_plan

    s = source()
    data = planning_bundle(s, runtime_scenarios(s)[0])
    data["directions"] = {d: direction() | {"runtime_minutes": 5} for d in data["directions"]}
    data["fleet_ceiling"] = 1
    measured = compile_plan(direction(), PLAN, {"compilation_lookahead": 256})
    departures = {d: measured["departures"] for d in data["directions"]}
    regimes = [r | {"direction": d} for d in data["directions"] for r in measured["regimes"]]
    candidate = compare_timetable(data, "measured", departures, regimes)
    assert not candidate["quality"]["hard_constraints_pass"]
    feedback = {
        "evaluation": 1,
        "plans": dict.fromkeys(data["directions"], PLAN),
        "departures": departures,
        "regimes": regimes,
        "quality": candidate["quality"],
    }
    result = {
        "recommended": None,
        "settings": {"compilation_lookahead": 0},
        "diagnostics": {"feedback": [feedback]},
    }
    retained, role = _strongest_trial(data, result)
    assert retained["departures"] == departures
    assert retained["quality"]["waiting_minutes"] == 6
    assert role == "STRONGEST_TRIAL_NOT_RECOMMENDED"


def test_private_route10_pilot_independent_evaluation(tmp_path):
    path = os.environ.get("BUS_MVP5_ROUTE10_WORKBOOK")
    if not path:
        pytest.skip("private MVP-5 workbook not configured")
    report = run_pilot(Path(path), tmp_path)
    primary = report["scenarios"][0]
    c = primary["comparison"]["C"]
    assert c["quality"]["hard_constraints_pass"]
    assert c["quality"]["required_fleet"] <= 14
    assert (
        c["quality"]["waiting_minutes"] < primary["comparison"]["X"]["quality"]["waiting_minutes"]
    )
    assert (
        c["quality"]["waiting_minutes"] <= primary["comparison"]["B"]["quality"]["waiting_minutes"]
    )
    for d, times in c["departures"].items():
        assert len(times) == 51
        assert times[0] == (285 if d == "outbound" else 300)
        assert times[-1] == 1260
    validate_chains(primary["bundle"], c["departures"], c["vehicle_chains"])
    assert primary["control"]["diagnostics"]["feasible_candidates"] == 0
    assert primary["improved"]["diagnostics"]["evaluations"] <= 25
    assert (
        json.loads((tmp_path / "pilot_report.json").read_text(encoding="utf-8"))["schema_version"]
        == "route10_pilot_v1"
    )


def test_pilot_cli_pair_limit_requires_joint(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts/run_route10_pilot.py"),
            "--input",
            str(tmp_path / "missing.xlsx"),
            "--output-dir",
            str(tmp_path / "output"),
            "--pairs-per-plan",
            "6",
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
    )
    assert result.returncode == 2
    assert "requires --joint" in result.stderr
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("pairs_per_plan", [16, 6])
def test_private_joint_route10_acceptance_and_incumbent_recovery(tmp_path, pairs_per_plan):
    from bus_schedule_engine.mvp.route10_joint_pilot import run_joint_pilot

    path = os.environ.get("BUS_MVP5_ROUTE10_WORKBOOK")
    if not path:
        pytest.skip("private MVP-5 workbook not configured")
    report = run_joint_pilot(Path(path), tmp_path, pairs_per_plan=pairs_per_plan)
    primary = report["scenarios"][0]
    c = primary["joint"]["recommended"]
    assert c["quality"]["required_fleet"] <= 14
    assert c["quality"]["waiting_minutes"] <= 9.441296
    for row in report["scenarios"]:
        assert row["joint"]["settings"]["pairs_per_plan"] == pairs_per_plan
        diag = row["joint"]["diagnostics"]
        assert diag["evaluations"] <= 25
        assert diag["exact_pair_evaluations"] <= 160
        assert row["infeasibility_proof"] is None
        assert len(row["trial_fleets"]) == diag["exact_pair_evaluations"]
        assert all(len(f.get("pairs", [])) <= pairs_per_plan for f in diag["feedback"])
        assert row["revalidated_incumbent"]["quality"]["required_fleet"] == (
            15 if row["id"] == "report_p75" else 14
        )
        for candidate in diag["incumbents"]:
            validate_chains(row["bundle"], candidate["departures"], candidate["vehicle_chains"])
        if row["joint"]["recommended"]:
            chosen = row["joint"]["recommended"]
            assert chosen["quality"]["hard_constraints_pass"]
            validate_chains(row["bundle"], chosen["departures"], chosen["vehicle_chains"])
        if "B25" in row["id"]:
            assert all(
                w["pass"] and w["maximum_allowed_gap"] == 25
                for w in row["comparison"]["C"]["quality"]["protected_windows"]
            )
    assert (tmp_path / "report_p50/vehicle_chains.json").is_file()
    assert (tmp_path / "report_p50/operational_review.html").is_file()

"""Hand-derived vehicle/crew sensitivity cases; no private data."""

from copy import deepcopy

import pytest

from bus_schedule_engine.mvp.circulation import assign_fleet
from bus_schedule_engine.mvp.crew_review import analyze_chains, validate_policies


def fleet(waits=(5, 5), runtime=20):
    trips, time = [], 600
    for i in range(len(waits) + 1):
        direction = "outbound" if i % 2 == 0 else "inbound"
        trips.append(
            {
                "trip_id": f"t{i}",
                "vehicle_id": "V001",
                "direction": direction,
                "departure": time,
                "arrival": time + runtime,
                "ready": time + runtime + 5,
            }
        )
        time += runtime + (waits[i] if i < len(waits) else 0)
    return {
        "status": "EXACT",
        "required_fleet": 1,
        "chains": [[t["trip_id"] for t in trips]],
        "trips": trips,
    }


def policy(duration=30, **overrides):
    return {
        "name": "meal",
        "start": 600,
        "end": 900,
        "minutes": duration,
        "tasks_after": 0,
        "tasks_before": 0,
        "reserve": 0,
        "handover": 5,
    } | overrides


def policies(driver=None, attendant=None):
    return {
        "authority": "ILLUSTRATIVE",
        "short_turnaround_minutes": 10,
        "roles": {"driver": [driver or policy()], "attendant": [attendant or policy()]},
    }


def analyze(f=None, p=None, data=None):
    return analyze_chains(
        f or fleet(),
        {"outbound": 5, "inbound": 5},
        policies() if p is None else p,
        runtime_data=data,
    )


def test_five_minute_vehicle_turnaround_is_not_thirty_minute_break():
    r = analyze()
    assert r["vehicle_status"] == "CONDITIONALLY_POSSIBLE"
    assert r["summary"]["minimum_dwell"] == 5
    assert r["summary"]["minimum_slack"] == 0
    role = r["chains"][0]["crew"]["driver"][0]
    assert role["fixed_vehicle_opportunities"] == []
    assert role["fixed_vehicle_status"] == "POTENTIAL_RISK"
    assert r["crew_status"] == "INSUFFICIENT_CREW_EVIDENCE"


def test_separate_short_waits_do_not_make_one_break():
    r = analyze(fleet((15, 15, 15)))
    assert r["summary"]["total_dwell"] == 45
    assert not r["chains"][0]["crew"]["driver"][0]["fixed_vehicle_opportunities"]


def test_tasks_and_recovery_are_charged_before_a_continuous_break():
    r = analyze(fleet((50,)), policies(policy(tasks_after=5, tasks_before=5, reserve=5)))
    interval = r["chains"][0]["intervals"][0]
    opportunity = r["chains"][0]["crew"]["driver"][0]["fixed_vehicle_opportunities"][0]
    assert opportunity["free_start"] == 635  # 620 + technical5 + task5 + reserve5
    assert opportunity["free_end"] == 665
    assert opportunity["continuous_minutes"] == 30
    assert interval["slack"] == 45
    assert opportunity["status"] == "CONDITIONALLY_POSSIBLE"
    assert r["crew_status"] == "INSUFFICIENT_CREW_EVIDENCE"


def test_relief_can_cover_a_trip_without_proving_employee_availability():
    role = analyze()["chains"][0]["crew"]["driver"][0]
    assert role["relief_opportunities"][0]["substitute_trip_ids"] == ["t1", "t2"]
    assert role["relief_opportunities"][0]["relief_staff_available"] is None
    assert role["relief_status"] == "CONDITIONALLY_POSSIBLE"


def test_driver_and_attendant_policies_are_independent():
    chain = analyze(fleet((40,)), policies(policy(30), policy(45)))["chains"][0]
    assert chain["crew"]["driver"][0]["fixed_vehicle_opportunities"]
    assert not chain["crew"]["attendant"][0]["fixed_vehicle_opportunities"]


def test_unknown_policies_do_not_become_a_compliance_claim():
    r = analyze(p={})
    assert r["policy_status"] == "MISSING_OPERATOR_POLICY"
    assert r["crew_status"] == "INSUFFICIENT_CREW_EVIDENCE"
    assert r["chains"][0]["crew"] == {}


@pytest.mark.parametrize(
    "change",
    [
        {"minutes": 301},
        {"minutes": 0},
        {"start": 901},
        {"tasks_before": -1},
        {"reserve": float("nan")},
        {"handover": True},
    ],
)
def test_contradictory_or_invalid_policy_is_rejected(change):
    with pytest.raises(ValueError):
        validate_policies(policies(policy(**change)))


def test_duplicate_policy_names_and_overlapping_windows_are_rejected():
    p = policies()
    p["roles"]["driver"].append(policy(name="afternoon", start=800, end=1000))
    with pytest.raises(ValueError, match="overlap"):
        validate_policies(p)
    p["roles"]["driver"][1] = policy(start=900, end=1000)
    with pytest.raises(ValueError, match="name"):
        validate_policies(p)


@pytest.mark.parametrize("roles", [["driver"], "driver", {"driver": [None]}, {"driver": [{}]}])
def test_malformed_role_or_window_objects_are_validation_errors(roles):
    p = policies() | {"roles": roles}
    with pytest.raises(ValueError):
        validate_policies(p)


def test_every_private_output_must_be_ignored_before_writing(tmp_path, monkeypatch):
    import subprocess

    from bus_schedule_engine.mvp import route10_crew_review

    subprocess.run(
        ["git", "init", str(tmp_path)], check=True, capture_output=True, stdin=subprocess.DEVNULL
    )
    (tmp_path / ".gitignore").write_text("crew_review.json\n", encoding="utf-8")
    monkeypatch.setattr(
        route10_crew_review,
        "__file__",
        str(tmp_path / "src/bus_schedule_engine/mvp/route10_crew_review.py"),
    )
    output = tmp_path / "private_results"
    with pytest.raises(ValueError, match="Git-ignored"):
        route10_crew_review.export_review({}, output)
    assert not output.exists()


def test_fixed_chain_fails_under_stress_but_reassignment_restores_three_vehicles():
    # t0 A600->B620, t1 B625->A645, t2 A650->B670; stress runtimes=25.
    f = fleet()
    data = {"directions": {d: {"runtime_minutes": 25} for d in ("outbound", "inbound")}}
    stressed = analyze(f, data=data)
    assert stressed["vehicle_status"] == "VERIFIED_CONSTRAINT_FAILURE"
    assert stressed["summary"]["incompatible_connections"] == 2
    assert stressed["chains"][0]["trips"][0]["ready"] == 630
    assert stressed["chains"][0]["trips"][0]["source_arrival"] == 620
    departures = {"outbound": [600, 650], "inbound": [625]}
    data |= {"layover_minutes": {"outbound": 5, "inbound": 5}, "fleet_ceiling": 3}
    reassigned = assign_fleet(data, departures)
    assert reassigned["required_fleet"] == 3
    assert analyze(reassigned, data=data)["summary"]["incompatible_connections"] == 0


def test_reassignment_can_repair_a_fixed_chain_without_an_extra_vehicle():
    # Both A trips arrive by B660/680 under stress; swap their B successors.
    data = {
        "directions": {"outbound": {"runtime_minutes": 60}, "inbound": {"runtime_minutes": 20}},
        "layover_minutes": {"outbound": 5, "inbound": 5},
        "fleet_ceiling": 2,
    }
    departures = {"outbound": [600, 620], "inbound": [665, 685]}
    exact = assign_fleet(data, departures)
    by_departure = {t["departure"]: t["trip_id"] for t in exact["trips"]}
    original = deepcopy(exact)
    original["chains"] = [
        [by_departure[600], by_departure[685]],
        [by_departure[620], by_departure[665]],
    ]
    for i, chain in enumerate(original["chains"], 1):
        for t in original["trips"]:
            if t["trip_id"] in chain:
                t["vehicle_id"] = f"V{i:03d}"
    # Original assignment was feasible with 40-minute outbound runtime.
    for t in original["trips"]:
        if t["direction"] == "outbound":
            t["arrival"] -= 20
            t["ready"] -= 20
    assert analyze(original)["summary"]["incompatible_connections"] == 0
    assert analyze(original, data=data)["summary"]["incompatible_connections"] == 1
    assert analyze(exact, data=data)["summary"]["incompatible_connections"] == 0
    assert exact["required_fleet"] == original["required_fleet"] == 2


def test_chain_metrics_are_deterministic_source_preserving_and_pressure_is_explicit():
    f = fleet((5, 5, 20, 5))
    before = deepcopy(f)
    first = analyze(f)
    assert first == analyze(f)
    assert f == before
    assert first["summary"]["short_turnarounds"] == 3
    assert first["summary"]["longest_short_run"] == 2
    chain = first["chains"][0]
    assert chain["trip_count"] == 5
    assert chain["driving_minutes"] == 100
    assert chain["span_minutes"] == 135
    assert chain["intervals"][0]["from_trip_id"] == "t0"


def test_missing_duplicate_and_same_terminal_chain_evidence_is_rejected():
    for mutation in ("missing", "duplicate", "direction", "vehicle"):
        f = fleet()
        if mutation == "missing":
            f["chains"][0].pop()
        elif mutation == "duplicate":
            f["trips"].append(deepcopy(f["trips"][0]))
        elif mutation == "direction":
            f["trips"][1]["direction"] = "outbound"
        else:
            f["trips"][1]["vehicle_id"] = "other"
        with pytest.raises(ValueError):
            analyze(f)


def test_illustrative_profiles_are_valid_and_are_never_operator_authority():
    from bus_schedule_engine.mvp.crew_review import illustrative_policies

    profiles = illustrative_policies()
    assert set(profiles) == {"optimistic", "illustrative", "conservative"}
    assert all(validate_policies(p)["authority"] == "ILLUSTRATIVE" for p in profiles.values())


def test_reserved_recovery_shortfalls_are_separate_from_break_coverage():
    r = analyze(fleet((5, 10, 20)), policies(policy(reserve=5)))
    assert r["summary"]["recovery_reserve_sensitivity"] == [
        {"reserve_minutes": 0, "connections_below_reserve": 0},
        {"reserve_minutes": 5, "connections_below_reserve": 1},
    ]
    chain = r["chains"][0]
    assert chain["median_dwell"] == 10
    assert chain["short_turnarounds"] == 1


def test_review_rejects_wrong_workbook_without_writing_outputs(tmp_path):
    from bus_schedule_engine.mvp.route10_crew_review import run_review

    wrong = tmp_path / "wrong.xlsx"
    wrong.write_bytes(b"not the verified source")
    with pytest.raises(ValueError, match="SHA-256"):
        run_review(wrong, tmp_path / "missing.json", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_recorded_x_chains_keep_source_cells_and_are_not_minimum_fleet_certificates():
    from bus_schedule_engine.mvp.route10_crew_review import recorded_fleet

    f = fleet((40,))
    source = {
        "vehicle_trips": [
            t
            | {
                "trip_sequence": i,
                "source_cells": [f"A{i}"],
                "source_sheet": "recorded",
                "recorded_layover": 999,
            }
            for i, t in enumerate(f["trips"], 1)
        ]
    }
    recorded = recorded_fleet(source)
    assert recorded["status"] == "RECORDED_NOT_MINIMUM_CERTIFICATE"
    assert recorded["trips"][0]["source_cells"] == ["A1"]
    assert analyze(recorded)["chains"][0]["intervals"][0]["scheduled_dwell"] == 40


def test_deterministic_export_and_private_provenance(tmp_path):
    import json

    from bus_schedule_engine.mvp.route10_crew_review import export_review

    analysis = analyze()
    report = {
        "schema_version": "crew_rest_review_v1",
        "status": "PARTIAL_EVIDENCE",
        "source": {"sha256": "synthetic-workbook", "frozen_evidence_sha256": "synthetic-json"},
        "operating_date": None,
        "review_date": "2026-10-27",
        "policies": {"test": policies()},
        "scenarios": [
            {
                "id": "synthetic_p50",
                "timetable_role": "test",
                "alternatives": {
                    "C": {
                        "exact_vehicle_requirement": 1,
                        "waiting_minutes": 10,
                        "review_exceptions": 0,
                        "profiles": {"test": analysis},
                    }
                },
            }
        ],
        "recorded_x": {"exact_vehicle_requirement": None, "profiles": {"test": analysis}},
        "fixed_chain_stress": {},
        "reassignment_stress": {},
        "legal_note": "test",
    }
    export_review(report, tmp_path)
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    export_review(report, tmp_path)
    assert first == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    exported = json.loads((tmp_path / "crew_review.json").read_text(encoding="utf-8"))
    assert exported["source"]["frozen_evidence_sha256"] == "synthetic-json"
    text = (tmp_path / "crew_report_vi.md").read_text(encoding="utf-8")
    assert "INSUFFICIENT_CREW_EVIDENCE" in text
    annex = (tmp_path / "chain_evidence_vi.md").read_text(encoding="utf-8")
    assert "t0" in annex and "t1" in annex


def test_private_frozen_review_preserves_incumbent_and_reconciles_every_dwell(tmp_path):
    import os

    from bus_schedule_engine.mvp.route10_crew_review import run_review

    workbook = os.environ.get("BUS_MVP5_ROUTE10_WORKBOOK")
    evidence = os.environ.get("BUS_CREW_FROZEN_EVIDENCE")
    if not workbook or not evidence:
        pytest.skip("private workbook and frozen MVP-6A evidence not configured")
    result = run_review(workbook, evidence, tmp_path)
    p50 = next(s for s in result["scenarios"] if s["id"] == "report_p50")
    assert p50["alternatives"]["C"]["exact_vehicle_requirement"] == 14
    assert p50["alternatives"]["C"]["waiting_minutes"] == pytest.approx(9.441295, abs=1e-6)
    assert p50["alternatives"]["C"]["review_exceptions"] == 9
    for scenario in result["scenarios"]:
        for alternative in scenario["alternatives"].values():
            for profile in alternative["profiles"].values():
                for chain in profile["chains"]:
                    for index, interval in enumerate(chain["intervals"]):
                        assert interval["scheduled_dwell"] == (
                            chain["trips"][index + 1]["departure"]
                            - chain["trips"][index]["arrival"]
                        )
    assert result["status"] == "PARTIAL_EVIDENCE"
    assert result["recorded_x"]["exact_vehicle_requirement"] is None

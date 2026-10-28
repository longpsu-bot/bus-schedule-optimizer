import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from bus_schedule_engine.mvp.peak_offpeak_pilot import (
    authored_plans,
    compile_manual,
    export_pilot,
    service_changes,
    split_sensitivity,
)
from bus_schedule_engine.mvp.quality import regime_failures


def test_authored_families_keep_counts_endpoints_and_uniform_meaningful_regimes():
    data = {
        "directions": {
            d: {"first": first, "last": 1260, "trip_count": 51}
            for d, first in [("outbound", 285), ("inbound", 300)]
        }
    }
    for plan in authored_plans().values():
        result = compile_manual(data, plan["directions"])
        assert result["status"] == "COMPILED"
        assert not regime_failures(result["departures"], result["regimes"], {})
        for d, times in result["departures"].items():
            assert len(times) == 51 and times[0] == data["directions"][d]["first"]
            assert times[-1] == 1260 and all(type(t) is int for t in times)
        assert plan["rationale"]["outbound"] != plan["rationale"]["inbound"]


def test_family_failure_is_disclosed_without_search_or_relaxation():
    data = {
        "directions": {
            d: {"first": 0, "last": 31, "trip_count": 5} for d in ("outbound", "inbound")
        }
    }
    plan = {d: [{"end": 31, "gaps": 4, "headway_minutes": 10}] for d in data["directions"]}
    result = compile_manual(data, plan)
    assert result["status"] == "FAMILY_INFEASIBLE"
    assert "departures" not in result


def test_demand_local_deterioration_is_not_hidden_by_daily_average():
    data = {
        "directions": {
            d: {
                "demand": [
                    {"start": 0, "end": 30, "passengers": 100},
                    {"start": 30, "end": 60, "passengers": 5},
                ]
            }
            for d in ("outbound", "inbound")
        }
    }
    baseline = dict.fromkeys(data["directions"], [0, 15, 30, 60])
    candidate = dict.fromkeys(data["directions"], [0, 30, 45, 60])
    rows = service_changes(data, baseline, candidate)
    assert rows[0]["waiting_change_minutes"] == 7.5
    assert rows[0]["added_waiting_passenger_minutes"] == 750
    assert rows[1]["waiting_change_minutes"] == -7.5


def test_zero_demand_and_outside_service_waits_stay_unknown():
    data = {
        "directions": {
            d: {
                "demand": [
                    {"start": 0, "end": 30, "passengers": 0},
                    {"start": 60, "end": 90, "passengers": 20},
                ]
            }
            for d in ("outbound", "inbound")
        }
    }
    times = dict.fromkeys(data["directions"], [0, 30, 60])
    rows = service_changes(data, times, times)
    assert rows[0]["waiting_change_minutes"] is None
    assert rows[1]["outside_service_passengers_after"] == 20
    assert rows[1]["waiting_after"] is None


def test_splitting_assigns_distinct_vehicle_and_physically_declared_origin():
    f = {
        "required_fleet": 1,
        "initial_vehicles_required": {"outbound": 1, "inbound": 0},
        "chains": [["a", "b"]],
        "trips": [
            {
                "trip_id": "a",
                "vehicle_id": "V001",
                "direction": "outbound",
                "departure": 600,
                "arrival": 650,
                "ready": 655,
            },
            {
                "trip_id": "b",
                "vehicle_id": "V001",
                "direction": "inbound",
                "departure": 720,
                "arrival": 770,
                "ready": 775,
            },
        ],
    }
    original = deepcopy(f)
    result = split_sensitivity(f)
    assert f == original
    assert result["fleet"]["required_fleet"] == 2
    assert result["fleet"]["initial_vehicles_required"] == {"outbound": 1, "inbound": 1}
    assert len({t["vehicle_id"] for t in result["fleet"]["trips"]}) == 2
    assert result["additional_vehicle_start_terminal"] == "B"


def test_deterministic_exports_source_traceability_and_privacy(tmp_path):
    report = {
        "source": {"sha256": "synthetic-only"},
        "status": "PARTIAL_EVIDENCE",
        "selection": "NO_OPERATIONALLY_ACCEPTABLE_CANDIDATE_FOUND_WITHIN_PILOT",
        "candidates": {},
        "rejections": [],
        "baseline_verification": {},
    }
    a, b = tmp_path / "a", tmp_path / "b"
    export_pilot(report, a)
    export_pilot(report, b)
    files = {p.name for p in a.iterdir()}
    assert {
        "peak_offpeak_report_vi.md",
        "fleet_timespace.json",
        "fleet_utilization.csv",
        "deployment_scenarios.json",
        "crew_meal_recovery.json",
        "fleet_timeline.html",
    } <= files
    assert all((a / f).read_bytes() == (b / f).read_bytes() for f in files)
    assert (
        json.loads((a / "deployment_scenarios.json").read_text(encoding="utf-8"))["source"][
            "sha256"
        ]
        == "synthetic-only"
    )
    repo = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="ignored"):
        export_pilot(report, repo / "unsafe-generated-evidence")


def test_report_uses_configured_meal_policy():
    from bus_schedule_engine.mvp.fleet_timespace import meal_policy
    from bus_schedule_engine.mvp.peak_offpeak_report import render_report

    p = meal_policy()
    p["minutes"] = 45
    p["tasks_after"] = 7
    p["tasks_before"] = 8
    p["windows"] = dict(dinner=[1050, 1200], lunch=[690, 840])
    text = render_report(
        dict(candidates={}, source={}, status="PARTIAL_EVIDENCE", selection="test", policy=p)
    )
    assert "Mỗi bữa cần 45 phút liên tục" in text
    assert "11:30–14:00 hoặc 17:30–20:00" in text
    assert "7 phút công việc" in text and "8 phút công việc" in text


def test_export_destination_cannot_overwrite_input_even_with_an_export_filename(tmp_path):
    from bus_schedule_engine.mvp.peak_offpeak_pilot import run_pilot

    source = tmp_path / "fleet_utilization.csv"
    source.write_bytes(b"original source")
    with pytest.raises(ValueError, match="overwrite source"):
        run_pilot(source, tmp_path / "evidence.json", tmp_path)
    assert source.read_bytes() == b"original source"


def test_cli_preserves_policy_file_when_it_collides_with_an_export(tmp_path, capsys):
    import runpy

    from bus_schedule_engine.mvp.fleet_timespace import meal_policy

    source = tmp_path / "deployment_scenarios.json"
    content = json.dumps(meal_policy())
    source.write_text(content, encoding="utf-8")
    main = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts" / "run_peak_offpeak_pilot.py")
    )["main"]
    assert (
        main(
            [
                "--input",
                str(tmp_path / "input.xlsx"),
                "--evidence",
                str(tmp_path / "evidence.json"),
                "--policy",
                str(source),
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 2
    )
    assert "overwrite source" in capsys.readouterr().err
    assert source.read_text(encoding="utf-8") == content


def test_peak_reactivation_uses_actual_assigned_passenger_trip():
    from bus_schedule_engine.mvp.circulation import assign_fleet
    from bus_schedule_engine.mvp.fleet_timespace import reconstruct
    from bus_schedule_engine.mvp.peak_offpeak_pilot import _deployment_opportunities

    data = dict(
        fleet_ceiling=1,
        layover_minutes=dict(outbound=5, inbound=5),
        directions={d: dict(runtime_minutes=60, demand=[]) for d in ("outbound", "inbound")},
    )
    times = dict(outbound=[600, 960], inbound=[750, 1080])
    f = assign_fleet(data, times)
    c = dict(
        candidate=dict(vehicle_chains=f, departures=times),
        nominal=reconstruct(f, f["initial_vehicles_required"]),
    )
    _deployment_opportunities({"test": c}, data, data)
    row = c["deployment_opportunities"][0]["next_peak_by_direction"]
    assert row["outbound"]["at_correct_terminal"] is False
    assert row["outbound"]["assigned_peak_trip"] == "outbound-002"
    assert row["outbound"]["actual_previous_passenger_trip"] == "inbound-001"
    assert row["outbound"]["ready_for_assigned_peak_with_recovery_tasks_and_selected_meals"] == 825
    assert row["inbound"]["assigned_peak_trip"] is None
    assert row["inbound"]["window"] == [930, 1050]


def test_private_route10_acceptance(tmp_path):
    import os

    from bus_schedule_engine.mvp.peak_offpeak_pilot import run_pilot

    workbook = os.getenv("BUS_MVP5_ROUTE10_WORKBOOK")
    evidence = os.getenv("BUS_CREW_FROZEN_EVIDENCE")
    if not workbook or not evidence:
        pytest.skip("private acceptance inputs not supplied")
    before = sha256(Path(evidence).read_bytes()).hexdigest()
    result = run_pilot(workbook, evidence, tmp_path)
    assert result["baseline_verification"]["all_locks_pass"]
    assert result["candidates"]["P0"]["nominal"]["metrics"]["unique_vehicles_required"] == 14
    assert result["candidates"]["P0"]["fixed_p75"]["summary"]["incompatible_connections"] == 15
    assert result["candidates"]["P0"]["initial_required"] == {"outbound": 8, "inbound": 6}
    assert sha256(Path(evidence).read_bytes()).hexdigest() == before
    assert result["selection"] == "NO_OPERATIONALLY_ACCEPTABLE_CANDIDATE_FOUND_WITHIN_PILOT"
    assert all(
        c["nominal"]["audit"]["physical_conservation_pass"] for c in result["candidates"].values()
    )

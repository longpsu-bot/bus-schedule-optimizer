import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from bus_schedule_engine.mvp import external_benchmark
from bus_schedule_engine.mvp.external_import import import_external_workbook

FIXTURE = Path(__file__).parent / "fixtures" / "external_report.xlsx"


def imported():
    return import_external_workbook(FIXTURE)


def test_external_is_evaluated_on_exact_departures_without_generator(monkeypatch):
    from bus_schedule_engine.mvp import planning, runner

    def forbidden(*args, **kwargs):
        pytest.fail("benchmark must not optimize or fabricate ServiceRegimes")

    monkeypatch.setattr(runner, "run_bundle", forbidden)
    monkeypatch.setattr(planning, "compile_plan", forbidden)
    report = external_benchmark.build_external_benchmark(imported())
    x = report["alternatives"]["EXTERNAL_CANDIDATE"]
    assert x["source"] == "EXTERNAL_CANDIDATE"
    assert x["directions"]["outbound"]["headways"][19:22] == [17, 17, 11]
    assert x["directions"]["outbound"]["maximum_headway"] == 17
    assert x["directions"]["outbound"]["distinct_headway_values"] == 3
    assert x["directions"]["outbound"]["potential_regime_irregularity"]
    assert "regimes" not in x
    assert x["directions"]["outbound"]["end_tail"]["last_departure"] == 1050


def test_crossing_gaps_and_waiting_are_shared_exact_integrals():
    data = imported()
    for source, times in [("BASELINE", [0, 20, 40]), ("EXTERNAL_CANDIDATE", [0, 10, 40])]:
        for d in ("outbound", "inbound"):
            data["timetables"][source][d] = [{"departure": t} for t in times]
    data["demand"] = [
        {"direction": d, "interval_start": 15, "interval_end": 30, "demand_passengers": 30}
        for d in ("outbound", "inbound")
    ]
    report = external_benchmark.build_external_benchmark(data)
    row = report["buckets"][0]
    assert row["baseline"]["waiting_integral"] == pytest.approx(325)
    assert row["candidate"]["waiting_integral"] == pytest.approx(525)
    assert row["demand_weighted_waiting_impact"] == pytest.approx(200)
    assert row["candidate"]["gaps"][0]["preceding_departure"] == 10
    assert row["candidate"]["gaps"][0]["following_departure"] == 40
    assert row["candidate"]["gaps"][0]["gap_minutes"] == 30
    assert row["candidate"]["gaps"][0]["overlap_minutes"] == 15
    assert row["baseline"]["departure_count"] == 1
    assert row["candidate"]["departure_count"] == 0
    assert row["protection_status"] == "UNVERIFIED"
    assert report["alternatives"]["EXTERNAL_CANDIDATE"]["waiting_minutes"] == pytest.approx(17.5)


def test_reported_validated_and_minimum_fleet_remain_distinct():
    report = external_benchmark.build_external_benchmark(imported())
    b, x = report["fleet"]["BASELINE"], report["fleet"]["EXTERNAL_CANDIDATE"]
    assert b["runtime_status"] == "BASELINE_RUNTIME_UNAVAILABLE"
    assert b["minimum_fleet"] is None
    assert x["reported_fleet"] == 2
    assert x["schedule_status"] == "CHAIN_VALIDATED"
    assert x["validated_assignment_fleet"] == 2
    assert x["minimum_fleet_status"] == "MINIMUM_FLEET_UNVERIFIED"
    assert x["minimum_fleet"] is None
    assert x["initial_terminal_requirements"] == {"outbound": 1, "inbound": 1}
    assert x["minimum_layover_assumption"] is None
    assert report["capacity"]["actual_onboard_load_certified"] is False
    assert report["readiness"] != "APPROVED"


@pytest.mark.parametrize("defect", ["overlap", "terminal", "coverage", "sequence", "duplicate"])
def test_vehicle_defects_prevent_validated_assignment(defect):
    data = imported()
    if defect == "overlap":
        data["vehicle_trips"][0]["arrival"] = 400
    elif defect == "terminal":
        data["vehicle_trips"][1]["vehicle_id"] = "A"
    elif defect == "coverage":
        data["vehicle_trips"].pop()
    elif defect == "sequence":
        data["vehicle_trips"][-1]["trip_sequence"] = 99
    else:
        data["vehicle_trips"].append(deepcopy(data["vehicle_trips"][0]))
    fleet = external_benchmark.build_external_benchmark(data)["fleet"]["EXTERNAL_CANDIDATE"]
    assert fleet["schedule_status"] == "CHAIN_INVALID"
    assert fleet["validated_assignment_fleet"] is None
    assert fleet["chain_issues"]


def test_layover_scenario_is_explicit_and_source_discrepancies_are_retained():
    data = imported()
    data["vehicle_trips"][0]["recorded_layover"] = 9.5
    default = external_benchmark.build_external_benchmark(data)["fleet"]["EXTERNAL_CANDIDATE"]
    assert default["schedule_status"] == "CHAIN_VALIDATED"
    assert default["source_discrepancies"][0]["code"] == "RECORDED_LAYOVER_DIFFERS"
    scenario = external_benchmark.build_external_benchmark(data, minimum_layover=11)["fleet"][
        "EXTERNAL_CANDIDATE"
    ]
    assert scenario["schedule_status"] == "CHAIN_INVALID"
    assert scenario["minimum_layover_assumption"] == 11
    assert any(i["code"] == "INSUFFICIENT_SCENARIO_LAYOVER" for i in scenario["chain_issues"])


def test_ambiguous_demand_keeps_headways_and_withholds_waiting():
    data = imported()
    data["demand"] = []
    data["demand_status"] = "UNRESOLVED_DEMAND_AGGREGATION"
    report = external_benchmark.build_external_benchmark(data)
    assert report["buckets"] == []
    assert report["alternatives"]["BASELINE"]["waiting_minutes"] is None
    assert (
        report["alternatives"]["EXTERNAL_CANDIDATE"]["directions"]["inbound"]["maximum_headway"]
        == 18
    )


def test_three_way_missing_or_mismatched_context_is_not_ranked():
    data = imported()
    comparison = {
        "id": "C",
        "departures": {
            d: [t["departure"] for t in data["timetables"]["BASELINE"][d]]
            for d in ("outbound", "inbound")
        },
        "context": {"route_identity": "another route"},
    }
    report = external_benchmark.build_external_benchmark(data, comparison=comparison)
    assert report["three_way"]["rankable"] is False
    assert report["three_way"]["reasons"]
    assert report["three_way"]["separate_result"]["source"] == "OPTIMIZED"


def comparable(data):
    context = {
        "route_identity": data["route_identity"],
        "operating_day_profile": "synthetic-weekday",
        "direction_definitions": data["route_identity"],
        "demand_basis": external_benchmark.demand_fingerprint(data),
        "runtime_layover_assumptions": {
            "runtime_minutes": {"outbound": 5, "inbound": 5},
            "layover_minutes": {"outbound": 5, "inbound": 5},
        },
        "trip_count_policy": {"outbound": 51, "inbound": 51},
        "protected_service_policy": {"outbound": [], "inbound": []},
        "fleet_assumptions": {"fleet_ceiling": 2},
    }
    return context, {
        "id": "C",
        "context": deepcopy(context),
        "departures": {
            d: [t["departure"] for t in data["timetables"]["BASELINE"][d]]
            for d in ("outbound", "inbound")
        },
    }


def test_complete_common_scenario_recomputes_three_way_without_trusting_original_quality():
    data = imported()
    context, comparison = comparable(data)
    comparison["quality"] = {"waiting_minutes": -100, "required_fleet": 0}
    three = external_benchmark.build_external_benchmark(
        data, context=context, comparison=comparison
    )["three_way"]
    assert three["rankable"] is True
    assert set(three["scenario_evaluations"]) == {"BASELINE", "EXTERNAL_CANDIDATE", "OPTIMIZED"}
    assert three["scenario_evaluations"]["OPTIMIZED"]["quality"][
        "waiting_minutes"
    ] == pytest.approx(7.5)
    assert three["scenario_evaluations"]["OPTIMIZED"]["fleet"]["required_fleet"] == 2
    assert "baseline runtime remains unobserved" in three["ranking_scope"]


@pytest.mark.parametrize(
    "field",
    [
        "route_identity",
        "operating_day_profile",
        "direction_definitions",
        "demand_basis",
        "runtime_layover_assumptions",
        "trip_count_policy",
        "protected_service_policy",
        "fleet_assumptions",
    ],
)
def test_each_incompatible_context_field_blocks_three_way(field):
    data = imported()
    context, comparison = comparable(data)
    comparison["context"][field] = "different"
    assert (
        external_benchmark.build_external_benchmark(data, context=context, comparison=comparison)[
            "three_way"
        ]["rankable"]
        is False
    )


def test_zero_demand_has_no_waiting_rank():
    data = imported()
    for bucket in data["demand"]:
        bucket["demand_passengers"] = 0
    context, comparison = comparable(data)
    three = external_benchmark.build_external_benchmark(
        data, context=context, comparison=comparison
    )["three_way"]
    assert three["rankable"] is False
    assert three["waiting_order"] is None


def test_runtime_claim_conflicting_with_recorded_arrivals_blocks_ranking():
    data = imported()
    context, comparison = comparable(data)
    context["runtime_layover_assumptions"]["runtime_minutes"]["outbound"] = 6
    comparison["context"] = deepcopy(context)
    assert (
        external_benchmark.build_external_benchmark(data, context=context, comparison=comparison)[
            "three_way"
        ]["rankable"]
        is False
    )


@pytest.mark.parametrize("value", [[], {}, False, 0, "  ", "UNVERIFIED"])
def test_missing_operating_profile_cannot_pass_a_matching_context(value):
    data = imported()
    context, comparison = comparable(data)
    context["operating_day_profile"] = value
    comparison["context"] = deepcopy(context)
    assert (
        external_benchmark.build_external_benchmark(data, context=context, comparison=comparison)[
            "three_way"
        ]["rankable"]
        is False
    )


def test_lost_service_is_a_deterioration_without_fabricating_waiting():
    data = imported()
    for source, times in [("BASELINE", [0, 60, 120]), ("EXTERNAL_CANDIDATE", [60, 90, 120])]:
        for d in ("outbound", "inbound"):
            data["timetables"][source][d] = [{"departure": t} for t in times]
    data["demand"] = [
        {"direction": d, "interval_start": start, "interval_end": end, "demand_passengers": 30}
        for d in ("outbound", "inbound")
        for start, end in [(30, 45), (60, 90), (90, 120)]
    ]
    report = external_benchmark.build_external_benchmark(data)
    lost = report["deterioration_intervals"][0]
    assert "SERVICE_COVERAGE_LOSS" in lost["warnings"]
    assert lost["outside_service_passenger_change"] == 30
    assert lost["candidate"]["waiting_minutes"] is None
    assert lost["demand_weighted_waiting_impact"] is None
    assert report["waiting_comparison_status"] == "DIFFERENT_SERVED_POPULATIONS"


def test_html_json_exports_are_deterministic_consistent_and_escape_source(tmp_path):
    data = imported()
    data["source"]["workbook"] = '</script><script>alert("source")</script>'
    report = external_benchmark.build_external_benchmark(data)
    external_benchmark.export_external_benchmark(data, report, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {
        "external_benchmark.json",
        "external_benchmark.html",
        "external_normalized_timetable.json",
    }
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    external_benchmark.export_external_benchmark(data, report, tmp_path)
    assert first == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    html = (tmp_path / "external_benchmark.html").read_text(encoding="utf-8")
    assert '<script>alert("source")</script>' not in html
    assert '<html lang="vi">' in html
    embedded = html.split('<script type="application/json" id="benchmark-data">')[1].split(
        "</script>"
    )[0]
    assert (
        json.loads(embedded)
        == json.loads((tmp_path / "external_benchmark.json").read_text(encoding="utf-8"))
        == report
    )
    assert 'data-value="17"' in html
    assert "Chưa phải phê duyệt" in html


def test_standalone_cli_needs_only_external_workbook(tmp_path):
    run = subprocess.run(
        [
            sys.executable,
            "scripts/run_external_benchmark.py",
            "--input",
            str(FIXTURE),
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "external_benchmark.html").exists()


def test_cli_malformed_input_fails_without_creating_reports(tmp_path):
    run = subprocess.run(
        [
            sys.executable,
            "scripts/run_external_benchmark.py",
            "--input",
            str(tmp_path / "missing.xlsx"),
            "--output-dir",
            str(tmp_path / "reports"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert run.returncode != 0
    assert not (tmp_path / "reports").exists()

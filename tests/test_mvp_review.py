"""Hand-checked operational evidence, independently of whole-day selection."""

import json
import os
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path

import pytest

from bus_schedule_engine.mvp.circulation import assign_fleet
from bus_schedule_engine.mvp.input import bundle_from_workbook, validate_bundle
from bus_schedule_engine.mvp.quality import evaluate
from bus_schedule_engine.mvp.runner import export_result, run_bundle


def comparison(protected=False, stock=None):
    data = {
        "route_id": "test",
        "provenance": {"source": "hand checked"},
        "demand_basis": "independent_arrivals",
        "fleet_ceiling": 10,
        "layover_minutes": dict.fromkeys(("outbound", "inbound"), 5),
        "directions": {
            d: {
                "first": 360,
                "last": 420,
                "trip_count": 5,
                "runtime_minutes": 10,
                "baseline": [360, 370, 390, 410, 420],
                "demand": [
                    {"start": a, "end": a + 10, "passengers": 10} for a in range(360, 420, 10)
                ],
                "protected_windows": [{"start": 360, "end": 380, "max_gap": 15}]
                if protected
                else [],
            }
            for d in ("outbound", "inbound")
        },
    }
    if stock is not None:
        data["initial_vehicles"] = stock
    data = validate_bundle(data)
    baseline_times = {d: data["directions"][d]["baseline"] for d in data["directions"]}
    candidate_times = dict.fromkeys(data["directions"], [360, 380, 400, 410, 420])
    candidates = []
    for name, source, times in (
        ("B", "BASELINE", baseline_times),
        ("C", "OPTIMIZED", candidate_times),
    ):
        fleet = assign_fleet(data, times)
        candidates.append(
            {
                "id": name,
                "source": source,
                "departures": times,
                "regimes": [],
                "vehicle_chains": fleet,
                "quality": evaluate(data, times, [], fleet),
            }
        )
    baseline, candidate = candidates
    result = {
        "route_id": data["route_id"],
        "operator_decision": "REPLACE_BASELINE",
        "status": "FEASIBLE_RECOMMENDATION",
        "search_status": "FEASIBLE_RECOMMENDATION",
        "selected_source": "OPTIMIZED",
        "recommended": candidate,
        "baseline": baseline["quality"],
        "baseline_evidence": baseline,
        "alternatives": [],
        "diagnostics": {},
        "settings": {},
        "decision": {"reason": "FLEET_SAVING_WITH_EQUIVALENT_WAIT"},
    }
    return data, result


def review(data, result, **kwargs):
    from bus_schedule_engine.mvp.review import build_review

    return build_review(data, result, **kwargs)


def test_equal_daily_wait_does_not_hide_bucket_deterioration():
    data, result = comparison()
    evidence = review(data, result)
    assert result["baseline"]["waiting_minutes"] == pytest.approx(25 / 3)
    assert result["recommended"]["quality"]["waiting_minutes"] == pytest.approx(25 / 3)
    row = evidence["buckets"][0]
    assert row["waiting_difference_minutes"] == 10
    assert row["waiting_difference_percent"] == 200
    assert row["demand_weighted_waiting_impact"] == 100
    assert "MATERIAL_WAIT_DETERIORATION" in row["warnings"]
    assert evidence["selected_assessment"]["readiness"] == "HUMAN_REVIEW_REQUIRED"
    assert evidence["selected_assessment"]["hard_rule_status"] == "PASS_DECLARED_RULES"
    assert evidence["selected_assessment"]["approval_blocked"] is False


def test_cross_bucket_gap_reports_complete_pair_and_only_positive_overlap():
    data, result = comparison()
    evidence = review(data, result)
    row = evidence["buckets"][3]  # 06:30-06:40, C gap 06:20-06:40
    gap = row["candidate"]["gaps"][0]
    assert (gap["preceding_departure"], gap["following_departure"]) == (380, 400)
    assert gap["gap_minutes"] == 20
    assert (gap["overlap_start"], gap["overlap_end"], gap["overlap_minutes"]) == (390, 400, 10)
    assert gap["waiting_integral"] == 50
    assert row["candidate"]["maximum_intersecting_headway"] == 20
    assert row["candidate"]["departures"] == []
    assert evidence["buckets"][0]["candidate"]["departures"] == [360]
    assert evidence["buckets"][5]["candidate"]["departures"] == [410, 420]
    assert all(
        g["overlap_minutes"] > 0 for b in evidence["buckets"] for g in b["candidate"]["gaps"]
    )


def test_confirmed_protected_failure_blocks_approval():
    data, result = comparison(protected=True)
    evidence = review(data, result)
    assessment = evidence["selected_assessment"]
    assert assessment["readiness"] == "CONFIRMED_HARD_RULE_FAILURE"
    assert assessment["approval_blocked"] is True
    rule = assessment["protected_windows"][0]
    assert rule["maximum_allowed_gap"] == 15
    assert rule["maximum_gap"] == 20
    assert rule["responsible_gaps"] == [{"start": 360, "end": 380, "gap_minutes": 20}]


def test_missing_protection_and_stock_are_not_certified():
    data, result = comparison()
    assessment = review(data, result)["selected_assessment"]
    assert assessment["evidence_label"] == "CHƯA ĐỦ DỮ LIỆU ĐÁNH GIÁ"
    assert {
        "PROTECTION_AUTHORITY_MISSING",
        "INITIAL_STOCK_UNCONFIRMED",
        "LAYOVER_UNVERIFIED",
        "RUNTIME_UNVERIFIED",
        "ONBOARD_LOAD_UNCERTIFIED",
    } <= set(assessment["missing_evidence"])
    assert assessment["stock_status"] == "UNVERIFIED"
    assert assessment["actual_onboard_load_certified"] is False


@pytest.mark.parametrize("sufficient", [True, False])
def test_declared_stock_compares_both_terminals_and_constrained_chains(sufficient):
    data, result = comparison()
    required = result["recommended"]["vehicle_chains"]["initial_vehicles_required"]
    data["initial_vehicles"] = dict(required)
    if not sufficient:
        data["initial_vehicles"]["inbound"] = 0
        times = result["recommended"]["departures"]
        fleet = assign_fleet(data, times)
        result["recommended"]["vehicle_chains"] = fleet
        result["recommended"]["quality"] = evaluate(data, times, [], fleet)
        baseline = result["baseline_evidence"]
        baseline["vehicle_chains"] = assign_fleet(data, baseline["departures"])
        baseline["quality"] = evaluate(data, baseline["departures"], [], baseline["vehicle_chains"])
    assessment = review(data, result)["selected_assessment"]
    if sufficient:
        assert assessment["stock_status"] == "VERIFIED_AGAINST_DECLARED_STOCK"
        assert assessment["stock_comparison"]["inbound"]["sufficient"] is True
    else:
        assert assessment["stock_status"] == "CONFIRMED_INFEASIBLE"
        assert assessment["approval_blocked"] is True


def test_terminal_flow_distinguishes_arrived_from_ready_and_conserves_fleet():
    data, result = comparison()
    circulation = review(data, result)["circulation"]
    required = circulation["required_fleet"]
    events = circulation["terminal_flow"]
    arrived = next(e for e in events if e["minute"] == 370)
    assert arrived["outbound"]["physically_present"] > arrived["outbound"]["ready"]
    assert arrived["inbound"]["physically_present"] > arrived["inbound"]["ready"]
    for event in events:
        assert (
            event["running"] + sum(event[d]["physically_present"] for d in ("outbound", "inbound"))
            == required
        )
        assert (
            event["unavailable"] + sum(event[d]["ready"] for d in ("outbound", "inbound"))
            == required
        )
        assert all(
            0 <= event[d]["ready"] <= event[d]["physically_present"]
            for d in ("outbound", "inbound")
        )
    for vehicle in circulation["vehicles"]:
        for trip in vehicle["trips"][:-1]:
            assert trip["turnaround_slack_minutes"] >= 0


def test_explicit_runtime_layover_scenario_is_reassigned_and_revalidated():
    data, result = comparison()
    before = deepcopy(data)
    evidence = review(
        data,
        result,
        scenarios=[
            {
                "name": "longer circulation",
                "runtime_minutes": {"outbound": 20, "inbound": 20},
                "layover_minutes": {"outbound": 7, "inbound": 7},
            }
        ],
    )
    scenario = evidence["sensitivities"][0]
    assert scenario["independently_validated"] is True
    assert scenario["departures_unchanged"] is True
    assert scenario["circulation"]["required_fleet"] > evidence["circulation"]["required_fleet"]
    trip = scenario["circulation"]["vehicles"][0]["trips"][0]
    assert trip["arrival"] - trip["departure"] == 20
    assert trip["ready"] - trip["arrival"] == 7
    assert data == before
    assert review(data, result)["sensitivities"] == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"warning_settings": {"waiting_increase_minutes": -1}},
        {"warning_settings": {"unknown": 1}},
        {"scenarios": [{"name": "bad", "legal_route_class": "urban"}]},
        {"scenarios": [{"name": "bad", "runtime_minutes": {"outbound": 0, "inbound": 10}}]},
    ],
)
def test_review_configuration_rejects_unknown_or_invalid_assumptions(kwargs):
    data, result = comparison()
    with pytest.raises(ValueError):
        review(data, result, **kwargs)


def test_warning_materiality_is_configurable_without_changing_hard_rules():
    data, result = comparison()
    evidence = review(
        data,
        result,
        warning_settings={
            "waiting_increase_minutes": 30,
            "departure_reduction_fraction": 1,
            "headway_increase_minutes": 30,
        },
    )
    assert "MATERIAL_WAIT_DETERIORATION" not in evidence["buckets"][0]["warnings"]
    assert evidence["selected_assessment"]["hard_rule_status"] == "PASS_DECLARED_RULES"


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.remote = []
        self.metrics = {}
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("src", "href"):
            if attrs.get(key, "").startswith(("https:", "http:", "//")):
                self.remote.append(attrs[key])
        if "data-metric" in attrs:
            self.metrics[attrs["data-metric"]] = attrs["data-value"]
        if tag == "script":
            self.scripts.append(attrs)


def test_html_json_metrics_match_and_untrusted_text_is_escaped(tmp_path):
    from bus_schedule_engine.mvp.review_html import render_review_html

    data, result = comparison()
    data["route_id"] = '<script>alert("x")</script>'
    data["provenance"]["source"] = '<img src=x onerror="evil()">'
    evidence = review(data, result)
    result["operational_review"] = evidence
    export_result(result, tmp_path)
    html = (tmp_path / "operational_review.html").read_text(encoding="utf-8")
    report = json.loads((tmp_path / "quality_report.json").read_text(encoding="utf-8"))
    assert report["operational_review"] == evidence
    parser = ReportParser()
    parser.feed(html)
    assert not parser.remote
    assert not parser.scripts
    assert "&lt;script&gt;" in html and "&lt;img" in html
    for metric, value in evidence["summary"].items():
        if isinstance(value, (int, float)) or value is None:
            assert json.loads(parser.metrics[metric]) == value
    assert html == render_review_html(evidence)
    assert render_review_html(evidence) == render_review_html(review(data, result))


def test_baseline_only_and_blocked_reports_are_usable(tmp_path):
    result = run_bundle(
        json.loads((Path(__file__).parent / "fixtures/mvp/synthetic_route.json").read_text())
    )
    assert result["operator_decision"] == "KEEP_BASELINE"
    assert result["recommended"]["regimes"] == []
    export_result(result, tmp_path)
    html = (tmp_path / "operational_review.html").read_text(encoding="utf-8")
    assert "KEEP_BASELINE" in html
    assert "Không dựng ServiceRegime cho B" in html
    export_result(run_bundle({}), tmp_path / "blocked")
    assert "UNRESOLVED" in (tmp_path / "blocked/operational_review.html").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("route", ["6", "10"])
def test_private_mvp3_review_regressions_independently(route, tmp_path):
    path = os.environ.get(f"BUS_MVP_ROUTE{route}_WORKBOOK")
    if not path:
        pytest.skip("Private workbook not configured")
    data = bundle_from_workbook(path, minimum_layover=5)
    result = run_bundle(data)
    evidence = result["operational_review"]
    assert result == run_bundle(data)
    assert evidence["selected_assessment"]["stock_status"] == "UNVERIFIED"
    assert evidence["selected_assessment"]["hard_rule_status"] == "PASS_DECLARED_RULES"
    if route == "6":
        assert evidence["summary"]["baseline_fleet"] == 20
        assert evidence["summary"]["selected_fleet"] == 16
        assert evidence["circulation"]["initial_vehicles_required"] == {"outbound": 7, "inbound": 9}
        for direction, start, bw, cw, bn, cn in [
            ("outbound", 390, 3.866667, 6.566667, 4, 2),
            ("inbound", 390, 3.866667, 6.4, 4, 3),
            ("inbound", 990, 4, 6.4, 4, 3),
        ]:
            row = next(
                b
                for b in evidence["buckets"]
                if b["direction"] == direction and b["interval_start"] == start
            )
            assert row["baseline"]["waiting_minutes"] == pytest.approx(bw, abs=1e-6)
            assert row["candidate"]["waiting_minutes"] == pytest.approx(cw, abs=1e-6)
            assert (row["baseline"]["departure_count"], row["candidate"]["departure_count"]) == (
                bn,
                cn,
            )
            assert "MATERIAL_WAIT_DETERIORATION" in row["warnings"]
            assert row["candidate"]["maximum_intersecting_headway"] < 18
        longest = evidence["maximum_headway_gaps"]
        assert all(g["direction"] == "inbound" and g["gap_minutes"] == 18 for g in longest)
        assert longest[0]["preceding_departure"] == 1062
        assert longest[-1]["following_departure"] == 1260
    else:
        assert evidence["operator_decision"] == "KEEP_BASELINE"
        assert evidence["summary"]["selected_fleet"] == 12
        assert evidence["comparison_id"] != "B"
    export_result(result, tmp_path)
    assert (tmp_path / "operational_review.html").stat().st_size > 1000


@pytest.mark.parametrize("factor", [0.8, 0.85])
def test_capacity_proxy_never_certifies_or_misstates_actual_onboard_load(factor):
    data, result = comparison()
    data.update(vehicle_capacity=50, maximum_load_factor=factor, capacity_policy="evaluation_only")
    c = result["recommended"]
    c["quality"] = evaluate(data, c["departures"], [], c["vehicle_chains"])
    b = result["baseline_evidence"]
    b["quality"] = evaluate(data, b["departures"], [], b["vehicle_chains"])
    evidence = review(data, result)
    assert evidence["selected_assessment"]["capacity_proxy"]["maximum_load_factor"] == factor
    assert evidence["selected_assessment"]["actual_onboard_load_certified"] is False
    from bus_schedule_engine.mvp.review_html import render_review_html

    assert str(factor).replace(".", ",") in render_review_html(evidence)
    assert "lượt lên xe" in render_review_html(evidence)


def test_unresolved_comparison_never_claims_baseline_is_retained(monkeypatch, tmp_path):
    from test_mvp_service_plan import bundle

    from bus_schedule_engine.mvp import runner

    original = runner.assign_fleet
    calls = 0

    def uncertain_baseline(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": "MINIMUM_FLEET_UNPROVED", "required_fleet": None, "trips": []}
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "assign_fleet", uncertain_baseline)
    result = run_bundle(bundle(), {"candidate_budget": 1})
    assert result["operator_decision"] == "UNRESOLVED"
    assert result["operational_review"]["comparison_role"] == "GENERATED_ALTERNATIVE"
    export_result(result, tmp_path)
    html = (tmp_path / "operational_review.html").read_text(encoding="utf-8")
    assert "B được giữ nguyên" not in html
    assert "Chưa chọn biểu đồ để triển khai" in html


def test_minimum_departure_violation_is_authoritative_even_when_gap_passes():
    data, result = comparison()
    for d in data["directions"].values():
        d["protected_windows"] = [
            {"start": 360, "end": 380, "max_gap": 30, "minimum_departures": 2}
        ]
    for c in (result["baseline_evidence"], result["recommended"]):
        c["quality"] = evaluate(data, c["departures"], [], c["vehicle_chains"])
    evidence = review(data, result)
    assert evidence["selected_assessment"]["approval_blocked"] is True
    rule = evidence["selected_assessment"]["protected_windows"][0]
    assert rule["maximum_gap"] < rule["maximum_allowed_gap"]
    assert (rule["minimum_departures"], rule["departures"]) == (2, 1)


def test_scenario_with_more_required_vehicles_blocks_on_existing_fleet_ceiling():
    data, result = comparison()
    evidence = review(
        data,
        result,
        scenarios=[{"name": "long runtime", "runtime_minutes": {"outbound": 100, "inbound": 100}}],
    )
    # Ten departures require ten vehicles when all trips overlap; ceiling was ten.
    assert evidence["sensitivities"][0]["circulation"]["required_fleet"] == 10
    assert evidence["sensitivities"][0]["assessment"]["hard_rule_status"] == "PASS_DECLARED_RULES"
    data["fleet_ceiling"] = 5
    evidence = review(
        data,
        result,
        scenarios=[{"name": "long runtime", "runtime_minutes": {"outbound": 100, "inbound": 100}}],
    )
    assert evidence["sensitivities"][0]["independently_validated"] is True
    assert evidence["sensitivities"][0]["assessment"]["approval_blocked"] is True


def test_unresolved_without_generated_alternative_still_reviews_actual_b():
    data, result = comparison(protected=True)
    result["recommended"] = None
    result["operator_decision"] = "UNRESOLVED"
    evidence = review(data, result)
    assert evidence["selected_id"] is None
    assert evidence["comparison_id"] == "B"
    assert evidence["comparison_role"] == "BASELINE_REFERENCE"
    assert evidence["buckets"]
    assert evidence["regimes"] == []
    from bus_schedule_engine.mvp.review_html import render_review_html

    assert "Điều kiện xem xét phương án thử C" not in render_review_html(evidence)


def test_ready_for_consideration_keeps_onboard_certification_separate():
    data, result = comparison(protected=True)
    result["recommended"] = result["baseline_evidence"]
    result["operator_decision"] = "KEEP_BASELINE"
    for d in data["directions"].values():
        d["protected_windows"] = [{"start": d["first"], "end": d["last"], "max_gap": 30}]
    c = result["recommended"]
    data["initial_vehicles"] = c["vehicle_chains"]["initial_vehicles_required"]
    data["provenance"].update(runtime_verified=True, layover_verified=True)
    c["quality"] = evaluate(data, c["departures"], [], c["vehicle_chains"])
    assessment = review(data, result)["selected_assessment"]
    assert assessment["readiness"] == "READY_FOR_HUMAN_APPROVAL_CONSIDERATION"
    assert assessment["actual_onboard_load_certified"] is False
    assert assessment["missing_evidence"] == ["ONBOARD_LOAD_UNCERTIFIED"]
    assert assessment["evidence_label"] == "CHƯA ĐỦ DỮ LIỆU ĐÁNH GIÁ"


def test_cli_exports_supplied_review_settings_and_scenarios_without_editing_input(tmp_path):
    from runpy import run_path

    input_path = Path(__file__).parent / "fixtures/mvp/synthetic_route.json"
    original = input_path.read_bytes()
    warning_path = tmp_path / "warnings.json"
    scenario_path = tmp_path / "scenarios.json"
    warning_path.write_text(json.dumps({"waiting_increase_minutes": 2}), encoding="utf-8")
    scenario_path.write_text(
        json.dumps(
            [
                {
                    "name": "explicit longer runtime",
                    "runtime_minutes": {"outbound": 25, "inbound": 25},
                }
            ]
        ),
        encoding="utf-8",
    )
    main = run_path(str(Path(__file__).parents[1] / "scripts/run_mvp_service_plan.py"))["main"]
    assert (
        main(
            [
                "--input",
                str(input_path),
                "--output-dir",
                str(tmp_path / "report"),
                "--review-settings",
                str(warning_path),
                "--operating-scenarios",
                str(scenario_path),
            ]
        )
        == 0
    )
    evidence = json.loads((tmp_path / "report/quality_report.json").read_text(encoding="utf-8"))[
        "operational_review"
    ]
    assert evidence["warning_policy"]["waiting_increase_minutes"] == 2
    assert evidence["sensitivities"][0]["independently_validated"] is True
    assert input_path.read_bytes() == original

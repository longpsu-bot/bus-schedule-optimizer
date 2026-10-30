"""The diagnostic observer and new seed must not change the constraint system."""

import runpy
from copy import deepcopy
from pathlib import Path

from test_integrated_blocking import oracle
from test_integrated_blocking_validation import blocks, request

from bus_schedule_engine.mvp import integrated_blocking
from bus_schedule_engine.mvp.integrated_blocking_validation import validate_assignment

REVIEW = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "review_integrated_blocking_gap.py")
)


def test_new_seed_changes_hints_but_not_constraint_fingerprint(monkeypatch):
    r = request(
        [("outbound", 480, 660), ("inbound", 705, 885)],
        meals=True,
        general=True,
        driving=True,
    )
    corrected = REVIEW["observe"](integrated_blocking, r)
    monkeypatch.setattr(integrated_blocking, "_rest_aware_seed", integrated_blocking._greedy)
    legacy = REVIEW["observe"](integrated_blocking, r)
    assert corrected["constraint_sha256"] == legacy["constraint_sha256"]
    assert corrected["result"]["model_sha256"] != legacy["result"]["model_sha256"]
    assert [e["fleet"] for e in corrected["events"][:2]] == [2, 1]
    assert corrected["events"][1]["source"] == "rest_aware_seed"
    for record in (legacy, corrected):
        assert record["result"]["lower_bound"] == record["result"]["upper_bound"] == 1
        assert sum(e["first_cp_sat"] for e in record["events"]) == 1
        for event in record["events"]:
            assert validate_assignment(r, event["blocks"])["required_fleet"] == event["fleet"]


def test_invalid_new_seed_never_becomes_upper_bound_or_model_cutoff(monkeypatch):
    r = request([("outbound", 480, 660), ("inbound", 705, 885)], driving=True)
    bad = blocks(r, [[0], [0]])
    monkeypatch.setattr(integrated_blocking, "_rest_aware_seed", lambda *args: bad)
    result = REVIEW["observe"](integrated_blocking, r)
    assert result["result"]["upper_bound"] == 1
    assert result["result"]["validator_pass"]
    assert all(e["source"] != "rest_aware_seed" for e in result["events"])


def test_relaxed_staircase_is_explicit_and_preserves_departures_and_budgets():
    r = request(
        [("outbound", 480, 660), ("inbound", 705, 885)], meals=True, general=True, driving=True
    )
    frozen = deepcopy(r)
    variants = dict(REVIEW["relaxations"](r))
    assert variants["full"] == r
    assert r == frozen
    assert variants["technical_only"]["terminal_policy"] == dict(technical=5, pre=0, post=0)
    assert variants["terminal_tasks"]["terminal_policy"] == r["terminal_policy"]
    for v in variants.values():
        assert v["timetable"] == r["timetable"]
        assert v["runtime_scenario"] == r["runtime_scenario"]
        assert v["search"] == r["search"]
    for name in ("lunch", "dinner"):
        meals = variants["without_" + name]["crew_policy"]["meals"]["windows"]
        assert next(m for m in meals if m["name"] == name)["mode"] == "DISABLED_EXPERIMENTAL"


def test_observer_does_not_change_synthetic_solver_result():
    r = request(
        [("outbound", 480, 580), ("inbound", 625, 725), ("outbound", 770, 870)], driving=True
    )
    plain = integrated_blocking.solve_integrated(r)
    observed = REVIEW["observe"](integrated_blocking, r)["result"]
    for key in ("blocks", "lower_bound", "upper_bound", "deterministic_seconds", "model_sha256"):
        assert observed[key] == plain[key]


def test_reset_workload_certificate_is_necessary_against_exact_partition_oracle():
    for count in range(1, 8):
        clocks = [
            ("outbound" if i % 2 == 0 else "inbound", 60 + i * 120, 160 + i * 120)
            for i in range(count)
        ]
        r = request(clocks, duty=240, driving=True)
        certificate = REVIEW["reset_workload_certificate"](r)
        assert certificate["maximum_trips_per_driving_segment"] == 2
        assert certificate["minimum_driving_segments"] == (count + 1) // 2
        assert certificate["lower_bound"] <= oracle(clocks, r)
    r["crew_policy"]["driving"]["mode"] = "DISABLED_EXPERIMENTAL"
    assert REVIEW["reset_workload_certificate"](r) is None

"""Small exact oracles enumerate partitions, not the solver's resource equations."""

import json
import random
from copy import deepcopy

import pytest
from test_integrated_blocking_validation import blocks, request, rest

from bus_schedule_engine.mvp.integrated_blocking import solve_integrated


def oracle(clocks, r):
    """Enumerate all executable subsets/partitions using literal interval arithmetic."""
    n = len(clocks)
    crew = r["crew_policy"]
    feasible = []
    for mask in range(1, 1 << n):
        chain = sorted((i for i in range(n) if mask >> i & 1), key=lambda i: clocks[i][1])
        start, end = clocks[chain[0]][1] - 5, clocks[chain[-1]][2] + 5
        gaps = []
        valid = True
        exposure = 0
        for k, i in enumerate(chain):
            d, dep, arr = clocks[i]
            if k:
                prev = clocks[chain[k - 1]]
                left, right = prev[2] + 10, dep - 5
                if prev[0] == d or left > right:
                    valid = False
                    break
                gaps.append((left, right))
                if right - left >= crew["driving"]["reset_minutes"]:
                    exposure = 0
            exposure += arr - dep
            if crew["driving"]["mode"] == "ENFORCED" and exposure > crew["driving"]["limit"]:
                valid = False
        if crew["duty"]["mode"] == "ENFORCED" and end - start > crew["duty"]["limit"]:
            valid = False
        if (
            crew["total_driving"]["mode"] == "ENFORCED"
            and sum(clocks[i][2] - clocks[i][1] for i in chain) > crew["total_driving"]["limit"]
        ):
            valid = False
        if (
            crew["general_rest"]["mode"] == "ENFORCED"
            and end - start >= crew["general_rest"]["duty_threshold"]
            and not any(u - lo >= crew["general_rest"]["minutes"] for lo, u in gaps)
        ):
            valid = False
        for m in crew["meals"]["windows"]:
            overlap = max(0, min(end, m["end"]) - max(start, m["start"]))
            required = m["mode"] == "ENFORCED" and (
                overlap > 0
                if crew["meals"]["eligibility"] == "DUTY_INTERSECTS_WINDOW"
                else end - start >= crew["meals"]["duty_threshold"]
                and overlap >= crew["meals"]["overlap_threshold"]
            )
            if required and not any(
                min(u, m["end"]) - max(lo, m["start"]) >= m["minutes"] for lo, u in gaps
            ):
                valid = False
        if valid:
            feasible.append((mask, clocks[chain[0]][0]))
    best = n + 1

    def partition(remaining, count, origins):
        nonlocal best
        if count >= best:
            return
        if not remaining:
            caps = r["stock"]["initial_vehicles"]
            if caps and (origins[0] > caps["A"] or origins[1] > caps["B"]):
                return
            if r["resource_cap"] and count > r["resource_cap"]["limit"]:
                return
            best = count
            return
        first = remaining & -remaining
        for mask, d in feasible:
            if mask & first and mask & remaining == mask:
                partition(
                    remaining ^ mask,
                    count + 1,
                    (origins[0] + (d == "outbound"), origins[1] + (d == "inbound")),
                )

    partition((1 << n) - 1, 0, (0, 0))
    return None if best == n + 1 else best


@pytest.mark.parametrize(
    "clocks,settings,want",
    [
        ([("outbound", 480, 500), ("inbound", 515, 535), ("outbound", 550, 570)], {}, 1),  # T1
        (
            [
                ("outbound", 600, 630),
                ("inbound", 645, 675),
                ("outbound", 690, 720),
                ("inbound", 735, 765),
                ("outbound", 780, 810),
                ("inbound", 825, 855),
            ],
            {"strict_lunch": True},
            2,
        ),  # T2
        (
            [("outbound", 360, 420), ("inbound", 435, 495)],
            {"meals": True, "general": True},
            1,
        ),  # T3
        ([("outbound", 900, 960), ("inbound", 975, 1035)], {"meals": True}, 1),
        ([("outbound", 900, 960), ("inbound", 975, 1035)], {"strict_meals": True}, None),
        ([("outbound", 600, 660), ("inbound", 674, 734)], {}, 2),  # T6
        ([("outbound", 600, 660), ("inbound", 675, 735)], {}, 1),
        ([("outbound", 600, 670), ("inbound", 675, 735)], {}, 2),  # T7 stress
        ([("outbound", 600, 1080)], {"duty": 480}, None),  # T9
        (
            [("outbound", 480, 580), ("inbound", 595, 695), ("outbound", 710, 810)],
            {"driving": True},
            2,
        ),  # T11
        ([("outbound", 600, 1070)], {"duty": 480}, 1),  # T17 final turnaround
        (
            [("outbound", 60, 180), ("inbound", 195, 315), ("outbound", 330, 450)],
            {"general": True},
            2,
        ),  # T18
        (
            [("outbound", 480, 660), ("inbound", 705, 885)],
            {"meals": True, "general": True, "driving": True},
            1,
        ),  # T19
    ],
)
def test_known_synthetic_optima(clocks, settings, want):
    settings = dict(settings)
    strict = settings.pop("strict_lunch", False)
    strict_all = settings.pop("strict_meals", False)
    r = request(clocks, **settings)
    if strict or strict_all:
        r["crew_policy"]["meals"]["eligibility"] = "DUTY_INTERSECTS_WINDOW"
        r["crew_policy"]["meals"]["windows"][0]["mode"] = "ENFORCED"
        if strict_all:
            r["crew_policy"]["meals"]["windows"][1]["mode"] = "ENFORCED"
    before = deepcopy(r)
    assert oracle(clocks, r) == want
    result = solve_integrated(r)
    assert r == before
    if want is None:
        assert result["status"] == "INFEASIBLE_PROVEN"
        assert result["upper_bound"] is None
    else:
        assert result["status"] == "OPTIMAL_PROVEN"
        assert result["lower_bound"] == result["upper_bound"] == want
        assert result["validation"]["validator_pass"]
        assert result["model_complete"]


def test_tiny_random_partitions_agree_with_full_dag_proofs():
    rng = random.Random(73)
    for _ in range(18):
        clocks = [
            (
                "outbound" if i % 2 == 0 else "inbound",
                450 + i * 60,
                450 + i * 60 + rng.choice([20, 40, 55]),
            )
            for i in range(6)
        ]
        r = request(clocks, duty=240, driving=True, general=True, meals=True)
        r["crew_policy"]["general_rest"]["duty_threshold"] = 160
        result = solve_integrated(r)
        assert result["upper_bound"] == result["lower_bound"] == oracle(clocks, r)


def test_timeout_retains_strongest_validated_incumbent_and_atomic_checkpoint(tmp_path):
    clocks = [
        ("outbound", 600, 630),
        ("inbound", 645, 675),
        ("outbound", 690, 720),
        ("inbound", 735, 765),
        ("outbound", 780, 810),
        ("inbound", 825, 855),
    ]
    r = request(clocks, meals=True)
    r["crew_policy"]["meals"]["eligibility"] = "DUTY_INTERSECTS_WINDOW"
    r["crew_policy"]["meals"]["windows"][1]["mode"] = "DISABLED_EXPERIMENTAL"
    witness = blocks(
        r,
        [[0, 3, 4], [1, 2, 5]],
        {1: [rest(r, 0, 3, 660, 690, "lunch")], 2: [rest(r, 2, 5, 730, 760, "lunch")]},
    )
    checkpoint = tmp_path / "checkpoint.json"
    stopped = solve_integrated(r, incumbent=witness, checkpoint=checkpoint, cancelled=lambda: True)
    assert stopped["status"] == "FEASIBLE_NOT_PROVEN_OPTIMAL"
    assert (stopped["lower_bound"], stopped["upper_bound"]) == (1, 2)
    assert json.loads(checkpoint.read_text())["blocks"] == witness
    # A cancelled subsequent attempt must not replace a verified complete witness.
    resumed = solve_integrated(r, checkpoint=checkpoint, cancelled=lambda: True)
    assert resumed["upper_bound"] == 2
    assert resumed["blocks"] == witness
    weaker = blocks(
        r,
        [[0, 3], [1, 4], [2, 5]],
        {
            1: [rest(r, 0, 3, 660, 690, "lunch")],
            2: [rest(r, 1, 4, 685, 715, "lunch")],
            3: [rest(r, 2, 5, 730, 760, "lunch")],
        },
    )
    resumed = solve_integrated(r, incumbent=weaker, checkpoint=checkpoint, cancelled=lambda: True)
    assert resumed["upper_bound"] == 2
    assert json.loads(checkpoint.read_text())["blocks"] == witness
    # A genuine time-budget cutoff during construction also retains the supplied witness.
    r["search"]["wall_seconds"] = 1e-9
    timed = solve_integrated(r, incumbent=witness)
    assert timed["status"] == "FEASIBLE_NOT_PROVEN_OPTIMAL"
    assert timed["upper_bound"] == 2
    assert "wall limit" in timed["termination_reason"]
    empty = solve_integrated(r, cancelled=lambda: True)
    assert empty["status"] == "SEARCH_INCOMPLETE" and empty["upper_bound"] is None


def test_initial_stock_and_resource_cap_are_actual_hard_constraints():
    r = request([("outbound", 480, 500), ("inbound", 480, 500)])
    r["stock"].update(mode="EXPERIMENTAL_CAPS", initial_vehicles=dict(A=2, B=0))
    assert solve_integrated(r)["status"] == "INFEASIBLE_PROVEN"
    r["stock"]["initial_vehicles"] = dict(A=1, B=1)
    assert solve_integrated(r)["upper_bound"] == 2
    r["resource_cap"] = dict(limit=1, authority="EXPERIMENTAL_DECLARED", provenance="test")
    assert solve_integrated(r)["status"] == "INFEASIBLE_PROVEN"


def test_reproducible_fixed_seed_and_full_matching_cut_certificate():
    r = request([("outbound", 480, 500), ("inbound", 515, 535), ("outbound", 550, 570)])
    a, b = solve_integrated(r), solve_integrated(r)
    assert a["blocks"] == b["blocks"]
    assert a["relaxation"]["matching_size"] == a["relaxation"]["cut_capacity"] == 2
    assert a["relaxation"]["task_path_bound"] == 1
    assert a["relaxation"]["workload_duty_bound"] == 1


def test_invalid_request_does_not_become_infeasibility():
    r = request([("outbound", 480, 500)])
    r["crew_policy"]["driving"]["reset_minutes"] = 0
    assert solve_integrated(r)["status"] == "BLOCKED_INPUT_AUTHORITY"


@pytest.mark.parametrize("field", ["seed", "duty_limit"])
def test_solver_unsafe_integer_is_blocked_before_native_parameter_or_model_error(field):
    r = request([("outbound", 480, 500)])
    if field == "seed":
        r["search"]["seed"] = 2**31
    else:
        r["crew_policy"]["duty"]["limit"] = 2**63
    assert solve_integrated(r)["status"] == "BLOCKED_INPUT_AUTHORITY"


def test_malformed_checkpoint_does_not_crash_or_erase_valid_input(tmp_path):
    r = request([("outbound", 480, 500)])
    checkpoint = tmp_path / "bad.checkpoint.json"
    checkpoint.write_text("[]", encoding="utf-8")
    result = solve_integrated(r, checkpoint=checkpoint)
    assert result["status"] == "SEARCH_INCOMPLETE"
    assert result["upper_bound"] is None
    assert checkpoint.read_text(encoding="utf-8") == "[]"


def test_malformed_witness_trip_id_is_rejected_as_invalid_input():
    r = request([("outbound", 480, 500)])
    b = blocks(r, [[0]])
    b[0]["trip_ids"] = [{}]
    result = solve_integrated(r, incumbent=b)
    assert result["status"] == "SEARCH_INCOMPLETE" and result["upper_bound"] is None


def test_checkpoint_io_failure_keeps_in_memory_validated_witness(tmp_path):
    r = request([("outbound", 480, 500)])
    obstacle = tmp_path / "not_a_directory"
    obstacle.write_text("preserve", encoding="utf-8")
    result = solve_integrated(
        r, incumbent=blocks(r, [[0]]), checkpoint=obstacle / "checkpoint.json"
    )
    assert result["status"] == "SEARCH_INCOMPLETE"
    assert result["upper_bound"] == 1 and result["validator_pass"]
    assert obstacle.read_text(encoding="utf-8") == "preserve"


def test_model_edge_budget_rejection_never_claims_complete_infeasibility():
    r = request([("outbound", 480, 500), ("inbound", 515, 535), ("outbound", 550, 570)])
    r["search"]["max_edges"] = 1
    result = solve_integrated(r)
    assert result["status"] == "SEARCH_INCOMPLETE" and not result["model_complete"]


def test_fragmented_lunch_cannot_be_aggregated_and_cap_has_complete_proof():
    r = request(
        [
            ("outbound", 600, 660),
            ("inbound", 690, 720),
            ("outbound", 750, 780),
            ("inbound", 810, 850),
        ],
        meals=True,
    )
    r["crew_policy"]["meals"]["eligibility"] = "DUTY_INTERSECTS_WINDOW"
    r["crew_policy"]["meals"]["windows"][1]["mode"] = "DISABLED_EXPERIMENTAL"
    r["resource_cap"] = dict(
        limit=1, authority="EXPERIMENTAL_DECLARED", provenance="T4 unique complete path test"
    )
    assert solve_integrated(r)["status"] == "INFEASIBLE_PROVEN"

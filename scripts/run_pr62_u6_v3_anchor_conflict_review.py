"""Compact, evidence-only review of the PR62-U6 Route 10 V3 anchor conflict.

This script never calls the global coordinator, never constructs a replacement
selection policy, and never reads or evaluates Route 6 timetable inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import subprocess
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bus_schedule_engine import service_plan_coordinator as coordinator
from bus_schedule_engine.contracts_v1.closed_loop_service_protection import (
    validate_closed_loop_service_protection_v1,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy import NUMERICAL_EPSILON
from bus_schedule_engine.contracts_v1.operational_selection_policy_v3 import (
    continuous_exposure_metrics_v3,
)
from bus_schedule_engine.contracts_v1.service_plan_state import (
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    service_plan_fingerprint_v1,
)

BASE_SHA = "185dbee3b86a7ec838723c4e9d50bc2e88bf373b"
CANONICAL_SEMANTIC_SHA256 = "46cd605e4ffb0a9aa00bb9376002b2001ada60760d460e1cbf38ba69aa549d99"
CANONICAL_EVIDENCE_SHA256 = "0dcb75205c329a3fc512f475cb619eee61be9b3d25342ae6e12fa923a9bf6877"
SAVED_BASE_SHA256 = "d2ba609ffd8fa4450e0a0662a0c9255dcdf1d8d2b759e63a8de6cf44fbfb114b"
SAVED_BASE_SIZE = 70_577
EXPECTED_ROUTE10_DEMAND_SHA256 = "f60e06f5de337a0acb1aa4716b951a6c6d5477c0ccbe9dc41e57c4814871600d"
EVIDENCE_NAME = "PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json"
OUTPUT_JSON = "PR62_U6_V3_ANCHOR_CONFLICT_REVIEW.json"
OUTPUT_MD = "PR62_U6_V3_ANCHOR_CONFLICT_REVIEW.md"
ROUTE6_GLOBAL_EXECUTION_COUNT = 0


class ReviewError(RuntimeError):
    """A fail-closed evidence authority or recomputation gate failed."""


def require(condition: bool, classification: str) -> None:
    if not condition:
        raise ReviewError(classification)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def semantic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


@contextmanager
def forbid_global_coordinator():
    """Make an accidental global search fail before it can execute."""

    original = coordinator.search_route_service_plans_v1
    observed = {"global_coordinator_executions": 0}

    def forbidden(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        observed["global_coordinator_executions"] += 1
        raise ReviewError("ROUTE10_REVIEW_GLOBAL_COORDINATOR_CALL_PROHIBITED")

    coordinator.search_route_service_plans_v1 = forbidden
    try:
        yield observed
    finally:
        coordinator.search_route_service_plans_v1 = original


def git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    require(result.returncode == 0, "REVIEW_GIT_AUTHORITY_UNAVAILABLE")
    return result.stdout.strip()


def load_authorities(
    *, repo_root: Path, evidence_path: Path, saved_base_path: Path
) -> tuple[dict[str, Any], Any, Any, dict[str, Any]]:
    require(evidence_path.name == EVIDENCE_NAME, "U6_CANONICAL_EVIDENCE_PATH_MISMATCH")
    require(
        file_sha256(evidence_path) == CANONICAL_EVIDENCE_SHA256, "U6_EVIDENCE_BYTE_HASH_MISMATCH"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    canonical = evidence["ROUTE 10"]["canonical"]
    semantic = canonical["semantic"]
    require(canonical["semantic_sha256"] == CANONICAL_SEMANTIC_SHA256, "U6_SEMANTIC_LABEL_MISMATCH")
    require(semantic_hash(semantic) == CANONICAL_SEMANTIC_SHA256, "U6_SEMANTIC_HASH_MISMATCH")
    require(semantic["global_coordinator_executions"] == 0, "U6_RECORDED_GLOBAL_CALL_NONZERO")
    require(
        evidence["ROUTE 6"]
        == {"global_coordinator_executions": 0, "state": "NOT_RUN_ROUTE10_GATE_FAILED"},
        "ROUTE6_CANONICAL_STATE_MISMATCH",
    )
    require(saved_base_path.stat().st_size == SAVED_BASE_SIZE, "ROUTE10_SAVED_BASE_SIZE_MISMATCH")
    require(file_sha256(saved_base_path) == SAVED_BASE_SHA256, "ROUTE10_SAVED_BASE_HASH_MISMATCH")
    with forbid_global_coordinator() as observed:
        context, base = pickle.loads(saved_base_path.read_bytes())
    require(observed["global_coordinator_executions"] == 0, "ROUTE10_REVIEW_GLOBAL_CALL_NONZERO")
    require(context.route_id == "10" and base.route_id == "10", "ROUTE10_CONTEXT_ID_MISMATCH")
    require(len(base.pareto_frontier) == 11, "ROUTE10_BASE_FRONTIER_COUNT_MISMATCH")
    require(
        context.immutable_demand_sha256 == EXPECTED_ROUTE10_DEMAND_SHA256,
        "ROUTE10_DEMAND_HASH_MISMATCH",
    )
    require(
        git_output(repo_root, "merge-base", "--is-ancestor", BASE_SHA, "HEAD") == "",
        "REVIEW_BASE_NOT_ANCESTOR",
    )
    authority = {
        "base_sha": BASE_SHA,
        "canonical_evidence": {
            "path": evidence_path.relative_to(repo_root).as_posix(),
            "size": evidence_path.stat().st_size,
            "sha256": file_sha256(evidence_path),
            "semantic_sha256": CANONICAL_SEMANTIC_SHA256,
        },
        "saved_route10_base": {
            "path": saved_base_path.resolve().as_posix(),
            "size": saved_base_path.stat().st_size,
            "sha256": file_sha256(saved_base_path),
        },
        "immutable_demand_sha256": context.immutable_demand_sha256,
        "route_6_global_execution_count": ROUTE6_GLOBAL_EXECUTION_COUNT,
    }
    return evidence, context, base, authority


def base_direction_records(base: Any) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for pair in base.pareto_frontier:
        for direction in ("outbound", "inbound"):
            candidate = getattr(pair, direction)
            compilation = candidate.compile_variant.compilation
            records[candidate.compile_variant.compilation_fingerprint] = {
                "departures": list(compilation.exact_departures),
                "fingerprint": candidate.compile_variant.compilation_fingerprint,
                "metrics": asdict(candidate.metrics),
                "state": asdict(candidate.state),
                "state_fingerprint": candidate.state_fingerprint,
                "actual_service_regimes": [asdict(item) for item in compilation.service_regimes],
                "origin": "BASE_FRONTIER",
            }
    return records


def direction_records_for_semantic(
    base: Any, semantic: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    records = base_direction_records(base)
    for source in semantic["sources"]:
        for retention in source["retentions"]:
            for candidate in retention["candidates"]:
                record = dict(candidate)
                record["origin"] = "U6_GENERATED"
                record["source_pair_fingerprint"] = source["source"]
                records[record["fingerprint"]] = record
    return records


def demand_bucket_rows(departures: list[int], buckets: Any) -> dict[str, Any]:
    require(len(departures) >= 2, "INDEPENDENT_METRIC_DEPARTURES_TOO_SHORT")
    require(departures == sorted(set(departures)), "INDEPENDENT_METRIC_DEPARTURES_INVALID")
    total_demand = float(sum(bucket.observed_demand for bucket in buckets))
    require(total_demand > 0, "INDEPENDENT_METRIC_DEMAND_EMPTY")
    total_trips = len(departures)
    rows = []
    for index, bucket in enumerate(buckets):
        count = sum(bucket.start <= departure < bucket.end for departure in departures)
        demand_share = float(bucket.observed_demand) / total_demand
        service_share = count / total_trips
        residual = service_share - demand_share
        rows.append(
            {
                "bucket_index": index,
                "start": bucket.start,
                "end": bucket.end,
                "observed_demand": float(bucket.observed_demand),
                "demand_share": demand_share,
                "service_count": count,
                "service_share": service_share,
                "residual": residual,
                "residual_squared": residual**2,
                "absolute_residual": abs(residual),
                "sse_contribution": residual**2,
                "te_contribution": total_trips * 0.5 * abs(residual),
            }
        )
    require(
        sum(row["service_count"] for row in rows) == total_trips, "BUCKET_COUNTS_DO_NOT_COVER_TRIPS"
    )
    sse = sum(row["sse_contribution"] for row in rows)
    te = sum(row["te_contribution"] for row in rows)
    return {
        "total_trips": total_trips,
        "total_demand": total_demand,
        "sse": sse,
        "te": te,
        "l1_residual": sum(row["absolute_residual"] for row in rows),
        "rows": rows,
    }


def exposure_units_by_bucket(departures: list[int], buckets: Any) -> list[float]:
    units = [0.0] * len(buckets)
    for left, right in zip(departures, departures[1:], strict=False):
        width = right - left
        require(width > 0, "EXPOSURE_GAP_NOT_POSITIVE")
        for index, bucket in enumerate(buckets):
            overlap = max(0, min(right, bucket.end) - max(left, bucket.start))
            units[index] += overlap / width
    return units


def equal_gap_runs(departures: list[int]) -> list[dict[str, int]]:
    gaps = [(right - left) // 60 for left, right in zip(departures, departures[1:], strict=False)]
    runs: list[dict[str, int]] = []
    for gap in gaps:
        if runs and runs[-1]["headway_minutes"] == gap:
            runs[-1]["gap_count"] += 1
        else:
            runs.append({"headway_minutes": gap, "gap_count": 1})
    return runs


def metric_value(record: dict[str, Any], name: str) -> Any:
    return record["metrics"][name]


def candidate_lineage(
    semantic: dict[str, Any], pair_fingerprint: str, base_pairs: set[str]
) -> dict[str, Any]:
    parent_by_child = {row["child_fingerprint"]: row for row in semantic["parents"]}
    source_by_pair: dict[str, str] = {}
    for source in semantic["sources"]:
        for decision in source["pair_decisions"]:
            if decision["pair_fingerprint"]:
                source_by_pair.setdefault(decision["pair_fingerprint"], source["source"])
    is_base = pair_fingerprint in base_pairs
    parent = None if is_base else parent_by_child.get(pair_fingerprint)
    return {
        "present_in_original_11_candidate_base_frontier": is_base,
        "generated_by_u6": not is_base,
        "source_pair_fingerprint": None if is_base else source_by_pair.get(pair_fingerprint),
        "parent_pair_fingerprint": None if parent is None else parent["parent_fingerprint"],
        "parent_rhythm": None if parent is None else parent["parent_rhythm"],
        "child_rhythm": None if parent is None else parent["child_rhythm"],
    }


def scenario_access(context: Any) -> dict[str, float]:
    return {
        direction: coordinator.expected_passenger_wait_metrics_v1(
            context.scenario_b_departures[direction], context.demand_buckets[direction]
        )[1]
        for direction in ("outbound", "inbound")
    }


def stage_fingerprints(selection: dict[str, Any], stage: str) -> set[str]:
    trace = next(row for row in selection["stage_trace"] if row["stage"] == stage)
    return set(trace["retained_fingerprints"])


def candidate_snapshot(
    *,
    pair: dict[str, Any],
    records: dict[str, dict[str, Any]],
    context: Any,
    semantic: dict[str, Any],
    base_pairs: set[str],
    hard_fingerprints: set[str],
    access_fingerprints: set[str],
    scenario_max: dict[str, float],
) -> dict[str, Any]:
    directions: dict[str, Any] = {}
    hard_checks: dict[str, bool] = {}
    for direction in ("outbound", "inbound"):
        record = records[pair[direction]]
        departures = list(record["departures"])
        buckets = context.demand_buckets[direction]
        independent = demand_bucket_rows(departures, buckets)
        serialized_sse = float(metric_value(record, "observed_demand_mismatch"))
        require(
            abs(independent["sse"] - serialized_sse) <= NUMERICAL_EPSILON,
            "DIRECTIONAL_SSE_RECOMPUTATION_MISMATCH",
        )
        serialized_counts = list(metric_value(record, "bucket_service_counts"))
        require(
            serialized_counts == [row["service_count"] for row in independent["rows"]],
            "DIRECTIONAL_BUCKET_COUNT_RECOMPUTATION_MISMATCH",
        )
        expected_wait, max_wait, _per_bucket, active_mass = (
            coordinator.expected_passenger_wait_metrics_v1(departures, buckets)
        )
        require(
            abs(
                expected_wait
                - float(metric_value(record, "demand_weighted_expected_passenger_wait_minutes"))
            )
            <= NUMERICAL_EPSILON,
            "DIRECTIONAL_WAIT_RECOMPUTATION_MISMATCH",
        )
        require(
            abs(max_wait - float(metric_value(record, "maximum_bucket_expected_wait_minutes")))
            <= NUMERICAL_EPSILON,
            "DIRECTIONAL_ACCESS_RECOMPUTATION_MISMATCH",
        )
        continuous = continuous_exposure_metrics_v3(
            departures,
            tuple(
                {"start": b.start, "end": b.end, "observed_demand": b.observed_demand}
                for b in buckets
            ),
        )
        state = record["state"]
        reconstructed_state = ServicePlanStateV1(
            **{
                **state,
                "service_regimes": tuple(
                    ServiceRegimeDecisionV1(**item) for item in state["service_regimes"]
                ),
            }
        )
        state_trip_count = sum(item["trip_count"] for item in state["service_regimes"])
        direction_checks = {
            "fixed_trip_total": len(departures)
            == len(context.scenario_b_departures[direction])
            == state_trip_count,
            "fixed_endpoints": departures[0]
            == context.endpoint_authority[direction].fixed_first_departure
            and departures[-1] == context.endpoint_authority[direction].fixed_last_departure,
            "strictly_increasing": departures == sorted(set(departures)),
            "whole_minute": all(value % 60 == 0 for value in departures),
            "tail_eligible": bool(metric_value(record, "tail_ordering")["eligible"]),
            "state_fingerprint_valid": (
                record["state_fingerprint"] == service_plan_fingerprint_v1(reconstructed_state)
            ),
        }
        protection = validate_closed_loop_service_protection_v1(
            authority=context.service_protection_authority,
            direction=direction,
            exact_departures=departures,
        )
        direction_checks["protection_valid"] = protection.passed
        hard_checks.update({f"{direction}_{key}": value for key, value in direction_checks.items()})
        runs = equal_gap_runs(departures)
        require(
            len(runs) == int(metric_value(record, "actual_service_regime_count")),
            "SERVICE_REGIME_RUN_RECONSTRUCTION_MISMATCH",
        )
        directions[direction] = {
            "compilation_fingerprint": pair[direction],
            "state_fingerprint": record["state_fingerprint"],
            "state_parent_fingerprint": state.get("parent_fingerprint"),
            "exact_departures": departures,
            "service_regime_headway_runs": runs,
            "bucket_metrics": independent,
            "continuous_exposure_equivalent": float(continuous["equivalent"]),
            "expected_passenger_wait_minutes": expected_wait,
            "maximum_access_minutes": max_wait,
            "active_demand_mass": active_mass,
            "tail_eligible": direction_checks["tail_eligible"],
            "protection_valid": protection.passed,
            "exposure_units_by_bucket": exposure_units_by_bucket(departures, buckets),
        }
    fleet = coordinator.build_minimum_fleet_plan_v1(
        route_id="10",
        outbound_candidate_id=pair["outbound"],
        inbound_candidate_id=pair["inbound"],
        outbound_departures=directions["outbound"]["exact_departures"],
        inbound_departures=directions["inbound"]["exact_departures"],
        runtime_minutes=context.runtime_minutes,
        minimum_layover_minutes=context.minimum_layover_minutes,
    )
    fleet_valid = (
        fleet.fleet_requirement == pair["metrics"]["fleet_required"] <= pair["fleet_ceiling"]
    )
    connections = [
        item for item in fleet.assignments if item.connection_layover_minutes is not None
    ]
    excess_waits = [
        max(0, int(item.connection_layover_minutes) - context.minimum_layover_minutes)
        for item in connections
    ]
    assignment_by_id = {item.trip_id: item for item in fleet.assignments}
    hard_checks["exact_fleet_valid"] = fleet_valid
    hard_checks["terminal_excess_recomputed"] = (
        sum(excess_waits) == pair["metrics"]["total_excess_terminal_wait"]
        and max(excess_waits, default=0) == pair["metrics"]["max_excess_terminal_wait"]
    )
    hard_checks["minimum_layover_valid"] = all(
        item.connection_layover_minutes >= context.minimum_layover_minutes for item in connections
    )
    hard_checks["no_invented_deadhead"] = all(
        item.next_trip_id is None or assignment_by_id[item.next_trip_id].direction != item.direction
        for item in fleet.assignments
    )
    recomputed_pair_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "route_id": "10",
                "outbound_compile": pair["outbound"],
                "inbound_compile": pair["inbound"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    hard_checks["pair_fingerprint_valid"] = recomputed_pair_fingerprint == pair["fingerprint"]
    hard_checks["canonical_hard_stage_retained"] = pair["fingerprint"] in hard_fingerprints
    hard_checks["independent_access_safe"] = all(
        directions[direction]["maximum_access_minutes"]
        <= scenario_max[direction] + NUMERICAL_EPSILON
        for direction in ("outbound", "inbound")
    )
    hard_checks["canonical_access_stage_retained"] = pair["fingerprint"] in access_fingerprints
    require(all(hard_checks.values()), "ANCHOR_UPSTREAM_GATE_REVALIDATION_FAILED")
    outbound = directions["outbound"]
    inbound = directions["inbound"]
    pair_sse = outbound["bucket_metrics"]["sse"] + inbound["bucket_metrics"]["sse"]
    pair_te = outbound["bucket_metrics"]["te"] + inbound["bucket_metrics"]["te"]
    pair_continuous = (
        outbound["continuous_exposure_equivalent"] + inbound["continuous_exposure_equivalent"]
    )
    pair_mass = outbound["active_demand_mass"] + inbound["active_demand_mass"]
    pair_wait = (
        outbound["expected_passenger_wait_minutes"] * outbound["active_demand_mass"]
        + inbound["expected_passenger_wait_minutes"] * inbound["active_demand_mass"]
    ) / pair_mass
    require(
        abs(pair_sse - float(pair["metrics"]["observed_demand_mismatch"])) <= NUMERICAL_EPSILON,
        "PAIR_SSE_RECOMPUTATION_MISMATCH",
    )
    require(
        abs(pair_wait - float(pair["metrics"]["demand_weighted_expected_passenger_wait_minutes"]))
        <= NUMERICAL_EPSILON,
        "PAIR_WAIT_RECOMPUTATION_MISMATCH",
    )
    return {
        "fingerprint": pair["fingerprint"],
        "lineage": candidate_lineage(semantic, pair["fingerprint"], base_pairs),
        "outbound_compilation_fingerprint": pair["outbound"],
        "inbound_compilation_fingerprint": pair["inbound"],
        "directions": directions,
        "rhythm_tuple": list(pair["rhythm"]),
        "fleet": pair["metrics"]["fleet_required"],
        "terminal_excess": {
            "total": pair["metrics"]["total_excess_terminal_wait"],
            "maximum": pair["metrics"]["max_excess_terminal_wait"],
        },
        "expected_passenger_wait_minutes": pair_wait,
        "directional_maximum_access_minutes": {
            direction: directions[direction]["maximum_access_minutes"]
            for direction in ("outbound", "inbound")
        },
        "pair_continuous_exposure_equivalent": pair_continuous,
        "sse": pair_sse,
        "te": pair_te,
        "hard_feasible": True,
        "access_safe": True,
        "tail_eligible": True,
        "protection_valid": True,
        "exact_fleet_valid": fleet_valid,
        "hard_gate_checks": hard_checks,
    }


def rank(value: float, values: list[float]) -> int:
    return 1 + sum(other < value - NUMERICAL_EPSILON for other in values)


def unique_best(snapshots: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    best = min(item[metric] for item in snapshots)
    matches = [item for item in snapshots if item[metric] <= best + NUMERICAL_EPSILON]
    require(len(matches) == 1, f"{metric.upper()}_BEST_NOT_UNIQUE")
    return matches[0]


def reconstruct_access_safe(
    *, semantic: dict[str, Any], context: Any, base: Any
) -> list[dict[str, Any]]:
    records = direction_records_for_semantic(base, semantic)
    base_pairs = {pair.pair_fingerprint for pair in base.pareto_frontier}
    selection = semantic["final_selection"]
    hard = stage_fingerprints(selection, "HARD_OPERATIONAL_FEASIBILITY")
    access = stage_fingerprints(selection, "SCENARIO_B_MAX_ACCESS_NON_REGRESSION")
    pairs = {pair["fingerprint"]: pair for pair in semantic["final_pareto"]}
    require(set(pairs) == hard, "FINAL_PARETO_AND_HARD_STAGE_DIVERGED")
    snapshots = [
        candidate_snapshot(
            pair=pairs[fingerprint],
            records=records,
            context=context,
            semantic=semantic,
            base_pairs=base_pairs,
            hard_fingerprints=hard,
            access_fingerprints=access,
            scenario_max=scenario_access(context),
        )
        for fingerprint in sorted(access)
    ]
    require(
        len(snapshots) == selection["passenger_access_safe_count"], "ACCESS_SAFE_COUNT_MISMATCH"
    )
    return snapshots


def attach_ranks(snapshots: list[dict[str, Any]]) -> None:
    for metric in ("sse", "te", "pair_continuous_exposure_equivalent"):
        values = [item[metric] for item in snapshots]
        rank_name = (
            "continuous_rank"
            if metric == "pair_continuous_exposure_equivalent"
            else f"{metric}_rank"
        )
        for item in snapshots:
            item[rank_name] = rank(item[metric], values)
    for direction in ("outbound", "inbound"):
        for metric in ("sse", "te"):
            values = [item["directions"][direction]["bucket_metrics"][metric] for item in snapshots]
            for item in snapshots:
                item["directions"][direction][f"{metric}_rank"] = rank(
                    item["directions"][direction]["bucket_metrics"][metric], values
                )


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    directions: dict[str, Any] = {}
    for direction in ("outbound", "inbound"):
        item = candidate["directions"][direction]
        directions[direction] = {
            "compilation_fingerprint": item["compilation_fingerprint"],
            "state_fingerprint": item["state_fingerprint"],
            "state_parent_fingerprint": item["state_parent_fingerprint"],
            "exact_departures": item["exact_departures"],
            "service_regime_headway_runs": item["service_regime_headway_runs"],
            "sse": item["bucket_metrics"]["sse"],
            "te": item["bucket_metrics"]["te"],
            "sse_rank": item["sse_rank"],
            "te_rank": item["te_rank"],
            "continuous_exposure_equivalent": item["continuous_exposure_equivalent"],
            "maximum_access_minutes": item["maximum_access_minutes"],
            "expected_passenger_wait_minutes": item["expected_passenger_wait_minutes"],
        }
    return {
        "fingerprint": candidate["fingerprint"],
        "lineage": candidate["lineage"],
        "outbound_compilation_fingerprint": candidate["outbound_compilation_fingerprint"],
        "inbound_compilation_fingerprint": candidate["inbound_compilation_fingerprint"],
        "directions": directions,
        "rhythm_tuple": candidate["rhythm_tuple"],
        "fleet": candidate["fleet"],
        "terminal_excess": candidate["terminal_excess"],
        "expected_passenger_wait_minutes": candidate["expected_passenger_wait_minutes"],
        "directional_maximum_access_minutes": candidate["directional_maximum_access_minutes"],
        "pair_continuous_exposure_equivalent": candidate["pair_continuous_exposure_equivalent"],
        "continuous_rank": candidate["continuous_rank"],
        "sse": candidate["sse"],
        "sse_rank": candidate["sse_rank"],
        "te": candidate["te"],
        "te_rank": candidate["te_rank"],
        "hard_feasible": candidate["hard_feasible"],
        "access_safe": candidate["access_safe"],
        "tail_eligible": candidate["tail_eligible"],
        "protection_valid": candidate["protection_valid"],
        "exact_fleet_valid": candidate["exact_fleet_valid"],
        "hard_gate_checks": candidate["hard_gate_checks"],
    }


def differing_anchor_buckets(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for direction in ("outbound", "inbound"):
        left_rows = left["directions"][direction]["bucket_metrics"]["rows"]
        right_rows = right["directions"][direction]["bucket_metrics"]["rows"]
        for a, b in zip(left_rows, right_rows, strict=True):
            if (
                a["service_count"] == b["service_count"]
                and abs(a["residual"] - b["residual"]) <= NUMERICAL_EPSILON
            ):
                continue
            rows.append(
                {
                    "direction": direction,
                    "bucket_index": a["bucket_index"],
                    "start": a["start"],
                    "end": a["end"],
                    "observed_demand": a["observed_demand"],
                    "demand_share": a["demand_share"],
                    "sse_best": {
                        key: a[key]
                        for key in (
                            "service_count",
                            "service_share",
                            "residual",
                            "residual_squared",
                            "absolute_residual",
                            "sse_contribution",
                            "te_contribution",
                        )
                    },
                    "te_best": {
                        key: b[key]
                        for key in (
                            "service_count",
                            "service_share",
                            "residual",
                            "residual_squared",
                            "absolute_residual",
                            "sse_contribution",
                            "te_contribution",
                        )
                    },
                    "te_best_minus_sse_best": {
                        "service_count": b["service_count"] - a["service_count"],
                        "residual": b["residual"] - a["residual"],
                        "sse_contribution": b["sse_contribution"] - a["sse_contribution"],
                        "te_contribution": b["te_contribution"] - a["te_contribution"],
                    },
                }
            )
    return rows


def bucket_index(value: int, buckets: Any) -> int:
    return next(index for index, bucket in enumerate(buckets) if bucket.start <= value < bucket.end)


def departure_and_edge_audit(
    left: dict[str, Any], right: dict[str, Any], context: Any
) -> dict[str, Any]:
    by_direction: dict[str, Any] = {}
    totals = {
        "changed_departures": 0,
        "total_absolute_departure_shift_minutes": 0.0,
        "departures_crossing_bucket_boundary": 0,
        "bucket_assignments_changed": 0,
        "service_exposure_changes_without_point_count_changes": 0,
    }
    for direction in ("outbound", "inbound"):
        a = left["directions"][direction]
        b = right["directions"][direction]
        buckets = context.demand_buckets[direction]
        require(
            len(a["exact_departures"]) == len(b["exact_departures"]), "ANCHOR_TRIP_TOTALS_DIFFER"
        )
        changes = []
        for index, (x, y) in enumerate(
            zip(a["exact_departures"], b["exact_departures"], strict=True)
        ):
            if x == y:
                continue
            old_bucket = bucket_index(x, buckets)
            new_bucket = bucket_index(y, buckets)
            changes.append(
                {
                    "trip_index": index,
                    "sse_best_departure": x,
                    "te_best_departure": y,
                    "shift_minutes": (y - x) / 60,
                    "sse_best_bucket": old_bucket,
                    "te_best_bucket": new_bucket,
                    "crossed_bucket_boundary": old_bucket != new_bucket,
                }
            )
        counts_a = [row["service_count"] for row in a["bucket_metrics"]["rows"]]
        counts_b = [row["service_count"] for row in b["bucket_metrics"]["rows"]]
        exposure_rows = []
        for index, (count_a, count_b, exposure_a, exposure_b) in enumerate(
            zip(
                counts_a,
                counts_b,
                a["exposure_units_by_bucket"],
                b["exposure_units_by_bucket"],
                strict=True,
            )
        ):
            if count_a == count_b and abs(exposure_a - exposure_b) > NUMERICAL_EPSILON:
                exposure_rows.append(
                    {
                        "bucket_index": index,
                        "start": buckets[index].start,
                        "end": buckets[index].end,
                        "point_count": count_a,
                        "sse_best_exposure_units": exposure_a,
                        "te_best_exposure_units": exposure_b,
                        "delta": exposure_b - exposure_a,
                    }
                )
        changed_assignments = sum(item["crossed_bucket_boundary"] for item in changes)
        result = {
            "changed_departures": len(changes),
            "total_absolute_departure_shift_minutes": sum(
                abs(item["shift_minutes"]) for item in changes
            ),
            "departures_crossing_bucket_boundary": changed_assignments,
            "bucket_assignments_changed": changed_assignments,
            "service_count_vector_sse_best": counts_a,
            "service_count_vector_te_best": counts_b,
            "changed_bucket_count": sum(x != y for x, y in zip(counts_a, counts_b, strict=True)),
            "service_exposure_changes_without_point_count_changes": len(exposure_rows),
            "exposure_only_rows": exposure_rows,
            "changed_departure_rows": changes,
        }
        by_direction[direction] = result
        for key in totals:
            totals[key] += result[key]
    return {"directions": by_direction, "pair": totals}


def norm_profile(candidate: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row
        for direction in ("outbound", "inbound")
        for row in candidate["directions"][direction]["bucket_metrics"]["rows"]
    ]
    nonzero = [row for row in rows if row["absolute_residual"] > NUMERICAL_EPSILON]
    l1 = sum(row["absolute_residual"] for row in rows)
    squared = sum(row["residual_squared"] for row in rows)
    ordered = sorted((row["absolute_residual"] for row in rows), reverse=True)
    return {
        "nonzero_residual_bucket_count": len(nonzero),
        "l1_residual_sum_unscaled": l1,
        "squared_residual_sum": squared,
        "maximum_absolute_residual": max(row["absolute_residual"] for row in rows),
        "residual_concentration_index_sum_squared_over_l1_squared": squared / (l1**2),
        "top_2_absolute_residual_share_of_l1": sum(ordered[:2]) / l1,
        "top_5_absolute_residual_share_of_l1": sum(ordered[:5]) / l1,
        "top_absolute_residuals": sorted(
            (
                {
                    "direction": direction,
                    "bucket_index": row["bucket_index"],
                    "absolute_residual": row["absolute_residual"],
                    "squared_contribution": row["residual_squared"],
                    "te_contribution": row["te_contribution"],
                }
                for direction in ("outbound", "inbound")
                for row in candidate["directions"][direction]["bucket_metrics"]["rows"]
                if row["absolute_residual"] > NUMERICAL_EPSILON
            ),
            key=lambda item: (-item["absolute_residual"], item["direction"], item["bucket_index"]),
        )[:8],
    }


def concordance(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    concordant = discordant = tied_sse_only = tied_te_only = tied_both = 0
    for index, left in enumerate(snapshots):
        for right in snapshots[index + 1 :]:
            ds = left["sse"] - right["sse"]
            dt = left["te"] - right["te"]
            s_tie = abs(ds) <= NUMERICAL_EPSILON
            t_tie = abs(dt) <= NUMERICAL_EPSILON
            if s_tie and t_tie:
                tied_both += 1
            elif s_tie:
                tied_sse_only += 1
            elif t_tie:
                tied_te_only += 1
            elif ds * dt < 0:
                discordant += 1
            else:
                concordant += 1
    denominator = math.sqrt(
        (concordant + discordant + tied_sse_only) * (concordant + discordant + tied_te_only)
    )
    tau_b = (concordant - discordant) / denominator if denominator else 0.0

    def top(metric: str, count: int) -> list[str]:
        return [
            item["fingerprint"]
            for item in sorted(snapshots, key=lambda row: (row[metric], row["fingerprint"]))[:count]
        ]

    result: dict[str, Any] = {
        "candidate_count": len(snapshots),
        "possible_pair_count": len(snapshots) * (len(snapshots) - 1) // 2,
        "concordant_pairs": concordant,
        "sse_te_ordering_disagreements": discordant,
        "tied_sse_only": tied_sse_only,
        "tied_te_only": tied_te_only,
        "tied_both": tied_both,
        "kendall_tau_b": tau_b,
    }
    for count in (5, 10):
        sse_top = top("sse", count)
        te_top = top("te", count)
        result[f"top_{count}"] = {
            "sse": sse_top,
            "te": te_top,
            "overlap_count": len(set(sse_top) & set(te_top)),
            "common": sorted(set(sse_top) & set(te_top)),
        }
    result["same_candidate_at_exact_rank"] = {
        str(index): sorted(
            {item["fingerprint"] for item in snapshots if item["sse_rank"] == index}
            & {item["fingerprint"] for item in snapshots if item["te_rank"] == index}
        )
        for index in range(1, 11)
    }
    return result


def universe_anchor_summary(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    attach_ranks(snapshots)
    sse_best = unique_best(snapshots, "sse")
    te_best = unique_best(snapshots, "te")
    continuous_best = unique_best(snapshots, "pair_continuous_exposure_equivalent")
    return {
        "pareto_count": None,
        "access_safe_count": len(snapshots),
        "sse_best_fingerprint": sse_best["fingerprint"],
        "sse_best_value": sse_best["sse"],
        "te_at_sse_best": sse_best["te"],
        "te_best_fingerprint": te_best["fingerprint"],
        "te_best_value": te_best["te"],
        "sse_at_te_best": te_best["sse"],
        "common_anchor": sse_best["fingerprint"] == te_best["fingerprint"],
        "continuous_best_fingerprint": continuous_best["fingerprint"],
        "continuous_best_value": continuous_best["pair_continuous_exposure_equivalent"],
    }


def source_batch_history(semantic: dict[str, Any], context: Any, base: Any) -> dict[str, Any]:
    universes = [semantic["base_pareto"], *[source["pareto"] for source in semantic["sources"]]]
    selections = semantic["selection_history"]
    labels = ["BASE_FRONTIER", *semantic["processed_source_order"]]
    require(
        len(universes) == len(selections) == len(labels), "U6_SOURCE_HISTORY_ALIGNMENT_MISMATCH"
    )
    full_records = direction_records_for_semantic(base, semantic)
    base_pairs = {pair.pair_fingerprint for pair in base.pareto_frontier}
    scenario_max = scenario_access(context)
    rows = []
    previous_access: set[str] = set()
    for index, (pairs, selection, label) in enumerate(
        zip(universes, selections, labels, strict=True)
    ):
        hard = stage_fingerprints(selection, "HARD_OPERATIONAL_FEASIBILITY")
        access = stage_fingerprints(selection, "SCENARIO_B_MAX_ACCESS_NON_REGRESSION")
        pair_map = {pair["fingerprint"]: pair for pair in pairs}
        snapshots = [
            candidate_snapshot(
                pair=pair_map[fingerprint],
                records=full_records,
                context=context,
                semantic=semantic,
                base_pairs=base_pairs,
                hard_fingerprints=hard,
                access_fingerprints=access,
                scenario_max=scenario_max,
            )
            for fingerprint in sorted(access)
        ]
        summary = universe_anchor_summary(snapshots)
        summary.update(
            {
                "batch_index": index,
                "completed_source_batch": label,
                "pareto_count": len(pairs),
                "v3_classification": selection["classification"],
                "newly_access_safe_fingerprints": sorted(access - previous_access),
            }
        )
        rows.append(summary)
        previous_access = access
    transition_index = next(
        index
        for index in range(1, len(rows))
        if rows[index - 1]["common_anchor"] and not rows[index]["common_anchor"]
    )
    transition = rows[transition_index]
    responsible = sorted(
        set(transition["newly_access_safe_fingerprints"])
        & {transition["sse_best_fingerprint"], transition["te_best_fingerprint"]}
    )
    transition["new_anchor_candidates_responsible"] = responsible
    transition["responsible_lineage"] = {
        fingerprint: candidate_lineage(semantic, fingerprint, base_pairs)
        for fingerprint in responsible
    }
    return {
        "history": rows,
        "first_common_anchor_to_conflict_transition": transition,
    }


def cap_stability(evidence: dict[str, Any], context: Any, base: Any) -> dict[str, Any]:
    runs = evidence["ROUTE 10"]["sensitivity"]["independent_runs"]
    summaries: dict[str, Any] = {}
    conflict_pairs = []
    for cap in ("16", "32", "64"):
        run = runs[cap]
        semantic = run["semantic"]
        require(semantic["global_coordinator_executions"] == 0, f"CAP{cap}_GLOBAL_CALL_NONZERO")
        snapshots = reconstruct_access_safe(semantic=semantic, context=context, base=base)
        summary = universe_anchor_summary(snapshots)
        summary.update(
            {
                "pareto_count": len(semantic["final_pareto"]),
                "semantic_sha256": run["semantic_sha256"],
                "v3_classification": semantic["final_selection"]["classification"],
            }
        )
        by_fingerprint = {item["fingerprint"]: item for item in snapshots}
        summary["sse_best_continuous_rank"] = by_fingerprint[summary["sse_best_fingerprint"]][
            "continuous_rank"
        ]
        summary["te_best_continuous_rank"] = by_fingerprint[summary["te_best_fingerprint"]][
            "continuous_rank"
        ]
        summaries[cap] = summary
        conflict_pairs.append((summary["sse_best_fingerprint"], summary["te_best_fingerprint"]))
    identical = len(set(conflict_pairs)) == 1
    return {
        "caps": summaries,
        "anchor_conflict_classification": (
            "ANCHOR_CONFLICT_CAP_STABLE"
            if identical
            else "ANCHOR_CONFLICT_CANDIDATE_UNIVERSE_SENSITIVE"
        ),
        "exact_same_conflict_pair_all_caps": identical,
        "selection_cap_binding_reported_by_u6": evidence["ROUTE 10"]["sensitivity"]["binding"],
        "selection_cap_binding_classification_reported_by_u6": evidence["ROUTE 10"]["sensitivity"][
            "classification"
        ],
        "selection_cap_binding_is_not_selector_adequacy_evidence": True,
    }


def historical_concordance(repo_root: Path) -> dict[str, Any]:
    root = repo_root / "docs" / "engine" / "evidence"
    names = {
        "M": "PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json",
        "M1": "PR62_M1_RANK_CONCORDANCE_CLARIFICATION.json",
        "N": "PR62_N_ONE_TRIP_POLICY_REHEARSAL.json",
        "O": "PR62_O_PRODUCTION_POLICY_FREEZE.json",
        "R": "PR62_R_DEMAND_FIT_METRIC_VALIDITY.json",
        "S": "PR62_S_PHASE_ROBUST_MATERIALITY_POLICY_EXPERIMENT.json",
        "T": "PR62_T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE.json",
    }
    source_hashes = {name: file_sha256(root / path) for name, path in names.items()}
    m = json.loads((root / names["M"]).read_text(encoding="utf-8"))
    m1 = json.loads((root / names["M1"]).read_text(encoding="utf-8"))
    o = json.loads((root / names["O"]).read_text(encoding="utf-8"))
    r = json.loads((root / names["R"]).read_text(encoding="utf-8"))
    t = json.loads((root / names["T"]).read_text(encoding="utf-8"))
    return {
        "source_sha256": source_hashes,
        "candidate_universes": {
            "PR62_M_M1_N_O_route_6": {"pareto": 47, "hard_feasible": 47, "access_safe": 41},
            "PR62_M_M1_N_O_route_10": {"pareto": 11, "hard_feasible": 11, "access_safe": 7},
            "PR62_R_S_T_route_6": {"production_access_safe": 41},
            "PR62_R_S_T_route_10": {"production_access_safe": 7, "q_augmented_review": 8},
        },
        "verified_source_facts": {
            "M_route10_top_same": m["routes"]["10"]["metric_ordering_audit"]["same_best_candidate"],
            "M1_route10_pairwise_disagreements": m1["routes"]["10"]["pairwise_disagreement_count"],
            "M1_route6_pairwise_disagreements": m1["routes"]["6"]["pairwise_disagreement_count"],
            "O_anchor_fail_closed": o["V2_current_production_selector"]["anchor_fail_closed"],
            "R_anchor_classification": r["anchor_validity"]["classification"],
            "T_common_anchor_stage": t["priority_order"][2],
        },
        "answers": {
            "why_common_anchor_was_adopted": "SSE remained production authority while TE supplied passenger-interpretable materiality; the frozen 41/7 access-safe universes empirically had the same unique top candidate.",
            "empirical_or_invariant": "EMPIRICAL_EVIDENCE_NOT_MATHEMATICAL_INVARIANT",
            "m1_lower_rank_disagreement": True,
            "r_s_t_preserved_without_expanded_universe_proof": True,
            "u6_first_real_top_rank_counterexample": True,
            "prior_evidence_supported": "Top-rank concordance on the then-current Route 6 and Route 10 access-safe universes, despite known lower-rank disagreements.",
            "prior_evidence_did_not_support": "A theorem or invariant guaranteeing one common SSE/TE minimizer after materially expanding the candidate universe.",
        },
    }


def policy_options(continuous_best_relation: str) -> dict[str, Any]:
    shared = {
        "route_6_control_basis": "Historical 41-candidate control evidence only; Route 6 was not executed in this review.",
        "implementation_status": "NOT_IMPLEMENTED",
    }
    return {
        "A_SSE_AUTHORITATIVE_ANCHOR": {
            **shared,
            "historical_policy_intent": "Strongest continuity: M/N explicitly kept production SSE authoritative.",
            "passenger_interpretation": "Indirect; TE remains the service-mass calibration diagnostic.",
            "bucket_edge_sensitivity": "Retains point-count boundary sensitivity.",
            "candidate_growth_stability": "Always defines a scalar anchor when the SSE minimum is unique, but identity may change as the universe grows.",
            "new_weight_or_threshold": False,
            "fail_closed_semantics": "Preservable through uniqueness and metric-validity gates.",
            "route_10_effect": "Would make the observed SSE-best candidate the anchor; downstream selection was not rehearsed.",
            "expected_route_6_control": "Historical Route 6 SSE/TE top candidate was common, so no historical anchor change is expected.",
            "migration_complexity": "Low.",
        },
        "B_TE_AUTHORITATIVE_ANCHOR": {
            **shared,
            "historical_policy_intent": "Changes anchor authority; aligns with TE's later materiality interpretation but not M/N's SSE-authoritative statement.",
            "passenger_interpretation": "Direct trip-equivalent displaced service mass.",
            "bucket_edge_sensitivity": "Retains point-count boundary sensitivity.",
            "candidate_growth_stability": "Always defines a scalar anchor when the TE minimum is unique, but identity may change as the universe grows.",
            "new_weight_or_threshold": False,
            "fail_closed_semantics": "Preservable through uniqueness and metric-validity gates.",
            "route_10_effect": "Would make the observed TE-best candidate the anchor; downstream selection was not rehearsed.",
            "expected_route_6_control": "Historical Route 6 SSE/TE top candidate was common, so no historical anchor change is expected.",
            "migration_complexity": "Low to medium because authority documentation changes.",
        },
        "C_CONTINUOUS_EXPOSURE_AUTHORITATIVE_ANCHOR": {
            **shared,
            "historical_policy_intent": "Promotes a metric frozen in T for materiality, not anchor authority.",
            "passenger_interpretation": "Phase-robust service-exposure mismatch in trip-equivalent units.",
            "bucket_edge_sensitivity": "Lower point-boundary sensitivity; demand support remains bucket-defined.",
            "candidate_growth_stability": "Scalar and phase-aware, but expanded-universe behavior still needs a policy rehearsal.",
            "new_weight_or_threshold": False,
            "fail_closed_semantics": "Preservable through uniqueness, finite-value, and authority gates.",
            "route_10_effect": f"Continuous exposure {continuous_best_relation}; downstream selection was not rehearsed.",
            "expected_route_6_control": "Historical Route 6 continuous best agreed with the common anchor; U6 Route 6 remains unexecuted.",
            "migration_complexity": "Medium to high because the metric's role changes.",
        },
        "D_MULTI_METRIC_DEMAND_FIT_FRONTIER": {
            **shared,
            "historical_policy_intent": "Acknowledges M1's non-interchangeable rankings but departs from the single-anchor contract.",
            "passenger_interpretation": "Preserves both concentration-sensitive SSE and displaced-mass TE evidence.",
            "bucket_edge_sensitivity": "Retains both point metrics unless phase-robust evidence is added separately.",
            "candidate_growth_stability": "Does not fail solely because minima differ; frontier membership can still grow or change.",
            "new_weight_or_threshold": False,
            "fail_closed_semantics": "Possible, but later-stage admissibility and boundedness must be predeclared to avoid an implicit tradeoff.",
            "route_10_effect": "Would retain both observed anchors in a demand-fit nondominated set; no final timetable was selected.",
            "expected_route_6_control": "Historical common top remains nondominated; later-stage equivalence has not been rehearsed.",
            "migration_complexity": "High because the selector contract changes from one anchor to a set.",
        },
    }


def aggregation_diagnostic(sse_best: dict[str, Any], te_best: dict[str, Any]) -> dict[str, Any]:
    rows = {}
    for direction in ("outbound", "inbound"):
        a = sse_best["directions"][direction]["bucket_metrics"]
        b = te_best["directions"][direction]["bucket_metrics"]
        rows[direction] = {
            "same_directional_compilation": (
                sse_best["directions"][direction]["compilation_fingerprint"]
                == te_best["directions"][direction]["compilation_fingerprint"]
            ),
            "te_best_minus_sse_best_sse": b["sse"] - a["sse"],
            "te_best_minus_sse_best_te": b["te"] - a["te"],
            "sse_pairwise_preference": "SSE_BEST"
            if a["sse"] < b["sse"] - NUMERICAL_EPSILON
            else ("TE_BEST" if b["sse"] < a["sse"] - NUMERICAL_EPSILON else "TIE"),
            "te_pairwise_preference": "SSE_BEST"
            if a["te"] < b["te"] - NUMERICAL_EPSILON
            else ("TE_BEST" if b["te"] < a["te"] - NUMERICAL_EPSILON else "TIE"),
        }
    same_schedule_driver = [
        direction for direction, row in rows.items() if row["same_directional_compilation"]
    ]
    cross_direction_trade = any(
        rows["outbound"][key] * rows["inbound"][key] < -NUMERICAL_EPSILON
        for key in ("te_best_minus_sse_best_sse", "te_best_minus_sse_best_te")
    )
    return {
        "directions": rows,
        "same_direction_schedule_shared": same_schedule_driver,
        "outbound_inbound_trade_against_each_other": cross_direction_trade,
        "pair_aggregation_introduces_defect": False,
        "diagnosis": (
            "SAME_DIRECTIONAL_SCHEDULE_DRIVES_REVERSAL"
            if same_schedule_driver
            else "OUTBOUND_INBOUND_TRADE"
            if cross_direction_trade
            else "BOTH_DIRECTIONS_CHANGE_WITHOUT_AGGREGATION_DEFECT"
        ),
    }


def materiality(
    sse_best: dict[str, Any], te_best: dict[str, Any], edge: dict[str, Any]
) -> dict[str, Any]:
    delta_continuous = (
        te_best["pair_continuous_exposure_equivalent"]
        - sse_best["pair_continuous_exposure_equivalent"]
    )
    delta_te = te_best["te"] - sse_best["te"]
    return {
        "direction": "SSE_BEST_TO_TE_BEST",
        "delta_sse": te_best["sse"] - sse_best["sse"],
        "delta_te": delta_te,
        "absolute_te_difference": abs(delta_te),
        "delta_continuous_exposure": delta_continuous,
        "delta_average_expected_passenger_wait_minutes": (
            te_best["expected_passenger_wait_minutes"] - sse_best["expected_passenger_wait_minutes"]
        ),
        "delta_maximum_access_minutes": {
            direction: te_best["directional_maximum_access_minutes"][direction]
            - sse_best["directional_maximum_access_minutes"][direction]
            for direction in ("outbound", "inbound")
        },
        "delta_rhythm_tuple": [
            b - a for a, b in zip(sse_best["rhythm_tuple"], te_best["rhythm_tuple"], strict=True)
        ],
        "delta_fleet": te_best["fleet"] - sse_best["fleet"],
        "delta_terminal_excess": {
            key: te_best["terminal_excess"][key] - sse_best["terminal_excess"][key]
            for key in ("total", "maximum")
        },
        "changed_bucket_allocations": sum(
            row["changed_bucket_count"] for row in edge["directions"].values()
        ),
        "changed_departures": edge["pair"]["changed_departures"],
        "within_one_te_of_each_other": abs(delta_te) <= 1.0 + NUMERICAL_EPSILON,
        "historical_v3_route10_continuous_bound": 1.985880666877822,
        "within_historical_continuous_bound_by_absolute_delta": abs(delta_continuous)
        <= 1.985880666877822 + NUMERICAL_EPSILON,
        "historical_continuous_bound_semantically_valid_for_anchor_adjudication": False,
        "historical_bound_note": "The bound was derived only after a common anchor existed and calibrated downstream materiality; it cannot adjudicate which conflicting anchor is authoritative.",
    }


def build_evidence(
    *, repo_root: Path, evidence: dict[str, Any], context: Any, base: Any, authority: dict[str, Any]
) -> dict[str, Any]:
    semantic = evidence["ROUTE 10"]["canonical"]["semantic"]
    require(len(semantic["final_pareto"]) == 123, "CANONICAL_PARETO_COUNT_MISMATCH")
    require(
        semantic["final_selection"]["passenger_access_safe_count"] == 83,
        "CANONICAL_ACCESS_COUNT_MISMATCH",
    )
    require(
        semantic["final_selection"]["classification"] == "DEMAND_FIT_ANCHOR_CONFLICT",
        "CANONICAL_V3_CLASSIFICATION_MISMATCH",
    )
    snapshots = reconstruct_access_safe(semantic=semantic, context=context, base=base)
    attach_ranks(snapshots)
    sse_best = unique_best(snapshots, "sse")
    te_best = unique_best(snapshots, "te")
    continuous_best = unique_best(snapshots, "pair_continuous_exposure_equivalent")
    require(
        sse_best["fingerprint"] != te_best["fingerprint"], "EXPECTED_SSE_TE_CONFLICT_NOT_REPRODUCED"
    )
    differing = differing_anchor_buckets(sse_best, te_best)
    edge = departure_and_edge_audit(sse_best, te_best, context)
    aggregation = aggregation_diagnostic(sse_best, te_best)
    sse_profile = norm_profile(sse_best)
    te_profile = norm_profile(te_best)
    spread_vs_concentrated = {
        "same_nonzero_residual_bucket_count": (
            sse_profile["nonzero_residual_bucket_count"]
            == te_profile["nonzero_residual_bucket_count"]
        ),
        "te_best_has_larger_maximum_absolute_residual": (
            te_profile["maximum_absolute_residual"]
            > sse_profile["maximum_absolute_residual"] + NUMERICAL_EPSILON
        ),
        "te_best_has_more_concentrated_absolute_residual_mass": (
            te_profile["residual_concentration_index_sum_squared_over_l1_squared"]
            > sse_profile["residual_concentration_index_sum_squared_over_l1_squared"]
            + NUMERICAL_EPSILON
        ),
        "sse_best_has_lower_squared_error": sse_best["sse"] < te_best["sse"] - NUMERICAL_EPSILON,
        "te_best_has_lower_absolute_trip_equivalent_error": te_best["te"]
        < sse_best["te"] - NUMERICAL_EPSILON,
    }
    require(all(spread_vs_concentrated.values()), "EXPECTED_NORM_REVERSAL_PATTERN_NOT_CONFIRMED")
    continuous_relation = (
        "agrees with SSE-best"
        if continuous_best["fingerprint"] == sse_best["fingerprint"]
        else "agrees with TE-best"
        if continuous_best["fingerprint"] == te_best["fingerprint"]
        else "prefers a third candidate"
    )
    continuous_delta = abs(
        sse_best["pair_continuous_exposure_equivalent"]
        - te_best["pair_continuous_exposure_equivalent"]
    )
    root_cause = {
        "diagnostic_subclassification": "SSE_TE_NORM_DISAGREEMENT_CONFIRMED",
        "norm_disagreement": True,
        "implementation_or_data_defect": False,
        "aggregation_defect": False,
        "bucket_aliasing_classification": "BUCKET_EDGE_ALIASING_NOT_PRIMARY_DRIVER",
        "bucket_aliasing_material_to_metric_values": edge["pair"][
            "departures_crossing_bucket_boundary"
        ]
        > 0,
        "explanation": "The independently reconstructed candidates use the same frozen bucket assignments for both metrics. Their valid residual vectors reverse order because squared L2 favors more dispersed smaller residuals while L1/TV favors less total displaced mass despite a larger peak residual. Boundary crossings affect the residual vectors, but no separate bucket or pair aggregation path exists between SSE and TE, so aliasing is not the primary cause of their mutual reversal.",
        "residual_pattern": spread_vs_concentrated,
        "sse_best_profile": sse_profile,
        "te_best_profile": te_profile,
        "differing_bucket_count": len(differing),
    }
    continuous = {
        "classification": (
            "CONTINUOUS_EXPOSURE_AGREES_WITH_SSE_BEST"
            if continuous_best["fingerprint"] == sse_best["fingerprint"]
            else "CONTINUOUS_EXPOSURE_AGREES_WITH_TE_BEST"
            if continuous_best["fingerprint"] == te_best["fingerprint"]
            else "CONTINUOUS_EXPOSURE_PREFERS_THIRD_CANDIDATE"
        ),
        "best_fingerprint": continuous_best["fingerprint"],
        "best_value": continuous_best["pair_continuous_exposure_equivalent"],
        "sse_best_value": sse_best["pair_continuous_exposure_equivalent"],
        "sse_best_rank": sse_best["continuous_rank"],
        "sse_best_directional": {
            direction: sse_best["directions"][direction]["continuous_exposure_equivalent"]
            for direction in ("outbound", "inbound")
        },
        "te_best_value": te_best["pair_continuous_exposure_equivalent"],
        "te_best_rank": te_best["continuous_rank"],
        "te_best_directional": {
            direction: te_best["directions"][direction]["continuous_exposure_equivalent"]
            for direction in ("outbound", "inbound")
        },
        "absolute_delta_between_anchors": continuous_delta,
        "nearly_equivalent_at_numerical_epsilon": continuous_delta <= NUMERICAL_EPSILON,
    }
    rankings = [
        {
            "fingerprint": item["fingerprint"],
            "sse": item["sse"],
            "sse_rank": item["sse_rank"],
            "te": item["te"],
            "te_rank": item["te_rank"],
            "continuous_exposure": item["pair_continuous_exposure_equivalent"],
            "continuous_rank": item["continuous_rank"],
        }
        for item in sorted(snapshots, key=lambda row: row["fingerprint"])
    ]
    primary = "COMMON_SSE_TE_ANCHOR_ASSUMPTION_INVALIDATED"
    result = {
        "review_profile": "pr62_u6_v3_anchor_conflict_root_cause_review_v1",
        "authority": authority,
        "metric_definitions_verified_from_source": {
            "bucket_membership": "bucket.start <= departure < bucket.end",
            "directional_sse": "sum((service_share_i - demand_share_i)^2)",
            "pair_sse": "outbound_sse + inbound_sse",
            "directional_te": "directional_trip_count * 0.5 * sum(abs(service_share_i - demand_share_i))",
            "pair_te": "outbound_te + inbound_te",
            "continuous_exposure": "unchanged V3 exact interdeparture exposure-density TV times exact directional departure count; pair is directional sum",
            "numerical_epsilon": NUMERICAL_EPSILON,
        },
        "canonical_universe": {
            "pareto_count": len(semantic["final_pareto"]),
            "hard_feasible_count": semantic["final_selection"]["hard_feasible_count"],
            "access_safe_count": len(snapshots),
            "v3_classification": semantic["final_selection"]["classification"],
            "all_83_independently_recomputed": True,
            "all_serialized_sse_wait_access_values_reproduced_and_te_recomputed_from_source_formula": True,
        },
        "exact_conflict": {
            "sse_best": compact_candidate(sse_best),
            "te_best": compact_candidate(te_best),
            "cross_values": {
                "sse_best_sse": sse_best["sse"],
                "sse_best_te": sse_best["te"],
                "te_best_sse": te_best["sse"],
                "te_best_te": te_best["te"],
            },
            "materially_differing_bucket_rows": differing,
        },
        "root_cause": root_cause,
        "direction_aggregation": aggregation,
        "continuous_exposure_cross_check": continuous,
        "bucket_edge_audit": edge,
        "history": historical_concordance(repo_root),
        "u6_source_batch_history": source_batch_history(semantic, context, base),
        "cap_stability": cap_stability(evidence, context, base),
        "rank_concordance": concordance(snapshots),
        "candidate_rankings": rankings,
        "materiality": materiality(sse_best, te_best, edge),
        "policy_options": policy_options(continuous_relation),
        "primary_classification": primary,
        "next_decision": {
            "recommendation_count": 1,
            "recommendation": "Run one evidence-only PR62-U7 demand-fit authority rehearsal over the saved U6 Route 10 cap/batch universes and the already-committed historical Route 6 snapshots, predeclaring stability, boundary-sensitivity, passenger-interpretability, and fail-closed criteria for options A-D; do not run either global coordinator or select a replacement timetable.",
        },
        "production_changes": False,
        "replacement_timetable_selected": False,
        "route_6_global_execution_count": ROUTE6_GLOBAL_EXECUTION_COUNT,
    }
    require(result["next_decision"]["recommendation_count"] == 1, "NEXT_DECISION_NOT_SINGLE")
    return result


def clock(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def f12(value: float) -> str:
    return f"{value:.12f}"


def render_markdown(evidence: dict[str, Any]) -> str:
    conflict = evidence["exact_conflict"]
    sse = conflict["sse_best"]
    te = conflict["te_best"]
    root = evidence["root_cause"]
    continuous = evidence["continuous_exposure_cross_check"]
    aggregation = evidence["direction_aggregation"]
    material = evidence["materiality"]
    caps = evidence["cap_stability"]
    rank_data = evidence["rank_concordance"]
    lines = [
        "# PR62-U6 V3 anchor conflict review",
        "",
        "This is an evidence/root-cause review only. No selector, coordinator, compiler, validator, Pareto logic, timetable, XLSX, or production policy was changed. No replacement timetable is selected.",
        "",
        "## Authority and invariant",
        "",
        f"- Base SHA: `{evidence['authority']['base_sha']}`.",
        f"- Canonical U6 semantic SHA-256: `{evidence['authority']['canonical_evidence']['semantic_sha256']}`.",
        f"- Canonical U6 evidence SHA-256: `{evidence['authority']['canonical_evidence']['sha256']}`.",
        f"- Frozen Route 10 demand SHA-256: `{evidence['authority']['immutable_demand_sha256']}`.",
        f"- Route 6 global execution count: `{evidence['route_6_global_execution_count']}`.",
        "",
        "Source verification confirms half-open bucket membership `[start,end)`, directional SSE as the sum of squared service-share residuals, and directional TE as directional trips times half the L1 residual. Pair values are directional sums. Thus SSE and TE are L2-squared and L1/TV norms over the same residual vectors; a common minimizer was never mathematically guaranteed.",
        "",
        "## Exact conflict",
        "",
        "The complete canonical 123-candidate Pareto frontier was reconstructed. All 83 access-safe snapshots independently reproduced serialized SSE, expected-wait, and access values within `1e-12`; TE was recomputed from exact counts and the verified V2 formula rather than trusted from serialization.",
        "",
        "| Role | Pair fingerprint | SSE | TE | Cross metric | Continuous | Continuous rank |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        f"| SSE-best | `{sse['fingerprint']}` | {f12(sse['sse'])} | {f12(sse['te'])} | TE={f12(sse['te'])} | {f12(sse['pair_continuous_exposure_equivalent'])} | {sse['continuous_rank']} |",
        f"| TE-best | `{te['fingerprint']}` | {f12(te['sse'])} | {f12(te['te'])} | SSE={f12(te['sse'])} | {f12(te['pair_continuous_exposure_equivalent'])} | {te['continuous_rank']} |",
        "",
        "Both candidates independently satisfy fixed trips/endpoints, strict whole-minute departures, tail eligibility, protected-service authority, Scenario-B directional access, and exact fleet validation; both also appear in the canonical hard-feasible and access-safe stage traces.",
        "",
        "### Candidate identity and operations",
        "",
    ]
    for role, candidate in (("SSE-best", sse), ("TE-best", te)):
        lines.extend(
            [
                f"#### {role}",
                "",
                f"- Lineage: `{json.dumps(candidate['lineage'], sort_keys=True, separators=(',', ':'))}`.",
                f"- Outbound/inbound compilation: `{candidate['outbound_compilation_fingerprint']}` / `{candidate['inbound_compilation_fingerprint']}`.",
                f"- Rhythm tuple: `{candidate['rhythm_tuple']}`; fleet `{candidate['fleet']}`; terminal excess total/max `{candidate['terminal_excess']['total']}` / `{candidate['terminal_excess']['maximum']}`.",
                f"- Average expected passenger wait: `{f12(candidate['expected_passenger_wait_minutes'])}` minutes; maximum access outbound/inbound `{f12(candidate['directional_maximum_access_minutes']['outbound'])}` / `{f12(candidate['directional_maximum_access_minutes']['inbound'])}` minutes.",
            ]
        )
        for direction in ("outbound", "inbound"):
            item = candidate["directions"][direction]
            departures = ", ".join(clock(value) for value in item["exact_departures"])
            headways = ", ".join(
                f"{row['headway_minutes']}m×{row['gap_count']}"
                for row in item["service_regime_headway_runs"]
            )
            lines.extend(
                [
                    f"- {direction.title()} exact departures: `{departures}`.",
                    f"- {direction.title()} exact ServiceRegime headway runs: `{headways}`.",
                ]
            )
        lines.append("")
    lines.extend(
        [
            "## Root cause",
            "",
            f"Diagnostic sub-classification: **{root['diagnostic_subclassification']}**.",
            "",
            root["explanation"],
            "",
            f"Both candidates have `{root['sse_best_profile']['nonzero_residual_bucket_count']}` nonzero residual buckets, so the reversal is not a literal nonzero-bucket-count difference. The SSE-best maximum absolute residual is `{f12(root['sse_best_profile']['maximum_absolute_residual'])}` and its concentration index is `{f12(root['sse_best_profile']['residual_concentration_index_sum_squared_over_l1_squared'])}`; TE-best has the larger peak `{f12(root['te_best_profile']['maximum_absolute_residual'])}` and higher concentration index `{f12(root['te_best_profile']['residual_concentration_index_sum_squared_over_l1_squared'])}`. Squared error rejects that concentration, while L1/TV accepts it because total displaced service mass falls from `{f12(root['sse_best_profile']['l1_residual_sum_unscaled'])}` to `{f12(root['te_best_profile']['l1_residual_sum_unscaled'])}`.",
            "",
            "### Materially differing buckets",
            "",
            "Only buckets whose point-count residuals differ are shown.",
            "",
            "| Dir | Bucket | Demand share | SSE-best count/residual/SSE/TE | TE-best count/residual/SSE/TE | TE-best − SSE-best SSE/TE |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for row in conflict["materially_differing_bucket_rows"]:
        a = row["sse_best"]
        b = row["te_best"]
        d = row["te_best_minus_sse_best"]
        lines.append(
            f"| {row['direction']} | {clock(row['start'])}–{clock(row['end'])} | {f12(row['demand_share'])} | {a['service_count']} / {f12(a['residual'])} / {f12(a['sse_contribution'])} / {f12(a['te_contribution'])} | {b['service_count']} / {f12(b['residual'])} / {f12(b['sse_contribution'])} / {f12(b['te_contribution'])} | {d['sse_contribution']:+.12f} / {d['te_contribution']:+.12f} |"
        )
    lines.extend(
        [
            "",
            "### Direction aggregation",
            "",
            "| Direction | SSE-best SSE rank | TE-best SSE rank | SSE-best TE rank | TE-best TE rank | Pairwise SSE preference | Pairwise TE preference |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for direction in ("outbound", "inbound"):
        lines.append(
            f"| {direction} | {sse['directions'][direction]['sse_rank']} | {te['directions'][direction]['sse_rank']} | {sse['directions'][direction]['te_rank']} | {te['directions'][direction]['te_rank']} | {aggregation['directions'][direction]['sse_pairwise_preference']} | {aggregation['directions'][direction]['te_pairwise_preference']} |"
        )
    lines.extend(
        [
            f"| pair | {sse['sse_rank']} | {te['sse_rank']} | {sse['te_rank']} | {te['te_rank']} | SSE_BEST | TE_BEST |",
            "",
            f"Aggregation diagnosis: `{aggregation['diagnosis']}`. Pair aggregation introduces a defect: `{str(aggregation['pair_aggregation_introduces_defect']).lower()}`. Directional trip totals are fixed and TE scaling is independently recomputed per direction before summation.",
            "",
            "### Continuous-exposure cross-check",
            "",
            f"Classification: `{continuous['classification']}`. Continuous exposure best is `{continuous['best_fingerprint']}` at `{f12(continuous['best_value'])}`. SSE-best is `{f12(continuous['sse_best_value'])}` (outbound/inbound `{f12(continuous['sse_best_directional']['outbound'])}` / `{f12(continuous['sse_best_directional']['inbound'])}`, rank `{continuous['sse_best_rank']}`); TE-best is `{f12(continuous['te_best_value'])}` (outbound/inbound `{f12(continuous['te_best_directional']['outbound'])}` / `{f12(continuous['te_best_directional']['inbound'])}`, rank `{continuous['te_best_rank']}`). The anchors differ by `{f12(continuous['absolute_delta_between_anchors'])}` and are numerically equivalent: `{str(continuous['nearly_equivalent_at_numerical_epsilon']).lower()}`. This diagnostic is not used to choose an anchor.",
            "",
            "### Bucket-edge audit",
            "",
            f"Changed departures `{evidence['bucket_edge_audit']['pair']['changed_departures']}`; total absolute shift `{f12(evidence['bucket_edge_audit']['pair']['total_absolute_departure_shift_minutes'])}` minutes; boundary-crossing assignments `{evidence['bucket_edge_audit']['pair']['departures_crossing_bucket_boundary']}`; exposure-only bucket changes `{evidence['bucket_edge_audit']['pair']['service_exposure_changes_without_point_count_changes']}`.",
            "",
            f"Classification: `{root['bucket_aliasing_classification']}`. Bucket edges affect the candidate residual vectors, but they do not create separate SSE and TE data paths; the verified ranking reversal is caused by applying different norms to the same vectors.",
            "",
            "## History",
            "",
            "PR62-M observed a common top candidate on the 41-access-safe Route 6 and 7-access-safe Route 10 universes while treating SSE as authoritative and TE as review-only calibration. M1 explicitly corrected the stronger reading: lower ranks already disagreed (61 Route 6 pairs and 2 Route 10 pairs). N/O froze a fail-closed common anchor because top-rank concordance held empirically, not because it was proved invariant. R/S/T preserved that requirement while adding phase-robust materiality diagnostics; they tested the same production universes (plus one external Q review candidate), not a materially expanded search universe. U6 is the first saved production-search counterexample at the exact top rank.",
            "",
            "## U6 transition and cap stability",
            "",
            "| Batch | Pareto | Access-safe | SSE-best | TE-best | Common | V3 |",
            "| --- | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for row in evidence["u6_source_batch_history"]["history"]:
        lines.append(
            f"| `{row['completed_source_batch']}` | {row['pareto_count']} | {row['access_safe_count']} | `{row['sse_best_fingerprint']}` | `{row['te_best_fingerprint']}` | {str(row['common_anchor']).lower()} | `{row['v3_classification']}` |"
        )
    first = evidence["u6_source_batch_history"]["first_common_anchor_to_conflict_transition"]
    lines.extend(
        [
            "",
            f"First transition: batch `{first['completed_source_batch']}`; responsible newly admitted top candidate(s): `{first['new_anchor_candidates_responsible']}` with lineage `{json.dumps(first['responsible_lineage'], sort_keys=True, separators=(',', ':'))}`.",
            "",
            "The first break is triggered by one local-rhythm source family. The conflict then persists after every later batch, the TE-best is replaced by the `c8eeb7…` family, and each cap has a different TE-best identity. The initial trigger is local, but persistence across sources and caps shows that disagreement is a broader property of the enriched universe.",
            "",
            "| Cap | Pareto | Access-safe | SSE-best/value | TE-best/value | SSE/TE continuous ranks |",
            "| ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for cap in ("16", "32", "64"):
        row = caps["caps"][cap]
        lines.append(
            f"| {cap} | {row['pareto_count']} | {row['access_safe_count']} | `{row['sse_best_fingerprint']}` / {f12(row['sse_best_value'])} | `{row['te_best_fingerprint']}` / {f12(row['te_best_value'])} | {row['sse_best_continuous_rank']} / {row['te_best_continuous_rank']} |"
        )
    lines.extend(
        [
            "",
            f"Anchor conflict: `{caps['anchor_conflict_classification']}`. Selection-cap binding remains separately reported as `{caps['selection_cap_binding_classification_reported_by_u6']}` and is not evidence that a null selector is adequate.",
            "",
            "## Rank concordance",
            "",
            f"Across 83 access-safe candidates there are `{rank_data['sse_te_ordering_disagreements']}` SSE/TE ordering disagreements among `{rank_data['possible_pair_count']}` possible pairs; Kendall tau-b is `{f12(rank_data['kendall_tau_b'])}`. Top-5 overlap is `{rank_data['top_5']['overlap_count']}/5`; top-10 overlap is `{rank_data['top_10']['overlap_count']}/10`. Exact common candidates by ranks 1–10 are `{json.dumps(rank_data['same_candidate_at_exact_rank'], sort_keys=True, separators=(',', ':'))}`.",
            "",
            "## Materiality",
            "",
            f"From SSE-best to TE-best: ΔSSE `{material['delta_sse']:+.12f}`, ΔTE `{material['delta_te']:+.12f}`, Δcontinuous `{material['delta_continuous_exposure']:+.12f}`, Δaverage wait `{material['delta_average_expected_passenger_wait_minutes']:+.12f}` minutes, Δmax access OB/IB `{material['delta_maximum_access_minutes']['outbound']:+.12f}` / `{material['delta_maximum_access_minutes']['inbound']:+.12f}` minutes, Δrhythm `{material['delta_rhythm_tuple']}`, Δfleet `{material['delta_fleet']:+d}`, changed bucket allocations `{material['changed_bucket_allocations']}`, changed departures `{material['changed_departures']}`.",
            "",
            f"Their absolute TE difference is within 1.0 TE: `{str(material['within_one_te_of_each_other']).lower()}`. The numeric continuous delta can be compared with the old Route 10 bound, but that bound is **not semantically valid for anchor adjudication** because V3 derived it only after a common anchor existed.",
            "",
            "## Policy options — evidence only",
            "",
            "| Option | Historical intent | Passenger meaning | Edge sensitivity | Growth behavior | New weight/threshold | Fail closed | Route 10 | Route 6 control | Migration |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for key, option in evidence["policy_options"].items():
        lines.append(
            f"| {key} | {option['historical_policy_intent']} | {option['passenger_interpretation']} | {option['bucket_edge_sensitivity']} | {option['candidate_growth_stability']} | {str(option['new_weight_or_threshold']).lower()} | {option['fail_closed_semantics']} | {option['route_10_effect']} | {option['expected_route_6_control']} | {option['migration_complexity']} |"
        )
    lines.extend(
        [
            "",
            "Route 6 impact statements above are reference-only expectations from committed historical evidence. Route 6 was not executed in this review.",
            "",
            "## Primary classification",
            "",
            f"**{evidence['primary_classification']}**",
            "",
            "The common-anchor contract was supported by the old finite universes, but U6 supplies a top-rank counterexample whose existence is stable across caps even though the TE-best identity is universe-sensitive. The review finds no metric implementation, data, gate-survival, or pair-aggregation defect.",
            "",
            "## Next decision",
            "",
            evidence["next_decision"]["recommendation"],
            "",
            f"Route 6 global execution count = `{evidence['route_6_global_execution_count']}`.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("docs/engine/evidence") / EVIDENCE_NAME,
    )
    parser.add_argument(
        "--saved-base",
        type=Path,
        default=Path(
            "E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u/"
            ".pr62-u-local/certification/route_10_complete_base.pickle"
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    evidence, context, base, authority = load_authorities(
        repo_root=repo_root,
        evidence_path=args.evidence.resolve(),
        saved_base_path=args.saved_base.resolve(),
    )
    review = build_evidence(
        repo_root=repo_root,
        evidence=evidence,
        context=context,
        base=base,
        authority=authority,
    )
    json_bytes = canonical_bytes(review)
    require(len(json_bytes) < 5 * 1024 * 1024, "REVIEW_JSON_EXCEEDS_HARD_CEILING")
    write_once(args.output_dir / OUTPUT_JSON, json_bytes)
    write_once(args.output_dir / OUTPUT_MD, render_markdown(review).encode("utf-8"))
    print(
        json.dumps(
            {
                "classification": review["primary_classification"],
                "json_size": len(json_bytes),
                "route_6_global_execution_count": ROUTE6_GLOBAL_EXECUTION_COUNT,
                "sse_best": review["exact_conflict"]["sse_best"]["fingerprint"],
                "te_best": review["exact_conflict"]["te_best"]["fingerprint"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Evidence-only PR62-U7 demand-fit authority rehearsal.

This review module consumes committed JSON evidence only. It must never import
production engine, coordinator, selector, compiler, or timetable modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from math import isfinite
from pathlib import Path
from typing import Any

NUMERICAL_EPSILON = 1e-12
REVIEW_BASE_SHA = "a1b96c779c50318af8c4b2db6b1aacd2ab49d3cb"
CANONICAL_U6_SEMANTIC_SHA256 = "46cd605e4ffb0a9aa00bb9376002b2001ada60760d460e1cbf38ba69aa549d99"
OUTPUT_JSON = "PR62_U7_DEMAND_FIT_AUTHORITY_REHEARSAL.json"
OUTPUT_MARKDOWN = "PR62_U7_DEMAND_FIT_AUTHORITY_REHEARSAL.md"

SOURCE_ARTIFACTS: dict[str, tuple[int, str, str]] = {
    "docs/engine/evidence/PR62_E_ROUTE10_CLOSED_LOOP_PILOT.json": (
        1_136_804,
        "0589b36a1c92b0e1c0c390eb38adc97702137bf413a7bd1656623605333f6aa2",
        "c1a741d4b62b9f23fd46a5ee4b80cfc956e2bcfe",
    ),
    "docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json": (
        525_934,
        "f9c5438c3d4b0b871b8fc1ec24a9dcd3a392efd76e85e7ab9ec385532c98c0c9",
        "3d6ebb9c4126aca833f5d7ddce12e2fa4755442a",
    ),
    "docs/engine/evidence/PR62_M1_RANK_CONCORDANCE_CLARIFICATION.json": (
        99_878,
        "fcb77df73cc5bdf39738a7e81300456870938cab489144fbe2f59a414fbffcda",
        "1902ac4e4b4d523d81a5a3d6d527c91fc8077b54",
    ),
    "docs/engine/evidence/PR62_N_ONE_TRIP_POLICY_REHEARSAL.json": (
        20_224,
        "6e15939240963171e80e20b95a4d728df8ec6ccecb3f0b6b192135fb56ad371b",
        "c956284102eb307e10068c1128151943da5246d7",
    ),
    "docs/engine/evidence/PR62_O_PRODUCTION_POLICY_FREEZE.json": (
        133_912,
        "91a93fa7e7abd4ede3e6848b241b0a3aa22f8f4942aa202c93dad6631df46346",
        "91702bae7d9b2a93afa6f470b3838f8b51e5a6df",
    ),
    "docs/engine/evidence/PR62_R_DEMAND_FIT_METRIC_VALIDITY.json": (
        273_425,
        "7f6b238981024ede96905072a6445f55df5fca09d41539088fdd1579b15840fd",
        "702e0fe494f340d27b862cd4ffbca64366f2df03",
    ),
    "docs/engine/evidence/PR62_S_PHASE_ROBUST_MATERIALITY_POLICY_EXPERIMENT.json": (
        268_759,
        "e54ab2a5d366c3d76613a93e73fae0a722cd642f64dbc1f077618d51c6472c2a",
        "b45a7317de9f8142da8d5976280b1503964ee054",
    ),
    "docs/engine/evidence/PR62_T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE.json": (
        115_723,
        "23d472e751d7811707f9b10dd3c1b8133a94ab0c7447356f06f14c7853ca2198",
        "d497748e8141195eb97c7a3dc6ad026ad689ce3b",
    ),
    "docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json": (
        54_651_797,
        "0dcb75205c329a3fc512f475cb619eee61be9b3d25342ae6e12fa923a9bf6877",
        "e9bcfec96470cbb6250a6bc82c3c3de65e967d49",
    ),
    "docs/engine/evidence/PR62_U6_V3_ANCHOR_CONFLICT_REVIEW.json": (
        106_376,
        "2f1e40faca338cb799801667c02d949b34c4ee5f71658e005e6267e3afefb426",
        REVIEW_BASE_SHA,
    ),
}

EPSILON_AUTHORITY = {
    "value": NUMERICAL_EPSILON,
    "source_path": "src/bus_schedule_engine/contracts_v1/operational_selection_policy.py",
    "source_sha256": "ba0f48b5d0f3d9ed3dacb96aaff2b13d69c68961d835ac2cd33c2f356b40c0d3",
    "source_line": 10,
}

SCHEDULE_TEMPLATE_SHA256 = "2e552e61f5929debd026edf1eb2076648aec8935f103caba98984a5174671cc7"

# U6 records committed LF hashes for these text files, while the authorized
# Windows worktree materializes CRLF bytes. Freeze both representations so the
# before/after guard remains byte-exact without misclassifying checkout-level
# line-ending conversion as a U7 mutation.
CONTROLLED_CRLF_WORKTREE_SHA256 = {
    "scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py": (
        "620ac9c2593c88ed7fafefe1e6e81dec49c6c0de60cc29ba32eca5413e2ddfb8"
    ),
    "src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py": (
        "86ef5994aab5210e438dd06a080df8487b0e3be8da1ea1a74fb2d5c558839c66"
    ),
    "src/bus_schedule_engine/kbest_shadow_refinement.py": (
        "db1b9da2c47194ead8df113778087e74e46ba26a6552e18c7b3d2414e1737737"
    ),
}


class ReviewError(RuntimeError):
    """Fail-closed U7 evidence or authority classification."""

    def __init__(self, classification: str) -> None:
        self.classification = classification
        super().__init__(classification)


def require(condition: bool, classification: str) -> None:
    if not condition:
        raise ReviewError(classification)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def semantic_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "EVIDENCE_ROOT_NOT_OBJECT")
    return value


def load_authorities(repo_root: Path) -> dict[str, Any]:
    source_records: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    key_by_name = {
        "PR62_E_ROUTE10_CLOSED_LOOP_PILOT.json": "e",
        "PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json": "m",
        "PR62_M1_RANK_CONCORDANCE_CLARIFICATION.json": "m1",
        "PR62_N_ONE_TRIP_POLICY_REHEARSAL.json": "n",
        "PR62_O_PRODUCTION_POLICY_FREEZE.json": "o",
        "PR62_R_DEMAND_FIT_METRIC_VALIDITY.json": "r",
        "PR62_S_PHASE_ROBUST_MATERIALITY_POLICY_EXPERIMENT.json": "s",
        "PR62_T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE.json": "t",
        "PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json": "u6",
        "PR62_U6_V3_ANCHOR_CONFLICT_REVIEW.json": "u6_review",
    }
    for relative, (expected_size, expected_hash, commit_sha) in SOURCE_ARTIFACTS.items():
        path = repo_root / relative
        require(path.is_file(), "COMMITTED_EVIDENCE_MISSING")
        actual_size = path.stat().st_size
        actual_hash = file_sha256(path)
        require(actual_size == expected_size, "COMMITTED_EVIDENCE_SIZE_MISMATCH")
        require(actual_hash == expected_hash, "COMMITTED_EVIDENCE_HASH_MISMATCH")
        source_records[relative] = {
            "commit_sha": commit_sha,
            "sha256": actual_hash,
            "size_bytes": actual_size,
        }
        payloads[key_by_name[path.name]] = _read_json(path)

    epsilon_path = repo_root / EPSILON_AUTHORITY["source_path"]
    require(
        file_sha256(epsilon_path) == EPSILON_AUTHORITY["source_sha256"],
        "EPSILON_AUTHORITY_HASH_MISMATCH",
    )
    epsilon_line = epsilon_path.read_text(encoding="utf-8").splitlines()[
        int(EPSILON_AUTHORITY["source_line"]) - 1
    ]
    require(epsilon_line.strip() == "NUMERICAL_EPSILON = 1e-12", "EPSILON_AUTHORITY_VALUE_MISMATCH")

    u6 = payloads["u6"]
    canonical = u6["ROUTE 10"]["canonical"]
    require(
        canonical["semantic_sha256"] == CANONICAL_U6_SEMANTIC_SHA256,
        "CANONICAL_U6_SEMANTIC_LABEL_MISMATCH",
    )
    require(
        semantic_sha256(canonical["semantic"]) == CANONICAL_U6_SEMANTIC_SHA256,
        "CANONICAL_U6_SEMANTIC_HASH_MISMATCH",
    )
    require(
        canonical["semantic"]["global_coordinator_executions"] == 0,
        "U6_ROUTE10_GLOBAL_EXECUTION_NONZERO",
    )
    require(
        u6["ROUTE 6"]
        == {"global_coordinator_executions": 0, "state": "NOT_RUN_ROUTE10_GATE_FAILED"},
        "U6_ROUTE6_EXECUTION_STATE_MISMATCH",
    )
    for cap, run in u6["ROUTE 10"]["sensitivity"]["independent_runs"].items():
        require(
            semantic_sha256(run["semantic"]) == run["semantic_sha256"],
            f"CAP{cap}_SEMANTIC_HASH_MISMATCH",
        )
        require(
            run["semantic"]["global_coordinator_executions"] == 0,
            f"CAP{cap}_GLOBAL_EXECUTION_NONZERO",
        )
    review = payloads["u6_review"]
    require(
        review["primary_classification"] == "COMMON_SSE_TE_ANCHOR_ASSUMPTION_INVALIDATED",
        "U6_REVIEW_CLASSIFICATION_MISMATCH",
    )
    require(review["route_6_global_execution_count"] == 0, "U6_REVIEW_ROUTE6_EXECUTION_NONZERO")
    require(review["production_changes"] is False, "U6_REVIEW_PRODUCTION_CHANGE_RECORDED")
    require(
        payloads["s"]["input_provenance"]["coordinator_replays_executed_by_S"] == 0,
        "S_COORDINATOR_REPLAY_NONZERO",
    )
    require(
        payloads["t"]["input_provenance"]["coordinator_replays_executed_by_T"] == 0,
        "T_COORDINATOR_REPLAY_NONZERO",
    )

    return {
        **payloads,
        "source_artifacts": source_records,
        "numerical_epsilon": dict(EPSILON_AUTHORITY),
    }


def _route10_buckets(authorities: Mapping[str, Any]) -> dict[str, tuple[dict[str, float], ...]]:
    result: dict[str, tuple[dict[str, float], ...]] = {}
    audit = authorities["r"]["bucket_edge_contribution_audit"]["directions"]
    for direction in ("outbound", "inbound"):
        buckets = tuple(
            {
                "start": float(row["start_seconds"]),
                "end": float(row["end_seconds"]),
                "demand_share": float(row["demand_share"]),
            }
            for row in audit[direction]["buckets"]
        )
        require(len(buckets) == 34, "ROUTE10_DEMAND_BUCKET_COUNT_MISMATCH")
        require(
            all(
                left["end"] == right["start"]
                for left, right in zip(buckets, buckets[1:], strict=False)
            ),
            "ROUTE10_DEMAND_BUCKETS_NOT_CONTIGUOUS",
        )
        require(
            abs(sum(row["demand_share"] for row in buckets) - 1.0) <= NUMERICAL_EPSILON,
            "ROUTE10_DEMAND_SHARES_INVALID",
        )
        result[direction] = buckets
    return result


def _point_metrics(
    departures: Sequence[int], buckets: Sequence[Mapping[str, float]]
) -> tuple[float, float, tuple[int, ...]]:
    exact = tuple(int(value) for value in departures)
    require(len(exact) >= 2 and exact == tuple(sorted(set(exact))), "EXACT_DEPARTURES_INVALID")
    counts = tuple(
        sum(bucket["start"] <= departure < bucket["end"] for departure in exact)
        for bucket in buckets
    )
    require(sum(counts) == len(exact), "DEMAND_BUCKETS_DO_NOT_COVER_DEPARTURES")
    residuals = tuple(
        count / len(exact) - bucket["demand_share"]
        for count, bucket in zip(counts, buckets, strict=True)
    )
    return (
        sum(value * value for value in residuals),
        len(exact) * 0.5 * sum(abs(value) for value in residuals),
        counts,
    )


def _continuous_exposure_equivalent(
    departures: Sequence[int], buckets: Sequence[Mapping[str, float]]
) -> float:
    exact = tuple(int(value) for value in departures)
    breakpoints = sorted(
        {
            buckets[0]["start"],
            buckets[-1]["end"],
            *exact,
            *(bucket["start"] for bucket in buckets),
            *(bucket["end"] for bucket in buckets),
        }
    )
    exposure_units = len(exact) - 1
    absolute_integral = 0.0
    for left, right in zip(breakpoints, breakpoints[1:], strict=False):
        bucket = next(row for row in buckets if row["start"] <= left < row["end"])
        demand_density = bucket["demand_share"] / (bucket["end"] - bucket["start"])
        service_density = 0.0
        for departure_left, departure_right in zip(exact, exact[1:], strict=False):
            if departure_left <= left < departure_right:
                service_density = 1.0 / (departure_right - departure_left) / exposure_units
                break
        absolute_integral += (right - left) * abs(service_density - demand_density)
    return len(exact) * 0.5 * absolute_integral


def _bucket_exposure_equivalent(
    departures: Sequence[int], buckets: Sequence[Mapping[str, float]]
) -> float:
    exact = tuple(int(value) for value in departures)
    units = [0.0] * len(buckets)
    for left, right in zip(exact, exact[1:], strict=False):
        width = right - left
        for index, bucket in enumerate(buckets):
            overlap = max(0.0, min(right, bucket["end"]) - max(left, bucket["start"]))
            units[index] += overlap / width
    total_units = sum(units)
    require(total_units > 0, "BUCKET_EXPOSURE_EMPTY")
    return (
        len(exact)
        * 0.5
        * sum(
            abs(unit / total_units - bucket["demand_share"])
            for unit, bucket in zip(units, buckets, strict=True)
        )
    )


def _wait_metrics(
    departures: Sequence[int], buckets: Sequence[Mapping[str, float]]
) -> tuple[float, float]:
    exact = tuple(int(value) for value in departures)
    total_mass = 0.0
    total_weighted_wait = 0.0
    bucket_waits: list[float] = []
    for bucket in buckets:
        active_start = max(exact[0], bucket["start"])
        active_end = min(exact[-1], bucket["end"])
        if active_end <= active_start or bucket["demand_share"] == 0:
            continue
        intensity = bucket["demand_share"] / (bucket["end"] - bucket["start"])
        mass = intensity * (active_end - active_start)
        weighted_wait = 0.0
        for left, right in zip(exact, exact[1:], strict=False):
            overlap_start = max(left, active_start)
            overlap_end = min(right, active_end)
            if overlap_end <= overlap_start:
                continue
            weighted_wait += intensity * (
                right * (overlap_end - overlap_start) - (overlap_end**2 - overlap_start**2) / 2
            )
        bucket_waits.append(weighted_wait / mass / 60)
        total_mass += mass
        total_weighted_wait += weighted_wait
    require(total_mass > 0 and bucket_waits, "WAIT_EVIDENCE_EMPTY")
    return total_weighted_wait / total_mass / 60, max(bucket_waits)


def _eligible_candidates(
    candidates: Sequence[Mapping[str, Any]],
    metric_names: Sequence[str],
) -> tuple[Mapping[str, Any], ...]:
    if not candidates:
        raise ReviewError("EMPTY_AUTHORITY_UNIVERSE")
    seen: set[str] = set()
    eligible: list[Mapping[str, Any]] = []
    for candidate in candidates:
        if (
            type(candidate.get("hard_feasible")) is not bool
            or type(candidate.get("access_safe")) is not bool
        ):
            raise ReviewError("MALFORMED_HARD_ACCESS_FLAG")
        fingerprint = candidate.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint or fingerprint in seen:
            raise ReviewError("MALFORMED_CANDIDATE_FINGERPRINT")
        seen.add(fingerprint)
        for metric_name in metric_names:
            value = candidate.get(metric_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ReviewError("NONFINITE_AUTHORITY_METRIC")
        if candidate["hard_feasible"] and candidate["access_safe"]:
            eligible.append(candidate)
    if not eligible:
        raise ReviewError("EMPTY_AUTHORITY_UNIVERSE")
    return tuple(eligible)


def unique_minimum(
    candidates: Sequence[Mapping[str, Any]],
    metric_name: str,
    *,
    epsilon: float = NUMERICAL_EPSILON,
) -> Mapping[str, Any]:
    eligible = _eligible_candidates(candidates, ("sse", "te", "continuous_exposure"))
    ordered = sorted(eligible, key=lambda row: (float(row[metric_name]), row["fingerprint"]))
    minimum = float(ordered[0][metric_name])
    tied = [row for row in ordered if abs(float(row[metric_name]) - minimum) <= epsilon]
    if len(tied) != 1:
        raise ReviewError("AUTHORITY_NOT_UNIQUE")
    return tied[0]


def pareto_frontier(
    candidates: Sequence[Mapping[str, Any]],
    metric_names: tuple[str, str] = ("sse", "te"),
    *,
    epsilon: float = NUMERICAL_EPSILON,
) -> tuple[Mapping[str, Any], ...]:
    eligible = _eligible_candidates(candidates, (*metric_names, "continuous_exposure"))

    def dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        values = [(float(left[name]), float(right[name])) for name in metric_names]
        return all(a <= b + epsilon for a, b in values) and any(a < b - epsilon for a, b in values)

    frontier = [
        candidate
        for candidate in eligible
        if not any(other is not candidate and dominates(other, candidate) for other in eligible)
    ]
    if not frontier:
        raise ReviewError("EMPTY_DEMAND_FIT_FRONTIER")
    return tuple(sorted(frontier, key=lambda row: row["fingerprint"]))


def _stage_fingerprints(selection: Mapping[str, Any], stage: str) -> tuple[str, ...]:
    matches = [row for row in selection["stage_trace"] if row["stage"] == stage]
    require(len(matches) == 1, "SELECTION_STAGE_TRACE_MALFORMED")
    return tuple(matches[0]["retained_fingerprints"])


def _direction_records(
    authorities: Mapping[str, Any], semantic: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    records = {
        fingerprint: {
            "departures": tuple(record["exact_departures"]),
            "direction": record["direction"],
            "metrics": record["metrics"],
            "origin": "PR62_E_BASE_FRONTIER",
        }
        for fingerprint, record in authorities["e"]["final_directional_compilations"].items()
    }
    for source in semantic["sources"]:
        for retention in source["retentions"]:
            direction = retention["direction"]
            for record in retention["candidates"]:
                normalized = {
                    "departures": tuple(record["departures"]),
                    "direction": direction,
                    "metrics": record["metrics"],
                    "origin": "PR62_U6_GENERATED",
                }
                previous = records.get(record["fingerprint"])
                if previous is not None:
                    require(
                        previous["departures"] == normalized["departures"]
                        and previous["direction"] == normalized["direction"],
                        "DIRECTIONAL_EVIDENCE_CONFLICT",
                    )
                records[record["fingerprint"]] = normalized
    return records


def _lineage(semantic: Mapping[str, Any], pair_fingerprint: str) -> dict[str, Any]:
    base_pairs = {row["fingerprint"] for row in semantic["base_pareto"]}
    if pair_fingerprint in base_pairs:
        return {
            "origin": "PR62_E_BASE_FRONTIER",
            "source_pair_fingerprint": None,
            "parent_pair_fingerprint": None,
            "parent_rhythm": None,
            "child_rhythm": None,
        }
    source_by_pair: dict[str, str] = {}
    for source in semantic["sources"]:
        for decision in source["pair_decisions"]:
            fingerprint = decision.get("pair_fingerprint")
            if fingerprint:
                source_by_pair.setdefault(fingerprint, source["source"])
    parent = next(
        (row for row in semantic["parents"] if row["child_fingerprint"] == pair_fingerprint),
        None,
    )
    return {
        "origin": "PR62_U6_GENERATED",
        "source_pair_fingerprint": source_by_pair.get(pair_fingerprint),
        "parent_pair_fingerprint": None if parent is None else parent["parent_fingerprint"],
        "parent_rhythm": None if parent is None else parent["parent_rhythm"],
        "child_rhythm": None if parent is None else parent["child_rhythm"],
    }


def _candidate_from_pair(
    *,
    pair: Mapping[str, Any],
    records: Mapping[str, Mapping[str, Any]],
    buckets: Mapping[str, Sequence[Mapping[str, float]]],
    semantic: Mapping[str, Any],
) -> dict[str, Any]:
    pair_sse = 0.0
    pair_te = 0.0
    pair_continuous = 0.0
    pair_bucket_exposure = 0.0
    directional_maximum_access: dict[str, float] = {}
    directional_departures: dict[str, tuple[int, ...]] = {}
    directional_metrics: dict[str, dict[str, float]] = {}
    for direction in ("outbound", "inbound"):
        fingerprint = pair[direction]
        require(fingerprint in records, "HISTORICAL_DIRECTIONAL_EVIDENCE_INSUFFICIENT")
        record = records[fingerprint]
        require(record["direction"] == direction, "DIRECTIONAL_EVIDENCE_LABEL_MISMATCH")
        departures = tuple(int(value) for value in record["departures"])
        sse, te, counts = _point_metrics(departures, buckets[direction])
        serialized_sse = float(record["metrics"]["observed_demand_mismatch"])
        require(
            abs(sse - serialized_sse) <= NUMERICAL_EPSILON,
            "DIRECTIONAL_SSE_RECONSTRUCTION_MISMATCH",
        )
        if "bucket_service_counts" in record["metrics"]:
            require(
                tuple(record["metrics"]["bucket_service_counts"]) == counts,
                "DIRECTIONAL_BUCKET_COUNT_MISMATCH",
            )
        continuous = _continuous_exposure_equivalent(departures, buckets[direction])
        bucket_exposure = _bucket_exposure_equivalent(departures, buckets[direction])
        average_wait, maximum_access = _wait_metrics(departures, buckets[direction])
        directional_departures[direction] = departures
        directional_maximum_access[direction] = maximum_access
        directional_metrics[direction] = {
            "sse": sse,
            "te": te,
            "continuous_exposure": continuous,
            "bucket_exposure": bucket_exposure,
            "average_scheduled_passenger_wait_minutes": average_wait,
            "maximum_bucket_average_wait_minutes": maximum_access,
        }
        pair_sse += sse
        pair_te += te
        pair_continuous += continuous
        pair_bucket_exposure += bucket_exposure

    metrics = pair["metrics"]
    require(
        abs(pair_sse - float(metrics["observed_demand_mismatch"])) <= NUMERICAL_EPSILON,
        "PAIR_SSE_RECONSTRUCTION_MISMATCH",
    )
    return {
        "fingerprint": pair["fingerprint"],
        "hard_feasible": True,
        "access_safe": True,
        "sse": pair_sse,
        "te": pair_te,
        "continuous_exposure": pair_continuous,
        "bucket_exposure": pair_bucket_exposure,
        "average_scheduled_passenger_wait_minutes": float(
            metrics["demand_weighted_expected_passenger_wait_minutes"]
        ),
        "directional_maximum_access_minutes": directional_maximum_access,
        "rhythm_tuple": list(pair["rhythm"]),
        "fleet": int(metrics["fleet_required"]),
        "terminal_excess": {
            "total": int(metrics["total_excess_terminal_wait"]),
            "maximum": int(metrics["max_excess_terminal_wait"]),
        },
        "lineage": _lineage(semantic, pair["fingerprint"]),
        "directional_compilation_fingerprints": {
            "outbound": pair["outbound"],
            "inbound": pair["inbound"],
        },
        "directional_departures": directional_departures,
        "directional_metrics": directional_metrics,
    }


def _reconstruct_universe(
    *,
    authorities: Mapping[str, Any],
    semantic: Mapping[str, Any],
    pairs: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    records = _direction_records(authorities, semantic)
    buckets = _route10_buckets(authorities)
    pair_by_fingerprint = {row["fingerprint"]: row for row in pairs}
    access = _stage_fingerprints(selection, "SCENARIO_B_MAX_ACCESS_NON_REGRESSION")
    require(set(access) <= pair_by_fingerprint.keys(), "ACCESS_SAFE_PAIR_EVIDENCE_INSUFFICIENT")
    rows = tuple(
        _candidate_from_pair(
            pair=pair_by_fingerprint[fingerprint],
            records=records,
            buckets=buckets,
            semantic=semantic,
        )
        for fingerprint in sorted(access)
    )
    require(len(rows) == selection["passenger_access_safe_count"], "ACCESS_SAFE_COUNT_MISMATCH")
    return rows


def reconstruct_route10_cap_universes(
    authorities: Mapping[str, Any],
) -> dict[str, tuple[dict[str, Any], ...]]:
    result: dict[str, tuple[dict[str, Any], ...]] = {}
    runs = authorities["u6"]["ROUTE 10"]["sensitivity"]["independent_runs"]
    expected_counts = {"16": 55, "32": 83, "64": 154}
    for cap in ("16", "32", "64"):
        semantic = runs[cap]["semantic"]
        result[cap] = _reconstruct_universe(
            authorities=authorities,
            semantic=semantic,
            pairs=semantic["final_pareto"],
            selection=semantic["final_selection"],
        )
        require(len(result[cap]) == expected_counts[cap], f"CAP{cap}_ACCESS_SAFE_COUNT_MISMATCH")
    return result


def reconstruct_route10_source_batch_universes(
    authorities: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    semantic = authorities["u6"]["ROUTE 10"]["canonical"]["semantic"]
    pair_universes = [
        semantic["base_pareto"],
        *[source["pareto"] for source in semantic["sources"]],
    ]
    selections = semantic["selection_history"]
    labels = ["BASE_FRONTIER", *semantic["processed_source_order"]]
    require(
        len(pair_universes) == len(selections) == len(labels),
        "SOURCE_BATCH_HISTORY_ALIGNMENT_MISMATCH",
    )
    return tuple(
        {
            "batch_index": index,
            "completed_source_batch": label,
            "pareto_count": len(pairs),
            "candidates": _reconstruct_universe(
                authorities=authorities,
                semantic=semantic,
                pairs=pairs,
                selection=selection,
            ),
        }
        for index, (pairs, selection, label) in enumerate(
            zip(pair_universes, selections, labels, strict=True)
        )
    )


def reconstruct_historical_route6_universe(
    authorities: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    candidates = authorities["s"]["routes"]["6"]["candidates"]
    require(len(candidates) == 41, "HISTORICAL_ROUTE6_EVIDENCE_INSUFFICIENT")
    return tuple(
        sorted(
            (
                {
                    "fingerprint": row["fingerprint"],
                    "hard_feasible": True,
                    "access_safe": True,
                    "sse": float(row["production_SSE"]),
                    "te": float(row["production_TE"]),
                    "continuous_exposure": float(row["continuous_exposure_equivalent"]),
                    "bucket_exposure": float(row["bucket_exposure_equivalent"]),
                    "average_scheduled_passenger_wait_minutes": float(
                        row["operations"]["average_passenger_wait_minutes"]
                    ),
                    "directional_maximum_access_minutes": {
                        direction: float(
                            row["operations"]["directions"][direction][
                                "maximum_bucket_wait_minutes"
                            ]
                        )
                        for direction in ("outbound", "inbound")
                    },
                    "rhythm_tuple": list(row["rhythm_tuple"]),
                    "fleet": int(row["fleet_tuple"][0]),
                    "terminal_excess": {
                        "total": int(row["fleet_tuple"][1]),
                        "maximum": int(row["fleet_tuple"][2]),
                    },
                    "lineage": {
                        "origin": "PR62_R_S_COMMITTED_ROUTE6_SNAPSHOT",
                        "source_pair_fingerprint": None,
                        "parent_pair_fingerprint": None,
                        "parent_rhythm": None,
                        "child_rhythm": None,
                    },
                }
                for row in candidates
            ),
            key=lambda row: row["fingerprint"],
        )
    )


def _ranked_candidates(candidates: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    metric_names = ("sse", "te", "continuous_exposure", "bucket_exposure")
    result: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        copy = dict(candidate)
        for metric_name in metric_names:
            value = float(candidate[metric_name])
            copy[f"{metric_name}_rank"] = 1 + sum(
                float(other[metric_name]) < value - NUMERICAL_EPSILON for other in candidates
            )
        result[candidate["fingerprint"]] = copy
    return result


def _compact_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": candidate["fingerprint"],
        "sse_rank": candidate["sse_rank"],
        "sse": candidate["sse"],
        "te_rank": candidate["te_rank"],
        "te": candidate["te"],
        "continuous_rank": candidate["continuous_exposure_rank"],
        "continuous_exposure": candidate["continuous_exposure"],
        "bucket_exposure_rank": candidate["bucket_exposure_rank"],
        "bucket_exposure": candidate["bucket_exposure"],
        "average_scheduled_passenger_wait_minutes": candidate[
            "average_scheduled_passenger_wait_minutes"
        ],
        "directional_maximum_access_minutes": candidate["directional_maximum_access_minutes"],
        "rhythm_tuple": candidate["rhythm_tuple"],
        "fleet": candidate["fleet"],
        "terminal_excess": candidate["terminal_excess"],
        "directional_compilation_fingerprints": candidate.get(
            "directional_compilation_fingerprints"
        ),
        "lineage": candidate["lineage"],
    }


def _boundedness(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    frontier = pareto_frontier(candidates)
    return {
        "access_safe_count": len(candidates),
        "sse_te_frontier_size": len(frontier),
        "frontier_proportion": len(frontier) / len(candidates),
        "frontier_fingerprints": [row["fingerprint"] for row in frontier],
        "rhythm_tuple_diversity": sorted({tuple(row["rhythm_tuple"]) for row in frontier}),
        "continuous_exposure_range": {
            "minimum": min(float(row["continuous_exposure"]) for row in frontier),
            "maximum": max(float(row["continuous_exposure"]) for row in frontier),
        },
        "waiting_range_minutes": {
            "minimum": min(
                float(row["average_scheduled_passenger_wait_minutes"]) for row in frontier
            ),
            "maximum": max(
                float(row["average_scheduled_passenger_wait_minutes"]) for row in frontier
            ),
        },
        "fleet_range": {
            "minimum": min(int(row["fleet"]) for row in frontier),
            "maximum": max(int(row["fleet"]) for row in frontier),
        },
    }


def _policy_results(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ranked = _ranked_candidates(candidates)
    a = ranked[unique_minimum(candidates, "sse")["fingerprint"]]
    b = ranked[unique_minimum(candidates, "te")["fingerprint"]]
    c = ranked[unique_minimum(candidates, "continuous_exposure")["fingerprint"]]
    d = [ranked[row["fingerprint"]] for row in pareto_frontier(candidates)]
    return {
        "A": {
            "policy": "SSE_AUTHORITATIVE_ANCHOR",
            "authority_metric_meaning": "unitless squared service-share residual",
            "anchor": _compact_candidate(a),
        },
        "B": {
            "policy": "TE_AUTHORITATIVE_ANCHOR",
            "authority_metric_meaning": "equivalent displaced departure mass in trips",
            "anchor": _compact_candidate(b),
        },
        "C": {
            "policy": "CONTINUOUS_EXPOSURE_AUTHORITATIVE_ANCHOR",
            "authority_metric_meaning": "equivalent interdeparture-exposure mismatch",
            "anchor": _compact_candidate(c),
        },
        "D": {
            "policy": "MULTI_METRIC_DEMAND_FIT_FRONTIER",
            "authority_metric_meaning": "set preserving both SSE and TE tradeoffs",
            "dimensions": ["sse", "te"],
            "frontier": [_compact_candidate(row) for row in d],
            "boundedness": _boundedness(candidates),
        },
    }


def _scalar_stability(
    policy: str,
    metric: str,
    batches: Sequence[Mapping[str, Any]],
    caps: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    history = []
    prior: str | None = None
    changes = 0
    first_change = None
    for batch in batches:
        anchor = unique_minimum(batch["candidates"], metric)
        fingerprint = anchor["fingerprint"]
        changed = prior is not None and fingerprint != prior
        if changed:
            changes += 1
            if first_change is None:
                first_change = {
                    "batch_index": batch["batch_index"],
                    "completed_source_batch": batch["completed_source_batch"],
                    "from": prior,
                    "to": fingerprint,
                }
        history.append(
            {
                "batch_index": batch["batch_index"],
                "completed_source_batch": batch["completed_source_batch"],
                "anchor_fingerprint": fingerprint,
                "authority_value": anchor[metric],
                "changed_from_previous": changed,
            }
        )
        prior = fingerprint
    cap_identities = {
        cap: unique_minimum(candidates, metric)["fingerprint"] for cap, candidates in caps.items()
    }
    return {
        "policy": policy,
        "batch_history": history,
        "anchor_change_count": changes,
        "first_change_batch": first_change,
        "final_anchor": history[-1]["anchor_fingerprint"],
        "cap_final_anchor_identities": cap_identities,
        "cap16_cap32_cap64_agree": len(set(cap_identities.values())) == 1,
        "stability_classification": (
            "AUTHORITY_TOP_STABLE"
            if changes == 0 and len(set(cap_identities.values())) == 1
            else "AUTHORITY_TOP_UNIVERSE_SENSITIVE"
        ),
    }


def _set_stability(
    batches: Sequence[Mapping[str, Any]],
    caps: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    history = []
    previous: set[str] = set()
    for batch in batches:
        current = {row["fingerprint"] for row in pareto_frontier(batch["candidates"])}
        history.append(
            {
                "batch_index": batch["batch_index"],
                "completed_source_batch": batch["completed_source_batch"],
                **_boundedness(batch["candidates"]),
                "entries": sorted(current - previous),
                "exits": sorted(previous - current),
            }
        )
        previous = current
    cap_sets = {
        cap: {row["fingerprint"] for row in pareto_frontier(candidates)}
        for cap, candidates in caps.items()
    }
    overlaps = {}
    for left, right in (("16", "32"), ("16", "64"), ("32", "64")):
        intersection = cap_sets[left] & cap_sets[right]
        union = cap_sets[left] | cap_sets[right]
        overlaps[f"cap{left}_cap{right}"] = {
            "intersection_count": len(intersection),
            "union_count": len(union),
            "intersection_fingerprints": sorted(intersection),
        }
    return {
        "batch_history": history,
        "cap_frontiers": {
            cap: {
                **_boundedness(candidates),
                "frontier_fingerprints": sorted(cap_sets[cap]),
            }
            for cap, candidates in caps.items()
        },
        "cap_set_overlaps": overlaps,
        "stability_classification": (
            "AUTHORITY_SET_STABLE"
            if len({tuple(sorted(value)) for value in cap_sets.values()}) == 1
            and all(not row["entries"] and not row["exits"] for row in history[1:])
            else "AUTHORITY_SET_UNIVERSE_SENSITIVE"
        ),
        "boundedness_classification": "MULTI_METRIC_FRONTIER_COHERENT_BUT_DOWNSTREAM_POLICY_REQUIRED",
    }


def _bucket_index(value: int, buckets: Sequence[Mapping[str, float]]) -> int:
    return next(
        index for index, bucket in enumerate(buckets) if bucket["start"] <= value < bucket["end"]
    )


def _edge_comparison(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    buckets: Mapping[str, Sequence[Mapping[str, float]]],
) -> dict[str, Any]:
    directions = {}
    for direction in ("outbound", "inbound"):
        left_departures = left["directional_departures"][direction]
        right_departures = right["directional_departures"][direction]
        require(len(left_departures) == len(right_departures), "EDGE_AUDIT_TRIP_COUNT_MISMATCH")
        crossings = []
        changed = 0
        for index, (a, b) in enumerate(zip(left_departures, right_departures, strict=True)):
            if a == b:
                continue
            changed += 1
            a_bucket = _bucket_index(a, buckets[direction])
            b_bucket = _bucket_index(b, buckets[direction])
            if a_bucket != b_bucket:
                crossings.append(
                    {
                        "departure_index": index,
                        "left_seconds": a,
                        "right_seconds": b,
                        "left_bucket_index": a_bucket,
                        "right_bucket_index": b_bucket,
                        "bucket_edges_crossed": abs(b_bucket - a_bucket),
                    }
                )
        directions[direction] = {
            "changed_departure_positions": changed,
            "bucket_boundary_crossing_count": len(crossings),
            "total_bucket_edges_crossed": sum(row["bucket_edges_crossed"] for row in crossings),
            "crossings": crossings,
        }
    return {
        "left_fingerprint": left["fingerprint"],
        "right_fingerprint": right["fingerprint"],
        "directions": directions,
    }


def _snapshot_protected(repo_root: Path, expected: Mapping[str, str]) -> dict[str, str]:
    result = {}
    for relative, expected_hash in expected.items():
        path = repo_root / relative
        require(path.is_file(), "PROTECTED_ARTIFACT_MISSING")
        actual = file_sha256(path)
        require(actual == expected_hash, "PROTECTED_ARTIFACT_HASH_MISMATCH")
        result[relative] = actual
    return result


def _criterion_matrix() -> dict[str, dict[str, str]]:
    common = {
        "C2": "PASS — no weights, percentages, normalized composite, preferred identity, or historical-Q rule.",
        "C5": "PASS — contextual wait/access/operations are reported without reranking; metric is not passenger welfare.",
        "C6": "PASS — committed Route 6 snapshots preserve the historical authority; U7 executions remain zero.",
        "C8": "PASS — empty, malformed, nonfinite, epsilon ties, equality, dominance, and nondominance fail or resolve deterministically.",
    }
    return {
        "A": {
            "C1": "PASS — finite unique SSE minimum with AUTHORITY_NOT_UNIQUE fail-closed semantics.",
            **common,
            "C3": "PASS — AUTHORITY_TOP_STABLE across completed batches and caps 16/32/64.",
            "C4": "CAUTION — point-count SSE retains bucket-edge sensitivity; exposure ranks are reported independently.",
            "C7": "PASS — Route 10 result is an SSE authority fingerprint only, not a timetable selection.",
            "C9": "LOWEST CONTRACT CHANGE — remove concordance and preserve SSE authority; not sufficient alone.",
        },
        "B": {
            "C1": "PASS — finite unique TE minimum with AUTHORITY_NOT_UNIQUE fail-closed semantics.",
            **common,
            "C3": "PASS WITH EVIDENCE — AUTHORITY_TOP_UNIVERSE_SENSITIVE; changes are descriptive, not rejection.",
            "C4": "CAUTION — point-count TE retains bucket-edge sensitivity; exposure ranks are reported independently.",
            "C7": "PASS — Route 10 result is a TE authority fingerprint only, not a timetable selection.",
            "C9": "MODERATE CONTRACT CHANGE — primary demand-fit authority changes from SSE to TE.",
        },
        "C": {
            "C1": "PASS — finite unique exact continuous-exposure minimum with AUTHORITY_NOT_UNIQUE fail-closed semantics.",
            **common,
            "C3": "PASS WITH EVIDENCE — AUTHORITY_TOP_UNIVERSE_SENSITIVE; changes are descriptive, not rejection.",
            "C4": "PASS WITH SCOPE — phase-robust to departure point buckets, while demand support remains bucket-defined.",
            "C7": "PASS — Route 10 result is a continuous authority fingerprint only, not a timetable selection.",
            "C9": "LARGER CONTRACT CHANGE — promotes continuous exposure from materiality to anchor authority.",
        },
        "D": {
            "C1": "PASS — finite nonempty strict-epsilon SSE/TE nondominated sets.",
            **common,
            "C3": "PASS WITH EVIDENCE — AUTHORITY_SET_UNIVERSE_SENSITIVE with explicit entries, exits, and overlaps.",
            "C4": "CAUTION — primary frontier remains point-bucket-sensitive; continuous ranks stay diagnostic.",
            "C7": "PASS — Route 10 result is an SSE/TE authority set only, not a timetable selection.",
            "C9": "UNRESOLVED — replacing one anchor with a set requires a separately designed downstream admissibility contract.",
        },
    }


def build_evidence(repo_root: Path) -> dict[str, Any]:
    authorities = load_authorities(repo_root)
    evidence_locks = dict(authorities["u6"]["PORT"]["production_file_sha256"])
    evidence_locks["Schedule template.xlsx"] = SCHEDULE_TEMPLATE_SHA256
    worktree_locks = {**evidence_locks, **CONTROLLED_CRLF_WORKTREE_SHA256}
    before = _snapshot_protected(repo_root, worktree_locks)

    caps = reconstruct_route10_cap_universes(authorities)
    batches = reconstruct_route10_source_batch_universes(authorities)
    historical_route6 = reconstruct_historical_route6_universe(authorities)
    cap_rehearsals = {
        cap: {
            "semantic_sha256": authorities["u6"]["ROUTE 10"]["sensitivity"]["independent_runs"][
                cap
            ]["semantic_sha256"],
            "access_safe_count": len(candidates),
            "policies": _policy_results(candidates),
        }
        for cap, candidates in caps.items()
    }
    batch_rehearsals = [
        {
            "batch_index": batch["batch_index"],
            "completed_source_batch": batch["completed_source_batch"],
            "pareto_count": batch["pareto_count"],
            "access_safe_count": len(batch["candidates"]),
            "policies": _policy_results(batch["candidates"]),
        }
        for batch in batches
    ]
    stability = {
        "A": _scalar_stability("SSE_AUTHORITATIVE_ANCHOR", "sse", batches, caps),
        "B": _scalar_stability("TE_AUTHORITATIVE_ANCHOR", "te", batches, caps),
        "C": _scalar_stability(
            "CONTINUOUS_EXPOSURE_AUTHORITATIVE_ANCHOR",
            "continuous_exposure",
            batches,
            caps,
        ),
        "D": _set_stability(batches, caps),
    }

    canonical_ranked = _ranked_candidates(caps["32"])
    canonical_results = _policy_results(caps["32"])
    special_fingerprints = {
        canonical_results["A"]["anchor"]["fingerprint"],
        canonical_results["B"]["anchor"]["fingerprint"],
        canonical_results["C"]["anchor"]["fingerprint"],
    }
    d_fingerprints = {row["fingerprint"] for row in canonical_results["D"]["frontier"]}
    special = []
    for fingerprint in sorted(special_fingerprints):
        row = _compact_candidate(canonical_ranked[fingerprint])
        row["in_D_frontier"] = fingerprint in d_fingerprints
        special.append(row)

    buckets = _route10_buckets(authorities)
    labels = {
        "A": canonical_results["A"]["anchor"]["fingerprint"],
        "B": canonical_results["B"]["anchor"]["fingerprint"],
        "C": canonical_results["C"]["anchor"]["fingerprint"],
    }
    edge_comparisons = {}
    for left, right in (("A", "B"), ("A", "C"), ("B", "C")):
        edge_comparisons[f"{left}_vs_{right}"] = _edge_comparison(
            canonical_ranked[labels[left]], canonical_ranked[labels[right]], buckets
        )

    route6_results = _policy_results(historical_route6)
    common_route6 = route6_results["A"]["anchor"]["fingerprint"]
    require(
        common_route6
        == route6_results["B"]["anchor"]["fingerprint"]
        == route6_results["C"]["anchor"]["fingerprint"],
        "HISTORICAL_ROUTE6_AUTHORITY_NOT_PRESERVED",
    )
    require(
        [row["fingerprint"] for row in route6_results["D"]["frontier"]] == [common_route6],
        "HISTORICAL_ROUTE6_FRONTIER_NOT_PRESERVED",
    )

    result = {
        "milestone": "PR62-U7",
        "review_profile": "demand_fit_authority_rehearsal_evidence_only_v1",
        "authority": {
            "review_base_sha": REVIEW_BASE_SHA,
            "canonical_u6_semantic_sha256": CANONICAL_U6_SEMANTIC_SHA256,
            "source_artifacts": authorities["source_artifacts"],
            "numerical_epsilon": authorities["numerical_epsilon"],
            "input_rule": "HASH_LOCKED_COMMITTED_JSON_EVIDENCE_ONLY",
            "production_module_imports": 0,
            "coordinator_calls_by_u7": 0,
            "route_6_global_executions": 0,
        },
        "metric_meanings": {
            "A": "unitless squared service-share residual",
            "B": "equivalent displaced departure mass in trips",
            "C": "equivalent interdeparture-exposure mismatch",
            "D": "set preserving both A and B tradeoffs",
            "passenger_welfare_claim": False,
        },
        "policies": {
            "A": {
                "name": "SSE_AUTHORITATIVE_ANCHOR",
                "metric": "sse",
                "weights_added": False,
                "minimum_contract_change": "Remove common SSE/TE requirement and preserve SSE authority.",
            },
            "B": {
                "name": "TE_AUTHORITATIVE_ANCHOR",
                "metric": "te",
                "weights_added": False,
                "minimum_contract_change": "Change primary demand-fit anchor authority to TE.",
            },
            "C": {
                "name": "CONTINUOUS_EXPOSURE_AUTHORITATIVE_ANCHOR",
                "metric": "continuous_exposure",
                "weights_added": False,
                "minimum_contract_change": "Promote continuous exposure from materiality to demand-fit authority.",
            },
            "D": {
                "name": "MULTI_METRIC_DEMAND_FIT_FRONTIER",
                "dimensions": ["sse", "te"],
                "weights_added": False,
                "continuous_is_primary_dimension": False,
                "minimum_contract_change": "Replace one anchor with an SSE/TE Pareto set and separately define downstream admissibility.",
            },
        },
        "route_10": {
            "canonical_cap": 32,
            "cap_rehearsals": cap_rehearsals,
            "source_batch_rehearsals": batch_rehearsals,
            "universe_growth_stability": stability,
            "canonical_policy_results": canonical_results,
            "special_candidate_table": special,
            "phase_edge_sensitivity": {
                "available_representations": [
                    "production_point_count_sse",
                    "production_point_count_te",
                    "pr62_r_bucket_exposure_equivalent_reconstruction",
                    "exact_continuous_exposure_equivalent",
                ],
                "authority_candidate_ranks": special,
                "changed_authority_candidate_edge_comparisons": edge_comparisons,
                "interpretation": "Point metrics assign departures to half-open buckets; exposure metrics integrate interdeparture service. Demand support remains bucket-defined in every representation.",
            },
            "final_timetable_selection_applied": False,
            "rhythm_fleet_fingerprint_selection_applied": False,
        },
        "historical_route_6": {
            "evidence_scope": "COMMITTED_PR62_M_M1_N_O_R_S_T_SNAPSHOTS_ONLY",
            "access_safe_count": len(historical_route6),
            "authority_result": "HISTORICAL_ROUTE6_AUTHORITY_PRESERVED",
            "policies": route6_results,
            "global_executions_by_u7": 0,
        },
        "criterion_matrix": _criterion_matrix(),
        "policy_classifications": {
            "A": "SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT",
            "B": "SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT",
            "C": "SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT",
            "D": "SUPPORTED_WITH_UNRESOLVED_POLICY_QUESTION",
        },
        "primary_classification": "MULTIPLE_DEMAND_FIT_AUTHORITIES_REMAIN_PLAUSIBLE",
        "next_decision": {
            "count": 1,
            "step": "Run one narrowed review-only A-versus-C downstream-admissibility rehearsal on the preserved Route 10 candidates; do not execute either route or change production selection.",
        },
        "longer_term_service_quality_context": {
            "scope": "DEMAND_FIT_AUTHORITY_ONLY",
            "resolves_crowding": False,
            "resolves_timetable_aware_passenger_arrival": False,
            "replaces_expected_wait_or_access_metrics": False,
            "constitutes_operational_reliability_validation": False,
        },
        "protected_artifact_hashes": {},
        "invariants": {
            "production selector changed": False,
            "U6 changed": False,
            "Route 10 production timetable selected": False,
            "Route 6 global executions": 0,
            "final pilot workbooks changed": False,
            "PR #62 modified": False,
        },
    }
    after = _snapshot_protected(repo_root, worktree_locks)
    result["protected_artifact_hashes"] = {
        relative: {
            "evidence_lock_sha256": evidence_locks[relative],
            "u7_start_worktree_sha256": worktree_locks[relative],
            "before_sha256": before[relative],
            "after_sha256": after[relative],
            "baseline_classification": (
                "CONTROLLED_CRLF_WORKTREE_BASELINE"
                if relative in CONTROLLED_CRLF_WORKTREE_SHA256
                else "MATCHES_U6_EVIDENCE_LOCK"
            ),
            "unchanged": before[relative] == after[relative] == worktree_locks[relative],
        }
        for relative in sorted(worktree_locks)
    }
    require(
        all(row["unchanged"] for row in result["protected_artifact_hashes"].values()),
        "PROTECTED_ARTIFACT_CHANGED_DURING_U7",
    )
    return result


def _f(value: float) -> str:
    return f"{value:.12f}"


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(evidence: Mapping[str, Any]) -> str:
    lines = [
        "# PR62-U7 — Demand-Fit Authority Rehearsal",
        "",
        "Policy-evidence experiment only. No production timetable is selected.",
        "",
        "## 1. Review authority",
        "",
        f"- Base SHA: `{evidence['authority']['review_base_sha']}`",
        f"- Canonical U6 semantic SHA-256: `{evidence['authority']['canonical_u6_semantic_sha256']}`",
        f"- Numerical epsilon: `{evidence['authority']['numerical_epsilon']['value']}` from hash-locked `{evidence['authority']['numerical_epsilon']['source_path']}`",
        f"- Route 6 global executions: `{evidence['authority']['route_6_global_executions']}`",
        "",
        "### Source artifacts",
        "",
        "| Artifact | Commit | SHA-256 | Bytes |",
        "|---|---:|---:|---:|",
    ]
    for path, row in evidence["authority"]["source_artifacts"].items():
        lines.append(
            f"| `{path}` | `{row['commit_sha']}` | `{row['sha256']}` | {row['size_bytes']} |"
        )

    lines.extend(
        [
            "",
            "## 2. Route 10 policy rehearsal",
            "",
            "### Cap-final authorities",
            "",
            "| Cap | Access-safe | A: SSE | B: TE | C: continuous | D: SSE/TE frontier |",
            "|---:|---:|---|---|---|---|",
        ]
    )
    for cap, row in evidence["route_10"]["cap_rehearsals"].items():
        policies = row["policies"]
        d_fps = ", ".join(item["fingerprint"] for item in policies["D"]["frontier"])
        lines.append(
            f"| {cap} | {row['access_safe_count']} | `{policies['A']['anchor']['fingerprint']}` | `{policies['B']['anchor']['fingerprint']}` | `{policies['C']['anchor']['fingerprint']}` | {len(policies['D']['frontier'])}: `{d_fps}` |"
        )
    lines.extend(
        [
            "",
            "### Source-batch evolution (canonical cap 32)",
            "",
            "| Batch | Completed source | Access-safe | A | B | C | D size |",
            "|---:|---|---:|---|---|---|---:|",
        ]
    )
    for row in evidence["route_10"]["source_batch_rehearsals"]:
        policies = row["policies"]
        lines.append(
            f"| {row['batch_index']} | `{row['completed_source_batch']}` | {row['access_safe_count']} | `{policies['A']['anchor']['fingerprint']}` | `{policies['B']['anchor']['fingerprint']}` | `{policies['C']['anchor']['fingerprint']}` | {len(policies['D']['frontier'])} |"
        )
    growth = evidence["route_10"]["universe_growth_stability"]
    lines.extend(
        [
            "",
            "### Scalar growth summary",
            "",
            "| Policy | Anchor changes | First change batch | Final anchor | Cap 16/32/64 agree | Classification |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for policy in ("A", "B", "C"):
        row = growth[policy]
        first_change = row["first_change_batch"]
        first_change_text = (
            "none"
            if first_change is None
            else f"{first_change['batch_index']}: {first_change['completed_source_batch']}"
        )
        lines.append(
            f"| {policy} | {row['anchor_change_count']} | `{first_change_text}` | `{row['final_anchor']}` | {row['cap16_cap32_cap64_agree']} | `{row['stability_classification']}` |"
        )

    lines.extend(
        [
            "",
            "### D boundedness audit",
            "",
            "No arbitrary frontier-size ceiling is applied.",
            "",
            "| Cap | Access-safe | Frontier size/proportion | Exact frontier | Rhythm diversity | Continuous range | Wait range (min) | Fleet range |",
            "|---:|---:|---|---|---|---|---|---|",
        ]
    )
    d_growth = growth["D"]
    for cap, row in d_growth["cap_frontiers"].items():
        lines.append(
            "| {} | {} | {} / {:.6f} | `{}` | `{}` | {}–{} | {}–{} | {}–{} |".format(
                cap,
                row["access_safe_count"],
                row["sse_te_frontier_size"],
                row["frontier_proportion"],
                ", ".join(row["frontier_fingerprints"]),
                row["rhythm_tuple_diversity"],
                _f(row["continuous_exposure_range"]["minimum"]),
                _f(row["continuous_exposure_range"]["maximum"]),
                _f(row["waiting_range_minutes"]["minimum"]),
                _f(row["waiting_range_minutes"]["maximum"]),
                row["fleet_range"]["minimum"],
                row["fleet_range"]["maximum"],
            )
        )
    lines.extend(
        [
            "",
            f"D stability: `{d_growth['stability_classification']}`; boundedness: `{d_growth['boundedness_classification']}`.",
            "",
            "#### D source-batch entries and exits",
            "",
            "| Batch | Frontier size | Entries | Exits |",
            "|---:|---:|---|---|",
        ]
    )
    for row in d_growth["batch_history"]:
        lines.append(
            f"| {row['batch_index']} | {row['sse_te_frontier_size']} | `{', '.join(row['entries']) or 'none'}` | `{', '.join(row['exits']) or 'none'}` |"
        )
    lines.extend(
        [
            "",
            "#### D cap-set overlaps",
            "",
            "| Caps | Intersection / union | Intersection fingerprints |",
            "|---|---|---|",
        ]
    )
    for pair, row in d_growth["cap_set_overlaps"].items():
        lines.append(
            f"| {pair} | {row['intersection_count']} / {row['union_count']} | `{', '.join(row['intersection_fingerprints'])}` |"
        )

    lines.extend(
        [
            "",
            "## 3. Phase / edge sensitivity and passenger/service context",
            "",
            "The metrics below are contextual outcomes, not a hidden reranking and not actual onboard passenger delay.",
            "",
            "| Fingerprint | SSE rank/value | TE rank/value | Continuous rank/value | Bucket exposure rank/value | Avg scheduled wait | Out max | In max | Rhythm | Fleet | Terminal excess total/max | Lineage | In D |",
            "|---|---|---|---|---|---:|---:|---:|---|---:|---|---|---|",
        ]
    )
    for row in evidence["route_10"]["special_candidate_table"]:
        lineage = row["lineage"]
        lineage_text = lineage["origin"]
        if lineage["parent_pair_fingerprint"] is not None:
            lineage_text += f" from {lineage['parent_pair_fingerprint']}"
        lines.append(
            "| `{}` | {}/{} | {}/{} | {}/{} | {}/{} | {} | {} | {} | `{}` | {} | {}/{} | `{}` | {} |".format(
                row["fingerprint"],
                row["sse_rank"],
                _f(row["sse"]),
                row["te_rank"],
                _f(row["te"]),
                row["continuous_rank"],
                _f(row["continuous_exposure"]),
                row["bucket_exposure_rank"],
                _f(row["bucket_exposure"]),
                _f(row["average_scheduled_passenger_wait_minutes"]),
                _f(row["directional_maximum_access_minutes"]["outbound"]),
                _f(row["directional_maximum_access_minutes"]["inbound"]),
                row["rhythm_tuple"],
                row["fleet"],
                row["terminal_excess"]["total"],
                row["terminal_excess"]["maximum"],
                lineage_text,
                row["in_D_frontier"],
            )
        )
    lines.extend(
        [
            "",
            "### Exact bucket-edge comparison summary",
            "",
            "| Pair | Direction | Changed departures | Bucket crossings | Total bucket edges crossed |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for pair, comparison in evidence["route_10"]["phase_edge_sensitivity"][
        "changed_authority_candidate_edge_comparisons"
    ].items():
        for direction, row in comparison["directions"].items():
            lines.append(
                f"| {pair} | {direction} | {row['changed_departure_positions']} | {row['bucket_boundary_crossing_count']} | {row['total_bucket_edges_crossed']} |"
            )
    lines.extend(
        [
            "",
            "Exact crossing departure positions are retained in the compact JSON evidence.",
        ]
    )

    route6 = evidence["historical_route_6"]
    lines.extend(
        [
            "",
            "## 4. Historical Route 6",
            "",
            f"- Result: `{route6['authority_result']}`",
            f"- Snapshot-only access-safe universe: {route6['access_safe_count']} candidates",
            f"- A/B/C authority and D singleton: `{route6['policies']['A']['anchor']['fingerprint']}`",
            f"- Route 6 global executions by U7: `{route6['global_executions_by_u7']}`",
            "",
            "## 5. Criterion matrix (no weighted score)",
            "",
            "| Criterion | A | B | C | D |",
            "|---|---|---|---|---|",
        ]
    )
    for index in range(1, 10):
        criterion = f"C{index}"
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                criterion,
                *(
                    _escape(evidence["criterion_matrix"][policy][criterion])
                    for policy in ("A", "B", "C", "D")
                ),
            )
        )
    lines.extend(["", "## 6. Policy classifications", ""])
    for policy, classification in evidence["policy_classifications"].items():
        lines.append(f"- {policy}: `{classification}`")
    lines.extend(
        [
            "",
            "## 7. Primary U7 classification",
            "",
            f"`{evidence['primary_classification']}`",
            "",
            "## 8. Exactly one next decision",
            "",
            evidence["next_decision"]["step"],
            "",
            "## 9. Longer-term service-quality boundary",
            "",
            "A/B/C/D concern demand-fit authority only. None resolves crowding, timetable-aware passenger arrival, expected-wait/access evidence, or operational reliability validation.",
            "",
            "## 10. Final invariants",
            "",
        ]
    )
    for key, value in evidence["invariants"].items():
        lines.append(f"`{key} = {str(value).lower()}`")
    return "\n".join(lines) + "\n"


def write_artifacts(evidence: Mapping[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / OUTPUT_JSON
    markdown_path = output_dir / OUTPUT_MARKDOWN
    with json_path.open("xb") as stream:
        stream.write(canonical_json_bytes(evidence))
    with markdown_path.open("xb") as stream:
        stream.write(render_markdown(evidence).encode("utf-8"))
    return {"json": json_path, "markdown": markdown_path}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else repo_root / "docs" / "engine" / "evidence"
    )
    evidence = build_evidence(repo_root)
    paths = write_artifacts(evidence, output_dir)
    print(
        json.dumps(
            {
                "classification": evidence["primary_classification"],
                "json": paths["json"].as_posix(),
                "markdown": paths["markdown"].as_posix(),
                "route_6_global_executions": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

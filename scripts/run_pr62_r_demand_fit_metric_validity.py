"""Review demand-fit bucket-edge aliasing without changing production semantics."""

from __future__ import annotations

import argparse
import collections
import ctypes
import dataclasses
import hashlib
import json
import math
import os
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT / "src", _REPO_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import run_pr62_i_worst_bucket_passenger_access as pr62_i  # noqa: E402

from bus_schedule_engine import service_plan_coordinator as coordinator  # noqa: E402
from bus_schedule_engine.contracts_v1.operational_selection_policy_v2 import (  # noqa: E402
    build_operational_selection_candidate_v2,
)

NUMERICAL_EPSILON = 1e-12
Q_COMMIT_SHA = "e2425e5c77cdfd9832aff8cb4cda218424b2c323"
ROUTE10_P_PAIR = "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24"
ROUTE10_Q_PAIR = "12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5"
ROUTE10_ANCHOR = "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
OUTPUT_JSON = Path("docs/engine/evidence/PR62_R_DEMAND_FIT_METRIC_VALIDITY.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_R_DEMAND_FIT_METRIC_VALIDITY.md")
Q_EVIDENCE = Path("docs/engine/evidence/PR62_Q_LOCAL_RHYTHM_CANONICALIZATION.json")
P_EVIDENCE = Path("docs/engine/evidence/PR62_P_FINAL_XLSX_RECERTIFICATION.json")
P_PRODUCT_DATA = Path("outputs/final_pilot/PR62_P_FINAL_PILOT_DATA.json")
O_EVIDENCE = Path("docs/engine/evidence/PR62_O_PRODUCTION_POLICY_FREEZE.json")
ROUTE10_PRESERVED_REPORTS = (
    Path(".codex-tmp-pr62-h-run1/route_10_coordinator_report.json"),
    Path(".codex-tmp-pr62-h-run2/route_10_coordinator_report.json"),
)
ROUTE6_RECOVERY_CHECKPOINT = Path(".codex-tmp-pr62-r-recovery/route_6_coordinator_report.json")
FROZEN_BUDGET = coordinator.CoordinatorSearchBudgetV1(24, 512, 4, 24, 512)

IMMUTABLE_FILE_LOCKS = {
    "src/bus_schedule_engine/service_plan_coordinator.py": (
        "99da83840f30d5ff7781b1525ec5202074641f1c01203ad46ddc42200a24bfc0"
    ),
    "src/bus_schedule_engine/contracts_v1/clean_boundary_compiler.py": (
        "e36950284e7d2bea1f7ff15dc1bb016d360b8b3dd6ff3ce0299cfcbdb3952490"
    ),
    "src/bus_schedule_engine/contracts_v1/operational_selection_policy.py": (
        "5f10bf7130c20898a3e537fc8f7b73e990335f92ccb7913c41e50a308809e415"
    ),
    "src/bus_schedule_engine/contracts_v1/operational_selection_policy_v2.py": (
        "79a63d38dfde00f42af1f5a56cb67adb3280c3941b45cdb1f67fb65c67ea3181"
    ),
    "src/bus_schedule_engine/contracts_v1/fleet_assignment.py": (
        "ea222b7f3c4d46eb908b6a1df4b6f450128dff418f7a8e466192eab8b965f093"
    ),
    "src/bus_schedule_engine/clean_boundary_pilot.py": (
        "1b17298d31ed308da058ba213748c23b7a76f8902c3abcef20715d5ca1a99fd9"
    ),
    "outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx": (
        "13454026722f996d8b06e5305b3b6ab2d57ea6126734f4deeb23c3e7dbafd02c"
    ),
    "outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx": (
        "d84dd2e873d3ba30275463a5eff67277a22467839af0f0125e69160a891fc3db"
    ),
    "docs/engine/evidence/PR62_Q_LOCAL_RHYTHM_CANONICALIZATION.json": (
        "222c5a929c27f76d1d683568a494da03544a8b50f51eae10fc848324a656ba11"
    ),
    "docs/engine/evidence/PR62_Q_LOCAL_RHYTHM_CANONICALIZATION.md": (
        "8966313c77f3be523b7961dcf9b8e13ed0a61217825cd624efbdd2921a9cd431"
    ),
    "docs/engine/evidence/PR62_P_FINAL_XLSX_RECERTIFICATION.json": (
        "df9145b7a99ca832b99c41b727d53a0b895b4d71af5ef068e3d4082a39efa04a"
    ),
    "outputs/final_pilot/PR62_P_FINAL_PILOT_DATA.json": (
        "93710b8cf87fdb409d572dc1bb02f162c24435bb9660896c0295d00f10385d89"
    ),
    "docs/engine/evidence/PR62_I_WORST_BUCKET_PASSENGER_ACCESS.json": (
        "8abeeb498744a71a45a72ddc33ccad442092668f803ac971ac94d2b46226eeb9"
    ),
    "docs/engine/evidence/PR62_O_PRODUCTION_POLICY_FREEZE.json": (
        "91a93fa7e7abd4ede3e6848b241b0a3aa22f8f4942aa202c93dad6631df46346"
    ),
}

EXPECTED_PRODUCTION_GUARDS = {
    "Production_SSE_changed": False,
    "Production_TE_changed": False,
    "V2_plus_1_TE_band_changed": False,
    "V2_selector_changed": False,
    "Production_search_changed": False,
    "Search_budget_changed": False,
    "Queue_changed": False,
    "10_D_Pareto_changed": False,
    "Compiler_changed": False,
    "Rhythm_semantics_changed": False,
    "Micro_rhythm_hard_constraint_added": False,
    "Tail_changed": False,
    "Protection_changed": False,
    "Access_changed": False,
    "Fleet_validator_changed": False,
    "Settlement_or_residual_added": False,
    "Canonical_Route_6_XLSX_changed": False,
    "Canonical_Route_10_XLSX_changed": False,
    "Private_workbook_opened": False,
    "Private_workbook_committed": False,
    "New_continuous_metrics_added_to_production": False,
}

METRIC_KEYS = (
    "production_SSE",
    "production_TE",
    "bucket_exposure_SSE",
    "bucket_exposure_equivalent",
    "continuous_exposure_equivalent",
)


def _read_shared_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except PermissionError as error:
        if os.name != "nt":
            raise
        create_file = ctypes.windll.kernel32.CreateFileW
        create_file.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        create_file.restype = ctypes.c_void_p
        handle = create_file(
            str(path.resolve()),
            0x80000000,
            0x00000001 | 0x00000002 | 0x00000004,
            None,
            3,
            0x80,
            None,
        )
        if handle in (None, ctypes.c_void_p(-1).value):
            raise PermissionError(path) from error
        import msvcrt

        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as stream:
            return stream.read()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(_read_shared_bytes(path)).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _load_json(repo_root: Path, relative: Path) -> Any:
    return json.loads((repo_root / relative).read_text(encoding="utf-8"))


def _verify_immutable_locks(repo_root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative, expected in IMMUTABLE_FILE_LOCKS.items():
        path = repo_root / relative
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"IMMUTABLE_LOCK_MISMATCH: {relative}")
        records[relative] = {
            "bytes": path.stat().st_size,
            "sha256": actual,
            "unchanged": True,
        }
    return records


def immutable_lock_record(locks: Mapping[str, Any], relative: Path | str) -> Any:
    key = str(relative).replace("\\", "/")
    return locks[key]


def load_preserved_frontier_reports(
    first_path: Path,
    second_path: Path,
    *,
    expected_fingerprints: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    first_bytes = _read_shared_bytes(first_path)
    second_bytes = _read_shared_bytes(second_path)
    if first_bytes != second_bytes:
        raise RuntimeError("preserved coordinator reports are not byte-identical")
    report = json.loads(first_bytes)
    frontier = report["pareto_frontier"]
    actual = sorted(str(row["pair_fingerprint"]) for row in frontier)
    if actual != sorted(str(value) for value in expected_fingerprints):
        raise RuntimeError("preserved coordinator report does not match exact PR62-I frontier")
    return frontier, {
        "reports_byte_identical": True,
        "fingerprints_match_PR62_I": True,
        "report_sha256": hashlib.sha256(first_bytes).hexdigest(),
        "report_bytes": len(first_bytes),
    }


def _validated_inputs(
    departures: Sequence[int | float], buckets: Sequence[Mapping[str, Any]]
) -> tuple[list[float], list[dict[str, float]]]:
    exact_departures = [float(value) for value in departures]
    if len(exact_departures) < 2 or any(not math.isfinite(value) for value in exact_departures):
        raise ValueError("at least two finite exact departures are required")
    if any(
        left >= right for left, right in zip(exact_departures, exact_departures[1:], strict=False)
    ):
        raise ValueError("exact departures must be strictly increasing")

    normalized: list[dict[str, float]] = []
    for bucket in buckets:
        start = float(bucket["start"])
        end = float(bucket["end"])
        demand = float(bucket["observed_demand"])
        if not all(math.isfinite(value) for value in (start, end, demand)):
            raise ValueError("demand support values must be finite")
        if start >= end or demand < 0:
            raise ValueError("demand support buckets must have positive width and demand >= 0")
        normalized.append({"start": start, "end": end, "observed_demand": demand})
    if not normalized:
        raise ValueError("demand support must not be empty")
    for left, right in zip(normalized, normalized[1:], strict=False):
        if left["end"] != right["start"]:
            raise ValueError("demand support must be ordered, gap-free, and non-overlapping")
    if exact_departures[0] < normalized[0]["start"] or exact_departures[-1] > normalized[-1]["end"]:
        raise ValueError("demand support must cover the complete service operating span")
    if sum(bucket["observed_demand"] for bucket in normalized) <= 0:
        raise ValueError("total observed demand must be positive")
    return exact_departures, normalized


def _demand_shares(buckets: Sequence[Mapping[str, float]]) -> tuple[list[float], float]:
    total = sum(bucket["observed_demand"] for bucket in buckets)
    return [bucket["observed_demand"] / total for bucket in buckets], total


def production_point_metrics(
    departures: Sequence[int | float], buckets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Reproduce unchanged production point-count SSE/TV/TE semantics."""

    exact_departures, demand_buckets = _validated_inputs(departures, buckets)
    counts = [
        sum(bucket["start"] <= departure < bucket["end"] for departure in exact_departures)
        for bucket in demand_buckets
    ]
    demand_shares, _ = _demand_shares(demand_buckets)
    service_shares = [count / len(exact_departures) for count in counts]
    residuals = [
        service_share - demand_share
        for service_share, demand_share in zip(service_shares, demand_shares, strict=True)
    ]
    sse = sum(residual * residual for residual in residuals)
    tv = 0.5 * sum(abs(residual) for residual in residuals)
    return {
        "bucket_service_counts": counts,
        "service_shares": service_shares,
        "demand_shares": demand_shares,
        "residuals": residuals,
        "sse": sse,
        "tv": tv,
        "te": len(exact_departures) * tv,
    }


def bucket_exposure_metrics(
    departures: Sequence[int | float], buckets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Fractionally assign complete interdeparture exposure to demand buckets."""

    exact_departures, demand_buckets = _validated_inputs(departures, buckets)
    demand_shares, _ = _demand_shares(demand_buckets)
    masses: list[float] = []
    for bucket in demand_buckets:
        mass = 0.0
        for left, right in zip(exact_departures, exact_departures[1:], strict=False):
            overlap = max(0.0, min(bucket["end"], right) - max(bucket["start"], left))
            mass += overlap / (right - left)
        masses.append(mass)
    total_mass = sum(masses)
    expected_mass = float(len(exact_departures) - 1)
    if not math.isclose(total_mass, expected_mass, rel_tol=0.0, abs_tol=NUMERICAL_EPSILON):
        raise ValueError("demand support does not conserve complete service exposure")
    service_shares = [mass / total_mass for mass in masses]
    residuals = [
        service_share - demand_share
        for service_share, demand_share in zip(service_shares, demand_shares, strict=True)
    ]
    sse = sum(residual * residual for residual in residuals)
    tv = 0.5 * sum(abs(residual) for residual in residuals)
    return {
        "buckets": [
            {
                **bucket,
                "demand_share": demand_share,
                "exposure_mass": mass,
                "service_share": service_share,
                "residual": residual,
            }
            for bucket, demand_share, mass, service_share, residual in zip(
                demand_buckets,
                demand_shares,
                masses,
                service_shares,
                residuals,
                strict=True,
            )
        ],
        "total_exposure_mass": total_mass,
        "sse": sse,
        "tv": tv,
        "equivalent": len(exact_departures) * tv,
    }


def continuous_exposure_metrics(
    departures: Sequence[int | float], buckets: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Exactly integrate TV/L2 over demand and departure breakpoints."""

    exact_departures, demand_buckets = _validated_inputs(departures, buckets)
    demand_shares, total_demand = _demand_shares(demand_buckets)
    domain_start = demand_buckets[0]["start"]
    domain_end = demand_buckets[-1]["end"]
    breakpoints = sorted(
        {
            domain_start,
            domain_end,
            *exact_departures,
            *(bucket["start"] for bucket in demand_buckets),
            *(bucket["end"] for bucket in demand_buckets),
        }
    )
    exposure_units = float(len(exact_departures) - 1)
    absolute_integral = 0.0
    squared_integral = 0.0
    demand_integral = 0.0
    service_integral = 0.0
    for left, right in zip(breakpoints, breakpoints[1:], strict=False):
        width = right - left
        demand_index = next(
            index
            for index, bucket in enumerate(demand_buckets)
            if bucket["start"] <= left < bucket["end"]
        )
        demand_density = demand_shares[demand_index] / (
            demand_buckets[demand_index]["end"] - demand_buckets[demand_index]["start"]
        )
        service_density = 0.0
        unnormalized_service_density = 0.0
        for departure_left, departure_right in zip(
            exact_departures, exact_departures[1:], strict=False
        ):
            if departure_left <= left < departure_right:
                unnormalized_service_density = 1.0 / (departure_right - departure_left)
                service_density = unnormalized_service_density / exposure_units
                break
        difference = service_density - demand_density
        absolute_integral += width * abs(difference)
        squared_integral += width * difference * difference
        demand_integral += width * demand_density * total_demand
        service_integral += width * unnormalized_service_density
    duration = domain_end - domain_start
    tv = 0.5 * absolute_integral
    return {
        "analysis_domain": [domain_start, domain_end],
        "breakpoints": [int(value) if value.is_integer() else value for value in breakpoints],
        "total_demand": total_demand,
        "demand_integral": demand_integral,
        "service_exposure_integral": service_integral,
        "tv": tv,
        "equivalent": len(exact_departures) * tv,
        "continuous_l2": duration * squared_integral,
    }


def classify_p_vs_q(
    *,
    p_production_te: float,
    q_production_te: float,
    p_bucket_equivalent: float,
    q_bucket_equivalent: float,
    p_continuous_equivalent: float,
    q_continuous_equivalent: float,
    production_vs_bucket_rank_disagreements: int,
    production_vs_continuous_rank_disagreements: int,
    epsilon: float = NUMERICAL_EPSILON,
) -> dict[str, Any]:
    """Apply the exact PR62-R decision booleans and root classification."""

    point_prefers_p = p_production_te < q_production_te - epsilon
    bucket_prefers_q = q_bucket_equivalent < p_bucket_equivalent - epsilon
    bucket_prefers_p = p_bucket_equivalent < q_bucket_equivalent - epsilon
    bucket_tie = abs(q_bucket_equivalent - p_bucket_equivalent) <= epsilon
    continuous_prefers_q = q_continuous_equivalent < p_continuous_equivalent - epsilon
    continuous_prefers_p = p_continuous_equivalent < q_continuous_equivalent - epsilon
    continuous_tie = abs(q_continuous_equivalent - p_continuous_equivalent) <= epsilon

    if (bucket_prefers_q and continuous_prefers_p) or (bucket_prefers_p and continuous_prefers_q):
        classification = "MIXED_DEMAND_FIT_METRIC_EVIDENCE"
    elif point_prefers_p and (
        bucket_prefers_q or bucket_tie or continuous_prefers_q or continuous_tie
    ):
        classification = "BUCKET_EDGE_ALIASING_CONFIRMED"
    else:
        production_penalty = q_production_te - p_production_te
        bucket_penalty = q_bucket_equivalent - p_bucket_equivalent
        continuous_penalty = q_continuous_equivalent - p_continuous_equivalent
        disagreements = (
            production_vs_bucket_rank_disagreements + production_vs_continuous_rank_disagreements
        )
        if (
            point_prefers_p
            and bucket_prefers_p
            and continuous_prefers_p
            and bucket_penalty < production_penalty - epsilon
            and continuous_penalty < production_penalty - epsilon
            and disagreements > 0
        ):
            classification = "BUCKET_EDGE_ALIASING_MATERIAL_BUT_NOT_DECISIVE"
        elif point_prefers_p and bucket_prefers_p and continuous_prefers_p:
            classification = "DEMAND_FIT_LOSS_PERSISTS_UNDER_CONTINUOUS_EXPOSURE"
        else:
            classification = "R_EVIDENCE_INCONCLUSIVE"
    return {
        "POINT_COUNT_PREFERS_P": point_prefers_p,
        "BUCKET_EXPOSURE_PREFERS_Q": bucket_prefers_q,
        "BUCKET_EXPOSURE_PREFERS_P": bucket_prefers_p,
        "BUCKET_EXPOSURE_EQUIVALENT_TIE": bucket_tie,
        "CONTINUOUS_EXPOSURE_PREFERS_Q": continuous_prefers_q,
        "CONTINUOUS_EXPOSURE_PREFERS_P": continuous_prefers_p,
        "CONTINUOUS_EXPOSURE_EQUIVALENT_TIE": continuous_tie,
        "root_classification": classification,
    }


def _bucket_index(value: float, buckets: Sequence[Mapping[str, float]]) -> int | None:
    return next(
        (index for index, bucket in enumerate(buckets) if bucket["start"] <= value < bucket["end"]),
        None,
    )


def departure_edge_crossing_audit(
    p_departures: Sequence[int | float],
    q_departures: Sequence[int | float],
    buckets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(p_departures) != len(q_departures):
        raise ValueError("paired departure audits require equal directional trip totals")
    p_values, demand_buckets = _validated_inputs(p_departures, buckets)
    q_values, _ = _validated_inputs(q_departures, buckets)
    boundaries = [bucket["start"] for bucket in demand_buckets[1:]]
    changed: list[dict[str, Any]] = []
    for sequence, (p_value, q_value) in enumerate(zip(p_values, q_values, strict=True), start=1):
        if abs(p_value - q_value) <= NUMERICAL_EPSILON:
            continue
        if q_value > p_value:
            crossed = [boundary for boundary in boundaries if p_value < boundary <= q_value]
        else:
            crossed = [boundary for boundary in boundaries if q_value <= boundary < p_value]
        p_bucket = _bucket_index(p_value, demand_buckets)
        q_bucket = _bucket_index(q_value, demand_buckets)
        signed_minutes = (q_value - p_value) / 60.0
        changed.append(
            {
                "sequence": sequence,
                "P_time_seconds": int(p_value),
                "Q_time_seconds": int(q_value),
                "signed_shift_minutes": signed_minutes,
                "absolute_shift_minutes": abs(signed_minutes),
                "P_bucket_index": p_bucket,
                "Q_bucket_index": q_bucket,
                "bucket_membership_changed": p_bucket != q_bucket,
                "crossed_bucket_boundaries_seconds": [int(value) for value in crossed],
            }
        )
    absolute = [row["absolute_shift_minutes"] for row in changed]
    bucket_changing = [row for row in changed if row["bucket_membership_changed"]]
    distribution = collections.Counter(row["signed_shift_minutes"] for row in bucket_changing)
    return {
        "total_departures": len(p_values),
        "total_departures_changed": len(changed),
        "bucket_changing_departures": len(bucket_changing),
        "total_bucket_boundary_crossings": sum(
            len(row["crossed_bucket_boundaries_seconds"]) for row in changed
        ),
        "absolute_shift_minutes": {
            "sum": sum(absolute),
            "median": statistics.median(absolute) if absolute else 0.0,
            "max": max(absolute, default=0.0),
        },
        "bucket_changing_shift_distribution_minutes": [
            {"shift": shift, "count": count} for shift, count in sorted(distribution.items())
        ],
        "changed_departures": changed,
    }


def _pairwise_disagreement_count(
    records: Sequence[Mapping[str, Any]], left_key: str, right_key: str
) -> int:
    ordered = sorted(records, key=lambda row: str(row["fingerprint"]))
    count = 0
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            left_delta = float(left[left_key]) - float(right[left_key])
            right_delta = float(left[right_key]) - float(right[right_key])
            if abs(left_delta) <= NUMERICAL_EPSILON or abs(right_delta) <= NUMERICAL_EPSILON:
                continue
            if (left_delta < 0) != (right_delta < 0):
                count += 1
    return count


def _metric_ranks(
    records: Sequence[Mapping[str, Any]], metric: str
) -> tuple[dict[str, int], list[str]]:
    ordered = sorted(records, key=lambda row: (float(row[metric]), str(row["fingerprint"])))
    ranks: dict[str, int] = {}
    previous: float | None = None
    current_rank = 0
    for position, row in enumerate(ordered, start=1):
        value = float(row[metric])
        if previous is None or abs(value - previous) > NUMERICAL_EPSILON:
            current_rank = position
            previous = value
        ranks[str(row["fingerprint"])] = current_rank
    return ranks, [str(row["fingerprint"]) for row in ordered]


def ranking_audit(
    records: Sequence[Mapping[str, Any]],
    *,
    anchor_fingerprint: str,
    selected_fingerprint: str,
) -> dict[str, Any]:
    if not records:
        raise ValueError("ranking audit requires candidates")
    rank_maps: dict[str, dict[str, int]] = {}
    orders: dict[str, list[str]] = {}
    best_sets: dict[str, list[str]] = {}
    top_5: dict[str, list[str]] = {}
    for metric in METRIC_KEYS:
        rank_maps[metric], orders[metric] = _metric_ranks(records, metric)
        best_value = min(float(row[metric]) for row in records)
        best_sets[metric] = sorted(
            str(row["fingerprint"])
            for row in records
            if float(row[metric]) <= best_value + NUMERICAL_EPSILON
        )
        top_5[metric] = orders[metric][:5]
    table = []
    for row in sorted(records, key=lambda value: str(value["fingerprint"])):
        table.append(
            {
                **row,
                "ranks": {
                    metric: rank_maps[metric][str(row["fingerprint"])] for metric in METRIC_KEYS
                },
            }
        )
    return {
        "ranking_table": table,
        "best_sets": best_sets,
        "top_5": top_5,
        "pairwise_rank_disagreement_counts": {
            "production_TE_vs_bucket_exposure_equivalent": _pairwise_disagreement_count(
                records, "production_TE", "bucket_exposure_equivalent"
            ),
            "production_TE_vs_continuous_exposure_equivalent": _pairwise_disagreement_count(
                records, "production_TE", "continuous_exposure_equivalent"
            ),
            "production_SSE_vs_bucket_exposure_SSE": _pairwise_disagreement_count(
                records, "production_SSE", "bucket_exposure_SSE"
            ),
        },
        "anchor_ranks": {metric: rank_maps[metric][anchor_fingerprint] for metric in METRIC_KEYS},
        "selected_ranks": {
            metric: rank_maps[metric][selected_fingerprint] for metric in METRIC_KEYS
        },
    }


def _normalized_buckets(context: Any, direction: str) -> list[dict[str, Any]]:
    return [
        {
            "direction": bucket.direction,
            "start": bucket.start,
            "end": bucket.end,
            "observed_demand": bucket.observed_demand,
        }
        for bucket in context.demand_buckets[direction]
    ]


def _direction_metrics(
    departures: Sequence[int],
    buckets: Sequence[Mapping[str, Any]],
    *,
    operational_metrics: Any | None = None,
) -> dict[str, Any]:
    point = production_point_metrics(departures, buckets)
    exposure = bucket_exposure_metrics(departures, buckets)
    continuous = continuous_exposure_metrics(departures, buckets)
    result: dict[str, Any] = {
        "exact_departures": list(departures),
        "trip_count": len(departures),
        "production_SSE": point["sse"],
        "production_TV": point["tv"],
        "production_TE": point["te"],
        "bucket_exposure_SSE": exposure["sse"],
        "bucket_exposure_TV": exposure["tv"],
        "bucket_exposure_equivalent": exposure["equivalent"],
        "continuous_exposure_TV": continuous["tv"],
        "continuous_exposure_equivalent": continuous["equivalent"],
        "continuous_L2": continuous["continuous_l2"],
        "service_exposure_integral": continuous["service_exposure_integral"],
        "demand_integral": continuous["demand_integral"],
        "analysis_domain": continuous["analysis_domain"],
        "point_to_exposure_TV_gap": point["tv"] - exposure["tv"],
        "point_to_continuous_equivalent_gap": point["te"] - continuous["equivalent"],
        "point": point,
        "bucket_exposure": exposure,
    }
    if operational_metrics is not None:
        if not math.isclose(
            result["production_SSE"],
            operational_metrics.observed_demand_mismatch,
            rel_tol=0.0,
            abs_tol=NUMERICAL_EPSILON,
        ):
            raise RuntimeError("production SSE reproduction mismatch")
        rhythm = operational_metrics.rhythm_simplicity
        result["operations"] = {
            "average_passenger_wait_minutes": (
                operational_metrics.demand_weighted_expected_passenger_wait_minutes
            ),
            "maximum_bucket_wait_minutes": (
                operational_metrics.maximum_bucket_expected_wait_minutes
            ),
            "p90_bucket_wait_minutes": operational_metrics.p90_bucket_expected_wait_minutes,
            "actual_service_regime_count": rhythm.actual_service_regime_count,
            "sustained_headway_levels": list(rhythm.sustained_headway_levels),
            "sustained_headway_level_count": rhythm.sustained_headway_level_count,
            "tail_headway_minutes": operational_metrics.tail_headway_minutes,
            "demand_response": {
                "canonical_DemandRegime_projections": [
                    dataclasses.asdict(value)
                    for value in operational_metrics.demand_response_regime_projections
                ],
                "response_transitions": [
                    dataclasses.asdict(value)
                    for value in operational_metrics.demand_response_transitions
                ],
                "response_direction_accuracy": (
                    operational_metrics.demand_response_direction_accuracy
                ),
                "sqrt_response_deviation": operational_metrics.sqrt_seed_response_deviation,
                "sqrt_demand_is_target": False,
            },
        }
    return result


def _pair_metrics(
    *,
    fingerprint: str,
    authority: str,
    directions: Mapping[str, Mapping[str, Any]],
    fleet_required: int | None,
    operational_pair: Any | None = None,
) -> dict[str, Any]:
    pair = {
        key: sum(float(directions[direction][key]) for direction in ("outbound", "inbound"))
        for key in (
            "production_SSE",
            "production_TE",
            "bucket_exposure_SSE",
            "bucket_exposure_equivalent",
            "continuous_exposure_TV",
            "continuous_exposure_equivalent",
            "continuous_L2",
        )
    }
    pair["point_to_exposure_equivalent_gap"] = (
        pair["production_TE"] - pair["bucket_exposure_equivalent"]
    )
    pair["point_to_continuous_equivalent_gap"] = (
        pair["production_TE"] - pair["continuous_exposure_equivalent"]
    )
    result: dict[str, Any] = {
        "fingerprint": fingerprint,
        "authority": authority,
        "directions": dict(directions),
        "pair": pair,
        "fleet_required": fleet_required,
    }
    if operational_pair is not None:
        result["operations"] = {
            "average_passenger_wait_minutes": (
                operational_pair.metrics.demand_weighted_expected_passenger_wait_minutes
            ),
            "maximum_bucket_wait_minutes": (
                operational_pair.metrics.maximum_bucket_expected_wait_minutes
            ),
            "maximum_directional_p90_bucket_wait_minutes": (
                operational_pair.metrics.maximum_directional_p90_bucket_wait_minutes
            ),
            "actual_service_regime_count": operational_pair.metrics.actual_service_regime_count,
            "sustained_headway_level_count": (
                operational_pair.metrics.total_directional_sustained_headway_level_count
            ),
        }
    return result


def _ranking_record(candidate: Mapping[str, Any]) -> dict[str, Any]:
    pair = candidate["pair"]
    return {
        "fingerprint": candidate["fingerprint"],
        "production_SSE": pair["production_SSE"],
        "production_TE": pair["production_TE"],
        "bucket_exposure_SSE": pair["bucket_exposure_SSE"],
        "bucket_exposure_equivalent": pair["bucket_exposure_equivalent"],
        "continuous_exposure_equivalent": pair["continuous_exposure_equivalent"],
        "fleet_required": candidate["fleet_required"],
    }


def _report_candidate(row: Mapping[str, Any], context: Any) -> dict[str, Any]:
    directions: dict[str, Any] = {}
    for direction in ("outbound", "inbound"):
        source = row[direction]
        operational = source["actual_service_metrics"]
        metrics = _direction_metrics(
            source["compile_variant"]["exact_departures"],
            _normalized_buckets(context, direction),
        )
        if not math.isclose(
            metrics["production_SSE"],
            float(operational["observed_demand_mismatch"]),
            rel_tol=0.0,
            abs_tol=NUMERICAL_EPSILON,
        ):
            raise RuntimeError("preserved report production SSE reproduction mismatch")
        rhythm = operational["rhythm_simplicity"]
        metrics["operations"] = {
            "average_passenger_wait_minutes": operational[
                "demand_weighted_expected_passenger_wait_minutes"
            ],
            "maximum_bucket_wait_minutes": operational["maximum_bucket_expected_wait_minutes"],
            "p90_bucket_wait_minutes": operational.get("p90_bucket_expected_wait_minutes"),
            "actual_service_regime_count": rhythm["actual_service_regime_count"],
            "sustained_headway_levels": rhythm["sustained_headway_levels"],
            "sustained_headway_level_count": rhythm["sustained_headway_level_count"],
            "tail_headway_minutes": operational["tail_headway_minutes"],
            "demand_response": {
                "canonical_DemandRegime_projections": operational[
                    "demand_response_regime_projections"
                ],
                "response_transitions": operational["demand_response_transitions"],
                "response_direction_accuracy": operational["demand_response_direction_accuracy"],
                "sqrt_response_deviation": operational["sqrt_seed_response_deviation"],
                "sqrt_demand_is_target": False,
            },
        }
        directions[direction] = metrics
    candidate = _pair_metrics(
        fingerprint=str(row["pair_fingerprint"]),
        authority="CURRENT_PRODUCTION_ACCESS_SAFE_FRONTIER",
        directions=directions,
        fleet_required=int(row["metrics"]["fleet_required"]),
    )
    pair_metrics = row["metrics"]
    candidate["operations"] = {
        "average_passenger_wait_minutes": pair_metrics[
            "demand_weighted_expected_passenger_wait_minutes"
        ],
        "maximum_bucket_wait_minutes": max(
            directions[direction]["operations"]["maximum_bucket_wait_minutes"]
            for direction in ("outbound", "inbound")
        ),
        "maximum_directional_p90_bucket_wait_minutes": None,
        "actual_service_regime_count": pair_metrics["actual_service_regime_count"],
        "sustained_headway_level_count": pair_metrics[
            "total_directional_sustained_headway_level_count"
        ],
    }
    return candidate


def _replay_route_once(
    *,
    repo_root: Path,
    artifact_root: Path,
    accepted_i: Mapping[str, Any],
    route_id: str,
    checkpoint_path: Path | None = None,
) -> tuple[Any, dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    workbook = repo_root / f"Engine_Input_MST_{route_id}_V3_MultiPeriod_Mar-Jul_2026.xlsx"
    context, seeds = coordinator.load_route_coordinator_inputs_v1(
        repo_root=artifact_root,
        route_id=route_id,
        workbook_path=workbook,
    )
    replay = coordinator.search_route_service_plans_v1(
        context=context,
        seeds=seeds,
        budget=FROZEN_BUDGET,
    )
    frontier = tuple(sorted(replay.pareto_frontier, key=lambda item: item.pair_fingerprint))

    # Fingerprints are the only replay fields read before the exact PR62-I lock passes.
    replay_fingerprints = tuple(item.pair_fingerprint for item in frontier)
    accepted_fingerprints = tuple(
        sorted(accepted_i["routes"][route_id]["deterministic_signature"]["i_pareto_fingerprints"])
    )
    if replay_fingerprints != accepted_fingerprints:
        raise RuntimeError(f"EVIDENCE_DRIFT: route {route_id} exact PR62-I frontier changed")
    if checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_payload = {
            "route_id": route_id,
            "status": replay.status,
            "search_budget": dataclasses.asdict(FROZEN_BUDGET),
            "PR62_I_fingerprints_validated_before_serialization": True,
            "pareto_frontier": [
                coordinator._pair_to_dict(index, item)  # noqa: SLF001
                for index, item in enumerate(frontier, start=1)
            ],
        }
        checkpoint_path.write_bytes(canonical_json_bytes(checkpoint_payload))

    scenario_access = {
        direction: coordinator.expected_passenger_wait_metrics_v1(
            context.scenario_b_departures[direction], context.demand_buckets[direction]
        )[1]
        for direction in ("outbound", "inbound")
    }
    snapshots = {
        item.pair_fingerprint: build_operational_selection_candidate_v2(
            context=context, candidate=item
        )
        for item in frontier
    }
    access_safe_items = []
    for item in frontier:
        snapshot = snapshots[item.pair_fingerprint]
        safe = snapshot.hard_feasible and all(
            float(getattr(snapshot, f"{direction}_maximum_bucket_expected_wait_minutes"))
            <= scenario_access[direction] + NUMERICAL_EPSILON
            for direction in ("outbound", "inbound")
        )
        if safe:
            access_safe_items.append(item)
    expected_access_safe = {"6": 41, "10": 7}[route_id]
    if len(access_safe_items) != expected_access_safe:
        raise RuntimeError(
            f"EVIDENCE_DRIFT: route {route_id} access-safe count "
            f"{len(access_safe_items)} != {expected_access_safe}"
        )

    candidates: dict[str, dict[str, Any]] = {}
    for item in access_safe_items:
        snapshot = snapshots[item.pair_fingerprint]
        directions = {}
        for direction in ("outbound", "inbound"):
            directional = getattr(item, direction)
            departures = directional.compile_variant.compilation.exact_departures
            directions[direction] = _direction_metrics(
                departures,
                _normalized_buckets(context, direction),
                operational_metrics=directional.metrics,
            )
            expected_te = float(getattr(snapshot, f"{direction}_trip_equivalent_error"))
            if not math.isclose(
                directions[direction]["production_TE"],
                expected_te,
                rel_tol=0.0,
                abs_tol=NUMERICAL_EPSILON,
            ):
                raise RuntimeError("production TE reproduction mismatch")
        candidates[item.pair_fingerprint] = _pair_metrics(
            fingerprint=item.pair_fingerprint,
            authority="CURRENT_PRODUCTION_ACCESS_SAFE_FRONTIER",
            directions=directions,
            fleet_required=item.metrics.fleet_required,
            operational_pair=item,
        )

    scenario_directions = {
        direction: _direction_metrics(
            context.scenario_b_departures[direction],
            _normalized_buckets(context, direction),
        )
        for direction in ("outbound", "inbound")
    }
    scenario_b = _pair_metrics(
        fingerprint=f"ROUTE_{route_id}_SCENARIO_B_CURRENT",
        authority="SCENARIO_B_CURRENT_TIMETABLE",
        directions=scenario_directions,
        fleet_required=None,
    )
    replay_record = {
        "route_id": route_id,
        "status": replay.status,
        "budget": dataclasses.asdict(FROZEN_BUDGET),
        "pareto_count": len(frontier),
        "pareto_fingerprints": list(replay_fingerprints),
        "PR62_I_fingerprints": list(accepted_fingerprints),
        "fingerprints_validated_before_use": True,
        "access_safe_count": len(access_safe_items),
    }
    return context, candidates, scenario_b, replay_record


def _q_candidate(
    context: Any, q_evidence: Mapping[str, Any]
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    summaries = q_evidence["compiler_backed_census"]["hard_valid_candidate_summaries"]
    summary = next(row for row in summaries if row["pair_fingerprint"] == ROUTE10_Q_PAIR)
    directions: dict[str, Any] = {}
    for direction in ("outbound", "inbound"):
        source = summary["directions"][direction]
        metrics = _direction_metrics(
            source["exact_departures"], _normalized_buckets(context, direction)
        )
        metrics["operations"] = {
            "average_passenger_wait_minutes": source["average_passenger_wait_minutes"],
            "maximum_bucket_wait_minutes": source["maximum_bucket_wait_minutes"],
            "p90_bucket_wait_minutes": source["p90_bucket_wait_minutes"],
            "actual_service_regime_count": source["rhythm_simplicity"][
                "actual_service_regime_count"
            ],
            "sustained_headway_levels": source["rhythm_simplicity"]["sustained_headway_levels"],
            "sustained_headway_level_count": source["rhythm_simplicity"][
                "sustained_headway_level_count"
            ],
            "tail_headway_minutes": source["tail_headway_minutes"],
            "demand_response": {
                "canonical_DemandRegime_service_evidence": source["tail_ordering"][
                    "service_regime_demand_evidence"
                ],
                "response_direction_accuracy": None,
                "sqrt_response_deviation": None,
                "sqrt_demand_is_target": False,
                "availability_note": (
                    "Q evidence retains immutable DemandRegime rates and service-regime "
                    "frequency evidence; aggregate response fields were not re-inferred."
                ),
            },
        }
        directions[direction] = metrics
    candidate = _pair_metrics(
        fingerprint=ROUTE10_Q_PAIR,
        authority="Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE",
        directions=directions,
        fleet_required=summary["fleet_required"],
    )
    candidate["operations"] = {
        "average_passenger_wait_minutes": summary["average_passenger_wait_minutes"],
        "maximum_bucket_wait_minutes": max(
            summary["directional_access"][direction]["candidate_maximum_bucket_wait_minutes"]
            for direction in ("outbound", "inbound")
        ),
        "maximum_directional_p90_bucket_wait_minutes": max(
            summary["directional_access"][direction]["p90_bucket_wait_minutes"]
            for direction in ("outbound", "inbound")
        ),
        "actual_service_regime_count": summary["review_metrics"]["actual_service_regime_count"],
        "sustained_headway_level_count": summary["review_metrics"][
            "sustained_exact_headway_level_count"
        ],
        "micro_rhythm_boundary_count": summary["review_metrics"]["micro_rhythm_boundary_count"],
        "rhythm_tuple": {
            "outbound": [
                regime["uniform_headway_minutes"]
                for regime in summary["directions"]["outbound"]["service_regimes"]
            ],
            "inbound": [
                regime["uniform_headway_minutes"]
                for regime in summary["directions"]["inbound"]["service_regimes"]
            ],
        },
    }
    if not math.isclose(
        candidate["pair"]["production_SSE"],
        summary["observed_demand_SSE"],
        rel_tol=0.0,
        abs_tol=NUMERICAL_EPSILON,
    ) or not math.isclose(
        candidate["pair"]["production_TE"],
        summary["pair_trip_equivalent_error"],
        rel_tol=0.0,
        abs_tol=NUMERICAL_EPSILON,
    ):
        raise RuntimeError("Q production demand-fit authority reproduction mismatch")
    return candidate, summary


def _enrich_p_operations(
    p_candidate: dict[str, Any],
    p_product: Mapping[str, Any],
    q_evidence: Mapping[str, Any],
) -> None:
    route = p_product["routes"]["10"]
    q_route = q_evidence["routes"]["10"]
    p_candidate["operations"]["micro_rhythm_boundary_count"] = q_route["baseline_review_metrics"][
        "micro_rhythm_boundary_count"
    ]
    p_candidate["operations"]["rhythm_tuple"] = {
        direction: [
            regime["uniform_headway_minutes"]
            for regime in route["directions"][direction]["service_regimes"]
        ]
        for direction in ("outbound", "inbound")
    }
    for direction in ("outbound", "inbound"):
        product_metrics = route["directions"][direction]["metrics"]
        operations = p_candidate["directions"][direction]["operations"]
        operations["average_passenger_wait_minutes"] = product_metrics[
            "demand_weighted_expected_passenger_wait_minutes"
        ]
        operations["maximum_bucket_wait_minutes"] = product_metrics[
            "maximum_bucket_expected_wait_minutes"
        ]
        operations["p90_bucket_wait_minutes"] = product_metrics["p90_bucket_expected_wait_minutes"]
        p_candidate["directions"][direction]["operations"]["micro_rhythm_boundary_count"] = sum(
            family["micro_rhythm_boundary_count"]
            for family in q_route["local_rhythm_families"][direction]
        )
    p_candidate["operations"]["maximum_directional_p90_bucket_wait_minutes"] = max(
        route["directions"][direction]["metrics"]["p90_bucket_expected_wait_minutes"]
        for direction in ("outbound", "inbound")
    )


def _metric_differences(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> dict[str, dict[str, float]]:
    keys = (
        "production_SSE",
        "production_TE",
        "bucket_exposure_SSE",
        "bucket_exposure_equivalent",
        "continuous_exposure_TV",
        "continuous_exposure_equivalent",
        "continuous_L2",
    )
    return {
        "outbound": {
            key: float(right["directions"]["outbound"][key])
            - float(left["directions"]["outbound"][key])
            for key in keys
        },
        "inbound": {
            key: float(right["directions"]["inbound"][key])
            - float(left["directions"]["inbound"][key])
            for key in keys
        },
        "pair": {key: float(right["pair"][key]) - float(left["pair"][key]) for key in keys},
    }


def _bucket_contribution_audit(
    p_candidate: Mapping[str, Any],
    q_candidate: Mapping[str, Any],
    *,
    left_label: str = "P",
    right_label: str = "Q",
) -> dict[str, Any]:
    directions: dict[str, Any] = {}
    delta_key = f"{right_label}_minus_{left_label}_production_TE_contribution"
    for direction in ("outbound", "inbound"):
        p = p_candidate["directions"][direction]
        q = q_candidate["directions"][direction]
        p_point = p["point"]
        q_point = q["point"]
        p_exposure = p["bucket_exposure"]["buckets"]
        q_exposure = q["bucket_exposure"]["buckets"]
        rows = []
        for index, (p_exp, q_exp) in enumerate(zip(p_exposure, q_exposure, strict=True)):
            p_residual = p_point["residuals"][index]
            q_residual = q_point["residuals"][index]
            p_exposure_residual = p_exp["residual"]
            q_exposure_residual = q_exp["residual"]
            p_te_contribution = 0.5 * p["trip_count"] * abs(p_residual)
            q_te_contribution = 0.5 * q["trip_count"] * abs(q_residual)
            rows.append(
                {
                    "bucket_index": index,
                    "start_seconds": int(p_exp["start"]),
                    "end_seconds": int(p_exp["end"]),
                    "demand_share": p_exp["demand_share"],
                    f"production_discrete_service_share_{left_label}": p_point["service_shares"][
                        index
                    ],
                    f"production_discrete_service_share_{right_label}": q_point["service_shares"][
                        index
                    ],
                    f"bucket_exposure_share_{left_label}": p_exp["service_share"],
                    f"bucket_exposure_share_{right_label}": q_exp["service_share"],
                    f"production_squared_residual_{left_label}": p_residual**2,
                    f"production_squared_residual_{right_label}": q_residual**2,
                    f"production_absolute_residual_{left_label}": abs(p_residual),
                    f"production_absolute_residual_{right_label}": abs(q_residual),
                    f"exposure_squared_residual_{left_label}": p_exposure_residual**2,
                    f"exposure_squared_residual_{right_label}": q_exposure_residual**2,
                    f"exposure_absolute_residual_{left_label}": abs(p_exposure_residual),
                    f"exposure_absolute_residual_{right_label}": abs(q_exposure_residual),
                    f"production_TE_contribution_{left_label}": p_te_contribution,
                    f"production_TE_contribution_{right_label}": q_te_contribution,
                    delta_key: q_te_contribution - p_te_contribution,
                }
            )
        ranked = sorted(
            rows,
            key=lambda row: (
                -abs(row[delta_key]),
                row["bucket_index"],
            ),
        )
        directions[direction] = {"buckets": rows, "top_contributors": ranked[:10]}
    return {
        "ranking_basis": (
            f"abs({right_label} production TE contribution - "
            f"{left_label} production TE contribution)"
        ),
        "directions": directions,
    }


def _format_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds_remainder = divmod(remainder, 60)
    return (
        f"{hours:02d}:{minutes:02d}"
        if seconds_remainder == 0
        else f"{hours:02d}:{minutes:02d}:{seconds_remainder:02d}"
    )


def _serialized_departure_audit(
    p_candidate: Mapping[str, Any],
    q_candidate: Mapping[str, Any],
    contexts: Mapping[str, Any],
) -> dict[str, Any]:
    directions = {}
    aggregate = {
        "total_departures_changed": 0,
        "bucket_changing_departures": 0,
        "total_bucket_boundary_crossings": 0,
    }
    for direction in ("outbound", "inbound"):
        buckets = _normalized_buckets(contexts["10"], direction)
        audit = departure_edge_crossing_audit(
            p_candidate["directions"][direction]["exact_departures"],
            q_candidate["directions"][direction]["exact_departures"],
            buckets,
        )
        for row in audit["changed_departures"]:
            row["P_time"] = _format_time(row["P_time_seconds"])
            row["Q_time"] = _format_time(row["Q_time_seconds"])
            row["crossed_immutable_bucket_boundaries"] = [
                _format_time(value) for value in row["crossed_bucket_boundaries_seconds"]
            ]
            for prefix in ("P", "Q"):
                index = row[f"{prefix}_bucket_index"]
                row[f"{prefix}_production_demand_bucket"] = (
                    None
                    if index is None
                    else {
                        "index": index,
                        "start": _format_time(int(buckets[index]["start"])),
                        "end": _format_time(int(buckets[index]["end"])),
                    }
                )
        directions[direction] = audit
        for key in aggregate:
            aggregate[key] += audit[key]
    return {"pair_aggregate": aggregate, "directions": directions}


def _comparison_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    directions = {}
    for direction in ("outbound", "inbound"):
        source = candidate["directions"][direction]
        directions[direction] = {
            key: source[key]
            for key in (
                "trip_count",
                "production_SSE",
                "production_TV",
                "production_TE",
                "bucket_exposure_SSE",
                "bucket_exposure_TV",
                "bucket_exposure_equivalent",
                "continuous_exposure_TV",
                "continuous_exposure_equivalent",
                "continuous_L2",
                "point_to_exposure_TV_gap",
                "point_to_continuous_equivalent_gap",
                "operations",
            )
            if key in source
        }
    return {
        "fingerprint": candidate["fingerprint"],
        "authority": candidate["authority"],
        "fleet_required": candidate["fleet_required"],
        "pair": dict(candidate["pair"]),
        "directions": directions,
        "operations": dict(candidate.get("operations", {})),
    }


def _deficit_effect(production_penalty: float, diagnostic_penalty: float) -> str:
    if production_penalty > NUMERICAL_EPSILON and diagnostic_penalty < -NUMERICAL_EPSILON:
        return "reverses"
    if abs(diagnostic_penalty) <= NUMERICAL_EPSILON:
        return "disappears"
    if diagnostic_penalty < production_penalty - NUMERICAL_EPSILON:
        return "decreases"
    if diagnostic_penalty > production_penalty + NUMERICAL_EPSILON:
        return "increases"
    return "unchanged_within_numerical_epsilon"


def _next_milestone(root: str, anchor_stable: bool) -> tuple[str, str]:
    if root == "BUCKET_EDGE_ALIASING_CONFIRMED":
        return (
            "PR62-S_PHASE_ROBUST_DEMAND_FIT_POLICY_EXPERIMENT",
            "materiality metric only" if anchor_stable else "both anchor and materiality",
        )
    if root == "BUCKET_EDGE_ALIASING_MATERIAL_BUT_NOT_DECISIVE":
        return "PR62-S_DEMAND_FIT_SEMANTICS_POLICY_REVIEW", "policy semantics review"
    if root == "DEMAND_FIT_LOSS_PERSISTS_UNDER_CONTINUOUS_EXPOSURE":
        return (
            "PR62-S_EXPLICIT_RHYTHM_VS_DEMAND_FIT_POLICY_REVIEW",
            "explicit domain tradeoff review",
        )
    if root == "MIXED_DEMAND_FIT_METRIC_EVIDENCE":
        return (
            "PR62-S_BOUNDED_DEMAND_FIT_CALIBRATION",
            "bounded calibration before policy mutation",
        )
    return "PR62-S_R_EVIDENCE_BLOCKER_RESOLUTION", "resolve evidence blockers only"


def build_evidence(repo_root: Path) -> dict[str, Any]:
    if dataclasses.astuple(FROZEN_BUDGET) != (24, 512, 4, 24, 512):
        raise RuntimeError("frozen coordinator budget changed")
    immutable_locks = _verify_immutable_locks(repo_root)
    q_evidence = _load_json(repo_root, Q_EVIDENCE)
    p_product = _load_json(repo_root, P_PRODUCT_DATA)
    accepted_i = _load_json(repo_root, pr62_i.OUTPUT_JSON)
    o_evidence = _load_json(repo_root, O_EVIDENCE)
    artifact_root = pr62_i._artifact_root(repo_root)
    coordinator.verify_frozen_prior_artifacts_v1(artifact_root)

    contexts: dict[str, Any] = {}
    candidate_sets: dict[str, dict[str, dict[str, Any]]] = {}
    scenarios: dict[str, dict[str, Any]] = {}
    replay_records: dict[str, dict[str, Any]] = {}
    calls_by_route = {"6": 2, "10": 1}

    # Authorized recovery: Route 6 only, with an immediate validated checkpoint.
    context6, candidates6, scenario6, replay6 = _replay_route_once(
        repo_root=repo_root,
        artifact_root=artifact_root,
        accepted_i=accepted_i,
        route_id="6",
        checkpoint_path=repo_root / ROUTE6_RECOVERY_CHECKPOINT,
    )
    contexts["6"] = context6
    candidate_sets["6"] = candidates6
    scenarios["6"] = scenario6
    replay_records["6"] = replay6

    # Route 10 is reconstructed from two preserved byte-identical reports; no replay.
    context10, _seeds10 = coordinator.load_route_coordinator_inputs_v1(
        repo_root=artifact_root,
        route_id="10",
        workbook_path=repo_root / "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    expected10 = accepted_i["routes"]["10"]["deterministic_signature"]["i_pareto_fingerprints"]
    preserved10, preserved10_provenance = load_preserved_frontier_reports(
        repo_root / ROUTE10_PRESERVED_REPORTS[0],
        repo_root / ROUTE10_PRESERVED_REPORTS[1],
        expected_fingerprints=expected10,
    )
    safe10 = {
        str(row["fingerprint"])
        for row in o_evidence["routes"]["10"]["candidate_audit"]
        if row["scenario_b_directional_max_access_safe"]
    }
    if len(safe10) != 7:
        raise RuntimeError("Route 10 O authority access-safe count changed")
    candidates10 = {
        str(row["pair_fingerprint"]): _report_candidate(row, context10)
        for row in preserved10
        if str(row["pair_fingerprint"]) in safe10
    }
    if set(candidates10) != safe10:
        raise RuntimeError("Route 10 preserved report access-safe frontier mismatch")
    o10_by_fingerprint = {
        str(row["fingerprint"]): row for row in o_evidence["routes"]["10"]["candidate_audit"]
    }
    for fingerprint, candidate in candidates10.items():
        authority = o10_by_fingerprint[fingerprint]
        if not math.isclose(
            candidate["pair"]["production_SSE"],
            float(authority["observed_demand_mismatch"]),
            rel_tol=0.0,
            abs_tol=NUMERICAL_EPSILON,
        ) or not math.isclose(
            candidate["pair"]["production_TE"],
            float(authority["pair_trip_equivalent_error"]),
            rel_tol=0.0,
            abs_tol=NUMERICAL_EPSILON,
        ):
            raise RuntimeError("Route 10 preserved report disagrees with O demand-fit authority")
    contexts["10"] = context10
    candidate_sets["10"] = candidates10
    scenario10_directions = {
        direction: _direction_metrics(
            context10.scenario_b_departures[direction],
            _normalized_buckets(context10, direction),
        )
        for direction in ("outbound", "inbound")
    }
    scenarios["10"] = _pair_metrics(
        fingerprint="ROUTE_10_SCENARIO_B_CURRENT",
        authority="SCENARIO_B_CURRENT_TIMETABLE",
        directions=scenario10_directions,
        fleet_required=None,
    )
    replay_records["10"] = {
        "route_id": "10",
        "source": "TWO_PRESERVED_BYTE_IDENTICAL_COORDINATOR_REPORTS",
        "pareto_count": len(preserved10),
        "pareto_fingerprints": sorted(str(row["pair_fingerprint"]) for row in preserved10),
        "PR62_I_fingerprints": sorted(str(value) for value in expected10),
        "fingerprints_validated_before_use": True,
        "access_safe_count": len(candidates10),
        **preserved10_provenance,
    }

    route_payloads: dict[str, Any] = {}
    audits: dict[str, Any] = {}
    for route_id in ("6", "10"):
        product_route = p_product["routes"][route_id]
        selected = product_route["selected_pair_fingerprint"]
        anchor = product_route["common_anchor_fingerprint"]
        candidates = candidate_sets[route_id]
        if selected not in candidates or anchor not in candidates:
            raise RuntimeError(f"route {route_id} P selected/anchor lock not access-safe")
        audit = ranking_audit(
            [_ranking_record(value) for value in candidates.values()],
            anchor_fingerprint=anchor,
            selected_fingerprint=selected,
        )
        audits[route_id] = audit
        route_payloads[route_id] = {
            "candidate_universe": "CURRENT_PRODUCTION_ACCESS_SAFE_FRONTIER",
            "production_candidate_count": len(candidates),
            "production_fingerprints": sorted(candidates),
            "common_anchor_fingerprint": anchor,
            "selected_fingerprint": selected,
            **audit,
        }

    route10_product = p_product["routes"]["10"]
    if route10_product["selected_pair_fingerprint"] != ROUTE10_P_PAIR:
        raise RuntimeError("Route 10 P selected fingerprint changed")
    if route10_product["common_anchor_fingerprint"] != ROUTE10_ANCHOR:
        raise RuntimeError("Route 10 common anchor fingerprint changed")
    p_candidate = candidate_sets["10"][ROUTE10_P_PAIR]
    anchor_candidate = candidate_sets["10"][ROUTE10_ANCHOR]
    _enrich_p_operations(p_candidate, p_product, q_evidence)
    q_candidate, q_summary = _q_candidate(contexts["10"], q_evidence)

    extended_records = [
        *(_ranking_record(value) for value in candidate_sets["10"].values()),
        _ranking_record(q_candidate),
    ]
    extended_audit = ranking_audit(
        extended_records,
        anchor_fingerprint=ROUTE10_ANCHOR,
        selected_fingerprint=ROUTE10_P_PAIR,
    )
    q_external_ranks = next(
        row["ranks"]
        for row in extended_audit["ranking_table"]
        if row["fingerprint"] == ROUTE10_Q_PAIR
    )
    route_payloads["10"]["Q_external_review_ranks_among_frontier_plus_Q"] = q_external_ranks
    route_payloads["10"]["Q_rank_universe_count"] = len(extended_records)

    p_vs_q_differences = _metric_differences(p_candidate, q_candidate)
    route10_disagreements = audits["10"]["pairwise_rank_disagreement_counts"]
    decision = classify_p_vs_q(
        p_production_te=p_candidate["pair"]["production_TE"],
        q_production_te=q_candidate["pair"]["production_TE"],
        p_bucket_equivalent=p_candidate["pair"]["bucket_exposure_equivalent"],
        q_bucket_equivalent=q_candidate["pair"]["bucket_exposure_equivalent"],
        p_continuous_equivalent=p_candidate["pair"]["continuous_exposure_equivalent"],
        q_continuous_equivalent=q_candidate["pair"]["continuous_exposure_equivalent"],
        production_vs_bucket_rank_disagreements=route10_disagreements[
            "production_TE_vs_bucket_exposure_equivalent"
        ],
        production_vs_continuous_rank_disagreements=route10_disagreements[
            "production_TE_vs_continuous_exposure_equivalent"
        ],
    )
    root_classification = decision["root_classification"]

    route10_best = audits["10"]["best_sets"]
    anchor_semantics = {
        "production_SSE_best": ROUTE10_ANCHOR in route10_best["production_SSE"],
        "production_TE_best": ROUTE10_ANCHOR in route10_best["production_TE"],
        "bucket_exposure_best": ROUTE10_ANCHOR in route10_best["bucket_exposure_equivalent"],
        "continuous_exposure_best": ROUTE10_ANCHOR
        in route10_best["continuous_exposure_equivalent"],
    }
    anchor_stable = all(anchor_semantics.values())
    anchor_validity = {
        "fingerprint": ROUTE10_ANCHOR,
        **anchor_semantics,
        "classification": (
            "ANCHOR_STABLE_ACROSS_DEMAND_FIT_SEMANTICS"
            if anchor_stable
            else "ANCHOR_SEMANTICS_SENSITIVE"
        ),
    }

    route6_product = p_product["routes"]["6"]
    route6_anchor = route6_product["common_anchor_fingerprint"]
    route6_best = audits["6"]["best_sets"]
    route6_top = {
        "production_SSE_best": route6_best["production_SSE"],
        "production_TE_best": route6_best["production_TE"],
        "bucket_exposure_best": route6_best["bucket_exposure_equivalent"],
        "continuous_exposure_best": route6_best["continuous_exposure_equivalent"],
    }
    route6_anchor_stable = all(
        route6_anchor in fingerprints for fingerprints in route6_top.values()
    )
    route6_control = {
        "anchor_fingerprint": route6_anchor,
        "selected_fingerprint": route6_product["selected_pair_fingerprint"],
        **route6_top,
        "pairwise_rank_disagreement_counts": audits["6"]["pairwise_rank_disagreement_counts"],
        "selected_ranks": audits["6"]["selected_ranks"],
        "top_anchor_changes": not route6_anchor_stable,
        "classification": (
            "ROUTE6_CONTROL_TOP_STABLE"
            if route6_anchor_stable
            else "ROUTE6_CONTROL_TOP_SEMANTICS_SENSITIVE"
        ),
    }

    recommendation, s_scope = _next_milestone(root_classification, anchor_stable)
    production_penalty = p_vs_q_differences["pair"]["production_TE"]
    bucket_penalty = p_vs_q_differences["pair"]["bucket_exposure_equivalent"]
    continuous_penalty = p_vs_q_differences["pair"]["continuous_exposure_equivalent"]
    anchor_differences = _metric_differences(anchor_candidate, q_candidate)["pair"]

    payload: dict[str, Any] = {
        "milestone": "PR62-R",
        "Q_commit_SHA": Q_COMMIT_SHA,
        "Q_evidence_lock": {
            "json": immutable_lock_record(immutable_locks, Q_EVIDENCE),
            "markdown": immutable_lock_record(
                immutable_locks,
                "docs/engine/evidence/PR62_Q_LOCAL_RHYTHM_CANONICALIZATION.md",
            ),
        },
        "P_workbook_locks": {
            "6": immutable_locks["outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx"],
            "10": immutable_locks["outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx"],
        },
        "READY_FOR_PR62_COMPLETION_REVIEW": False,
        "READY_FOR_FINAL_PILOT_USE": False,
        "metric_definitions": {
            "production_discrete_service_share": ("bucket_service_count / total_directional_trips"),
            "production_demand_share": "observed_demand / total_directional_demand",
            "production_SSE": "sum((discrete_service_share - demand_share)^2)",
            "production_directional_TV": ("0.5 * sum(abs(discrete_service_share - demand_share))"),
            "production_directional_TE": "directional_trips * production_directional_TV",
            "production_pair_TE": "outbound_TE + inbound_TE",
            "bucket_exposure": (
                "sum(overlap_seconds(bucket, interdeparture_interval) / interdeparture_seconds)"
            ),
            "bucket_exposure_equivalent": (
                "directional_trips * bucket_exposure_TV; review-only and not production TE"
            ),
            "continuous_exposure_TV": (
                "0.5 * exact integral abs(normalized service intensity - normalized "
                "demand density) over union breakpoints"
            ),
            "continuous_exposure_equivalent": (
                "directional_trips * continuous_exposure_TV; review-only and not production TE"
            ),
            "continuous_L2": (
                "analysis_duration * exact integral squared normalized-density difference"
            ),
        },
        "metric_authority": {
            "production_point_metrics": "unchanged production authority",
            "production_point_metrics_changed": False,
            "bucket_exposure_metrics": "PR62-R review-only diagnostic",
            "continuous_exposure_metrics": "PR62-R review-only diagnostic",
            "continuous_metrics_added_to_production": False,
            "why_metrics_differ": (
                "Point counts assign an entire departure to one half-open bucket; exposure "
                "metrics fractionally integrate sustained frequency across exact time."
            ),
        },
        "candidate_universe": {
            "production": {
                "authority": "CURRENT_PRODUCTION_ACCESS_SAFE_FRONTIER",
                "route_10_count": 7,
                "route_6_count": 41,
            },
            "Q_canonical": {
                "fingerprint": ROUTE10_Q_PAIR,
                "authority": "Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE",
                "compiler_backed": True,
                "hard_valid": True,
                "access_safe": True,
                "production_Pareto_relevant": q_summary["production_pareto_audit"][
                    "pareto_relevant"
                ],
                "currently_in_production_frontier": False,
            },
        },
        "replay_provenance": {
            "route_6": {
                "attempts": 2,
                "recovery_replay_authorized": True,
                "first_attempt_search_completed": True,
                "first_attempt_postprocessing_lost": True,
                "failure_stage": "WINDOWS_PATH_NORMALIZATION_POSTPROCESSING",
                "recovery_scope": "ROUTE_6_ONLY_COMPLETE_ACCESS_SAFE_AUDIT",
                "recovery_replay_fingerprints_match_PR62_I": replay_records["6"][
                    "fingerprints_validated_before_use"
                ],
                "same_frozen_inputs_code_seed_and_budget": True,
            },
            "route_10": {
                "attempts": 1,
                "recovery_replay_authorized": False,
                "recovery_replay_executed": False,
                "evidence_source": "TWO_PRESERVED_BYTE_IDENTICAL_COORDINATOR_REPORTS",
                "preserved_report_count": 2,
                "reports_byte_identical": preserved10_provenance["reports_byte_identical"],
                "preserved_report_sha256": preserved10_provenance["report_sha256"],
                "preserved_reports_match_PR62_I": preserved10_provenance[
                    "fingerprints_match_PR62_I"
                ],
                "current_R_attempt_search_completed": True,
                "current_R_attempt_postprocessing_lost": True,
            },
            "route_6_recovery_necessity": (
                "Preserved attempt-1 reports predated the exact current PR62-I Route 6 "
                "frontier and omitted access-safe candidate "
                "e5e3545595252a70a44f571d0356dfae0e7889caed3e3db7ec94cce7bfc21bf4; "
                "therefore they could not reconstruct the required complete 41-candidate "
                "control audit. The authorized replay is recovery only, not sensitivity "
                "analysis, calibration, or additional optimization evidence."
            ),
        },
        "coordinator_replay": {
            "reason": (
                "Exact departures were not serialized for every access-safe production "
                "candidate in committed evidence. Route 6 attempt 2 is an authorized "
                "post-processing recovery only; Route 10 was not replayed for recovery."
            ),
            "calls_by_route": {"10": calls_by_route["10"], "6": calls_by_route["6"]},
            "fingerprints_validated_before_use": all(
                record["fingerprints_validated_before_use"] for record in replay_records.values()
            ),
            "routes": replay_records,
        },
        "routes": route_payloads,
        "central_route10_comparison": {
            "Scenario_B_current": _comparison_summary(scenarios["10"]),
            "V2_common_anchor": _comparison_summary(anchor_candidate),
            "P_selected": _comparison_summary(p_candidate),
            "Q_canonical": _comparison_summary(q_candidate),
        },
        "route10_P_vs_Q": {
            "P_fingerprint": ROUTE10_P_PAIR,
            "Q_fingerprint": ROUTE10_Q_PAIR,
            "P": _comparison_summary(p_candidate),
            "Q": _comparison_summary(q_candidate),
            "Q_minus_P": p_vs_q_differences,
            "decision_states": decision,
            "apparent_Q_deficit_effect": {
                "bucket_exposure_equivalent": _deficit_effect(production_penalty, bucket_penalty),
                "continuous_exposure_equivalent": _deficit_effect(
                    production_penalty, continuous_penalty
                ),
            },
        },
        "route10_anchor_vs_Q": {
            "anchor_fingerprint": ROUTE10_ANCHOR,
            "Q_fingerprint": ROUTE10_Q_PAIR,
            "Q_minus_anchor": {
                "production_TE": anchor_differences["production_TE"],
                "bucket_exposure_equivalent": anchor_differences["bucket_exposure_equivalent"],
                "continuous_exposure_equivalent": anchor_differences[
                    "continuous_exposure_equivalent"
                ],
            },
        },
        "bucket_edge_contribution_audit": {
            **_bucket_contribution_audit(p_candidate, q_candidate),
            "anchor_vs_Q": _bucket_contribution_audit(
                anchor_candidate,
                q_candidate,
                left_label="anchor",
                right_label="Q",
            ),
        },
        "departure_edge_crossing_audit": _serialized_departure_audit(
            p_candidate, q_candidate, contexts
        ),
        "anchor_validity": anchor_validity,
        "route6_control": route6_control,
        "root_classification": root_classification,
        "next_milestone_recommendation": recommendation,
        "next_milestone_scope": s_scope,
        "production_guards": dict(EXPECTED_PRODUCTION_GUARDS),
        "immutable_file_locks": immutable_locks,
        "deterministic_render": {
            "json_rendered_twice_byte_identically": True,
            "markdown_rendered_twice_byte_identically": True,
        },
    }
    return payload


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.12f}"
    return str(value)


def _inline_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_markdown(payload: Mapping[str, Any]) -> str:
    route10 = payload["routes"]["10"]
    route6 = payload["routes"]["6"]
    tradeoff = payload["route10_P_vs_Q"]
    pair_delta = tradeoff["Q_minus_P"]["pair"]
    edge = payload["departure_edge_crossing_audit"]["pair_aggregate"]
    anchor = payload["anchor_validity"]
    top_buckets = []
    for direction in ("outbound", "inbound"):
        for row in payload["bucket_edge_contribution_audit"]["directions"][direction][
            "top_contributors"
        ][:3]:
            top_buckets.append(
                (
                    direction,
                    row["bucket_index"],
                    row["start_seconds"],
                    row["end_seconds"],
                    row["Q_minus_P_production_TE_contribution"],
                )
            )
    lines = [
        "# PR62-R — Demand-fit metric validity review",
        "",
        f"Root classification: **{payload['root_classification']}**.",
        "",
        "Production point-count SSE/TE remain unchanged. Bucket exposure and exact continuous exposure are review-only diagnostics; neither is production TE.",
        "",
        "## Metric definitions",
        "",
        "- Production: whole departures are assigned to half-open immutable demand buckets; directional TE is trips × TV.",
        "- Bucket exposure: each complete interdeparture exposure unit is fractionally split by exact overlap with immutable demand buckets.",
        "- Continuous exposure: normalized service and demand densities are integrated exactly over the union of demand boundaries and departures.",
        "",
        "## Route 10 ranking",
        "",
        f"Production access-safe candidates: `{route10['production_candidate_count']}`.",
    ]
    for metric in METRIC_KEYS:
        lines.append(
            f"- {metric}: best `{', '.join(route10['best_sets'][metric])}`; anchor rank `{route10['anchor_ranks'][metric]}`; P rank `{route10['selected_ranks'][metric]}`; Q external-review rank `{route10['Q_external_review_ranks_among_frontier_plus_Q'][metric]}` among frontier plus Q."
        )
    lines.extend(
        [
            f"- Pairwise disagreements: `{_inline_json(route10['pairwise_rank_disagreement_counts'])}`.",
            "",
            "## P versus Q",
            "",
            f"P `{tradeoff['P_fingerprint']}` versus Q `{tradeoff['Q_fingerprint']}`.",
        ]
    )
    for metric in (
        "production_SSE",
        "production_TE",
        "bucket_exposure_SSE",
        "bucket_exposure_equivalent",
        "continuous_exposure_TV",
        "continuous_exposure_equivalent",
        "continuous_L2",
    ):
        lines.append(f"- Q − P {metric}: `{_fmt(pair_delta[metric])}`.")
    lines.extend(
        [
            f"- Deficit effect: `{_inline_json(tradeoff['apparent_Q_deficit_effect'])}`.",
            f"- Exact decision states: `{_inline_json(tradeoff['decision_states'])}`.",
            "",
            "## Bucket-edge audit",
            "",
            f"Changed departures `{edge['total_departures_changed']}`; bucket-changing departures `{edge['bucket_changing_departures']}`; crossed immutable boundaries `{edge['total_bucket_boundary_crossings']}`.",
            "",
            "Top production-TE contribution changes:",
            "",
        ]
    )
    for direction, index, start, end, delta in sorted(
        top_buckets, key=lambda item: (-abs(item[4]), item[0], item[1])
    ):
        lines.append(
            f"- {direction} bucket {index} `{_format_time(start)}–{_format_time(end)}`: Q − P contribution `{_fmt(delta)}`."
        )
    lines.extend(
        [
            "",
            "## Anchor validity",
            "",
            f"`{anchor['classification']}` with states `{_inline_json(anchor)}`.",
            "",
            "## Route 6 control",
            "",
            f"Candidates `{route6['production_candidate_count']}`; `{payload['route6_control']['classification']}`; disagreements `{_inline_json(route6['pairwise_rank_disagreement_counts'])}`.",
            "",
            "## Next milestone",
            "",
            f"Recommend **{payload['next_milestone_recommendation']}** with scope **{payload['next_milestone_scope']}**. No policy or threshold change is implemented in R.",
            "",
            "## Readiness and guards",
            "",
            "`READY_FOR_PR62_COMPLETION_REVIEW = false` and `READY_FOR_FINAL_PILOT_USE = false`.",
            "",
            "All production guards are `false` (NO change), canonical XLSX files remain hash-locked, and PR62-Q/P authorities remain immutable.",
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence(repo_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    json_first = canonical_json_bytes(payload)
    json_second = canonical_json_bytes(payload)
    markdown_first = render_markdown(payload).encode("utf-8")
    markdown_second = render_markdown(payload).encode("utf-8")
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("evidence render is not byte-deterministic")
    json_path = repo_root / OUTPUT_JSON
    markdown_path = repo_root / OUTPUT_MARKDOWN
    json_path.write_bytes(json_first)
    markdown_path.write_bytes(markdown_first)
    if json_path.stat().st_size >= 1_000_000:
        raise RuntimeError("PR62-R JSON evidence exceeds 1 MB")
    return {
        "json": {
            "path": str(OUTPUT_JSON).replace("\\", "/"),
            "bytes": len(json_first),
            "sha256": hashlib.sha256(json_first).hexdigest(),
        },
        "markdown": {
            "path": str(OUTPUT_MARKDOWN).replace("\\", "/"),
            "bytes": len(markdown_first),
            "sha256": hashlib.sha256(markdown_first).hexdigest(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    payload = build_evidence(repo_root)
    outputs = write_evidence(repo_root, payload)
    _verify_immutable_locks(repo_root)
    print(json.dumps(outputs, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

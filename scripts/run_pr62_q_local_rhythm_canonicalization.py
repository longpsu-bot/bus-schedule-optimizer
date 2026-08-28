"""Audit local passenger-facing rhythm canonicalization without production changes."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT / "src", _REPO_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import run_pr62_i_worst_bucket_passenger_access as pr62_i  # noqa: E402

from bus_schedule_engine import service_plan_coordinator as coordinator  # noqa: E402
from bus_schedule_engine.contracts_v1.clean_compile_frontier import (  # noqa: E402
    compile_service_plan_frontier_v1,
)
from bus_schedule_engine.contracts_v1.closed_loop_service_protection import (  # noqa: E402
    validate_closed_loop_service_protection_v1,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy import (  # noqa: E402
    NUMERICAL_EPSILON,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy_v2 import (  # noqa: E402
    directional_trip_equivalent_error_v2,
)
from bus_schedule_engine.contracts_v1.service_plan_state import (  # noqa: E402
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    service_plan_fingerprint_v1,
    validate_service_plan_state_v1,
)

P_COMMIT_SHA = "01614f98c7cc53c3098ac37bbf1e3c82634f1a84"
ROUTE10_P_PAIR = "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24"
P_PRODUCT_DATA = Path("outputs/final_pilot/PR62_P_FINAL_PILOT_DATA.json")
P_EVIDENCE = Path("docs/engine/evidence/PR62_P_FINAL_XLSX_RECERTIFICATION.json")
I_EVIDENCE = Path("docs/engine/evidence/PR62_I_WORST_BUCKET_PASSENGER_ACCESS.json")
O_EVIDENCE = Path("docs/engine/evidence/PR62_O_PRODUCTION_POLICY_FREEZE.json")
E_ROUTE10_EVIDENCE = Path("docs/engine/evidence/PR62_E_ROUTE10_CLOSED_LOOP_PILOT.json")
OUTPUT_JSON = Path("docs/engine/evidence/PR62_Q_LOCAL_RHYTHM_CANONICALIZATION.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_Q_LOCAL_RHYTHM_CANONICALIZATION.md")

WORKBOOK_LOCKS = {
    "6": (
        Path("outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx"),
        "13454026722f996d8b06e5305b3b6ab2d57ea6126734f4deeb23c3e7dbafd02c",
    ),
    "10": (
        Path("outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx"),
        "d84dd2e873d3ba30275463a5eff67277a22467839af0f0125e69160a891fc3db",
    ),
}

PRODUCTION_FILE_LOCKS = {
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
    "src/bus_schedule_engine/clean_boundary_pilot.py": (
        "1b17298d31ed308da058ba213748c23b7a76f8902c3abcef20715d5ca1a99fd9"
    ),
}

EXPECTED_PRODUCTION_GUARDS = {
    "production_search_changed": False,
    "search_budget_changed": False,
    "queue_changed": False,
    "10_D_Pareto_changed": False,
    "compiler_changed": False,
    "boundary_semantics_changed": False,
    "settlement_or_residual_added": False,
    "tail_semantics_changed": False,
    "protection_changed": False,
    "access_changed": False,
    "SSE_changed": False,
    "TE_changed": False,
    "V2_selector_changed": False,
    "fleet_validator_changed": False,
    "canonical_XLSX_regenerated": False,
    "route_6_timetable_changed": False,
    "route_10_canonical_workbook_changed": False,
    "private_workbook_opened": False,
    "private_workbook_committed": False,
}

PRODUCTION_DIMENSIONS = (
    "observed_demand_mismatch",
    "demand_weighted_expected_passenger_wait_minutes",
    "maximum_bucket_expected_wait_minutes",
    "actual_service_regime_count",
    "total_directional_sustained_headway_level_count",
    "max_frequency_jump",
    "total_frequency_variation",
    "moved_trips_vs_b",
    "fleet_required",
    "total_excess_terminal_wait",
)
REVIEW_DIMENSIONS = (
    "micro_rhythm_boundary_count",
    "sustained_exact_headway_level_count",
    "actual_service_regime_count",
    "pair_trip_equivalent_error",
    "average_passenger_wait_minutes",
    "fleet_required",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _representative(regimes: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    headways = [int(item["uniform_headway_minutes"]) for item in regimes]
    lower = max(headways) - 1
    upper = min(headways) + 1
    feasible = range(lower, upper + 1)
    weighted = [
        (
            sum(
                (int(item["trip_count"]) - 1)
                * abs(int(item["uniform_headway_minutes"]) - candidate)
                for item in regimes
            ),
            candidate,
        )
        for candidate in feasible
    ]
    return min(weighted)


def _family_payload(regimes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    deviation, representative = _representative(regimes)
    starts = [int(item.get("first_departure", item.get("start", 0))) for item in regimes]
    ends = [int(item.get("last_departure", item.get("end", 0))) for item in regimes]
    headways = [int(item["uniform_headway_minutes"]) for item in regimes]
    trip_counts = [int(item["trip_count"]) for item in regimes]
    gap_counts = [value - 1 for value in trip_counts]
    return {
        "regime_ids": [str(item["service_regime_id"]) for item in regimes],
        "start": starts[0],
        "end": ends[-1],
        "exact_headways": headways,
        "trip_counts": trip_counts,
        "internal_gap_counts": gap_counts,
        "canonical_representative": representative,
        "internal_family_regime_boundary_count": len(regimes) - 1,
        "micro_rhythm_boundary_count": len(regimes) - 1,
        "exact_sustained_headway_levels": sorted(set(headways)),
        "gap_weighted_absolute_deviation": deviation,
    }


def detect_local_rhythm_families(
    service_regimes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Greedily partition maximal sustained runs into longest valid local families."""

    result: list[dict[str, Any]] = []
    index = 0
    while index < len(service_regimes):
        if int(service_regimes[index]["trip_count"]) < 3:
            index += 1
            continue
        end = index + 1
        while end < len(service_regimes) and int(service_regimes[end]["trip_count"]) >= 3:
            headways = [
                int(item["uniform_headway_minutes"]) for item in service_regimes[index : end + 1]
            ]
            if max(headways) - min(headways) > 2:
                break
            end += 1
        if end - index >= 2:
            result.append(_family_payload(service_regimes[index:end]))
            index = end
        else:
            index += 1
    return result


def detect_product_families(route: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        direction: detect_local_rhythm_families(route["directions"][direction]["service_regimes"])
        for direction in ("outbound", "inbound")
    }


def demand_justification_audit(
    family: Mapping[str, Any], demand_evidence: Mapping[str, Mapping[str, float]]
) -> list[dict[str, Any]]:
    records = []
    ids = family["regime_ids"]
    headways = family["exact_headways"]
    for left_id, right_id, left_h, right_h in zip(
        ids, ids[1:], headways, headways[1:], strict=False
    ):
        left_rate = float(demand_evidence[left_id]["demand_rate_per_hour"])
        right_rate = float(demand_evidence[right_id]["demand_rate_per_hour"])
        service_delta = 60 / right_h - 60 / left_h
        demand_delta = right_rate - left_rate

        def direction(value: float) -> str:
            return "UP" if value > 0 else "DOWN" if value < 0 else "FLAT"

        service_direction = direction(service_delta)
        demand_direction = direction(demand_delta)
        explanatory = service_direction == demand_direction or service_direction == "FLAT"
        records.append(
            {
                "left_regime_id": left_id,
                "right_regime_id": right_id,
                "left_headway": left_h,
                "right_headway": right_h,
                "left_frequency_per_hour": 60 / left_h,
                "right_frequency_per_hour": 60 / right_h,
                "left_integrated_demand_mass": demand_evidence[left_id]["integrated_demand_mass"],
                "right_integrated_demand_mass": demand_evidence[right_id]["integrated_demand_mass"],
                "left_demand_rate_per_hour": left_rate,
                "right_demand_rate_per_hour": right_rate,
                "service_frequency_direction": service_direction,
                "demand_direction": demand_direction,
                "classification": (
                    "DEMAND_RESPONSE_EXPLANATORY"
                    if explanatory
                    else "NOT_DEMAND_RESPONSE_EXPLANATORY"
                ),
            }
        )
    return records


def strict_arithmetic_census(
    *,
    service_span_minutes: int,
    gap_count: int,
    ordered_headways: Sequence[int],
    require_each: bool = True,
) -> dict[str, Any]:
    """Enumerate exact integer compositions in a fixed ordered headway vocabulary."""

    headways = tuple(int(value) for value in ordered_headways)
    if not headways or min(headways) <= 0 or gap_count <= 0:
        return {
            "service_span_minutes": service_span_minutes,
            "gap_count": gap_count,
            "ordered_headways": list(headways),
            "feasible": False,
            "compositions": [],
        }
    lower = 1 if require_each else 0
    compositions: list[dict[str, Any]] = []

    def visit(index: int, remaining_count: int, remaining_span: int, counts: list[int]) -> None:
        if index == len(headways) - 1:
            count = remaining_count
            if count >= lower and count * headways[index] == remaining_span:
                values = [*counts, count]
                compositions.append(
                    {"gap_counts": values, "weighted_minutes": service_span_minutes}
                )
            return
        minimum_after = lower * (len(headways) - index - 1)
        for count in range(lower, remaining_count - minimum_after + 1):
            visit(
                index + 1,
                remaining_count - count,
                remaining_span - count * headways[index],
                [*counts, count],
            )

    visit(0, gap_count, service_span_minutes, [])
    compositions.sort(key=lambda item: tuple(item["gap_counts"]))
    return {
        "service_span_minutes": service_span_minutes,
        "gap_count": gap_count,
        "ordered_headways": list(headways),
        "feasible": bool(compositions),
        "compositions": compositions,
    }


def _residual_census(
    *, service_span_minutes: int, gap_count: int, allowed_headways: Sequence[int]
) -> dict[str, Any]:
    witnesses: list[dict[str, Any]] = []
    for residual_position in range(gap_count):
        base = strict_arithmetic_census(
            service_span_minutes=service_span_minutes,
            gap_count=gap_count - 1,
            ordered_headways=allowed_headways,
            require_each=False,
        )
        # The base span is unknown; enumerate counts directly and derive the residual.
        for counts in _count_compositions(gap_count - 1, len(allowed_headways)):
            base_minutes = sum(
                count * headway for count, headway in zip(counts, allowed_headways, strict=True)
            )
            residual = service_span_minutes - base_minutes
            if residual > 0 and residual not in allowed_headways:
                witnesses.append(
                    {
                        "residual_position": residual_position,
                        "residual_gap_minutes": residual,
                        "ordinary_gap_counts": list(counts),
                        "distance_from_neighboring_rhythms": min(
                            abs(residual - value) for value in allowed_headways
                        ),
                    }
                )
        del base
    witnesses.sort(
        key=lambda item: (
            item["distance_from_neighboring_rhythms"],
            item["residual_gap_minutes"],
            item["residual_position"],
            item["ordinary_gap_counts"],
        )
    )
    witness = witnesses[0] if witnesses else None
    return {
        "residual_required": witness is not None,
        "residual_gap_minutes": None if witness is None else witness["residual_gap_minutes"],
        "theoretical_positions": sorted(
            {
                item["residual_position"]
                for item in witnesses
                if item == witness or witness is not None
            }
        )
        if witness
        else [],
        "witness": witness,
        "production_compiler_changed": False,
        "settlement_added": False,
        "residual_service_regime_created": False,
    }


def _count_compositions(total: int, width: int) -> Iterable[tuple[int, ...]]:
    if width == 1:
        yield (total,)
        return
    for first in range(total + 1):
        for rest in _count_compositions(total - first, width - 1):
            yield (first, *rest)


def arithmetic_tier_census(
    *,
    service_span_minutes: int,
    gap_count: int,
    canonical_headway: int,
    frozen_non_family_headways: Sequence[int],
    frozen_tail_headway: int | None,
    permitted_tail_headways: Iterable[int],
) -> dict[str, Any]:
    non_tail = (canonical_headway, *tuple(frozen_non_family_headways))
    q_a_heads = non_tail + (() if frozen_tail_headway is None else (frozen_tail_headway,))
    q_a = strict_arithmetic_census(
        service_span_minutes=service_span_minutes,
        gap_count=gap_count,
        ordered_headways=q_a_heads,
    )
    tail_witnesses = []
    if not q_a["feasible"] and frozen_tail_headway is not None:
        for tail in sorted(set(int(value) for value in permitted_tail_headways)):
            if tail == frozen_tail_headway or tail < max(non_tail):
                continue
            census = strict_arithmetic_census(
                service_span_minutes=service_span_minutes,
                gap_count=gap_count,
                ordered_headways=(*non_tail, tail),
            )
            for composition in census["compositions"]:
                tail_witnesses.append(
                    {
                        "tail_headway": tail,
                        "gap_counts": composition["gap_counts"],
                        "weighted_minutes": composition["weighted_minutes"],
                    }
                )
    tail_witnesses.sort(
        key=lambda item: (
            abs(item["tail_headway"] - (frozen_tail_headway or item["tail_headway"])),
            item["tail_headway"],
            item["gap_counts"],
        )
    )
    q_b = {
        "feasible": bool(tail_witnesses),
        "witness": tail_witnesses[0] if tail_witnesses else None,
        "witnesses": tail_witnesses,
    }
    q_c = (
        _residual_census(
            service_span_minutes=service_span_minutes,
            gap_count=gap_count,
            allowed_headways=q_a_heads,
        )
        if not q_a["feasible"] and not q_b["feasible"]
        else {
            "residual_required": False,
            "residual_gap_minutes": None,
            "theoretical_positions": [],
            "witness": None,
            "production_compiler_changed": False,
            "settlement_added": False,
            "residual_service_regime_created": False,
        }
    )
    return {"Q_A": q_a, "Q_B": q_b, "Q_C": q_c}


def access_gate(candidate: float, scenario_b: float, *, epsilon: float = NUMERICAL_EPSILON) -> bool:
    return candidate <= scenario_b + epsilon


def te_materiality_gate(
    candidate: float, anchor: float, *, epsilon: float = NUMERICAL_EPSILON
) -> bool:
    return candidate - anchor <= 1.0 + epsilon


def _dominates(left: Sequence[float], right: Sequence[float], *, epsilon: float) -> bool:
    return all(a <= b + epsilon for a, b in zip(left, right, strict=True)) and any(
        a < b - epsilon for a, b in zip(left, right, strict=True)
    )


def production_pareto_audit(
    candidate: Sequence[float],
    frontier: Mapping[str, Sequence[float | None]],
    *,
    epsilon: float = NUMERICAL_EPSILON,
) -> dict[str, Any]:
    dominated_by = []
    dominates = []
    unresolved = []
    for fingerprint, vector in sorted(frontier.items()):
        known = [
            (index, float(value), float(candidate[index]))
            for index, value in enumerate(vector)
            if value is not None
        ]
        missing = len(known) != len(candidate)
        if not missing and _dominates(
            tuple(value for _index, value, _candidate in known),
            tuple(value for _index, _value, value in known),
            epsilon=epsilon,
        ):
            dominated_by.append(fingerprint)
        elif missing and not any(
            value > candidate_value + epsilon for _, value, candidate_value in known
        ):
            unresolved.append(fingerprint)
        if not missing and _dominates(
            tuple(value for _index, _current, value in known),
            tuple(value for _index, value, _candidate in known),
            epsilon=epsilon,
        ):
            dominates.append(fingerprint)
    witnesses = {
        fingerprint: [
            index
            for index, (left, right) in enumerate(zip(candidate, vector, strict=True))
            if right is not None and float(left) < float(right) - epsilon
        ]
        for fingerprint, vector in sorted(frontier.items())
        if fingerprint not in dominated_by
    }
    return {
        "pareto_relevant": not dominated_by and not unresolved,
        "dominated_by_current_frontier": bool(dominated_by),
        "dominated_by": dominated_by,
        "unresolved_current_candidates": unresolved,
        "current_candidates_dominated": dominates,
        "nondominance_witness_dimensions": witnesses,
    }


def _gap_counts(departures: Sequence[int]) -> Counter[int]:
    return Counter(
        (right - left) // 60 for left, right in zip(departures, departures[1:], strict=False)
    )


def _baseline_arithmetic(
    direction_payload: Mapping[str, Any], family: Mapping[str, Any]
) -> dict[str, Any]:
    departures = [int(value) for value in direction_payload["exact_departures"]]
    counts = _gap_counts(departures)
    family_heads = set(family["exact_headways"])
    canonical = int(family["canonical_representative"])
    service_heads = [
        int(item["uniform_headway_minutes"]) for item in direction_payload["service_regimes"]
    ]
    tail = service_heads[-1]
    frozen = []
    for headway in service_heads:
        if headway not in family_heads and headway != tail and headway not in frozen:
            frozen.append(headway)
    tiers = arithmetic_tier_census(
        service_span_minutes=(departures[-1] - departures[0]) // 60,
        gap_count=len(departures) - 1,
        canonical_headway=canonical,
        frozen_non_family_headways=tuple(frozen),
        frozen_tail_headway=tail,
        permitted_tail_headways=range(max(canonical, max(frozen, default=canonical)), 61),
    )
    return {
        "service_span_minutes": (departures[-1] - departures[0]) // 60,
        "gap_count": len(departures) - 1,
        "exact_gap_sum_minutes": sum(value * count for value, count in sorted(counts.items())),
        "baseline_gap_counts": {str(key): counts[key] for key in sorted(counts)},
        "canonical_representative": canonical,
        "frozen_non_family_headways": frozen,
        "frozen_tail_headway": tail,
        **tiers,
    }


def _load_json(repo_root: Path, relative: Path) -> Any:
    return json.loads((repo_root / relative).read_text(encoding="utf-8"))


def _product_locks(repo_root: Path, product: Mapping[str, Any]) -> dict[str, Any]:
    if product["routes"]["10"]["selected_pair_fingerprint"] != ROUTE10_P_PAIR:
        raise RuntimeError("Route 10 P pair lock changed")
    result = {}
    for route_id, (relative, expected_hash) in WORKBOOK_LOCKS.items():
        actual = _sha256(repo_root / relative)
        if actual != expected_hash:
            raise RuntimeError(f"Route {route_id} canonical workbook lock changed")
        result[route_id] = {
            "path": relative.as_posix(),
            "sha256": actual,
            "bytes": (repo_root / relative).stat().st_size,
        }
    production = {}
    for relative, expected_hash in PRODUCTION_FILE_LOCKS.items():
        actual = _sha256(repo_root / relative)
        if actual != expected_hash:
            raise RuntimeError(f"production file lock changed: {relative}")
        production[relative] = actual
    return {"workbooks": result, "production_files": production}


def _baseline_state(
    *,
    route_payload: Mapping[str, Any],
    route_evidence: Mapping[str, Any],
    direction: str,
) -> ServicePlanStateV1:
    compile_fingerprint = route_payload["directions"][direction]["compilation_fingerprint"]
    record = route_evidence["final_directional_compilations"][compile_fingerprint]
    authority = route_payload["directions"][direction]
    state = ServicePlanStateV1(
        route_id="10",
        direction=direction,
        fixed_first_departure=int(authority["authoritative_first_departure"]),
        fixed_last_departure=int(authority["authoritative_last_departure"]),
        service_regimes=tuple(
            ServiceRegimeDecisionV1(int(item["start"]), int(item["end"]), int(item["trip_count"]))
            for item in record["service_plan_regimes"]
        ),
        seed_id="PR62_P_SELECTED_STATE",
    )
    if service_plan_fingerprint_v1(state) != record["state_fingerprint"]:
        raise RuntimeError(f"Route 10 {direction} P-selected ServicePlan state drift")
    return state


def _family_plan_indices(
    direction_payload: Mapping[str, Any], family: Mapping[str, Any]
) -> tuple[int, ...]:
    by_id = {item["service_regime_id"]: item for item in direction_payload["service_regimes"]}
    ids = {
        demand_id
        for service_id in family["regime_ids"]
        for demand_id in by_id[service_id]["demand_regime_ids"]
    }
    prefix = f"PLAN-{direction_payload['service_regimes'][0]['direction'].upper()}-"
    indices = tuple(sorted(int(value.removeprefix(prefix)) - 1 for value in ids))
    if indices != tuple(range(indices[0], indices[-1] + 1)):
        raise RuntimeError("target local family does not map to contiguous planning regimes")
    return indices


def _merged_family_state(state: ServicePlanStateV1, indices: Sequence[int]) -> ServicePlanStateV1:
    first, last = min(indices), max(indices)
    merged = ServiceRegimeDecisionV1(
        state.service_regimes[first].start,
        state.service_regimes[last].end,
        sum(item.trip_count for item in state.service_regimes[first : last + 1]),
    )
    return dataclasses.replace(
        state,
        service_regimes=(
            *state.service_regimes[:first],
            merged,
            *state.service_regimes[last + 1 :],
        ),
        parent_fingerprint=service_plan_fingerprint_v1(state),
        operation="Q_LOCAL_FAMILY_MERGE",
        operation_evidence="LOCAL_CANONICAL_FAMILY",
    )


def _local_states(
    state: ServicePlanStateV1,
    *,
    family_index: int,
    transfer_radius: int,
    planning_grid_seconds: int,
) -> tuple[list[ServicePlanStateV1], dict[str, Any]]:
    """Exhaust the declared Cartesian transfer/boundary neighborhood."""

    right_index = family_index + 1
    if right_index >= len(state.service_regimes):
        raise RuntimeError("canonical family has no immediate right neighbor")
    left = state.service_regimes[family_index]
    right = state.service_regimes[right_index]
    states: dict[str, ServicePlanStateV1] = {}
    theoretical = 0
    rejected = 0
    for boundary_steps in range(-transfer_radius, transfer_radius + 1):
        boundary = left.end + boundary_steps * planning_grid_seconds
        for transfer in range(-transfer_radius, transfer_radius + 1):
            theoretical += 1
            left_count = left.trip_count + transfer
            right_count = right.trip_count - transfer
            if boundary <= left.start or boundary >= right.end or min(left_count, right_count) < 2:
                rejected += 1
                continue
            regimes = list(state.service_regimes)
            regimes[family_index] = ServiceRegimeDecisionV1(left.start, boundary, left_count)
            regimes[right_index] = ServiceRegimeDecisionV1(boundary, right.end, right_count)
            candidate = dataclasses.replace(
                state,
                service_regimes=tuple(regimes),
                parent_fingerprint=service_plan_fingerprint_v1(state),
                operation="Q_LOCAL_CARTESIAN_CENSUS",
                operation_evidence=f"boundary_steps={boundary_steps};transfer={transfer}",
            )
            errors = validate_service_plan_state_v1(
                candidate,
                authoritative_total_trips=state.total_trips,
                planning_grid_seconds=planning_grid_seconds,
                floor_headway_minutes=None,
            )
            if errors:
                rejected += 1
                continue
            states.setdefault(service_plan_fingerprint_v1(candidate), candidate)
    return list(states.values()), {
        "boundary_step_radius": transfer_radius,
        "trip_transfer_radius": transfer_radius,
        "total_theoretical_combinations": theoretical,
        "invalid_service_plan_combinations": rejected,
        "valid_unique_service_plan_states": len(states),
    }


def _compile_directional_census(
    *,
    context: Any,
    states: Sequence[ServicePlanStateV1],
    target_headways: Sequence[int] | None,
    canonical: int,
    tier: str,
) -> tuple[list[Any], dict[str, Any]]:
    compiled = 0
    rejected_compilations = 0
    hard_valid = []
    compiler_pruned = 0
    for state in states:
        frontier = compile_service_plan_frontier_v1(
            state,
            endpoint_authority=context.endpoint_authority[state.direction],
            compile_frontier_limit=256,
        )
        compiler_pruned += frontier.variants_limit_pruned
        if not frontier.variants:
            rejected_compilations += 1
            continue
        for variant in frontier.variants:
            compiled += 1
            services = tuple(variant.compilation.service_regimes)
            sustained_headways = tuple(
                item.uniform_headway_minutes for item in services if item.trip_count >= 3
            )
            families = detect_local_rhythm_families([dataclasses.asdict(item) for item in services])
            if any(
                canonical in family["exact_headways"] and len(set(family["exact_headways"])) > 1
                for family in families
            ):
                rejected_compilations += 1
                continue
            if target_headways is not None and sustained_headways != tuple(target_headways):
                rejected_compilations += 1
                continue
            protection = validate_closed_loop_service_protection_v1(
                authority=context.service_protection_authority,
                direction=state.direction,
                exact_departures=variant.compilation.exact_departures,
            )
            if not protection.passed:
                rejected_compilations += 1
                continue
            metrics, feedback = coordinator.evaluate_actual_service_v1(
                variant,
                demand_buckets=context.demand_buckets[state.direction],
                scenario_b_departures=context.scenario_b_departures[state.direction],
                demand_response_regimes=context.demand_response_regimes[state.direction],
                protection_authority=context.service_protection_authority,
                protection_validation=protection,
            )
            if not metrics.tail_ordering.eligible:
                rejected_compilations += 1
                continue
            hard_valid.append(
                coordinator.DirectionalCompilationCandidateV1(
                    state=state,
                    state_fingerprint=service_plan_fingerprint_v1(state),
                    compile_variant=variant,
                    metrics=metrics,
                    feedback=feedback,
                    history=(f"PR62-Q {tier} local exhaustive census",),
                )
            )
    unique = {}
    for item in hard_valid:
        unique.setdefault(item.compile_variant.compilation_fingerprint, item)
    return list(unique.values()), {
        "states_compiled": len(states),
        "compiled_candidates": compiled,
        "rejected_compilations": rejected_compilations,
        "hard_valid_directional_candidates": len(unique),
        "compiler_internal_limit_pruned": compiler_pruned,
        "compile_frontier_limit_per_state": 256,
    }


def _current_frontier_vectors(repo_root: Path) -> dict[str, tuple[float | None, ...]]:
    o = _load_json(repo_root, O_EVIDENCE)["routes"]["10"]
    e = _load_json(repo_root, E_ROUTE10_EVIDENCE)
    pairs = {item["pair_fingerprint"]: item for item in e["final_pareto_pairs"]}
    vectors = {}
    for audit in o["candidate_audit"]:
        fingerprint = audit["fingerprint"]
        pair = pairs.get(fingerprint)
        old = None if pair is None else pair["metrics"]
        rhythm = audit["rhythm_simplicity_tuple"]
        fleet = audit["fleet_efficiency_tuple"]
        vectors[fingerprint] = (
            float(audit["observed_demand_mismatch"]),
            float(audit["average_wait_minutes"]),
            max(
                float(value) for value in audit["directional_maximum_bucket_wait_minutes"].values()
            ),
            float(rhythm[1]),
            float(rhythm[0]),
            None if old is None else float(old["max_frequency_jump"]),
            None if old is None else float(old["total_frequency_variation"]),
            None if old is None else float(old["moved_trips_vs_b"]),
            float(fleet[0]),
            float(fleet[1]),
        )
    return vectors


def _pair_summary(
    pair: Any,
    *,
    anchor_te: float,
    scenario_b_access: Mapping[str, float],
    production_frontier: Mapping[str, Sequence[float]],
) -> dict[str, Any]:
    direction_te = {
        direction: directional_trip_equivalent_error_v2(
            getattr(pair, direction).metrics,
            total_trips=len(getattr(pair, direction).compile_variant.compilation.exact_departures),
        )
        for direction in ("outbound", "inbound")
    }
    pair_te = sum(direction_te.values())
    access = {
        direction: {
            "candidate_maximum_bucket_wait_minutes": getattr(
                pair, direction
            ).metrics.maximum_bucket_expected_wait_minutes,
            "scenario_b_maximum_bucket_wait_minutes": scenario_b_access[direction],
            "safe": access_gate(
                getattr(pair, direction).metrics.maximum_bucket_expected_wait_minutes,
                scenario_b_access[direction],
            ),
            "p90_bucket_wait_minutes": getattr(
                pair, direction
            ).metrics.p90_bucket_expected_wait_minutes,
            "tail_maximum_bucket_wait_minutes": getattr(
                pair, direction
            ).metrics.tail_maximum_bucket_expected_wait_minutes,
        }
        for direction in ("outbound", "inbound")
    }
    directional_families = {
        direction: detect_local_rhythm_families(
            [
                dataclasses.asdict(item)
                for item in getattr(pair, direction).compile_variant.compilation.service_regimes
            ]
        )
        for direction in ("outbound", "inbound")
    }
    micro_boundaries = sum(
        family["micro_rhythm_boundary_count"]
        for families in directional_families.values()
        for family in families
    )
    vector = tuple(float(value) for value in pair.metrics.pareto_vector)
    pareto = production_pareto_audit(vector, production_frontier)
    directions = {}
    for direction in ("outbound", "inbound"):
        item = getattr(pair, direction)
        compilation = item.compile_variant.compilation
        metrics = item.metrics
        directions[direction] = {
            "state_fingerprint": item.state_fingerprint,
            "compilation_fingerprint": item.compile_variant.compilation_fingerprint,
            "exact_departure_fingerprint": _fingerprint(list(compilation.exact_departures)),
            "exact_departures": list(compilation.exact_departures),
            "service_regimes": [dataclasses.asdict(value) for value in compilation.service_regimes],
            "observed_demand_SSE": metrics.observed_demand_mismatch,
            "trip_equivalent_error": direction_te[direction],
            "average_passenger_wait_minutes": metrics.demand_weighted_expected_passenger_wait_minutes,
            "maximum_bucket_wait_minutes": metrics.maximum_bucket_expected_wait_minutes,
            "p90_bucket_wait_minutes": metrics.p90_bucket_expected_wait_minutes,
            "tail_maximum_bucket_wait_minutes": (metrics.tail_maximum_bucket_expected_wait_minutes),
            "tail_headway_minutes": metrics.tail_headway_minutes,
            "tail_ordering": dataclasses.asdict(metrics.tail_ordering),
            "rhythm_simplicity": dataclasses.asdict(metrics.rhythm_simplicity),
            "max_frequency_jump": metrics.max_frequency_jump,
            "total_frequency_variation": metrics.total_frequency_variation,
            "local_rhythm_families": directional_families[direction],
        }
    review = {
        "micro_rhythm_boundary_count": micro_boundaries,
        "sustained_exact_headway_level_count": pair.metrics.total_directional_sustained_headway_level_count,
        "actual_service_regime_count": pair.metrics.actual_service_regime_count,
        "pair_trip_equivalent_error": pair_te,
        "average_passenger_wait_minutes": pair.metrics.demand_weighted_expected_passenger_wait_minutes,
        "fleet_required": pair.metrics.fleet_required,
    }
    return {
        "pair_fingerprint": pair.pair_fingerprint,
        "directions": directions,
        "observed_demand_SSE": pair.metrics.observed_demand_mismatch,
        "pair_trip_equivalent_error": pair_te,
        "delta_TE_from_common_anchor": pair_te - anchor_te,
        "V2_materiality_compatible": te_materiality_gate(pair_te, anchor_te),
        "average_passenger_wait_minutes": pair.metrics.demand_weighted_expected_passenger_wait_minutes,
        "directional_access": access,
        "access_safe": all(value["safe"] for value in access.values()),
        "fleet_required": pair.metrics.fleet_required,
        "total_excess_terminal_wait": pair.metrics.total_excess_terminal_wait,
        "max_excess_terminal_wait": pair.metrics.max_excess_terminal_wait,
        "production_pareto_vector": dict(zip(PRODUCTION_DIMENSIONS, vector, strict=True)),
        "production_pareto_audit": pareto,
        "review_metrics": review,
    }


def _review_frontier(candidates: Sequence[Mapping[str, Any]]) -> list[str]:
    result = []
    for candidate in candidates:
        vector = tuple(float(candidate["review_metrics"][key]) for key in REVIEW_DIMENSIONS)
        if any(
            other["pair_fingerprint"] != candidate["pair_fingerprint"]
            and _dominates(
                tuple(float(other["review_metrics"][key]) for key in REVIEW_DIMENSIONS),
                vector,
                epsilon=NUMERICAL_EPSILON,
            )
            for other in candidates
        ):
            continue
        result.append(candidate["pair_fingerprint"])
    return sorted(result)


def _compiler_census(
    *,
    repo_root: Path,
    product: Mapping[str, Any],
    families: Mapping[str, Sequence[Mapping[str, Any]]],
    arithmetic: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    artifact_root = pr62_i._artifact_root(repo_root)
    context, _ = coordinator.load_route_coordinator_inputs_v1(
        repo_root=artifact_root,
        route_id="10",
        workbook_path=repo_root / "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    e = _load_json(repo_root, E_ROUTE10_EVIDENCE)
    directional_candidates: dict[str, list[Any]] = {}
    directional_audit = {}
    specifications = {
        "outbound": {"radius": 2, "target": (20, 14, 18, 23), "tier": "Q-A"},
        "inbound": {"radius": 3, "target": (19, 24), "tier": "Q-B"},
    }
    for direction in ("outbound", "inbound"):
        baseline = _baseline_state(
            route_payload=product["routes"]["10"],
            route_evidence=e,
            direction=direction,
        )
        indices = _family_plan_indices(
            product["routes"]["10"]["directions"][direction], families[direction][0]
        )
        merged = _merged_family_state(baseline, indices)
        family_index = min(indices)
        spec = specifications[direction]
        states, domain = _local_states(
            merged,
            family_index=family_index,
            transfer_radius=spec["radius"],
            planning_grid_seconds=context.planning_grid_seconds,
        )
        candidates, compile_audit = _compile_directional_census(
            context=context,
            states=states,
            target_headways=spec["target"],
            canonical=int(families[direction][0]["canonical_representative"]),
            tier=spec["tier"],
        )
        directional_candidates[direction] = candidates
        directional_audit[direction] = {
            "tier": spec["tier"],
            "arithmetic_transfer_radius": spec["radius"],
            "family_planning_regime_indices": list(indices),
            "starting_state_fingerprint": service_plan_fingerprint_v1(baseline),
            "merged_state_fingerprint": service_plan_fingerprint_v1(merged),
            "target_sustained_headways": list(spec["target"]),
            **domain,
            **compile_audit,
            "classification": (
                "CANONICAL_FAMILY_CLEANLY_REPRESENTABLE"
                if candidates and spec["tier"] == "Q-A"
                else "CANONICAL_FAMILY_REQUIRES_TAIL_REALLOCATION"
                if candidates
                else "CANONICAL_FAMILY_NOT_FOUND_IN_EXHAUSTED_LOCAL_CENSUS"
            ),
        }
    pairs = []
    pair_rejections = 0
    for outbound in directional_candidates["outbound"]:
        for inbound in directional_candidates["inbound"]:
            pair, _feedback = coordinator.evaluate_operating_pair_v1(
                outbound, inbound, context=context
            )
            if pair is None:
                pair_rejections += 1
            else:
                pairs.append(pair)
    unique_pairs = {item.pair_fingerprint: item for item in pairs}
    o = _load_json(repo_root, O_EVIDENCE)["routes"]["10"]
    anchor = next(
        item
        for item in o["candidate_audit"]
        if item["fingerprint"] == o["selection_result"]["common_anchor_fingerprint"]
    )
    anchor_te = float(anchor["pair_trip_equivalent_error"])
    scenario_b_access = {
        direction: float(
            product["routes"]["10"]["scenario_b"]["directions"][direction]["maximum_bucket_wait"]
        )
        for direction in ("outbound", "inbound")
    }
    production = _current_frontier_vectors(repo_root)
    summaries = [
        _pair_summary(
            pair,
            anchor_te=anchor_te,
            scenario_b_access=scenario_b_access,
            production_frontier=production,
        )
        for pair in unique_pairs.values()
    ]
    summaries.sort(key=lambda item: item["pair_fingerprint"])
    plausible = [
        item for item in summaries if item["access_safe"] and item["V2_materiality_compatible"]
    ]
    relevant = [item for item in plausible if item["production_pareto_audit"]["pareto_relevant"]]
    return {
        "declared_local_search_domain": directional_audit,
        "pair_cartesian_combinations": len(directional_candidates["outbound"])
        * len(directional_candidates["inbound"]),
        "fleet_rejected_pairs": pair_rejections,
        "hard_valid_pairs": len(summaries),
        "access_safe_pairs": sum(item["access_safe"] for item in summaries),
        "within_one_TE_pairs": sum(item["V2_materiality_compatible"] for item in summaries),
        "plausible_review_pairs": len(plausible),
        "production_pareto_relevant_pairs": sum(
            item["production_pareto_audit"]["pareto_relevant"] for item in summaries
        ),
        "hard_valid_candidate_summaries": summaries,
        "Q_LOCAL_CANONICALIZATION_REVIEW_FRONTIER": _review_frontier(summaries),
        "descriptive_review_representative": (
            min(
                relevant,
                key=lambda item: (
                    item["review_metrics"]["micro_rhythm_boundary_count"],
                    item["review_metrics"]["sustained_exact_headway_level_count"],
                    item["review_metrics"]["actual_service_regime_count"],
                    item["pair_trip_equivalent_error"],
                    item["fleet_required"],
                    item["pair_fingerprint"],
                ),
            )["pair_fingerprint"]
            if relevant
            else None
        ),
    }


def _baseline_review(route: Mapping[str, Any], families: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "actual_service_regime_count": route["metrics"]["actual_service_regime_count"],
        "sustained_exact_headway_level_count": route["metrics"][
            "total_directional_sustained_headway_level_count"
        ],
        "effective_palette_count": route["metrics"]["total_directional_effective_palette_count"],
        "local_rhythm_family_count": sum(len(value) for value in families.values()),
        "micro_rhythm_boundary_count": sum(
            family["micro_rhythm_boundary_count"] for value in families.values() for family in value
        ),
        "gap_weighted_canonical_deviation": sum(
            family["gap_weighted_absolute_deviation"]
            for value in families.values()
            for family in value
        ),
        "max_frequency_jump": route["metrics"]["max_frequency_jump"],
        "total_frequency_variation": route["metrics"]["total_frequency_variation"],
        "SSE": route["metrics"]["observed_demand_mismatch"],
        "pair_TE": route["te"]["pair"],
        "average_wait": route["metrics"]["demand_weighted_expected_passenger_wait_minutes"],
        "maximum_access": route["metrics"]["maximum_bucket_expected_wait_minutes"],
        "P90": route["metrics"]["maximum_directional_p90_bucket_wait_minutes"],
        "fleet": route["fleet_plan"]["fleet_required"],
        "terminal_excess_wait": route["metrics"]["total_excess_terminal_wait"],
        "tails": {
            direction: route["directions"][direction]["metrics"]["tail_headway_minutes"]
            for direction in ("outbound", "inbound")
        },
    }


def _classification(
    compiler: Mapping[str, Any], arithmetic: Mapping[str, Any]
) -> tuple[str, str | None, str]:
    candidates = compiler.get("hard_valid_candidate_summaries", [])
    access_safe = [item for item in candidates if item["access_safe"]]
    plausible = [item for item in access_safe if item["V2_materiality_compatible"]]
    if any(item["production_pareto_audit"]["pareto_relevant"] for item in plausible):
        return (
            "SEARCH_GENERATION_GAP_CONFIRMED",
            "PR62-R_TARGETED_RHYTHM_CANONICALIZATION_SEARCH_OPERATOR",
            "PRODUCTION_SEARCH_GENERATION",
        )
    if plausible:
        return (
            "CURRENT_PARETO_BLOCKS_CANONICAL_RHYTHM",
            "PR62-R_POLICY_PARETO_REVIEW",
            "PRODUCTION_10_D_PARETO_BLOCKER",
        )
    if access_safe:
        return (
            "Q_EVIDENCE_INCONCLUSIVE",
            "PR62-R_LOCAL_RHYTHM_DEMAND_FIT_TRADEOFF_REVIEW",
            "V2_TE_MATERIALITY_BLOCKER",
        )
    if candidates:
        return (
            "Q_EVIDENCE_INCONCLUSIVE",
            "PR62-R_LOCAL_RHYTHM_ACCESS_REVIEW",
            "SCENARIO_B_MAX_ACCESS_BLOCKER",
        )
    if any(value["Q_C"]["residual_required"] for value in arithmetic.values() if value is not None):
        return (
            "ARITHMETIC_RESIDUAL_DESIGN_REQUIRED",
            "PR62-R_RESIDUAL_SEMANTICS_DESIGN",
            "ARITHMETIC_RESIDUAL_NECESSITY",
        )
    if all(value["Q_A"]["feasible"] or value["Q_B"]["feasible"] for value in arithmetic.values()):
        return (
            "COMPILER_REPRESENTATION_BLOCKER",
            "PR62-R_COMPILER_REPRESENTATION_REVIEW",
            "CLEAN_COMPILER_REPRESENTATION",
        )
    return "Q_EVIDENCE_INCONCLUSIVE", "PR62-R_BLOCKER_REVIEW", "ARITHMETIC_INFEASIBLE"


def build_evidence(repo_root: Path, *, run_compiler_census: bool = True) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    product = _load_json(repo_root, P_PRODUCT_DATA)
    locks = _product_locks(repo_root, product)
    routes = {}
    arithmetic_by_direction = {}
    for route_id in ("6", "10"):
        route = product["routes"][route_id]
        families = detect_product_families(route)
        route_payload: dict[str, Any] = {
            "selected_pair_fingerprint": route["selected_pair_fingerprint"],
            "current_service_regimes": {
                direction: route["directions"][direction]["service_regimes"]
                for direction in ("outbound", "inbound")
            },
            "local_rhythm_families": families,
            "baseline_review_metrics": _baseline_review(route, families),
        }
        if route_id == "6":
            route_payload["classification"] = (
                "NO_LOCAL_MICRO_RHYTHM_TARGET"
                if not any(families.values())
                else "UNEXPECTED_LOCAL_MICRO_RHYTHM_TARGET"
            )
        else:
            route_payload["baseline_pair_fingerprint"] = route["selected_pair_fingerprint"]
            route_payload["directions"] = {}
            for direction in ("outbound", "inbound"):
                family = families[direction][0]
                demand = {
                    item["service_regime_id"]: item
                    for item in route["directions"][direction]["metrics"]["tail_ordering"][
                        "service_regime_demand_evidence"
                    ]
                }
                for regime_id, headway in zip(
                    family["regime_ids"], family["exact_headways"], strict=True
                ):
                    demand[regime_id]["service_frequency_per_hour"] = 60 / headway
                family["integrated_immutable_demand_by_member"] = [
                    demand[value]["integrated_demand_mass"] for value in family["regime_ids"]
                ]
                family["demand_rate_per_hour_by_member"] = [
                    demand[value]["demand_rate_per_hour"] for value in family["regime_ids"]
                ]
                family["service_frequency_per_hour_by_member"] = [
                    demand[value]["service_frequency_per_hour"] for value in family["regime_ids"]
                ]
                arithmetic = _baseline_arithmetic(route["directions"][direction], family)
                arithmetic_by_direction[direction] = arithmetic
                route_payload["directions"][direction] = {
                    "target_family": family,
                    "demand_justification_audit": demand_justification_audit(family, demand),
                    "arithmetic_census": arithmetic,
                }
        routes[route_id] = route_payload
    compiler = (
        _compiler_census(
            repo_root=repo_root,
            product=product,
            families=routes["10"]["local_rhythm_families"],
            arithmetic=arithmetic_by_direction,
        )
        if run_compiler_census
        else {
            "skipped": True,
            "hard_valid_candidate_summaries": [],
            "Q_LOCAL_CANONICALIZATION_REVIEW_FRONTIER": [],
        }
    )
    classification, recommendation, blocking_stage = (
        _classification(compiler, arithmetic_by_direction)
        if run_compiler_census
        else ("Q_EVIDENCE_INCONCLUSIVE", None, "COMPILER_CENSUS_SKIPPED")
    )
    return {
        "milestone": "PR62-Q",
        "P_commit_SHA": P_COMMIT_SHA,
        "P_product_locks": locks,
        "routes": routes,
        "compiler_backed_census": compiler,
        "root_cause_classification": classification,
        "blocking_stage": blocking_stage,
        "next_milestone_recommendation": recommendation,
        "Q_LOCAL_CANONICALIZATION_REVIEW_FRONTIER": compiler[
            "Q_LOCAL_CANONICALIZATION_REVIEW_FRONTIER"
        ],
        "READY_FOR_PR62_COMPLETION_REVIEW": False,
        "production_guards": EXPECTED_PRODUCTION_GUARDS,
        "deterministic_render": True,
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    route10 = payload["routes"]["10"]
    ob = route10["directions"]["outbound"]
    ib = route10["directions"]["inbound"]
    compiler = payload["compiler_backed_census"]
    inbound_tail_witness = ib["arithmetic_census"]["Q_B"]["witness"]
    inbound_tail_text = (
        "none"
        if inbound_tail_witness is None
        else (
            f"tail {inbound_tail_witness['tail_headway']} minutes with gap counts "
            f"{inbound_tail_witness['gap_counts']}"
        )
    )
    lines = [
        "# PR62-Q — Local rhythm-family canonicalization experiment",
        "",
        "PR62-P remains mechanically V2-certified. Final product review exposed local,",
        "passenger-facing near-equivalent sustained rhythm churn on Route 10.",
        "",
        "## Baseline diagnosis",
        "",
        f"- Route 10 outbound: `{ob['target_family']['exact_headways']}` → canonical "
        f"`{ob['target_family']['canonical_representative']}`; "
        f"{ob['target_family']['micro_rhythm_boundary_count']} micro boundaries.",
        f"- Route 10 inbound: `{ib['target_family']['exact_headways']}` → canonical "
        f"`{ib['target_family']['canonical_representative']}`; "
        f"{ib['target_family']['micro_rhythm_boundary_count']} micro boundaries.",
        f"- Route 6 control: `{payload['routes']['6']['classification']}`.",
        "",
        "## Arithmetic census",
        "",
        f"- Outbound Q-A feasible: `{ob['arithmetic_census']['Q_A']['feasible']}`; "
        f"Q-B feasible: `{ob['arithmetic_census']['Q_B']['feasible']}`.",
        f"- Inbound Q-A feasible: `{ib['arithmetic_census']['Q_A']['feasible']}`; "
        f"Q-B feasible: `{ib['arithmetic_census']['Q_B']['feasible']}`; "
        f"witness: `{inbound_tail_text}`.",
        "",
        "## Compiler-backed census",
        "",
        f"- Hard-valid pairs: {compiler.get('hard_valid_pairs', 0)}.",
        f"- Access-safe pairs: {compiler.get('access_safe_pairs', 0)}.",
        f"- Within +1 TE: {compiler.get('within_one_TE_pairs', 0)}.",
        f"- Production-Pareto relevant: {compiler.get('production_pareto_relevant_pairs', 0)}.",
        f"- Review frontier: `{payload['Q_LOCAL_CANONICALIZATION_REVIEW_FRONTIER']}`.",
        "",
        "## Decision",
        "",
        f"Root cause: **{payload['root_cause_classification']}**.",
        f"Blocking stage: **{payload['blocking_stage']}**.",
        "",
        f"Next milestone: `{payload['next_milestone_recommendation']}`.",
        "",
        "No production search, compiler, selector, Pareto, protection, access, fleet,",
        "settlement/residual semantics, or canonical XLSX product changed.",
        "",
        "`READY_FOR_PR62_COMPLETION_REVIEW = false`",
        "",
    ]
    return "\n".join(lines)


def write_evidence(repo_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    json_first = canonical_json_bytes(payload)
    json_second = canonical_json_bytes(payload)
    markdown_first = render_markdown(payload).encode()
    markdown_second = render_markdown(payload).encode()
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("PR62-Q evidence rendering is not byte-identical")
    if len(json_first) >= 1_000_000:
        raise RuntimeError("PR62-Q JSON evidence exceeds 1 MB")
    json_path = repo_root / OUTPUT_JSON
    markdown_path = repo_root / OUTPUT_MARKDOWN
    json_path.write_bytes(json_first)
    markdown_path.write_bytes(markdown_first)
    return {
        "json_path": OUTPUT_JSON.as_posix(),
        "json_bytes": len(json_first),
        "json_sha256": hashlib.sha256(json_first).hexdigest(),
        "markdown_path": OUTPUT_MARKDOWN.as_posix(),
        "markdown_bytes": len(markdown_first),
        "markdown_sha256": hashlib.sha256(markdown_first).hexdigest(),
        "root_cause_classification": payload["root_cause_classification"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    payload = build_evidence(repo_root)
    print(json.dumps(write_evidence(repo_root, payload), sort_keys=True))
    _product_locks(repo_root, _load_json(repo_root, P_PRODUCT_DATA))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

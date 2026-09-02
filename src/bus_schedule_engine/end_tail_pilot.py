"""Routes 6/10 tail-aware allocation, end-tail compilation, and fleet pilot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .clean_boundary_pilot import (
    PILOT_MINIMUM_LAYOVER_MINUTES_V1,
    build_minimum_fleet_plan_v1,
    build_product_headway_rows_v1,
    select_final_candidate_pair_v1,
    validate_fleet_combination_v1,
)
from .contracts_v1.clean_boundary_compiler import (
    OperationalEndpointAuthorityV1,
    clean_boundary_compilation_to_dict_v1,
    scan_serialized_headway_outliers_v1,
)
from .contracts_v1.end_tail_settlement import (
    DEFAULT_TAIL_AWARE_ALLOCATOR_CONFIG_V2,
    TailAwareAllocatorConfigV2,
    TailAwareCandidateSetV2,
    TailAwareSelectedCandidateV2,
    allocate_tail_aware_trips_v2,
    select_tail_aware_candidates_v2,
    tail_aware_regime_from_mapping_v2,
)
from .time_utils import format_hhmm
from .v3_workbook import import_v3_multi_period_workbook_v1

END_TAIL_PILOT_PROFILE_V2 = "routes_6_10_end_tail_settlement_pilot_v2"
END_TAIL_OUTPUT_VERSION = "end_tail_settlement_v3_human_review"
_CANDIDATE_KEYS = ("c1_demand_fit", "c2_conservative", "c3_balanced")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_prior_fingerprints_v2(repo_root: Path) -> dict[str, str]:
    manifest_path = repo_root / "config" / "end_tail_frozen_prior_fingerprints_v2.json"
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))["sha256"]
    actual = {relative: _sha256(repo_root / relative) for relative in sorted(expected)}
    mismatches = {
        relative: {"expected": expected[relative], "actual": actual[relative]}
        for relative in expected
        if actual[relative] != expected[relative]
    }
    if mismatches:
        raise ValueError(f"frozen V1/V2 artifacts changed: {mismatches}")
    return actual


def _endpoint_authority(
    *,
    workbook_path: Path,
    direction: str,
    analysis_window_start: int,
    analysis_window_end: int,
) -> tuple[OperationalEndpointAuthorityV1, int, int]:
    imported = import_v3_multi_period_workbook_v1(workbook_path)
    parameters = imported.base_workbook.parameters_b
    if direction == "outbound":
        fixed_first = parameters.terminal_1_first_departure
        fixed_last = parameters.terminal_1_last_departure
        fields = "terminal_1_first_departure,terminal_1_last_departure"
    elif direction == "inbound":
        fixed_first = parameters.terminal_2_first_departure
        fixed_last = parameters.terminal_2_last_departure
        fields = "terminal_2_first_departure,terminal_2_last_departure"
    else:
        raise ValueError(f"unsupported direction {direction!r}")
    return (
        OperationalEndpointAuthorityV1(
            route_id=str(parameters.route_id),
            direction=direction,
            analysis_window_start=analysis_window_start,
            analysis_window_end=analysis_window_end,
            fixed_first_departure=fixed_first,
            fixed_last_departure=fixed_last,
            authority_source=f"{workbook_path.resolve()}::THAM_SO_B::{fields}",
        ),
        parameters.trip_runtime_minutes,
        parameters.available_fleet_limit,
    )


def _selected_candidates(
    result: TailAwareCandidateSetV2,
) -> tuple[TailAwareSelectedCandidateV2, ...]:
    selected = (
        result.c1_demand_fit,
        result.c2_conservative,
        result.c3_balanced,
    )
    if any(item is None for item in selected):
        raise ValueError("all C1/C2/C3 tail-aware candidates must compile in the pilot")
    return tuple(item for item in selected if item is not None)


def _old_candidate_lookup(allocation_payload: Mapping[str, Any]) -> dict[tuple[str, str], Any]:
    result: dict[tuple[str, str], Any] = {}
    for candidate_set in allocation_payload["candidate_sets"]:
        direction = str(candidate_set["direction"])
        for key in _CANDIDATE_KEYS:
            item = candidate_set[key]
            if item is not None:
                result[(direction, str(item["candidate_id"]))] = item
    return result


def _old_compilation_lookup(
    clean_payload: Mapping[str, Any], route_id: str
) -> dict[tuple[str, str], Any]:
    route = next(item for item in clean_payload["routes"] if str(item["route_id"]) == route_id)
    return {
        (str(item["direction"]), str(item["candidate_id"])): item for item in route["compilations"]
    }


def _new_candidate_payload(item: TailAwareSelectedCandidateV2) -> dict[str, Any]:
    compilation = item.plan.compilation
    evidence = item.plan.tail_evidence
    if compilation is None or evidence is None:
        raise AssertionError("selected tail-aware candidate must be fully compiled")
    return {
        "candidate_id": item.candidate_id,
        "semantic_status": item.semantic_status,
        "allocation": asdict(item.plan.allocation),
        "tail_settlement_evidence": asdict(evidence),
        "compilation": clean_boundary_compilation_to_dict_v1(compilation),
    }


def _comparison_payload(
    *,
    direction: str,
    selected: TailAwareSelectedCandidateV2,
    old_candidate: Mapping[str, Any],
    old_compilation: Mapping[str, Any],
) -> dict[str, Any]:
    compilation = selected.plan.compilation
    tail = selected.plan.tail_evidence
    if compilation is None or tail is None:
        raise AssertionError("comparison requires a compiled tail plan")
    old_slices = old_compilation["demand_regime_slices"]
    old_services = old_compilation["service_regimes"]
    old_tail_slice = old_slices[-1]
    old_previous_slice = old_slices[-2]
    new_tail_slice = compilation.demand_regime_slices[-1]
    new_previous_slice = compilation.demand_regime_slices[-2]
    old_first_allocation = old_candidate["regime_allocations"][0]
    new_first_allocation = selected.plan.allocation.core_regime_evidence[0]
    old_inversion = int(old_tail_slice["uniform_headway_minutes"]) < int(
        old_previous_slice["uniform_headway_minutes"]
    )
    new_inversion = tail.tail_headway < tail.previous_core_headway
    return {
        "direction": direction,
        "candidate_id": selected.candidate_id,
        "before_clean_boundary_v2": {
            "allocation_vector": [
                int(item["allocated_trip_count"]) for item in old_candidate["regime_allocations"]
            ],
            "demand_mismatch": float(old_candidate["demand_mismatch"]),
            "moved_trips_vs_b": int(old_candidate["moved_trips"]),
            "first_edge_demand_duration_minutes": int(old_first_allocation["duration_minutes"]),
            "first_edge_nominal_headway": float(old_first_allocation["nominal_headway"]),
            "previous_core_headway": int(old_previous_slice["uniform_headway_minutes"]),
            "tail_trip_count": int(old_tail_slice["authoritative_trip_count"]),
            "tail_headway": int(old_tail_slice["uniform_headway_minutes"]),
            "tail_start": int(old_tail_slice["first_departure"]),
            "tail_last_departure": int(old_tail_slice["last_departure"]),
            "service_intensity_inversion": old_inversion,
            "service_regimes": old_services,
        },
        "after_end_tail_v3": {
            "allocation_vector": [
                *selected.plan.allocation.core_trip_counts,
                selected.plan.allocation.residual_tail_trip_count,
            ],
            "core_demand_mismatch": selected.plan.allocation.core_demand_mismatch,
            "full_day_demand_mismatch": (
                selected.plan.allocation.full_day_demand_mismatch_after_tail
            ),
            "moved_trips_vs_b": selected.plan.allocation.moved_trips_vs_b,
            "first_edge_demand_duration_minutes": (
                new_first_allocation.effective_duration_minutes
                + (new_first_allocation.effective_start - new_first_allocation.demand_start) // 60
            ),
            "first_edge_effective_duration_minutes": (
                new_first_allocation.effective_duration_minutes
            ),
            "first_edge_nominal_operational_headway": (
                new_first_allocation.nominal_operational_headway
            ),
            "previous_core_headway": new_previous_slice.uniform_headway_minutes,
            "tail_trip_count": new_tail_slice.authoritative_trip_count,
            "tail_headway": new_tail_slice.uniform_headway_minutes,
            "tail_start": new_tail_slice.first_departure,
            "tail_last_departure": new_tail_slice.last_departure,
            "service_intensity_inversion": new_inversion,
            "service_regimes": [asdict(item) for item in compilation.service_regimes],
        },
        "changes": {
            "tail_trip_count": (
                new_tail_slice.authoritative_trip_count
                - int(old_tail_slice["authoritative_trip_count"])
            ),
            "tail_headway_minutes": (
                new_tail_slice.uniform_headway_minutes
                - int(old_tail_slice["uniform_headway_minutes"])
            ),
            "tail_start_minutes": (
                new_tail_slice.first_departure - int(old_tail_slice["first_departure"])
            )
            // 60,
            "service_intensity_inversion_removed": old_inversion and not new_inversion,
        },
    }


def run_end_tail_pilot_v2(
    *,
    repo_root: Path,
    route_workbooks: Mapping[str, Path],
    output_directory: Path,
    config: TailAwareAllocatorConfigV2 = DEFAULT_TAIL_AWARE_ALLOCATOR_CONFIG_V2,
) -> dict[str, Any]:
    fingerprints_before = frozen_prior_fingerprints_v2(repo_root)
    clean_payload = json.loads(
        (
            repo_root
            / "outputs"
            / "final_scenario_c_clean_boundaries_v2"
            / "clean_boundary_pilot_report.json"
        ).read_text(encoding="utf-8")
    )
    routes_payload: list[dict[str, Any]] = []
    total_outliers = 0
    total_compiled = 0

    for route_id in sorted(route_workbooks, key=int):
        workbook_path = route_workbooks[route_id]
        allocation_payload = json.loads(
            (
                repo_root
                / "outputs"
                / "demand_regime_trip_allocation"
                / f"route_{route_id}_demand_regime_trip_allocations.json"
            ).read_text(encoding="utf-8")
        )
        old_candidates = _old_candidate_lookup(allocation_payload)
        old_compilations = _old_compilation_lookup(clean_payload, route_id)
        selected_by_direction: dict[str, tuple[TailAwareSelectedCandidateV2, ...]] = {}
        direction_payload: list[dict[str, Any]] = []
        runtime_minutes: int | None = None
        fleet_ceiling: int | None = None

        for candidate_set in allocation_payload["candidate_sets"]:
            direction = str(candidate_set["direction"])
            b_reference = candidate_set["b_reference"]
            regimes = tuple(
                tail_aware_regime_from_mapping_v2(item)
                for item in b_reference["regime_allocations"]
            )
            authority, route_runtime, route_ceiling = _endpoint_authority(
                workbook_path=workbook_path,
                direction=direction,
                analysis_window_start=regimes[0].start_time,
                analysis_window_end=regimes[-1].end_time,
            )
            runtime_minutes = route_runtime
            fleet_ceiling = route_ceiling
            frontier = allocate_tail_aware_trips_v2(
                regimes=regimes,
                total_trips=int(candidate_set["total_trips"]),
                endpoint_authority=authority,
                config=config,
            )
            result = select_tail_aware_candidates_v2(
                route_id=route_id,
                direction=direction,
                regimes=regimes,
                endpoint_authority=authority,
                frontier=frontier,
                config=config,
            )
            selected = _selected_candidates(result)
            selected_by_direction[direction] = selected
            total_compiled += len(selected)
            for item in selected:
                if item.plan.compilation is not None:
                    total_outliers += len(
                        scan_serialized_headway_outliers_v1(item.plan.compilation)
                    )
            direction_payload.append(
                {
                    "direction": direction,
                    "endpoint_authority": asdict(authority),
                    "tail_eligibility": asdict(result.eligibility),
                    "effective_service_spans": [asdict(item) for item in frontier.effective_spans],
                    "service_floor_headway_minutes": frontier.service_floor_headway_minutes,
                    "service_floor_provenance": frontier.service_floor_provenance,
                    "tail_ideal_trip_count": frontier.tail_ideal_trip_count,
                    "b_full_day_demand_mismatch": frontier.b_full_day_demand_mismatch,
                    "core_frontier": {
                        "generated_record_count": frontier.generated_record_count,
                        "bounded_frontier_limit": frontier.bounded_frontier_limit,
                        "retained_candidate_count": len(frontier.candidates),
                        "candidates": [asdict(item) for item in frontier.candidates],
                    },
                    "compile_screen": {
                        "feasible_compiled_candidate_count": (
                            result.feasible_compiled_candidate_count
                        ),
                        "infeasible_candidate_count": result.infeasible_candidate_count,
                        "failure_code_counts": result.failure_code_counts,
                        "pareto_frontier_size": result.pareto_frontier_size,
                    },
                    "selected_candidates": [_new_candidate_payload(item) for item in selected],
                    "before_after": [
                        _comparison_payload(
                            direction=direction,
                            selected=item,
                            old_candidate=old_candidates[(direction, item.candidate_id)],
                            old_compilation=old_compilations[(direction, item.candidate_id)],
                        )
                        for item in selected
                    ],
                }
            )

        if runtime_minutes is None or fleet_ceiling is None:
            raise ValueError(f"route {route_id} authority is incomplete")
        outbound = {item.candidate_id: item for item in selected_by_direction["outbound"]}
        inbound = {item.candidate_id: item for item in selected_by_direction["inbound"]}
        candidate_ids = ("C1_DEMAND_FIT", "C2_CONSERVATIVE", "C3_BALANCED")
        matrix = tuple(
            validate_fleet_combination_v1(
                route_id=route_id,
                outbound=outbound[outbound_id].plan.compilation,
                inbound=inbound[inbound_id].plan.compilation,
                outbound_allocation={
                    "demand_mismatch": (
                        outbound[outbound_id].plan.allocation.full_day_demand_mismatch_after_tail
                    ),
                    "moved_trips": outbound[outbound_id].plan.allocation.moved_trips_vs_b,
                },
                inbound_allocation={
                    "demand_mismatch": (
                        inbound[inbound_id].plan.allocation.full_day_demand_mismatch_after_tail
                    ),
                    "moved_trips": inbound[inbound_id].plan.allocation.moved_trips_vs_b,
                },
                runtime_minutes=runtime_minutes,
                minimum_layover_minutes=PILOT_MINIMUM_LAYOVER_MINUTES_V1,
                fleet_ceiling=fleet_ceiling,
            )
            for outbound_id in candidate_ids
            for inbound_id in candidate_ids
        )
        selection = select_final_candidate_pair_v1(route_id, matrix)
        selected_outbound = outbound[selection.outbound_candidate_id]
        selected_inbound = inbound[selection.inbound_candidate_id]
        if selected_outbound.plan.compilation is None or selected_inbound.plan.compilation is None:
            raise AssertionError("fleet selection requires exact compiled timetables")
        fleet_plan = build_minimum_fleet_plan_v1(
            route_id=route_id,
            outbound_candidate_id=selection.outbound_candidate_id,
            inbound_candidate_id=selection.inbound_candidate_id,
            outbound_departures=selected_outbound.plan.compilation.exact_departures,
            inbound_departures=selected_inbound.plan.compilation.exact_departures,
            runtime_minutes=runtime_minutes,
            minimum_layover_minutes=PILOT_MINIMUM_LAYOVER_MINUTES_V1,
        )
        routes_payload.append(
            {
                "route_id": route_id,
                "route_name": allocation_payload["route_name"],
                "canonical_workbook": str(workbook_path.resolve()),
                "canonical_workbook_sha256": _sha256(workbook_path),
                "runtime_minutes": runtime_minutes,
                "minimum_layover_minutes": PILOT_MINIMUM_LAYOVER_MINUTES_V1,
                "minimum_layover_authority": "UNCHANGED_FIXED_TIMETABLE_VALIDATOR",
                "fleet_ceiling": fleet_ceiling,
                "directions": direction_payload,
                "fleet_matrix": [asdict(item) for item in matrix],
                "candidate_pair_count": len(matrix),
                "final_selection": asdict(selection),
                "selected_fleet_plan": asdict(fleet_plan),
                "selected_product_rows": {
                    "outbound": [
                        asdict(item)
                        for item in build_product_headway_rows_v1(
                            selected_outbound.plan.compilation
                        )
                    ],
                    "inbound": [
                        asdict(item)
                        for item in build_product_headway_rows_v1(selected_inbound.plan.compilation)
                    ],
                },
            }
        )

    fingerprints_after = frozen_prior_fingerprints_v2(repo_root)
    payload = {
        "review_profile": END_TAIL_PILOT_PROFILE_V2,
        "output_version": END_TAIL_OUTPUT_VERSION,
        "authority_status": "PILOT_FOR_HUMAN_REVIEW_NOT_FINAL",
        "architecture": [
            "VALIDATED_DEMAND_REGIME_PLAN",
            "SCALE_FREE_TAIL_ELIGIBILITY",
            "BOUNDED_CORE_ALLOCATION_FRONTIER",
            "RESIDUAL_TAIL_TRIP_COUNT",
            "BACKWARD_FIXED_LAST_END_TAIL_SETTLEMENT",
            "CLEAN_FULL_TIMETABLE",
            "UNCHANGED_FIXED_TIMETABLE_FLEET_VALIDATOR",
        ],
        "candidate_semantic_note": (
            "C1 ranks feasible plans by core mismatch first; C2 minimizes movement among "
            "full-day improvements; C3 applies the existing normalized parameter-free "
            "balanced rule to the feasible post-settlement Pareto frontier."
        ),
        "routes": routes_payload,
        "pilot_totals": {
            "compiled_direction_candidates": total_compiled,
            "fleet_combinations": sum(item["candidate_pair_count"] for item in routes_payload),
            "serialized_headway_outliers": total_outliers,
        },
        "frozen_prior_fingerprints_before": fingerprints_before,
        "frozen_prior_fingerprints_after": fingerprints_after,
        "frozen_prior_artifacts_unchanged": fingerprints_before == fingerprints_after,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "end_tail_settlement_pilot_report.json"
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def compact_end_tail_summary_v2(payload: Mapping[str, Any]) -> str:
    lines = [
        f"profile={payload['review_profile']}",
        f"authority={payload['authority_status']}",
        f"compiled={payload['pilot_totals']['compiled_direction_candidates']}",
        f"fleet_combinations={payload['pilot_totals']['fleet_combinations']}",
        f"outliers={payload['pilot_totals']['serialized_headway_outliers']}",
    ]
    for route in payload["routes"]:
        selection = route["final_selection"]
        lines.append(
            f"route={route['route_id']} selected="
            f"{selection['outbound_candidate_id']}/{selection['inbound_candidate_id']} "
            f"fleet={selection['fleet_requirement']}/{selection['fleet_ceiling']}"
        )
        for direction in route["directions"]:
            for candidate in direction["selected_candidates"]:
                tail = candidate["tail_settlement_evidence"]
                lines.append(
                    f"  {direction['direction']} {candidate['candidate_id']} "
                    f"tail={tail['tail_trip_count']}@{tail['tail_headway']} "
                    f"{format_hhmm(tail['tail_start'])}-{format_hhmm(tail['tail_last_departure'])} "
                    f"capacity={tail['min_feasible_tail_trip_count']}-"
                    f"{tail['max_feasible_tail_trip_count']}"
                )
    return "\n".join(lines)


__all__ = [
    "END_TAIL_OUTPUT_VERSION",
    "END_TAIL_PILOT_PROFILE_V2",
    "compact_end_tail_summary_v2",
    "frozen_prior_fingerprints_v2",
    "run_end_tail_pilot_v2",
]

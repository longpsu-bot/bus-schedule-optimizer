"""Production orchestration and deterministic artifacts for the local V3 runner."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts_v1 import (
    TWO_STAGE_QUALITY_VECTOR_NAMES_V1,
    DemandConfidence,
    DemandProfileDerivationResultV1,
    DemandResponseMode,
    DemandSourceType,
    NormalizationOptions,
    NormalizedInputBundleV1,
    ScenarioBEvaluationBundleV1,
    ScenarioCOptimizationModeV1,
    SolverPolicyV1,
    TwoStageScenarioCResultV1,
    build_two_stage_uniform_request_v1,
    derive_demand_profile_v1,
    evaluate_scenario_b_v1,
    normalize_multi_period_profile_v1,
    run_two_stage_scenario_c_v1,
    trip_allocation_plan_to_contract_dict_v1,
    two_stage_result_to_contract_dict_v1,
)
from .contracts_v1.solver_models import ScheduleSolutionV1
from .contracts_v1.two_stage_models import TripAllocationPlanV1
from .time_utils import format_hhmm
from .v3_workbook import ImportedV3WorkbookV1, import_v3_multi_period_workbook_v1

V3_MULTI_PERIOD_RUNNER_PROFILE_V1 = "v3_multi_period_runner_v1"
DEFAULT_V3_TOTAL_SOLVE_BUDGET_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class V3ProfileRunV1:
    input_path: Path
    imported: ImportedV3WorkbookV1
    derivation: DemandProfileDerivationResultV1
    normalized_inputs: NormalizedInputBundleV1
    b_evaluation: ScenarioBEvaluationBundleV1
    result: TwoStageScenarioCResultV1
    payload: dict[str, object]


def _time(value: int) -> str:
    return f"{format_hhmm(value)}:00"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _normalization_options(path: Path, imported: ImportedV3WorkbookV1) -> NormalizationOptions:
    authority = imported.base_workbook.authority_metadata
    imported_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return NormalizationOptions(
        source_id=path.name,
        imported_at=imported_at,
        demand_source_type=(authority.demand_source_type or DemandSourceType.AGGREGATE_REPORT),
        demand_confidence=(authority.demand_confidence or DemandConfidence.UNKNOWN),
        demand_response_mode=(authority.demand_response_mode or DemandResponseMode.STATIC),
        source_notes=authority.source_notes,
        optimization_mode=ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE,
    )


def _quality(vector: tuple[int, ...] | None) -> dict[str, int] | None:
    if vector is None:
        return None
    return dict(zip(TWO_STAGE_QUALITY_VECTOR_NAMES_V1, vector, strict=True))


def _period_diagnostic_payload(
    derivation: DemandProfileDerivationResultV1,
) -> list[dict[str, object]]:
    return [
        {
            "period_id": item.period_id,
            "direction": item.direction.value,
            "average_daily_passengers": item.average_daily_passengers,
            "normalized_share_by_time_block": [
                {
                    "start": _time(start),
                    "end": _time(end),
                    "share": share,
                }
                for start, end, share in item.normalized_block_shares
            ],
            "peak_block": {
                "start": _time(item.peak_block_start),
                "end": _time(item.peak_block_end),
            },
            "peak_share": item.peak_share,
            "compared_period_id": item.compared_period_id,
            "maximum_shape_distance": item.maximum_shape_distance,
            "shape_distance_metric": "L1_DISTANCE_DIVIDED_BY_TWO",
            "shape_distance_threshold": item.shape_distance_threshold,
            "structural_change_detected": item.structural_change_detected,
        }
        for item in derivation.period_diagnostics
    ]


def _stage_2_plan_statuses(
    result: TwoStageScenarioCResultV1,
    plans: tuple[TripAllocationPlanV1, ...],
) -> list[dict[str, object]]:
    diagnostics = {
        item.allocation_plan_fingerprint: item
        for item in result.diagnostics.stage_2_infeasibility_diagnostics
    }
    selected = (
        result.allocation_plan.allocation_fingerprint
        if result.allocation_plan is not None
        else None
    )
    output: list[dict[str, object]] = []
    for plan in plans[: result.diagnostics.stage_2_allocation_attempt_count]:
        diagnostic = diagnostics.get(plan.allocation_fingerprint)
        if diagnostic is not None:
            status = diagnostic.native_solver_status.value
        elif plan.allocation_fingerprint == selected:
            status = (
                result.native_solver_status.value
                if result.native_solver_status is not None
                else "UNKNOWN"
            )
        else:
            status = "UNKNOWN"
        output.append(
            {
                "allocation_plan_fingerprint": plan.allocation_fingerprint,
                "rank": plan.rank,
                "status": status,
            }
        )
    return output


def _regime_payload(
    result: TwoStageScenarioCResultV1,
) -> list[dict[str, object]]:
    solution = result.candidate_outcome.solution if result.candidate_outcome is not None else None
    if solution is None:
        return []
    final_tail_ids = {
        regime.regime_id
        for regime in (result.allocation_plan.proposed_regimes if result.allocation_plan else ())
        if regime.is_final_service_tail
    }
    return [
        {
            "direction": item.direction.value,
            "regime_id": item.regime_id,
            "start": _time(item.start_time),
            "end": _time(item.end_time),
            "trip_count": item.trip_count,
            "uniform_headway_minutes": (
                item.actual_headway_sequence[0] if item.actual_headway_sequence else None
            ),
            "boundary_reason": item.boundary_reason,
            "is_final_service_tail": item.regime_id in final_tail_ids,
        }
        for item in solution.c_headway_regimes
    ]


def _timetable_c_payload(
    solution: ScheduleSolutionV1 | None,
    normalized: NormalizedInputBundleV1,
) -> list[dict[str, object]]:
    if solution is None:
        return []
    source = {item.trip_id: item for item in normalized.scenario_b.exact_timetable}
    return [
        {
            "c_trip_id": item.c_trip_id,
            "source_b_trip_id": item.source_b_trip_id,
            "direction": item.direction.value,
            "departure_terminal": item.departure_terminal.value,
            "b_departure_time": _time(item.b_departure_time),
            "c_departure_time": _time(item.c_departure_time),
            "arrival_time": _time(
                item.c_departure_time + source[item.source_b_trip_id].runtime_minutes * 60
            ),
            "shift_minutes": item.shift_minutes,
            "headway_regime_id": item.headway_regime_id,
            "vehicle_assignment": item.vehicle_assignment,
        }
        for item in solution.c_exact_timetable
    ]


def build_v3_result_payload_v1(
    run_input_path: Path,
    derivation: DemandProfileDerivationResultV1,
    normalized: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    result: TwoStageScenarioCResultV1,
    stage_1_plans: tuple[TripAllocationPlanV1, ...],
) -> dict[str, object]:
    scenario_b = normalized.scenario_b
    solution = result.candidate_outcome.solution if result.candidate_outcome is not None else None
    selected_plan = (
        trip_allocation_plan_to_contract_dict_v1(result.allocation_plan)
        if result.allocation_plan is not None
        else None
    )
    necessary = (
        _jsonable(asdict(result.allocation_plan.necessary_feasibility))
        if result.allocation_plan is not None
        else None
    )
    diagnostics = result.diagnostics
    return {
        "runner_profile": V3_MULTI_PERIOD_RUNNER_PROFILE_V1,
        "input_file": run_input_path.name,
        "route_id": scenario_b.route_id,
        "route_name": scenario_b.route_name,
        "selected_profile": {
            "profile_id": derivation.profile.profile_id,
            "profile_fingerprint": derivation.profile.profile_fingerprint,
            "included_period_ids": list(derivation.profile.included_period_ids),
            "aggregation_method": derivation.profile.aggregation_method.value,
            "period_weight_method": derivation.profile.period_weight_method,
            "total_observation_days": derivation.profile.total_observation_days,
            "direction_grain": derivation.profile.direction_grain.value,
        },
        "period_diagnostics": _period_diagnostic_payload(derivation),
        "diagnostic_codes": list(derivation.diagnostic_codes),
        "scenario_b": {
            "total_daily_trips": scenario_b.total_daily_trips,
            "trips_by_direction": {
                "outbound": scenario_b.trips_by_direction.outbound,
                "inbound": scenario_b.trips_by_direction.inbound,
            },
            "available_fleet_limit": scenario_b.available_fleet_limit,
            "runtime": scenario_b.trip_runtime_minutes,
            "first_departures": {
                "terminal_1": _time(scenario_b.first_departures.terminal_1),
                "terminal_2": _time(scenario_b.first_departures.terminal_2),
            },
            "last_departures": {
                "terminal_1": _time(scenario_b.last_departures.terminal_1),
                "terminal_2": _time(scenario_b.last_departures.terminal_2),
            },
        },
        "stage_1": {
            "candidate_count": diagnostics.stage_1_candidate_count,
            "admitted_count": diagnostics.stage_1_admissible_allocation_count,
            "pruned_count": diagnostics.stage_1_necessary_feasibility_pruned_count,
            "selected_allocation_plan": selected_plan,
            "objective_vector": (
                list(result.allocation_plan.objective_vector)
                if result.allocation_plan is not None
                else None
            ),
            "necessary_feasibility": necessary,
        },
        "stage_2": {
            "allocation_attempt_count": diagnostics.stage_2_allocation_attempt_count,
            "per_plan_status": _stage_2_plan_statuses(result, stage_1_plans),
            "per_plan_infeasibility_diagnostics": [
                _jsonable(asdict(item)) for item in diagnostics.stage_2_infeasibility_diagnostics
            ],
        },
        "aggregate_native_status": (
            result.native_solver_status.value if result.native_solver_status is not None else None
        ),
        "final_acceptance_state": result.final_acceptance_state.value,
        "quality": {
            "B": _quality(result.b_quality_vector),
            "C": _quality(result.c_quality_vector),
        },
        "final_service_regimes": _regime_payload(result),
        "final_service_tail_metrics": [
            {
                **_jsonable(asdict(item)),
                "final_tail_start": _time(item.final_tail_start),
                "final_tail_end": _time(item.final_tail_end),
            }
            for item in result.final_tail_metrics
        ],
        "shift_metrics": {
            "shifted_trip_count": solution.shifted_trip_count if solution else 0,
            "total_shift_minutes": solution.total_shift_minutes if solution else 0,
            "maximum_shift_minutes": solution.maximum_shift_minutes if solution else 0,
        },
        "fleet": {
            "available": scenario_b.available_fleet_limit,
            "required": (
                solution.minimum_required_fleet
                if solution is not None
                else b_evaluation.fleet_assessment.minimum_required_fleet
            ),
        },
        "budget": {
            "total_seconds": diagnostics.total_budget_seconds,
            "consumed_seconds": diagnostics.total_solve_duration,
            "exhausted": diagnostics.budget_exhausted,
        },
        "timetable_c": _timetable_c_payload(solution, normalized),
        "explanations": list(result.explanations),
        "limitations": [
            *derivation.profile.limitations,
            *derivation.limitations,
            *result.limitations,
        ],
        "engine_result": two_stage_result_to_contract_dict_v1(result),
    }


def run_v3_profile_v1(
    input_path: str | Path,
    profile_id: str,
    *,
    total_budget_seconds: float = DEFAULT_V3_TOTAL_SOLVE_BUDGET_SECONDS,
    shape_distance_threshold: float = 0.15,
) -> V3ProfileRunV1:
    path = Path(input_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if not 0 < total_budget_seconds <= DEFAULT_V3_TOTAL_SOLVE_BUDGET_SECONDS:
        raise ValueError(
            "total_budget_seconds must be positive and cannot exceed the ordinary 120-second budget"
        )
    imported = import_v3_multi_period_workbook_v1(path)
    derivation = derive_demand_profile_v1(
        imported.multi_period_demand,
        profile_id,
        shape_distance_threshold=shape_distance_threshold,
    )
    normalized = normalize_multi_period_profile_v1(
        imported.base_workbook,
        imported.multi_period_demand,
        derivation.profile,
        _normalization_options(path, imported),
    )
    b_evaluation = evaluate_scenario_b_v1(normalized)
    context, solver = build_two_stage_uniform_request_v1(
        normalized,
        b_evaluation,
        solver_policy=SolverPolicyV1(time_limit_seconds=total_budget_seconds),
        demand_profile_fingerprint=derivation.profile.profile_fingerprint,
    )
    result = run_two_stage_scenario_c_v1(context, solver)
    detailed = solver.last_detailed_run
    if detailed is None:  # pragma: no cover - the adapter guarantees this
        raise AssertionError("two-stage solver did not retain detailed diagnostics")
    payload = build_v3_result_payload_v1(
        path,
        derivation,
        normalized,
        b_evaluation,
        result,
        detailed.stage_1_result.plans,
    )
    return V3ProfileRunV1(
        input_path=path,
        imported=imported,
        derivation=derivation,
        normalized_inputs=normalized,
        b_evaluation=b_evaluation,
        result=result,
        payload=payload,
    )


def write_deterministic_json(path: str | Path, payload: dict[str, object]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


__all__ = [
    "DEFAULT_V3_TOTAL_SOLVE_BUDGET_SECONDS",
    "V3_MULTI_PERIOD_RUNNER_PROFILE_V1",
    "V3ProfileRunV1",
    "build_v3_result_payload_v1",
    "run_v3_profile_v1",
    "write_deterministic_json",
]

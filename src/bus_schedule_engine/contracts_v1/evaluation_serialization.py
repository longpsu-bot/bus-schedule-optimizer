from __future__ import annotations

from bus_schedule_engine.time_utils import format_hhmm

from .demand_resolution import DemandAnalysisBlockV1, DemandResolutionContractV1
from .evaluation import (
    BlockSupplyPlanV1,
    EvaluationDimensionV1,
    EvaluationIssueV1,
    ScheduleEvaluationResultV1,
)


def demand_resolution_to_contract_dict(
    contract: DemandResolutionContractV1,
) -> dict[str, object]:
    return {
        "contract_version": contract.contract_version,
        "source_resolution_type": contract.source_resolution_type.value,
        "source_resolution_minutes": contract.source_resolution_minutes,
        "source_is_timestamp_level": contract.source_is_timestamp_level,
        "source_is_trip_level": contract.source_is_trip_level,
        "source_is_irregular": contract.source_is_irregular,
        "block_mode": contract.block_mode.value,
        "manual_boundaries": [format_hhmm(item) for item in contract.manual_boundaries],
        "minimum_block_duration": contract.minimum_block_duration,
        "maximum_block_duration": contract.maximum_block_duration,
        "minimum_sustained_intervals": contract.minimum_sustained_intervals,
        "material_change_ratio": contract.material_change_ratio,
        "smoothing_method": contract.smoothing_method.value,
        "interpolation_method": contract.interpolation_method.value,
        "confidence_level": contract.confidence_level.value,
        "observation_days": contract.observation_days,
        "sample_count": contract.sample_count,
    }


def demand_analysis_block_to_contract_dict(
    block: DemandAnalysisBlockV1,
) -> dict[str, object]:
    return {
        "contract_version": block.contract_version,
        "block_id": block.block_id,
        "start_time": format_hhmm(block.start_time),
        "end_time": format_hhmm(block.end_time),
        "duration_minutes": block.duration_minutes,
        "direction": block.direction.value,
        "observed_passengers": block.observed_passengers,
        "demand_rate_per_hour": block.demand_rate_per_hour,
        "source_interval_ids": list(block.source_interval_ids),
        "source_resolution_type": block.source_resolution_type.value,
        "source_resolution_minutes": block.source_resolution_minutes,
        "block_mode": block.block_mode.value,
        "aggregation_method": block.aggregation_method.value,
        "confidence": block.confidence.value,
        "interpolation_status": block.interpolation_status.value,
        "observation_days": block.observation_days,
        "sample_count": block.sample_count,
        "block_boundary_reason": block.block_boundary_reason.value,
    }


def block_supply_plan_to_contract_dict(plan: BlockSupplyPlanV1) -> dict[str, object]:
    return {
        "contract_version": plan.contract_version,
        "scenario": plan.scenario.value,
        "direction": plan.direction.value,
        "block_id": plan.block_id,
        "block_start": format_hhmm(plan.block_start),
        "block_end": format_hhmm(plan.block_end),
        "duration_minutes": plan.duration_minutes,
        "passenger_demand": plan.passenger_demand,
        "demand_rate_per_hour": plan.demand_rate_per_hour,
        "vehicle_capacity": plan.vehicle_capacity,
        "a_trip_count": plan.a_trip_count,
        "b_trip_count": plan.b_trip_count,
        "c_planned_trip_count": plan.c_planned_trip_count,
        "c_actual_trip_count": plan.c_actual_trip_count,
        "trip_rate_per_hour": plan.trip_rate_per_hour,
        "required_trips_85": plan.required_trips_85,
        "required_trips_90": plan.required_trips_90,
        "required_trip_rate_85": plan.required_trip_rate_85,
        "required_trip_rate_90": plan.required_trip_rate_90,
        "nominal_capacity": plan.nominal_capacity,
        "capacity_at_85": plan.capacity_at_85,
        "capacity_at_90": plan.capacity_at_90,
        "load_factor": plan.load_factor,
        "shortage": plan.shortage,
        "status": plan.status.value,
        "allocation_reason": plan.allocation_reason,
        "confidence": plan.confidence.value,
    }


def _issue_to_dict(issue: EvaluationIssueV1) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": issue.code,
        "severity": issue.severity.value,
        "message": issue.message,
        "references": list(issue.references),
    }
    if issue.suggestion is not None:
        payload["suggestion"] = issue.suggestion
    return payload


def _dimension_to_dict(dimension: EvaluationDimensionV1) -> dict[str, object]:
    return {
        "status": dimension.status.value,
        "issues": [_issue_to_dict(item) for item in dimension.issues],
        "evidence": list(dimension.evidence),
        "explanation": dimension.explanation,
        "confidence": dimension.confidence.value,
    }


def schedule_evaluation_to_contract_dict(
    evaluation: ScheduleEvaluationResultV1,
) -> dict[str, object]:
    return {
        "contract_version": evaluation.contract_version,
        "scenario_id": evaluation.scenario_id.value,
        "disposition": evaluation.disposition.value,
        "input_validity": _dimension_to_dict(evaluation.input_validity),
        "parameter_consistency": _dimension_to_dict(
            evaluation.parameter_consistency
        ),
        "technical_feasibility": _dimension_to_dict(
            evaluation.technical_feasibility
        ),
        "demand_suitability": _dimension_to_dict(evaluation.demand_suitability),
        "fleet_feasibility": _dimension_to_dict(evaluation.fleet_feasibility),
        "headway_quality": _dimension_to_dict(evaluation.headway_quality),
        "block_evaluations": [
            {
                "block_id": item.block_id,
                "direction": item.direction.value,
                "load_factor": item.load_factor,
                "shortage": item.shortage,
                "status": item.status.value,
                "confidence": item.confidence.value,
            }
            for item in evaluation.block_evaluations
        ],
        "warnings": list(evaluation.warnings),
        "limitations": list(evaluation.limitations),
        "confidence": evaluation.confidence.value,
    }

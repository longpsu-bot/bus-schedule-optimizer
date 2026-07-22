from __future__ import annotations

from bus_schedule_engine.time_utils import format_hhmm

from .models import (
    DemandAnalysisBlock,
    DemandResolutionEvidence,
    DimensionResult,
    EvaluationIssue,
    ScheduleEvaluationResultV1,
)


def demand_resolution_to_dict(value: DemandResolutionEvidence) -> dict[str, object]:
    return {
        "contract_version": value.contract_version,
        "source_resolution_type": value.source_resolution_type.value,
        "source_resolution_minutes": value.source_resolution_minutes,
        "source_is_timestamp_level": value.source_is_timestamp_level,
        "source_is_trip_level": value.source_is_trip_level,
        "source_is_irregular": value.source_is_irregular,
        "block_mode": value.block_mode.value,
        "manual_boundaries": [format_hhmm(item) for item in value.manual_boundaries],
        "minimum_block_duration": value.minimum_block_duration,
        "maximum_block_duration": value.maximum_block_duration,
        "minimum_sustained_intervals": value.minimum_sustained_intervals,
        "material_change_ratio": value.material_change_ratio,
        "smoothing_method": value.smoothing_method,
        "interpolation_method": value.interpolation_method,
        "confidence_level": value.confidence_level.value,
        "observation_days": value.observation_days,
        "sample_count": value.sample_count,
    }


def demand_block_to_dict(value: DemandAnalysisBlock) -> dict[str, object]:
    return {
        "contract_version": value.contract_version,
        "block_id": value.block_id,
        "start_time": format_hhmm(value.start_time),
        "end_time": format_hhmm(value.end_time),
        "duration_minutes": value.duration_minutes,
        "direction": value.direction.value,
        "observed_passengers": value.observed_passengers,
        "demand_rate_per_hour": value.demand_rate_per_hour,
        "source_interval_ids": list(value.source_interval_ids),
        "source_resolution_type": value.source_resolution_type.value,
        "source_resolution_minutes": value.source_resolution_minutes,
        "block_mode": value.block_mode.value,
        "aggregation_method": value.aggregation_method.value,
        "confidence": value.confidence.value,
        "interpolation_status": value.interpolation_status.value,
        "observation_days": value.observation_days,
        "sample_count": value.sample_count,
        "block_boundary_reason": value.block_boundary_reason.value,
    }


def _issue_to_dict(value: EvaluationIssue) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": value.code,
        "severity": value.severity.value,
        "message": value.message,
        "references": list(value.references),
    }
    if value.suggestion:
        payload["suggestion"] = value.suggestion
    return payload


def _dimension_to_dict(value: DimensionResult) -> dict[str, object]:
    return {
        "status": value.status.value,
        "issues": [_issue_to_dict(item) for item in value.issues],
        "evidence": list(value.evidence),
        "explanation": value.explanation,
        "confidence": value.confidence.value,
    }


def schedule_evaluation_to_dict(value: ScheduleEvaluationResultV1) -> dict[str, object]:
    return {
        "contract_version": value.contract_version,
        "scenario_id": value.scenario_id,
        "disposition": value.disposition.value,
        "input_validity": _dimension_to_dict(value.input_validity),
        "parameter_consistency": _dimension_to_dict(value.parameter_consistency),
        "technical_feasibility": _dimension_to_dict(value.technical_feasibility),
        "demand_suitability": _dimension_to_dict(value.demand_suitability),
        "fleet_feasibility": _dimension_to_dict(value.fleet_feasibility),
        "headway_quality": _dimension_to_dict(value.headway_quality),
        "block_evaluations": [
            {
                "block_id": item.block_id,
                "direction": item.direction.value,
                "load_factor": item.load_factor,
                "shortage": item.shortage,
                "status": item.status.value,
                "confidence": item.confidence.value,
            }
            for item in value.block_evaluations
        ],
        "warnings": list(value.warnings),
        "limitations": list(value.limitations),
        "confidence": value.confidence.value,
    }

"""Deterministic expert-review packages for one external Contract V1 workbook."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from statistics import mean, median

from .application_pipeline import (
    CONTRACT_V1_APPLICATION_ERROR,
    CONTRACT_V1_ARTIFACT_FAILED,
    WORKBOOK_IMPORT_INVALID,
    UnifiedApplicationRunV1,
    UnifiedApplicationStatusV1,
    run_unified_application_pipeline_v1,
)
from .contracts_v1 import SERVICE_QUALITY_OBJECTIVE_NAMES_V1, GenerationResultStatus
from .contracts_v1.models import ContractDirection, ExactTimetableTrip, ScenarioBInput
from .contracts_v1.terminal_occupancy import assess_terminal_occupancy_v1
from .importer import import_workbook
from .input_authority import WorkbookInputReadinessV1, assess_workbook_input_readiness_v1
from .models import ProtectedServiceFloorAssessmentV1
from .optimization_service import BusScheduleOptimizationResult, OptimizationAction, SolverChoice
from .time_utils import format_hhmm
from .unified_diagram import available_unified_directions_v1
from .unified_page5_artifacts import (
    UNIFIED_PAGE5_HTML_FILENAME,
    UNIFIED_PAGE5_PNG_FILENAME,
    UNIFIED_PAGE5_XLSX_FILENAME,
    UnifiedPage5ArtifactsV1,
    build_unified_page5_artifacts_v1,
)
from .unified_presentation import UnifiedPresentationBundleV1

REVIEW_PROFILE_V1 = "m6a2e_real_route_operational_review_v1"
EXPERT_REVIEW_REQUIRED = "EXPERT_REVIEW_REQUIRED"
REVIEW_JSON_FILENAME = "operational-review.json"
REVIEW_MARKDOWN_FILENAME = "operational-review.md"
REVIEW_IMPORTED_AT_V1 = datetime(1970, 1, 1, tzinfo=UTC)

_FIXED_RESOURCE_ACTIONS = {
    OptimizationAction.FIXED_RESOURCE_REDISTRIBUTION,
    OptimizationAction.FIXED_RESOURCE_RESPACE,
}
_STRUCTURAL_ACTIONS = {
    OptimizationAction.TRIP_INCREASE_RECOMMENDED,
    OptimizationAction.TRIP_REDUCTION_RECOMMENDED,
}
_PROTECTED_REJECTION_PREFIX = "PROTECTED_"
_ABSOLUTE_PATH_PATTERN = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s,;]+|(?:/[^/\s]+){2,}")


class ReviewPipelineStatusV1(StrEnum):
    REVIEW_COMPLETE = "REVIEW_COMPLETE"
    INPUT_NOT_READY = "INPUT_NOT_READY"
    PIPELINE_FAILED = "PIPELINE_FAILED"
    ARTIFACT_FAILED = "ARTIFACT_FAILED"


_REVIEW_EXIT_CODE_BY_STATUS_V1 = {
    ReviewPipelineStatusV1.REVIEW_COMPLETE: 0,
    ReviewPipelineStatusV1.INPUT_NOT_READY: 2,
    ReviewPipelineStatusV1.PIPELINE_FAILED: 3,
    ReviewPipelineStatusV1.ARTIFACT_FAILED: 4,
}


class ReviewDispositionV1(StrEnum):
    CURRENT_B_RETAINED = "CURRENT_B_RETAINED"
    ACCEPTED_CANDIDATE_AVAILABLE = "ACCEPTED_CANDIDATE_AVAILABLE"
    NO_ACCEPTED_CANDIDATE = "NO_ACCEPTED_CANDIDATE"
    SOLVER_DIVERGENCE_REVIEW_REQUIRED = "SOLVER_DIVERGENCE_REVIEW_REQUIRED"
    DEMAND_AUTHORITY_INCOMPLETE = "DEMAND_AUTHORITY_INCOMPLETE"
    PROTECTED_FLOOR_REJECTION = "PROTECTED_FLOOR_REJECTION"
    EXPERT_REVIEW_REQUIRED = EXPERT_REVIEW_REQUIRED


class NextDecisionCategoryV1(StrEnum):
    NO_ENGINE_CHANGE_REQUIRED = "NO_ENGINE_CHANGE_REQUIRED"
    DATA_AUTHORITY_GAP = "DATA_AUTHORITY_GAP"
    PRESENTATION_GAP = "PRESENTATION_GAP"
    OBJECTIVE_QUALITY_GAP = "OBJECTIVE_QUALITY_GAP"
    HARD_CONSTRAINT_GAP = "HARD_CONSTRAINT_GAP"
    FIXED_RESOURCE_SCOPE_GAP = "FIXED_RESOURCE_SCOPE_GAP"
    OUTSIDE_MODEL_SCOPE = "OUTSIDE_MODEL_SCOPE"


class ReviewFactAuthorityV1(StrEnum):
    SUPPLIED_FACT = "SUPPLIED_FACT"
    DERIVED_FACT = "DERIVED_FACT"
    ASSUMPTION = "ASSUMPTION"
    NOT_EVALUATED = "NOT_EVALUATED"


class ChecklistStatusV1(StrEnum):
    CONFIRMED_BY_INPUT = "CONFIRMED_BY_INPUT"
    DERIVED_FOR_REVIEW = "DERIVED_FOR_REVIEW"
    REQUIRES_EXPERT_CONFIRMATION = "REQUIRES_EXPERT_CONFIRMATION"
    NOT_EVALUATED = "NOT_EVALUATED"
    OUTSIDE_MODEL_SCOPE = "OUTSIDE_MODEL_SCOPE"


@dataclass(frozen=True, slots=True)
class ExpertChecklistItemV1:
    item_id: str
    prompt: str
    status: ChecklistStatusV1
    evidence: str


@dataclass(frozen=True, slots=True)
class RealRouteOperationalReviewV1:
    profile: str
    source_id: str
    requested_solver: SolverChoice
    pipeline_status: ReviewPipelineStatusV1
    review_disposition: ReviewDispositionV1
    expert_review_status: str
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]
    input_readiness_summary: Mapping[str, object]
    route_facts: Mapping[str, object]
    demand_authority_summary: Mapping[str, object]
    scenario_b_operational_summary: Mapping[str, object]
    heuristic_outcome_summary: Mapping[str, object]
    ortools_outcome_summary: Mapping[str, object]
    recommendation_summary: Mapping[str, object]
    b_to_accepted_c_comparison: Mapping[str, object] | None
    protected_service_floor_summary: Mapping[str, object]
    artifact_metadata: Mapping[str, object]
    expert_review_checklist: tuple[ExpertChecklistItemV1, ...]
    next_decision_category: NextDecisionCategoryV1
    next_decision_reason: str
    authoritative_fingerprint_references: Mapping[str, object]
    review_fingerprint: str


@dataclass(frozen=True, slots=True)
class OperationalReviewPackageV1:
    review: RealRouteOperationalReviewV1
    json_bytes: bytes
    markdown_bytes: bytes
    artifacts: UnifiedPage5ArtifactsV1 | None
    exit_code: int


def _fact(value: object, authority: ReviewFactAuthorityV1) -> dict[str, object]:
    return {"value": value, "authority": authority.value}


def _jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda x: str(x[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("review payload may not contain non-finite numbers")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported review payload type: {value.__class__.__name__}")


def operational_review_to_dict_v1(review: RealRouteOperationalReviewV1) -> dict[str, object]:
    """Return the complete deterministic JSON object for one review."""
    if not isinstance(review, RealRouteOperationalReviewV1):
        raise TypeError("review must be a RealRouteOperationalReviewV1")
    payload = _jsonable(review)
    if not isinstance(payload, dict):
        raise TypeError("review serialization did not produce an object")
    return payload


def _fingerprint_payload(review: RealRouteOperationalReviewV1) -> dict[str, object]:
    payload = operational_review_to_dict_v1(review)
    payload.pop("review_fingerprint", None)
    return payload


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def calculate_operational_review_fingerprint_v1(review: RealRouteOperationalReviewV1) -> str:
    """Calculate the SHA-256 over the canonical non-self-referential review payload."""
    return hashlib.sha256(_canonical_json_bytes(_fingerprint_payload(review))).hexdigest()


def _review_payload_respects_content_invariants(payload: Mapping[str, object]) -> bool:
    payload_text = _canonical_json_bytes(payload).decode("utf-8")
    return not _ABSOLUTE_PATH_PATTERN.search(payload_text) and (
        "operationally" + "_approved" not in payload_text.lower()
    )


def verify_operational_review_fingerprint_v1(review: RealRouteOperationalReviewV1) -> bool:
    """Verify a review model's stored fingerprint and bounded privacy invariants."""
    if not isinstance(review, RealRouteOperationalReviewV1):
        return False
    if review.profile != REVIEW_PROFILE_V1 or not re.fullmatch(
        r"[0-9a-f]{64}", review.review_fingerprint
    ):
        return False
    if not _review_payload_respects_content_invariants(operational_review_to_dict_v1(review)):
        return False
    return calculate_operational_review_fingerprint_v1(review) == review.review_fingerprint


def verify_operational_review_json_bytes_v1(content: bytes) -> bool:
    """Verify canonical bytes and detect payload or fingerprint tampering."""
    try:
        payload = json.loads(content)
        if not isinstance(payload, dict) or payload.get("profile") != REVIEW_PROFILE_V1:
            return False
        fingerprint = payload.pop("review_fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            return False
        expected = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
        restored = {**payload, "review_fingerprint": fingerprint}
        return (
            expected == fingerprint
            and _review_payload_respects_content_invariants(restored)
            and content == _canonical_json_bytes(restored)
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def serialize_operational_review_v1(review: RealRouteOperationalReviewV1) -> bytes:
    """Serialize and verify one canonical review JSON document."""
    if not verify_operational_review_fingerprint_v1(review):
        raise ValueError("operational review fingerprint verification failed")
    content = _canonical_json_bytes(operational_review_to_dict_v1(review))
    if not verify_operational_review_json_bytes_v1(content):
        raise ValueError("operational review canonical JSON integrity failed")
    return content


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(float(value), digits)


def _time(value: int | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {"seconds": value, "hhmm": format_hhmm(value)}


def _directional_trips(scenario: ScenarioBInput) -> dict[str, tuple[ExactTimetableTrip, ...]]:
    return {
        direction.value: tuple(
            sorted(
                (item for item in scenario.exact_timetable if item.direction == direction),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }


def _headway_statistics(scenario: ScenarioBInput) -> dict[str, object]:
    output: dict[str, object] = {}
    for direction, trips in _directional_trips(scenario).items():
        gaps = tuple(
            (right.departure_time - left.departure_time) / 60
            for left, right in zip(trips, trips[1:], strict=False)
        )
        output[direction] = {
            "trip_count": len(trips),
            "first_departure": _time(trips[0].departure_time) if trips else None,
            "last_departure": _time(trips[-1].departure_time) if trips else None,
            "minimum_headway_minutes": _round(min(gaps)) if gaps else None,
            "median_headway_minutes": _round(median(gaps)) if gaps else None,
            "mean_headway_minutes": _round(mean(gaps)) if gaps else None,
            "maximum_headway_minutes": _round(max(gaps)) if gaps else None,
        }
    return output


def _regime_rows(
    assessment: ProtectedServiceFloorAssessmentV1 | None,
) -> tuple[dict[str, object], ...]:
    if assessment is None:
        return ()
    return tuple(
        {
            "regime_id": item.regime_id,
            "direction": item.direction.value,
            "first_departure": _time(item.first_departure),
            "last_departure": _time(item.last_departure),
            "trip_count": item.trip_count,
            "minimum_internal_headway_minutes": _round(item.minimum_b_headway),
            "maximum_internal_headway_minutes": _round(item.maximum_b_headway),
            "representative_headway_minutes": _round(item.representative_b_headway),
            "transition_headway_before_minutes": _round(item.transition_headway_before),
            "transition_headway_after_minutes": _round(item.transition_headway_after),
            "regularity_classification": item.regularity_classification,
        }
        for item in assessment.regimes
    )


def _terminal_occupancy(
    scenario: ScenarioBInput, initial_1: int, initial_2: int
) -> dict[str, object]:
    assessment = assess_terminal_occupancy_v1(
        scenario,
        initial_terminal_1=initial_1,
        initial_terminal_2=initial_2,
    )
    return {
        "event_order": assessment.event_order,
        "terminal_1": {
            "limit": assessment.terminal_1.capacity,
            "maximum_reconstructed_occupancy": assessment.terminal_1.maximum_occupancy,
            "remaining_capacity_margin": assessment.terminal_1.remaining_capacity_margin,
            "limit_binding": assessment.terminal_1.limit_binding,
            "limit_exceeded": assessment.terminal_1.limit_exceeded,
        },
        "terminal_2": {
            "limit": assessment.terminal_2.capacity,
            "maximum_reconstructed_occupancy": assessment.terminal_2.maximum_occupancy,
            "remaining_capacity_margin": assessment.terminal_2.remaining_capacity_margin,
            "limit_binding": assessment.terminal_2.limit_binding,
            "limit_exceeded": assessment.terminal_2.limit_exceeded,
        },
        "issue_codes": tuple(sorted(assessment.issue_codes)),
        "limitation_codes": tuple(sorted(assessment.limitations)),
    }


def _route_facts(result: BusScheduleOptimizationResult | None) -> Mapping[str, object]:
    if result is None:
        return {"availability": _fact("NOT_EVALUATED", ReviewFactAuthorityV1.NOT_EVALUATED)}
    b = result.normalized_inputs.scenario_b
    observed = result.normalized_inputs.observed_demand
    runtimes = tuple(sorted({trip.runtime_minutes for trip in b.exact_timetable}))
    demand_source_types = (
        tuple(sorted({item.source_type.value for item in observed.observations}))
        if observed is not None
        else ()
    )
    demand_confidence = (
        tuple(sorted({item.demand_confidence.value for item in observed.observations}))
        if observed is not None
        else ()
    )
    limits = b.terminal_occupancy_limits
    return {
        "route_id": _fact(b.route_id, ReviewFactAuthorityV1.SUPPLIED_FACT),
        "route_name": _fact(b.route_name, ReviewFactAuthorityV1.SUPPLIED_FACT),
        "route_type": _fact(b.route_type.value, ReviewFactAuthorityV1.SUPPLIED_FACT),
        "terminal_names": _fact(
            {"terminal_1": b.terminal_1_name, "terminal_2": b.terminal_2_name},
            ReviewFactAuthorityV1.SUPPLIED_FACT,
        ),
        "total_daily_trips": _fact(b.total_daily_trips, ReviewFactAuthorityV1.SUPPLIED_FACT),
        "directional_trip_counts": _fact(
            {
                "outbound": b.trips_by_direction.outbound,
                "inbound": b.trips_by_direction.inbound,
            },
            ReviewFactAuthorityV1.SUPPLIED_FACT,
        ),
        "service_windows": _fact(
            {
                "outbound": {
                    "first": _time(b.first_departures.terminal_1),
                    "last": _time(b.last_departures.terminal_1),
                },
                "inbound": {
                    "first": _time(b.first_departures.terminal_2),
                    "last": _time(b.last_departures.terminal_2),
                },
            },
            ReviewFactAuthorityV1.SUPPLIED_FACT,
        ),
        "supplied_runtime_minutes": _fact(runtimes, ReviewFactAuthorityV1.SUPPLIED_FACT),
        "minimum_turnaround_minutes": _fact(
            {
                "terminal_1": b.turnaround_minutes.terminal_1,
                "terminal_2": b.turnaround_minutes.terminal_2,
            },
            ReviewFactAuthorityV1.SUPPLIED_FACT,
        ),
        "available_fleet_limit": _fact(
            b.available_fleet_limit, ReviewFactAuthorityV1.SUPPLIED_FACT
        ),
        "approved_active_fleet": _fact(
            b.approved_active_fleet,
            ReviewFactAuthorityV1.SUPPLIED_FACT
            if b.approved_active_fleet is not None
            else ReviewFactAuthorityV1.NOT_EVALUATED,
        ),
        "terminal_occupancy_limits": _fact(
            {
                "terminal_1": limits.terminal_1 if limits is not None else None,
                "terminal_2": limits.terminal_2 if limits is not None else None,
            },
            ReviewFactAuthorityV1.SUPPLIED_FACT
            if limits is not None
            else ReviewFactAuthorityV1.NOT_EVALUATED,
        ),
        "vehicle_capacity": _fact(b.vehicle_capacity, ReviewFactAuthorityV1.SUPPLIED_FACT),
        "operating_day_type": _fact(
            b.operating_day_type.value, ReviewFactAuthorityV1.SUPPLIED_FACT
        ),
        "demand_source_type": _fact(
            demand_source_types,
            ReviewFactAuthorityV1.SUPPLIED_FACT
            if observed is not None
            else ReviewFactAuthorityV1.NOT_EVALUATED,
        ),
        "demand_confidence": _fact(
            demand_confidence,
            ReviewFactAuthorityV1.SUPPLIED_FACT
            if observed is not None
            else ReviewFactAuthorityV1.NOT_EVALUATED,
        ),
        "demand_observation_period": _fact(
            (
                {
                    "start": observed.observation_period_start.isoformat(),
                    "end": observed.observation_period_end.isoformat(),
                    "observation_days": observed.observation_days,
                }
                if observed is not None
                else None
            ),
            ReviewFactAuthorityV1.SUPPLIED_FACT
            if observed is not None
            else ReviewFactAuthorityV1.NOT_EVALUATED,
        ),
    }


def _input_readiness(readiness: WorkbookInputReadinessV1) -> Mapping[str, object]:
    return {
        "import_ready": readiness.import_ready,
        "optimization_ready": readiness.optimization_ready,
        "blocking_import_codes": tuple(sorted(readiness.blocking_import_codes)),
        "missing_optimization_authority_codes": tuple(
            sorted(readiness.missing_optimization_authority_codes)
        ),
        "optional_limitation_codes": tuple(sorted(readiness.optional_limitations)),
    }


def _demand_authority(
    result: BusScheduleOptimizationResult | None,
    presentation: UnifiedPresentationBundleV1 | None,
) -> Mapping[str, object]:
    if result is None:
        return {
            "authoritative_demand_grain": None,
            "coverage_status": "NOT_EVALUATED",
            "canonical_solver_request_constructible": False,
            "solve_not_performed_reasons": ("PIPELINE_RESULT_UNAVAILABLE",),
        }
    observed = result.normalized_inputs.observed_demand
    resolution = result.b_evaluation.demand_resolution
    coverage = resolution.coverage_assessment if resolution is not None else None
    uncovered = (
        tuple(
            {
                "code": item.code,
                "direction": item.stream.value,
                "start": _time(item.start_time),
                "end": _time(item.end_time),
            }
            for item in coverage.uncovered_segments
        )
        if coverage is not None
        else ()
    )
    coverage_complete = bool(
        coverage is not None
        and not coverage.uncovered_segments
        and not coverage.uncovered_departures
    )
    fixed_resource_requested = result.selected_action in _FIXED_RESOURCE_ACTIONS
    request_constructible = bool(
        fixed_resource_requested
        and coverage is not None
        and coverage.directional_c_generation_supported
        and result.protected_service_floor_enforcement_failure_code is None
    )
    reasons: set[str] = set()
    if not result.solver_attempted:
        reasons.add(f"SELECTED_ACTION_{result.selected_action.value}")
        if coverage is not None:
            reasons.update(coverage.generation_issue_codes)
        if result.protected_service_floor_enforcement_failure_code is not None:
            reasons.add(result.protected_service_floor_enforcement_failure_code)
    gaps = (
        tuple(
            {
                "code": item.code,
                "direction": item.direction,
                "start": _time(item.start_time_seconds),
                "end": _time(item.end_time_seconds),
            }
            for item in presentation.demand_gaps
        )
        if presentation is not None
        else ()
    )
    contract = resolution.contract if resolution is not None else None
    return {
        "demand_supplied": observed is not None,
        "authoritative_demand_grain": (
            contract.source_resolution_type.value if contract is not None else None
        ),
        "coverage_status": "COMPLETE" if coverage_complete else "INCOMPLETE",
        "coverage_mode": coverage.mode.value if coverage is not None else None,
        "direction_coverage": {
            "present": tuple(item.value for item in coverage.present_streams) if coverage else (),
            "missing": tuple(item.value for item in coverage.missing_streams) if coverage else (),
        },
        "observation_period": (
            {
                "start": observed.observation_period_start.isoformat(),
                "end": observed.observation_period_end.isoformat(),
            }
            if observed is not None
            else None
        ),
        "observation_days": contract.observation_days if contract is not None else None,
        "confidence": contract.confidence_level.value if contract is not None else None,
        "uncovered_intervals": uncovered,
        "uncovered_departure_count": len(coverage.uncovered_departures) if coverage else 0,
        "demand_gaps": gaps,
        "coverage_issue_codes": (
            tuple(sorted(set(coverage.evaluation_issue_codes + coverage.generation_issue_codes)))
            if coverage
            else ()
        ),
        "canonical_solver_request_constructible": request_constructible,
        "solve_not_performed_reasons": tuple(sorted(reasons)),
        "interpolation_used": False,
        "fabricated_zero_demand_used": False,
    }


def _scenario_b_summary(
    result: BusScheduleOptimizationResult | None,
    presentation: UnifiedPresentationBundleV1 | None,
    assessment: ProtectedServiceFloorAssessmentV1 | None,
) -> Mapping[str, object]:
    if result is None:
        return {"availability": "NOT_EVALUATED"}
    b = result.normalized_inputs.scenario_b
    headways = _headway_statistics(b)
    blocks = presentation.blocks if presentation is not None else ()
    target = result.adjustment_context.b_evaluation_policy.planning_load_factor_ceiling
    maximum = result.adjustment_context.b_evaluation_policy.critical_load_factor_ceiling
    fleet = result.b_evaluation.fleet_assessment
    technical = result.adjustment_assessment.technical_evidence
    minimum_observed_turnaround = None
    if (
        technical.minimum_turnaround_margin_minutes is not None
        and b.turnaround_minutes.terminal_1 == b.turnaround_minutes.terminal_2
    ):
        minimum_observed_turnaround = (
            b.turnaround_minutes.terminal_1 + technical.minimum_turnaround_margin_minutes
        )
    occupancy = _terminal_occupancy(
        b,
        fleet.recommended_initial_fleet_terminal_1,
        fleet.recommended_initial_fleet_terminal_2,
    )
    validation_codes = {
        issue.code
        for dimension in (
            result.b_evaluation.evaluation.input_validity,
            result.b_evaluation.evaluation.parameter_consistency,
            result.b_evaluation.evaluation.technical_feasibility,
            result.b_evaluation.evaluation.demand_suitability,
            result.b_evaluation.evaluation.fleet_feasibility,
            result.b_evaluation.evaluation.headway_quality,
        )
        for issue in dimension.issues
    }
    daily_demand = sum(item.passenger_demand for item in blocks)
    largest_gap = max(
        (
            row["maximum_headway_minutes"]
            for row in headways.values()
            if isinstance(row, Mapping) and row["maximum_headway_minutes"] is not None
        ),
        default=None,
    )
    return {
        "total_trips": b.total_daily_trips,
        "directional_trips": {
            "outbound": b.trips_by_direction.outbound,
            "inbound": b.trips_by_direction.inbound,
        },
        "directional_headways": headways,
        "sustained_service_regimes": _regime_rows(assessment),
        "transition_headways_minutes": tuple(
            value
            for row in _regime_rows(assessment)
            for value in (
                row["transition_headway_before_minutes"],
                row["transition_headway_after_minutes"],
            )
            if value is not None
        ),
        "largest_service_gap_minutes": largest_gap,
        "blocks_with_no_service": tuple(item.block_id for item in blocks if item.b_trip_count == 0),
        "blocks_above_target_load_factor": tuple(
            item.block_id
            for item in blocks
            if item.b_load_factor is not None and item.b_load_factor > target
        ),
        "blocks_above_maximum_load_factor": tuple(
            item.block_id
            for item in blocks
            if item.b_load_factor is not None and item.b_load_factor > maximum
        ),
        "daily_demand_total": _round(daily_demand) if blocks else None,
        "daily_nominal_supply_total": b.total_daily_trips * b.vehicle_capacity,
        "minimum_required_fleet": fleet.minimum_required_fleet,
        "available_fleet_limit": fleet.available_fleet_limit,
        "fleet_slack": fleet.fleet_margin,
        "minimum_observed_turnaround_minutes": _round(minimum_observed_turnaround),
        "minimum_observed_turnaround_slack_minutes": _round(
            technical.minimum_turnaround_margin_minutes
        ),
        "turnaround_violation_count": technical.turnaround_violation_count,
        "terminal_occupancy": occupancy,
        "validation_issue_codes": tuple(sorted(validation_codes)),
        "b_disposition": result.b_evaluation.evaluation.disposition.value,
    }


def _outcome_vector(
    result: BusScheduleOptimizationResult, solver: SolverChoice
) -> tuple[int, ...] | None:
    comparison = result.comparison
    if comparison is None:
        return None
    return (
        comparison.heuristic_vector
        if solver == SolverChoice.HEURISTIC
        else comparison.ortools_vector
    )


def _solver_summary(
    result: BusScheduleOptimizationResult | None,
    solver: SolverChoice,
    requested_solver: SolverChoice,
) -> Mapping[str, object]:
    requested = requested_solver in {solver, SolverChoice.BOTH}
    outcome = None
    if result is not None:
        outcome = (
            result.heuristic_outcome if solver == SolverChoice.HEURISTIC else result.ortools_outcome
        )
    diagnostic = outcome.diagnostic_candidate if outcome is not None else None
    solution = outcome.solution if outcome is not None else None
    limitations: set[str] = set(outcome.limitations if outcome is not None else ())
    if solver == SolverChoice.HEURISTIC:
        limitations.update(
            {
                "The heuristic does not prove optimality.",
                "Failure to find a candidate does not prove infeasibility.",
            }
        )
    else:
        limitations.add(
            "An OR-Tools INFEASIBLE status applies only to the exact encoded fixed-resource "
            "model and does not generalize to variable trips, expanded fleet, policy relaxation, "
            "or structural demand response."
        )
    authority = result.protected_service_floor_enforcement_authority if result is not None else None
    enforceable = bool(authority is not None and authority.has_enforceable_regimes)
    if not requested:
        request_status = "NOT_REQUESTED"
    elif outcome is not None:
        request_status = "CONSTRUCTED_AND_EXECUTED"
    elif result is not None and result.selected_action not in _FIXED_RESOURCE_ACTIONS:
        request_status = "NOT_CONSTRUCTED_ACTION_OUTSIDE_FIXED_RESOURCE_SOLVING"
    else:
        request_status = "NOT_CONSTRUCTED"
    validation_codes = tuple(sorted(diagnostic.rejection_codes)) if diagnostic is not None else ()
    common_validation = (
        "ACCEPTED"
        if solution is not None
        and outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
        else "REJECTED"
        if diagnostic is not None
        else "NOT_EVALUATED"
    )
    return {
        "requested": requested,
        "request_constructed": outcome is not None,
        "request_status": request_status,
        "adapter_id": outcome.solver_adapter if outcome is not None else None,
        "execution_status": outcome.execution_status.value if outcome is not None else None,
        "native_solver_status": outcome.solver_status.value
        if outcome and outcome.solver_status
        else None,
        "generation_result_status": outcome.result_status.value if outcome is not None else None,
        "accepted": bool(
            outcome is not None
            and outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
            and solution is not None
        ),
        "candidate_fingerprint": diagnostic.candidate_fingerprint if diagnostic else None,
        "accepted_solution_fingerprint": solution.solution_fingerprint if solution else None,
        "outcome_fingerprint": outcome.outcome_fingerprint if outcome is not None else None,
        "objective_vector": _outcome_vector(result, solver) if result is not None else None,
        "objective_stage_names": SERVICE_QUALITY_OBJECTIVE_NAMES_V1 if outcome is not None else (),
        "explanations": tuple(sorted(outcome.explanations)) if outcome is not None else (),
        "limitations": tuple(sorted(limitations)),
        "independent_validator_codes": validation_codes,
        "common_independent_validation_result": common_validation,
        "protected_floor_fingerprint": (
            outcome.protected_service_floor_enforcement_fingerprint if outcome is not None else None
        ),
        "protected_floor_authority_enforceable": enforceable,
        "native_protected_floor_result": (
            "ENFORCED_IN_NATIVE_SEARCH"
            if outcome is not None
            and enforceable
            and outcome.protected_service_floor_enforcement_fingerprint
            else "NO_ENFORCEABLE_REGIME"
            if not enforceable
            else "NOT_EVALUATED"
        ),
    }


def _accepted_solution(result: BusScheduleOptimizationResult | None):
    if result is None or result.recommended_outcome is None:
        return None
    outcome = result.recommended_outcome
    if outcome.result_status != GenerationResultStatus.SOLUTION_ACCEPTED:
        return None
    return outcome.solution


def _minimum_assignment_slack(presentation: UnifiedPresentationBundleV1) -> float | None:
    by_vehicle: defaultdict[str, list[object]] = defaultdict(list)
    for item in presentation.fleet_assignments:
        by_vehicle[item.vehicle_id].append(item)
    slacks = [
        (current.departure_time_seconds - previous.ready_time_seconds) / 60
        for assignments in by_vehicle.values()
        for previous, current in zip(
            sorted(assignments, key=lambda x: (x.departure_time_seconds, x.trip_id)),
            sorted(assignments, key=lambda x: (x.departure_time_seconds, x.trip_id))[1:],
            strict=False,
        )
    ]
    return min(slacks) if slacks else None


def _accepted_c_scenario(
    b: ScenarioBInput,
    presentation: UnifiedPresentationBundleV1,
) -> ScenarioBInput | None:
    scenario_c = presentation.scenario("C")
    if scenario_c is None:
        return None
    source_by_id = {item.trip_id: item for item in b.exact_timetable}
    trips: list[ExactTimetableTrip] = []
    for item in scenario_c.trips:
        source = source_by_id.get(item.source_b_trip_id or "")
        if source is None:
            return None
        trips.append(
            replace(
                source,
                trip_id=item.trip_id,
                departure_time=item.departure_time_seconds,
                arrival_time=item.arrival_time_seconds,
                vehicle_assignment=item.vehicle_assignment,
            )
        )
    return replace(b, exact_timetable=tuple(trips))


def _headway_delta(b: ScenarioBInput, c: ScenarioBInput) -> dict[str, object]:
    b_rows = _headway_statistics(b)
    c_rows = _headway_statistics(c)
    output: dict[str, object] = {}
    for direction in (ContractDirection.OUTBOUND.value, ContractDirection.INBOUND.value):
        b_row = b_rows[direction]
        c_row = c_rows[direction]
        output[direction] = {
            "maximum_headway_delta_minutes": _round(
                c_row["maximum_headway_minutes"] - b_row["maximum_headway_minutes"]
                if c_row["maximum_headway_minutes"] is not None
                and b_row["maximum_headway_minutes"] is not None
                else None
            ),
            "mean_headway_delta_minutes": _round(
                c_row["mean_headway_minutes"] - b_row["mean_headway_minutes"]
                if c_row["mean_headway_minutes"] is not None
                and b_row["mean_headway_minutes"] is not None
                else None
            ),
            "first_departure_delta_minutes": _round(
                (c_row["first_departure"]["seconds"] - b_row["first_departure"]["seconds"]) / 60
                if c_row["first_departure"] and b_row["first_departure"]
                else None
            ),
            "last_departure_delta_minutes": _round(
                (c_row["last_departure"]["seconds"] - b_row["last_departure"]["seconds"]) / 60
                if c_row["last_departure"] and b_row["last_departure"]
                else None
            ),
        }
    return output


def _bc_comparison(
    result: BusScheduleOptimizationResult | None,
    presentation: UnifiedPresentationBundleV1 | None,
) -> Mapping[str, object] | None:
    solution = _accepted_solution(result)
    if result is None or presentation is None or solution is None:
        return None
    b = result.normalized_inputs.scenario_b
    c = _accepted_c_scenario(b, presentation)
    if c is None:
        return None
    b_counts = b.trips_by_direction
    c_trips = _directional_trips(c)
    b_blocks = presentation.blocks
    no_service_b = sum(item.b_trip_count == 0 for item in b_blocks)
    no_service_c = sum(item.c_actual_trip_count == 0 for item in b_blocks)
    overload_b = sum((item.b_shortage or 0) > 0 for item in b_blocks)
    overload_c = sum((item.c_shortage or 0) > 0 for item in b_blocks)
    b_shortage = sum(item.b_shortage or 0 for item in b_blocks)
    c_shortage = sum(item.c_shortage or 0 for item in b_blocks)
    fleet_b = result.b_evaluation.fleet_assessment
    initial = presentation.initial_fleet
    terminal_delta = None
    if initial is not None:
        b_occupancy = _terminal_occupancy(
            b,
            fleet_b.recommended_initial_fleet_terminal_1,
            fleet_b.recommended_initial_fleet_terminal_2,
        )
        c_occupancy = _terminal_occupancy(
            c,
            initial.terminal_1_vehicle_count,
            initial.terminal_2_vehicle_count,
        )
        if b.terminal_occupancy_limits is not None:
            terminal_delta = {
                terminal: (
                    c_occupancy[terminal]["maximum_reconstructed_occupancy"]
                    - b_occupancy[terminal]["maximum_reconstructed_occupancy"]
                )
                for terminal in ("terminal_1", "terminal_2")
            }
    b_turnaround = result.adjustment_assessment.technical_evidence.minimum_turnaround_margin_minutes
    c_turnaround = _minimum_assignment_slack(presentation)
    vector = (
        _outcome_vector(result, result.comparison.recommended_solver)
        if result.comparison is not None and result.comparison.recommended_solver is not None
        else None
    )
    authority = result.protected_service_floor_enforcement_authority
    protected_compliance = (
        "NO_ENFORCEABLE_REGIME"
        if authority is None or not authority.has_enforceable_regimes
        else "ACCEPTED_BY_COMMON_VALIDATOR"
        if solution.protected_service_floor_validation_fingerprint is not None
        else "NOT_EVALUATED"
    )
    return {
        "trip_count_delta": len(c.exact_timetable) - len(b.exact_timetable),
        "directional_count_delta": {
            "outbound": len(c_trips[ContractDirection.OUTBOUND.value]) - b_counts.outbound,
            "inbound": len(c_trips[ContractDirection.INBOUND.value]) - b_counts.inbound,
        },
        "service_window_and_headway_deltas": _headway_delta(b, c),
        "no_service_block_delta": no_service_c - no_service_b,
        "overload_or_shortage_block_delta": overload_c - overload_b,
        "total_shortage_delta": _round(c_shortage - b_shortage),
        "minimum_fleet_delta": solution.minimum_required_fleet - fleet_b.minimum_required_fleet,
        "fleet_slack_delta": solution.fleet_margin - fleet_b.fleet_margin,
        "turnaround_slack_delta_minutes": _round(
            c_turnaround - b_turnaround
            if c_turnaround is not None and b_turnaround is not None
            else None
        ),
        "terminal_occupancy_delta": terminal_delta,
        "protected_regime_compliance": protected_compliance,
        "objective_stage_names": (
            result.comparison.objective_names if result.comparison is not None else ()
        ),
        "current_b_objective_vector": None,
        "accepted_c_objective_vector": vector,
        "objective_vector_note": (
            "The accepted-C vector is available only when the existing BOTH-solver comparison "
            "computed it; no alternative B vector is invented by this review."
        ),
        "shifted_trip_count": solution.shifted_trip_count,
        "maximum_absolute_trip_shift_minutes": _round(solution.maximum_shift_minutes),
        "total_absolute_trip_shift_minutes": _round(solution.total_shift_minutes),
        "review_status": EXPERT_REVIEW_REQUIRED,
    }


def _protected_summary(
    run: UnifiedApplicationRunV1 | None,
    result: BusScheduleOptimizationResult | None,
) -> Mapping[str, object]:
    analysis = run.trip_ridership_analysis if run is not None else None
    assessment = run.protected_service_floor_assessment if run is not None else None
    authority = result.protected_service_floor_enforcement_authority if result is not None else None
    protected = authority.protected_regimes if authority is not None else ()
    heuristic = result.heuristic_outcome if result is not None else None
    ortools = result.ortools_outcome if result is not None else None

    def common(outcome) -> str:
        if outcome is None:
            return "NOT_EVALUATED"
        if outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED:
            return "ACCEPTED"
        if outcome.diagnostic_candidate is not None:
            return "REJECTED"
        return "NO_CANDIDATE"

    return {
        "trip_ridership_dataset_status": (
            analysis.dataset_summary.status.value if analysis is not None else "NOT_PROVIDED"
        ),
        "trip_ridership_scheduled_trip_coverage_rate": (
            _round(analysis.dataset_summary.scheduled_trip_coverage_rate) if analysis else None
        ),
        "trip_ridership_direction_coverage_rate": (
            _round(analysis.dataset_summary.direction_coverage_rate) if analysis else None
        ),
        "trip_ridership_confidence": analysis.confidence if analysis is not None else None,
        "current_scenario_b_regimes": _regime_rows(assessment),
        "protected_regime_count": len(protected),
        "protected_source_trip_ids_included": False,
        "protected_regimes": tuple(
            {
                "regime_id": item.regime_id,
                "direction": item.direction.value,
                "protected_service_window": {
                    "start": _time(item.protected_window_start),
                    "end": _time(item.protected_window_end),
                },
                "protected_source_trip_count": len(item.ordered_b_trip_ids),
                "minimum_future_trip_count": item.minimum_future_c_trip_count,
                "maximum_internal_headway_minutes": item.maximum_future_c_headway_minutes,
                "future_boundary_tolerance_minutes": item.future_boundary_tolerance_minutes,
                "donor_removal_prohibited": item.donor_removal_prohibited,
            }
            for item in protected
        ),
        "protected_floor_enforcement_fingerprint": (
            authority.enforcement_fingerprint if authority is not None else None
        ),
        "candidate_acceptance": {
            "heuristic": common(heuristic),
            "ortools": common(ortools),
        },
        "native_heuristic_search_result": (
            heuristic.solver_status.value
            if heuristic and heuristic.solver_status
            else "NOT_EVALUATED"
        ),
        "native_ortools_constraint_result": (
            ortools.solver_status.value if ortools and ortools.solver_status else "NOT_EVALUATED"
        ),
        "common_independent_validation_result": {
            "heuristic": common(heuristic),
            "ortools": common(ortools),
        },
        "transition_gaps_excluded_from_protected_internal_headways": True,
        "no_enforceable_regime": not protected,
        "non_protected_regimes_are_not_classified_as_low_demand": True,
    }


def _solver_divergence(result: BusScheduleOptimizationResult | None) -> bool:
    if result is None or result.solver_choice != SolverChoice.BOTH:
        return False
    heuristic = result.heuristic_outcome
    ortools = result.ortools_outcome
    if heuristic is None or ortools is None:
        return False
    heuristic_accepted = heuristic.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    ortools_accepted = ortools.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    if heuristic_accepted != ortools_accepted:
        return True
    comparison = result.comparison
    return bool(
        heuristic_accepted
        and ortools_accepted
        and comparison is not None
        and comparison.heuristic_vector != comparison.ortools_vector
    )


def _disposition(
    status: ReviewPipelineStatusV1,
    result: BusScheduleOptimizationResult | None,
    demand: Mapping[str, object],
) -> ReviewDispositionV1:
    if status in {ReviewPipelineStatusV1.PIPELINE_FAILED, ReviewPipelineStatusV1.ARTIFACT_FAILED}:
        return ReviewDispositionV1.EXPERT_REVIEW_REQUIRED
    if status == ReviewPipelineStatusV1.INPUT_NOT_READY:
        demand_codes = {
            code
            for code in demand.get("coverage_issue_codes", ())
            if str(code).startswith("DEMAND_")
        }
        return (
            ReviewDispositionV1.DEMAND_AUTHORITY_INCOMPLETE
            if demand_codes
            else ReviewDispositionV1.EXPERT_REVIEW_REQUIRED
        )
    if demand.get("coverage_status") == "INCOMPLETE":
        return ReviewDispositionV1.DEMAND_AUTHORITY_INCOMPLETE
    if _solver_divergence(result):
        return ReviewDispositionV1.SOLVER_DIVERGENCE_REVIEW_REQUIRED
    if result is not None:
        rejection_codes = {
            code
            for outcome in (result.heuristic_outcome, result.ortools_outcome)
            if outcome is not None and outcome.diagnostic_candidate is not None
            for code in outcome.diagnostic_candidate.rejection_codes
        }
        if any(code.startswith(_PROTECTED_REJECTION_PREFIX) for code in rejection_codes):
            return ReviewDispositionV1.PROTECTED_FLOOR_REJECTION
        if _accepted_solution(result) is not None:
            return ReviewDispositionV1.ACCEPTED_CANDIDATE_AVAILABLE
        if result.selected_action == OptimizationAction.NO_CHANGE:
            return ReviewDispositionV1.CURRENT_B_RETAINED
    return ReviewDispositionV1.NO_ACCEPTED_CANDIDATE


def _next_decision(
    status: ReviewPipelineStatusV1,
    result: BusScheduleOptimizationResult | None,
    demand: Mapping[str, object],
    scenario_b: Mapping[str, object],
) -> tuple[NextDecisionCategoryV1, str]:
    if status == ReviewPipelineStatusV1.ARTIFACT_FAILED:
        return (
            NextDecisionCategoryV1.PRESENTATION_GAP,
            "Verified analysis exists, but the bounded artifact package could not be completed.",
        )
    if status == ReviewPipelineStatusV1.PIPELINE_FAILED:
        # No solver-semantic change is authorized until the sanitized failure is diagnosed.
        return (
            NextDecisionCategoryV1.NO_ENGINE_CHANGE_REQUIRED,
            "The sanitized pipeline failure requires diagnosis before an engine-change category is chosen.",
        )
    if (
        status == ReviewPipelineStatusV1.INPUT_NOT_READY
        or demand.get("coverage_status") == "INCOMPLETE"
    ):
        return (
            NextDecisionCategoryV1.DATA_AUTHORITY_GAP,
            "Required input or directional demand authority is incomplete; no demand values were fabricated.",
        )
    if result is not None and result.selected_action in _STRUCTURAL_ACTIONS:
        return (
            NextDecisionCategoryV1.FIXED_RESOURCE_SCOPE_GAP,
            "The authoritative adjustment decision is structural, while the current generator locks trip counts.",
        )
    terminal = scenario_b.get("terminal_occupancy")
    if isinstance(terminal, Mapping) and terminal.get("limitation_codes"):
        return (
            NextDecisionCategoryV1.DATA_AUTHORITY_GAP,
            "At least one terminal occupancy limit was not supplied, so terminal capacity cannot be approved.",
        )
    if _solver_divergence(result):
        return (
            NextDecisionCategoryV1.OBJECTIVE_QUALITY_GAP,
            "The existing solvers produced materially different accepted-result evidence for expert review.",
        )
    return (
        NextDecisionCategoryV1.NO_ENGINE_CHANGE_REQUIRED,
        "The bounded review identified no evidence that authorizes a solver-semantic change.",
    )


def _checklist(
    result: BusScheduleOptimizationResult | None,
    demand: Mapping[str, object],
    scenario_b: Mapping[str, object],
    comparison: Mapping[str, object] | None,
) -> tuple[ExpertChecklistItemV1, ...]:
    confirmed = (
        ChecklistStatusV1.CONFIRMED_BY_INPUT
        if result is not None
        else ChecklistStatusV1.NOT_EVALUATED
    )
    derived = (
        ChecklistStatusV1.DERIVED_FOR_REVIEW
        if result is not None
        else ChecklistStatusV1.NOT_EVALUATED
    )
    occupancy = scenario_b.get("terminal_occupancy")
    occupancy_missing = bool(isinstance(occupancy, Mapping) and occupancy.get("limitation_codes"))
    demand_supplied = bool(demand.get("demand_supplied"))
    items = (
        (
            "route_identity",
            "Confirm route identity and operating-day type",
            confirmed,
            "Workbook route and day-type fields.",
        ),
        (
            "timetable_meaning",
            "Confirm current and proposed timetable meaning",
            ChecklistStatusV1.REQUIRES_EXPERT_CONFIRMATION,
            "Workbook labels do not replace operator confirmation.",
        ),
        (
            "trip_authority",
            "Confirm total and directional trip authority",
            confirmed,
            "Normalized Scenario B locked counts.",
        ),
        (
            "vehicle_capacity",
            "Confirm vehicle capacity",
            confirmed,
            "Supplied Scenario B capacity.",
        ),
        (
            "available_fleet",
            "Confirm available fleet",
            confirmed,
            "Supplied available-fleet upper bound.",
        ),
        ("runtime_range", "Confirm runtime range", confirmed, "Exact source-trip runtimes."),
        (
            "minimum_turnaround",
            "Confirm minimum turnaround",
            confirmed,
            "Arrival-terminal-specific supplied values.",
        ),
        (
            "terminal_limits",
            "Confirm terminal occupancy limits or acknowledge they were not supplied",
            ChecklistStatusV1.REQUIRES_EXPERT_CONFIRMATION if occupancy_missing else confirmed,
            "No limit is inferred from fleet or timetable behavior.",
        ),
        (
            "demand_period",
            "Confirm demand observation period and confidence",
            confirmed if demand_supplied else ChecklistStatusV1.REQUIRES_EXPERT_CONFIRMATION,
            "Observed-demand metadata only.",
        ),
        (
            "demand_gaps",
            "Review uncovered demand intervals",
            derived,
            f"Coverage status: {demand.get('coverage_status')}.",
        ),
        (
            "largest_gaps",
            "Review largest service gaps",
            derived,
            "Directional Scenario B headways.",
        ),
        (
            "peak_load",
            "Review peak load blocks",
            derived if demand_supplied else ChecklistStatusV1.NOT_EVALUATED,
            "Authoritative demand/supply block results.",
        ),
        (
            "protected_regimes",
            "Review protected regimes",
            derived,
            "Current 6A2 authority and enforcement facts.",
        ),
        (
            "large_shifts",
            "Review large trip shifts",
            derived if comparison is not None else ChecklistStatusV1.NOT_EVALUATED,
            "Accepted-C source-linked shifts only.",
        ),
        (
            "solver_divergence",
            "Review solver divergence",
            derived,
            "Heuristic and OR-Tools accepted-result evidence.",
        ),
        (
            "traffic_variability",
            "Consider traffic variability not represented by scheduled runtime",
            ChecklistStatusV1.OUTSIDE_MODEL_SCOPE,
            "Scheduled source runtime is deterministic.",
        ),
        (
            "operating_resources",
            "Consider driver duties, breaks, depot, deadhead, and maintenance outside the current model",
            ChecklistStatusV1.OUTSIDE_MODEL_SCOPE,
            "These resources are not modeled by Contract V1.",
        ),
        (
            "non_approval",
            "Confirm no operational approval is implied",
            ChecklistStatusV1.REQUIRES_EXPERT_CONFIRMATION,
            EXPERT_REVIEW_REQUIRED,
        ),
    )
    return tuple(ExpertChecklistItemV1(*item) for item in items)


def _approved_artifact_metadata_files() -> tuple[Mapping[str, str], ...]:
    return (
        {"filename": UNIFIED_PAGE5_XLSX_FILENAME, "kind": "XLSX"},
        {"filename": UNIFIED_PAGE5_HTML_FILENAME, "kind": "HTML"},
        {"filename": UNIFIED_PAGE5_PNG_FILENAME, "kind": "PNG"},
    )


def _artifact_metadata(
    artifacts: UnifiedPage5ArtifactsV1 | None,
    presentation: UnifiedPresentationBundleV1 | None,
) -> Mapping[str, object]:
    return {
        "contract_v1_artifacts_available": artifacts is not None,
        "files": (_approved_artifact_metadata_files() if artifacts is not None else ()),
        "presentation_fingerprint": (
            presentation.presentation_fingerprint if presentation is not None else None
        ),
        "scenario_b_fingerprint": (
            presentation.source_b_fingerprint if presentation is not None else None
        ),
        "accepted_solution_fingerprint": (
            presentation.accepted_solution_fingerprint if presentation is not None else None
        ),
        "artifact_boundary": "EXISTING_UNIFIED_PAGE_05",
    }


def _collect_codes(
    readiness: WorkbookInputReadinessV1,
    run: UnifiedApplicationRunV1 | None,
    result: BusScheduleOptimizationResult | None,
    demand: Mapping[str, object],
    presentation: UnifiedPresentationBundleV1 | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reasons = {
        *readiness.blocking_import_codes,
        *readiness.missing_optimization_authority_codes,
        *demand.get("coverage_issue_codes", ()),
    }
    limitations = {
        EXPERT_REVIEW_REQUIRED,
        "FIXED_RESOURCE_TRIP_COUNTS_LOCKED",
        "TRAFFIC_VARIABILITY_OUTSIDE_MODEL",
        "DRIVER_DEPOT_DEADHEAD_MAINTENANCE_OUTSIDE_MODEL",
        *readiness.optional_limitations,
    }
    if run is not None and run.failure is not None:
        reasons.add(run.failure.code)
    if result is not None:
        reasons.update(result.adjustment_assessment.reason_codes)
        if result.protected_service_floor_enforcement_failure_code:
            reasons.add(result.protected_service_floor_enforcement_failure_code)
        for outcome in (result.heuristic_outcome, result.ortools_outcome):
            if outcome is not None and outcome.diagnostic_candidate is not None:
                reasons.update(outcome.diagnostic_candidate.rejection_codes)
        if result.solver_choice in {SolverChoice.HEURISTIC, SolverChoice.BOTH}:
            limitations.update(
                {"HEURISTIC_NO_OPTIMALITY_PROOF", "HEURISTIC_NO_INFEASIBILITY_PROOF"}
            )
        if result.solver_choice in {SolverChoice.OR_TOOLS, SolverChoice.BOTH}:
            limitations.add("ORTOOLS_INFEASIBILITY_SCOPE_FIXED_RESOURCE")
    if presentation is not None:
        reasons.update(presentation.expert_review_required_codes)
        limitations.update(presentation.terminal_occupancy_issue_codes)
    return tuple(sorted(str(item) for item in reasons)), tuple(
        sorted(str(item) for item in limitations)
    )


def _pipeline_status(
    run: UnifiedApplicationRunV1 | None,
    *,
    import_failed: bool,
    page5_failed: bool,
) -> ReviewPipelineStatusV1:
    if import_failed or (
        run is not None and run.status == UnifiedApplicationStatusV1.INPUT_NOT_READY
    ):
        return ReviewPipelineStatusV1.INPUT_NOT_READY
    if page5_failed or (
        run is not None and run.status == UnifiedApplicationStatusV1.ARTIFACT_FAILED
    ):
        return ReviewPipelineStatusV1.ARTIFACT_FAILED
    if run is None or run.status == UnifiedApplicationStatusV1.FAILED:
        return ReviewPipelineStatusV1.PIPELINE_FAILED
    return ReviewPipelineStatusV1.REVIEW_COMPLETE


def build_operational_review_v1(
    *,
    source_id: str,
    requested_solver: SolverChoice,
    readiness: WorkbookInputReadinessV1,
    run: UnifiedApplicationRunV1 | None,
    artifacts: UnifiedPage5ArtifactsV1 | None,
    import_failed: bool = False,
    page5_failed: bool = False,
) -> RealRouteOperationalReviewV1:
    """Build one immutable review strictly from existing unified facts."""
    result = run.unified_result if run is not None else None
    presentation = run.unified_presentation if run is not None else None
    status = _pipeline_status(run, import_failed=import_failed, page5_failed=page5_failed)
    demand = _demand_authority(result, presentation)
    scenario_b = _scenario_b_summary(
        result,
        presentation,
        run.protected_service_floor_assessment if run is not None else None,
    )
    bc_comparison = _bc_comparison(result, presentation)
    disposition = _disposition(status, result, demand)
    next_category, next_reason = _next_decision(status, result, demand, scenario_b)
    reason_codes, limitation_codes = _collect_codes(
        readiness,
        run,
        result,
        demand,
        presentation,
    )
    if page5_failed:
        reason_codes = tuple(sorted({*reason_codes, CONTRACT_V1_ARTIFACT_FAILED}))
    if status == ReviewPipelineStatusV1.PIPELINE_FAILED and run is None:
        reason_codes = tuple(sorted({*reason_codes, CONTRACT_V1_APPLICATION_ERROR}))
    recommendation = {
        "existing_recommended_solver": (
            result.comparison.recommended_solver.value
            if result is not None
            and result.comparison is not None
            and result.comparison.recommended_solver is not None
            else result.solver_choice.value
            if result is not None and _accepted_solution(result) is not None
            else None
        ),
        "accepted_candidate_available": _accepted_solution(result) is not None,
        "accepted_solution_fingerprint": (
            _accepted_solution(result).solution_fingerprint if _accepted_solution(result) else None
        ),
        "comparison_reason_code": (
            result.comparison.reason_code if result is not None and result.comparison else None
        ),
        "review_disposition": disposition.value,
        "review_status": EXPERT_REVIEW_REQUIRED,
        "operational_approval_implied": False,
    }
    references = {
        "scenario_a_fingerprint": (
            result.normalized_inputs.scenario_a_fingerprint if result is not None else None
        ),
        "scenario_b_fingerprint": (
            result.normalized_inputs.scenario_b_fingerprint if result is not None else None
        ),
        "observed_demand_fingerprint": (
            result.normalized_inputs.observed_demand_fingerprint if result is not None else None
        ),
        "authoritative_b_evaluation_fingerprint": (
            result.adjustment_context.authoritative_b_evaluation_fingerprint
            if result is not None
            else None
        ),
        "adjustment_assessment_fingerprint": (
            result.adjustment_assessment.evaluator_fingerprint if result is not None else None
        ),
        "presentation_fingerprint": (
            presentation.presentation_fingerprint if presentation is not None else None
        ),
        "heuristic_outcome_fingerprint": (
            result.heuristic_outcome.outcome_fingerprint
            if result is not None and result.heuristic_outcome is not None
            else None
        ),
        "ortools_outcome_fingerprint": (
            result.ortools_outcome.outcome_fingerprint
            if result is not None and result.ortools_outcome is not None
            else None
        ),
    }
    review = RealRouteOperationalReviewV1(
        profile=REVIEW_PROFILE_V1,
        source_id=source_id,
        requested_solver=requested_solver,
        pipeline_status=status,
        review_disposition=disposition,
        expert_review_status=EXPERT_REVIEW_REQUIRED,
        reason_codes=reason_codes,
        limitation_codes=limitation_codes,
        input_readiness_summary=_input_readiness(readiness),
        route_facts=_route_facts(result),
        demand_authority_summary=demand,
        scenario_b_operational_summary=scenario_b,
        heuristic_outcome_summary=_solver_summary(result, SolverChoice.HEURISTIC, requested_solver),
        ortools_outcome_summary=_solver_summary(result, SolverChoice.OR_TOOLS, requested_solver),
        recommendation_summary=recommendation,
        b_to_accepted_c_comparison=bc_comparison,
        protected_service_floor_summary=_protected_summary(run, result),
        artifact_metadata=_artifact_metadata(artifacts, presentation),
        expert_review_checklist=_checklist(result, demand, scenario_b, bc_comparison),
        next_decision_category=next_category,
        next_decision_reason=next_reason,
        authoritative_fingerprint_references=references,
        review_fingerprint="0" * 64,
    )
    review = replace(review, review_fingerprint=calculate_operational_review_fingerprint_v1(review))
    if not verify_operational_review_fingerprint_v1(review):
        raise ValueError("constructed operational review failed integrity verification")
    return review


def _md_value(value: object) -> str:
    if value is None:
        return "Not evaluated"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (tuple, list)):
        return ", ".join(_md_value(item) for item in value) if value else "None"
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {_md_value(item)}" for key, item in value.items())
    return str(value).replace("|", "\\|")


def _markdown_solver(title: str, summary: Mapping[str, object]) -> list[str]:
    return [
        f"## {title}",
        "",
        f"- Requested: {_md_value(summary['requested'])}",
        f"- Request: {_md_value(summary['request_status'])}",
        f"- Adapter: {_md_value(summary['adapter_id'])}",
        f"- Native status: {_md_value(summary['native_solver_status'])}",
        f"- Generation result: {_md_value(summary['generation_result_status'])}",
        f"- Independently accepted: {_md_value(summary['accepted'])}",
        f"- Objective vector: {_md_value(summary['objective_vector'])}",
        f"- Validator codes: {_md_value(summary['independent_validator_codes'])}",
        f"- Protected-floor search: {_md_value(summary['native_protected_floor_result'])}",
        f"- Limitations: {_md_value(summary['limitations'])}",
        "",
    ]


def render_operational_review_markdown_v1(review: RealRouteOperationalReviewV1) -> bytes:
    """Render an answer-first deterministic expert report without copying raw JSON."""
    if not verify_operational_review_fingerprint_v1(review):
        raise ValueError("cannot render an unverified operational review")
    readiness = review.input_readiness_summary
    demand = review.demand_authority_summary
    b = review.scenario_b_operational_summary
    route = review.route_facts
    protected = review.protected_service_floor_summary
    artifacts = review.artifact_metadata
    lines = [
        "# Real-route operational review",
        "",
        f"**{EXPERT_REVIEW_REQUIRED}**",
        "",
        "This package is expert decision support. It does not approve or publish a timetable, "
        "declare a ridership forecast, or claim global optimality or global infeasibility.",
        "",
        "## 1. Review conclusion",
        "",
        f"- Pipeline status: `{review.pipeline_status.value}`",
        f"- Disposition: `{review.review_disposition.value}`",
        f"- Next-decision category: `{review.next_decision_category.value}`",
        f"- Evidence-based next gate: {review.next_decision_reason}",
        "",
        "## 2. Input readiness and authority",
        "",
        f"- Import ready: {_md_value(readiness['import_ready'])}",
        f"- Optimization ready: {_md_value(readiness['optimization_ready'])}",
        f"- Blocking codes: {_md_value(readiness['blocking_import_codes'])}",
        f"- Missing authority: {_md_value(readiness['missing_optimization_authority_codes'])}",
        f"- Demand grain: {_md_value(demand.get('authoritative_demand_grain'))}",
        f"- Coverage: {_md_value(demand.get('coverage_status'))}",
        f"- Confidence: {_md_value(demand.get('confidence'))}",
        f"- Observation days: {_md_value(demand.get('observation_days'))}",
        f"- Canonical request constructible: {_md_value(demand.get('canonical_solver_request_constructible'))}",
        "",
        "## 3. Current Scenario B",
        "",
        f"- Route: {_md_value(route.get('route_id'))} · {_md_value(route.get('route_name'))}",
        f"- Trips: {_md_value(b.get('total_trips'))} · {_md_value(b.get('directional_trips'))}",
        f"- Directional headways: {_md_value(b.get('directional_headways'))}",
        f"- Largest service gap: {_md_value(b.get('largest_service_gap_minutes'))} minutes",
        f"- Scenario B disposition: {_md_value(b.get('b_disposition'))}",
        "",
        "## 4. Demand and service gaps",
        "",
        f"- Uncovered intervals: {_md_value(demand.get('uncovered_intervals'))}",
        f"- Demand gaps: {_md_value(demand.get('demand_gaps'))}",
        f"- Blocks with no service: {_md_value(b.get('blocks_with_no_service'))}",
        f"- Above target load factor: {_md_value(b.get('blocks_above_target_load_factor'))}",
        f"- Above maximum load factor: {_md_value(b.get('blocks_above_maximum_load_factor'))}",
        "",
        "## 5. Fleet, turnaround, and terminal operations",
        "",
        f"- Minimum fleet / available / slack: {_md_value(b.get('minimum_required_fleet'))} / "
        f"{_md_value(b.get('available_fleet_limit'))} / {_md_value(b.get('fleet_slack'))}",
        f"- Minimum observed turnaround: {_md_value(b.get('minimum_observed_turnaround_minutes'))} minutes",
        f"- Minimum observed turnaround slack: {_md_value(b.get('minimum_observed_turnaround_slack_minutes'))} minutes",
        f"- Terminal occupancy: {_md_value(b.get('terminal_occupancy'))}",
        "",
    ]
    lines.extend(_markdown_solver("6. Heuristic result", review.heuristic_outcome_summary))
    lines.extend(_markdown_solver("7. OR-Tools result", review.ortools_outcome_summary))
    lines.extend(
        [
            "## 8. Recommended existing outcome",
            "",
            f"- Existing recommendation: {_md_value(review.recommendation_summary)}",
            f"- Review boundary: `{EXPERT_REVIEW_REQUIRED}`",
            "",
            "## 9. B-to-C operational comparison",
            "",
            _md_value(review.b_to_accepted_c_comparison),
            "",
            "## 10. Protected service floors",
            "",
            f"- Dataset status: {_md_value(protected.get('trip_ridership_dataset_status'))}",
            f"- Current regimes: {_md_value(protected.get('current_scenario_b_regimes'))}",
            f"- Enforceable regimes: {_md_value(protected.get('protected_regime_count'))}",
            f"- Candidate acceptance: {_md_value(protected.get('candidate_acceptance'))}",
            "- Transition gaps are excluded from protected internal-headway checks.",
            "- A non-protected regime is not reinterpreted as low demand.",
            "",
            "## 11. Solver divergence",
            "",
            f"- Divergence detected: {_md_value(_solver_divergence_from_review(review))}",
            f"- Comparison reason: {_md_value(review.recommendation_summary.get('comparison_reason_code'))}",
            "",
            "## 12. Expert checklist",
            "",
            "| Item | Status | Evidence |",
            "|---|---|---|",
            *(
                f"| {item.prompt} | `{item.status.value}` | {_md_value(item.evidence)} |"
                for item in review.expert_review_checklist
            ),
            "",
            "## 13. Limitations",
            "",
            f"- Codes: {_md_value(review.limitation_codes)}",
            "- Trip counts, directional counts, fleet resources, objective stages, and protected-floor policy remain unchanged.",
            "- Traffic variability, driver duties, breaks, depot work, deadhead, and maintenance remain outside the model.",
            "",
            "## 14. Artifact and fingerprint references",
            "",
            f"- Contract artifacts: {_md_value(artifacts.get('files'))}",
            f"- Authoritative references: {_md_value(review.authoritative_fingerprint_references)}",
            f"- Review fingerprint: `{review.review_fingerprint}`",
            f"- Profile: `{review.profile}`",
            "",
        ]
    )
    content = "\n".join(lines).encode("utf-8")
    if ("operationally" + "_approved").encode() in content.lower():
        raise ValueError("forbidden approval state in Markdown")
    return content


def _solver_divergence_from_review(review: RealRouteOperationalReviewV1) -> bool:
    h = review.heuristic_outcome_summary
    o = review.ortools_outcome_summary
    if not (h.get("requested") and o.get("requested")):
        return False
    if h.get("accepted") != o.get("accepted"):
        return True
    return bool(
        h.get("accepted")
        and o.get("accepted")
        and h.get("objective_vector") != o.get("objective_vector")
    )


def _unready_import() -> WorkbookInputReadinessV1:
    return WorkbookInputReadinessV1(
        import_ready=False,
        optimization_ready=False,
        blocking_import_codes=(WORKBOOK_IMPORT_INVALID,),
        missing_optimization_authority_codes=(),
        optional_limitations=(),
    )


def _verify_bounded_artifact_filenames(artifacts: UnifiedPage5ArtifactsV1) -> None:
    if not isinstance(artifacts, UnifiedPage5ArtifactsV1):
        raise TypeError("artifacts must be a UnifiedPage5ArtifactsV1")
    filenames = (
        ("XLSX", artifacts.xlsx_filename, UNIFIED_PAGE5_XLSX_FILENAME),
        ("HTML", artifacts.html_filename, UNIFIED_PAGE5_HTML_FILENAME),
        ("PNG", artifacts.png_filename, UNIFIED_PAGE5_PNG_FILENAME),
    )
    for artifact_kind, value, expected in filenames:
        if not isinstance(value, str):
            raise TypeError(f"{artifact_kind} artifact filename must be a string")
        if (
            value != expected
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or Path(value).name != value
        ):
            raise ValueError(
                f"{artifact_kind} artifact filename must be the approved Contract V1 basename"
            )


def _page5_artifacts(
    run: UnifiedApplicationRunV1,
    builder: Callable[..., UnifiedPage5ArtifactsV1],
) -> UnifiedPage5ArtifactsV1:
    presentation = run.unified_presentation
    if (
        presentation is None
        or run.unified_demand_supply_figure is None
        or run.unified_departure_figure is None
        or run.unified_xlsx_bytes is None
    ):
        raise ValueError("complete unified artifact inputs are unavailable")
    directions = available_unified_directions_v1(presentation)
    selected = "outbound" if "outbound" in directions else directions[0]
    artifacts = builder(
        presentation,
        run.unified_demand_supply_figure,
        run.unified_departure_figure,
        run.unified_xlsx_bytes,
        selected_direction=selected,
    )
    _verify_bounded_artifact_filenames(artifacts)
    return artifacts


def create_operational_review_package_v1(
    workbook: str | Path | bytes,
    *,
    source_id: str,
    solver_choice: SolverChoice,
    imported_at: datetime = REVIEW_IMPORTED_AT_V1,
    pipeline_runner: Callable[..., UnifiedApplicationRunV1] = run_unified_application_pipeline_v1,
    artifact_builder: Callable[..., UnifiedPage5ArtifactsV1] = build_unified_page5_artifacts_v1,
) -> OperationalReviewPackageV1:
    """Run one workbook through the unified boundary and build a bounded review package."""
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must be a non-empty string")
    if not isinstance(solver_choice, SolverChoice):
        raise TypeError("solver_choice must be a SolverChoice")
    if imported_at.tzinfo is None or imported_at.utcoffset() is None:
        raise ValueError("imported_at must be timezone-aware")
    try:
        imported = import_workbook(workbook)
    except Exception:
        readiness = _unready_import()
        review = build_operational_review_v1(
            source_id=source_id.strip(),
            requested_solver=solver_choice,
            readiness=readiness,
            run=None,
            artifacts=None,
            import_failed=True,
        )
        return OperationalReviewPackageV1(
            review=review,
            json_bytes=serialize_operational_review_v1(review),
            markdown_bytes=render_operational_review_markdown_v1(review),
            artifacts=None,
            exit_code=_REVIEW_EXIT_CODE_BY_STATUS_V1[review.pipeline_status],
        )

    try:
        run = pipeline_runner(
            imported,
            source_id=source_id.strip(),
            imported_at=imported_at,
            solver_choice=solver_choice,
        )
    except Exception:
        readiness = assess_workbook_input_readiness_v1(imported)
        review = build_operational_review_v1(
            source_id=source_id.strip(),
            requested_solver=solver_choice,
            readiness=readiness,
            run=None,
            artifacts=None,
        )
        return OperationalReviewPackageV1(
            review=review,
            json_bytes=serialize_operational_review_v1(review),
            markdown_bytes=render_operational_review_markdown_v1(review),
            artifacts=None,
            exit_code=_REVIEW_EXIT_CODE_BY_STATUS_V1[review.pipeline_status],
        )
    artifacts = None
    page5_failed = False
    if run.status == UnifiedApplicationStatusV1.COMPLETE:
        try:
            artifacts = _page5_artifacts(run, artifact_builder)
        except Exception:
            page5_failed = True
    review = build_operational_review_v1(
        source_id=source_id.strip(),
        requested_solver=solver_choice,
        readiness=run.input_readiness,
        run=run,
        artifacts=artifacts,
        page5_failed=page5_failed,
    )
    exit_code = _REVIEW_EXIT_CODE_BY_STATUS_V1[review.pipeline_status]
    return OperationalReviewPackageV1(
        review=review,
        json_bytes=serialize_operational_review_v1(review),
        markdown_bytes=render_operational_review_markdown_v1(review),
        artifacts=artifacts,
        exit_code=exit_code,
    )


def output_filenames_v1() -> tuple[str, ...]:
    return (
        REVIEW_JSON_FILENAME,
        REVIEW_MARKDOWN_FILENAME,
        UNIFIED_PAGE5_XLSX_FILENAME,
        UNIFIED_PAGE5_HTML_FILENAME,
        UNIFIED_PAGE5_PNG_FILENAME,
    )


def _verify_operational_review_package(package: OperationalReviewPackageV1) -> None:
    if not isinstance(package, OperationalReviewPackageV1):
        raise TypeError("package must be an OperationalReviewPackageV1")
    review = package.review
    if not verify_operational_review_fingerprint_v1(review):
        raise ValueError("review package model failed fingerprint or content verification")
    if package.json_bytes != serialize_operational_review_v1(review):
        raise ValueError("review package JSON does not belong to the supplied review")
    if package.markdown_bytes != render_operational_review_markdown_v1(review):
        raise ValueError("review package Markdown does not belong to the supplied review")
    try:
        expected_exit_code = _REVIEW_EXIT_CODE_BY_STATUS_V1[review.pipeline_status]
    except (KeyError, TypeError) as exc:
        raise ValueError("review package has an unsupported pipeline status") from exc
    if type(package.exit_code) is not int or package.exit_code != expected_exit_code:
        raise ValueError("review package exit code does not match its pipeline status")

    artifacts_expected = review.pipeline_status == ReviewPipelineStatusV1.REVIEW_COMPLETE
    artifacts_available = package.artifacts is not None
    if artifacts_available != artifacts_expected:
        raise ValueError("review package artifact presence does not match its pipeline status")
    metadata = review.artifact_metadata
    if not isinstance(metadata, Mapping):
        raise TypeError("review artifact metadata must be a mapping")
    if metadata.get("contract_v1_artifacts_available") is not artifacts_available:
        raise ValueError("review artifact availability metadata does not match the package")
    if metadata.get("artifact_boundary") != "EXISTING_UNIFIED_PAGE_05":
        raise ValueError("review artifact boundary metadata is invalid")

    if package.artifacts is None:
        if metadata.get("files") != ():
            raise ValueError("artifact-free review package must not list artifact filenames")
        return

    _verify_bounded_artifact_filenames(package.artifacts)
    expected_metadata = {
        "contract_v1_artifacts_available": True,
        "files": _approved_artifact_metadata_files(),
        "presentation_fingerprint": package.artifacts.presentation_fingerprint,
        "scenario_b_fingerprint": package.artifacts.b_fingerprint,
        "accepted_solution_fingerprint": package.artifacts.accepted_solution_fingerprint,
        "artifact_boundary": "EXISTING_UNIFIED_PAGE_05",
    }
    if metadata != expected_metadata:
        raise ValueError("review artifact metadata does not match the bounded artifact bundle")


def write_operational_review_package_v1(
    package: OperationalReviewPackageV1,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> tuple[Path, ...]:
    """Write only bounded filenames, removing stale Contract artifacts on failed reruns."""
    _verify_operational_review_package(package)
    target = Path(output_dir)
    collisions = tuple(target / name for name in output_filenames_v1() if (target / name).exists())
    if collisions and not overwrite:
        raise FileExistsError("review output already exists; pass --overwrite to replace it")
    target.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in collisions:
            if path.is_file():
                path.unlink()
            else:
                raise IsADirectoryError(
                    "a bounded review output filename is occupied by a directory"
                )
    written = []
    for name, content in (
        (REVIEW_JSON_FILENAME, package.json_bytes),
        (REVIEW_MARKDOWN_FILENAME, package.markdown_bytes),
    ):
        path = target / name
        path.write_bytes(content)
        written.append(path)
    if package.artifacts is not None:
        for name, content in (
            (UNIFIED_PAGE5_XLSX_FILENAME, package.artifacts.xlsx_bytes),
            (UNIFIED_PAGE5_HTML_FILENAME, package.artifacts.html_bytes),
            (UNIFIED_PAGE5_PNG_FILENAME, package.artifacts.png_bytes),
        ):
            path = target / name
            path.write_bytes(content)
            written.append(path)
    return tuple(written)


__all__ = [
    "ChecklistStatusV1",
    "EXPERT_REVIEW_REQUIRED",
    "ExpertChecklistItemV1",
    "NextDecisionCategoryV1",
    "OperationalReviewPackageV1",
    "REVIEW_IMPORTED_AT_V1",
    "REVIEW_JSON_FILENAME",
    "REVIEW_MARKDOWN_FILENAME",
    "REVIEW_PROFILE_V1",
    "RealRouteOperationalReviewV1",
    "ReviewDispositionV1",
    "ReviewFactAuthorityV1",
    "ReviewPipelineStatusV1",
    "build_operational_review_v1",
    "calculate_operational_review_fingerprint_v1",
    "create_operational_review_package_v1",
    "operational_review_to_dict_v1",
    "output_filenames_v1",
    "render_operational_review_markdown_v1",
    "serialize_operational_review_v1",
    "verify_operational_review_fingerprint_v1",
    "verify_operational_review_json_bytes_v1",
    "write_operational_review_package_v1",
]

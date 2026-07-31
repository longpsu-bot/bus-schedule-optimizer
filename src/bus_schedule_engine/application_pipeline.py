"""Application orchestration for the unified runtime and offline legacy oracle."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from .contracts_v1 import GenerationResultStatus, normalize_imported_workbook_v1
from .importer import ImportedWorkbook
from .input_authority import (
    WorkbookInputReadinessV1,
    assess_workbook_input_readiness_v1,
    normalization_options_from_workbook_v1,
)
from .models import (
    AnalysisBundle,
    ProtectedServiceFloorAssessmentV1,
    ProtectedServiceFloorEnforcementAuthorityV1,
    ProtectedServiceFloorEnforcementFailureV1,
    ProtectedServiceFloorFailureV1,
    TripRidershipAnalysisFailureV1,
    TripRidershipAnalysisV1,
)
from .optimization_service import (
    BusScheduleOptimizationResult,
    OptimizationExecutionErrorV1,
    OptimizationExecutionStageV1,
    SolverChoice,
    analyze_and_optimize_schedule_v1,
)
from .protected_service_floor import (
    assess_protected_service_floors_v1,
    protected_service_floor_assessment_is_current_v1,
    protected_service_floor_policy_from_workbook_v1,
)
from .protected_service_floor_codes import (
    PROTECTED_SERVICE_FLOOR_ASSESSMENT_FAILED,
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID,
)
from .protected_service_floor_enforcement import (
    ProtectedServiceFloorEnforcementAuthorityError,
    build_protected_service_floor_enforcement_authority_v1,
)
from .trip_ridership import analyze_trip_ridership_v1, trip_ridership_input_fingerprint_v1
from .trip_ridership_codes import TRIP_RIDERSHIP_ANALYSIS_FAILED
from .unified_diagram import (
    build_unified_demand_supply_figure_v1,
    build_unified_departure_figure_v1,
)
from .unified_presentation import (
    UnifiedPresentationBundleV1,
    UnifiedPresentationConsistencyError,
    build_unified_application_presentation_v1,
    build_unified_presentation_v1,
    verify_unified_presentation_integrity_v1,
)
from .unified_result_exporter import (
    export_unified_result_workbook_v1,
    read_unified_export_metadata_v1,
)

if TYPE_CHECKING:
    from .side_by_side_validation import SideBySideValidationReportV1
else:
    SideBySideValidationReportV1 = object

LOGGER = logging.getLogger(__name__)

UNIFIED_SHADOW_RUNTIME_FAILURE = "UNIFIED_SHADOW_RUNTIME_FAILED"
WORKBOOK_IMPORT_INVALID = "WORKBOOK_IMPORT_INVALID"
WORKBOOK_OPTIMIZATION_NOT_READY = "WORKBOOK_OPTIMIZATION_NOT_READY"
CONTRACT_V1_NORMALIZATION_FAILED = "CONTRACT_V1_NORMALIZATION_FAILED"
CONTRACT_V1_SOLVER_FAILED = "CONTRACT_V1_SOLVER_FAILED"
CONTRACT_V1_APPLICATION_ERROR = "CONTRACT_V1_APPLICATION_ERROR"
CONTRACT_V1_ARTIFACT_FAILED = "CONTRACT_V1_ARTIFACT_FAILED"
CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH = "CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH"

_LOCAL_PATH_PATTERN = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s,;]+|(?:/[^/\s]+){2,}")
_SENSITIVE_SOURCE_PATTERN = re.compile(
    r"(?i)\b(?:passenger observations?|raw workbook rows?|workbook bytes|raw rows?)\b"
)
_MAX_SANITIZED_MESSAGE_LENGTH = 240
_SAFE_IMPORT_SHEET_PATTERN = re.compile(
    r"\b(?:THONG_SO_[AB]|BIEU_DO_[AB]|SAN_LUONG(?:_CHUYEN)?|"
    r"THONG_TIN_(?:DU_LIEU|SAN_LUONG_CHUYEN)|CAU_HINH|HUONG_DAN)\b"
)
_SAFE_IMPORT_FIELD_PATTERN = re.compile(
    r"\b(?:"
    r"route_id|route_name|route_type|terminal_[12]_name|"
    r"terminal_[12]_(?:first|last)_departure|"
    r"terminal_[12]_max_occupancy_vehicles|"
    r"vehicle_capacity_passengers|total_daily_trips|minimum_layover_minutes|"
    r"allowed_trip_runtime_minutes|trip_runtime_minutes|available_fleet_limit|"
    r"approved_active_fleet|operating_day_type|target_load_factor|"
    r"maximum_load_factor|time_block_minutes|trip_id|departure_terminal|"
    r"direction|departure_time|arrival_time|vehicle_id|vehicle_capacity_override|"
    r"period_start|period_end|observation_days|time_block_start|time_block_end|"
    r"passenger_volume|volume_type|demand_dataset_id|demand_source_type|"
    r"demand_confidence|demand_response_mode|source_notes|observation_id|"
    r"service_date|source_trip_id|scheduled_trip_id|scheduled_departure_time|"
    r"actual_departure_time|passenger_count|trip_ridership_dataset_id|"
    r"trip_ridership_source_type|trip_ridership_confidence|"
    r"observed_schedule_scenario|match_tolerance_minutes"
    r")\b"
)


class UnifiedApplicationStatusV1(StrEnum):
    INPUT_NOT_READY = "INPUT_NOT_READY"
    COMPLETE = "COMPLETE"
    ARTIFACT_FAILED = "ARTIFACT_FAILED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class UnifiedRuntimeFailureV1:
    code: str
    stage: str
    correlation_id: str
    sanitized_message: str
    retryable: bool
    solver_choice: str
    source_id: str
    presentation_fingerprint: str | None
    b_fingerprint: str | None
    accepted_solution_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class UnifiedApplicationRunV1:
    status: UnifiedApplicationStatusV1
    input_readiness: WorkbookInputReadinessV1
    unified_result: BusScheduleOptimizationResult | None
    unified_presentation: UnifiedPresentationBundleV1 | None
    unified_demand_supply_figure: object | None
    unified_departure_figure: object | None
    unified_xlsx_bytes: bytes | None
    source_id: str
    imported_at: datetime
    failure: UnifiedRuntimeFailureV1 | None
    trip_ridership_analysis: TripRidershipAnalysisV1 | None = None
    trip_ridership_failure: TripRidershipAnalysisFailureV1 | None = None
    protected_service_floor_assessment: ProtectedServiceFloorAssessmentV1 | None = None
    protected_service_floor_failure: ProtectedServiceFloorFailureV1 | None = None
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None
    protected_service_floor_enforcement_failure: (
        ProtectedServiceFloorEnforcementFailureV1 | None
    ) = None


def run_and_build_artifacts(
    imported: ImportedWorkbook,
) -> tuple[AnalysisBundle, object, Mapping[str, bytes]]:
    """Load the legacy runtime only when the offline parallel adapter is invoked."""
    from .ui_utils import run_and_build_artifacts as legacy_runner

    return legacy_runner(imported)


def build_side_by_side_validation_report_v1(
    legacy_bundle: AnalysisBundle,
    unified_result: BusScheduleOptimizationResult,
) -> SideBySideValidationReportV1:
    """Load comparison code only for explicit offline parallel validation."""
    from .side_by_side_validation import (
        build_side_by_side_validation_report_v1 as legacy_comparator,
    )

    return legacy_comparator(legacy_bundle, unified_result)


def _sanitize_failure_message(exc: Exception) -> str:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    if _SENSITIVE_SOURCE_PATTERN.search(message):
        return f"{exc.__class__.__name__}: source-data details redacted"
    message = _LOCAL_PATH_PATTERN.sub("[path]", message)
    message = re.sub(r"\{[^{}]{1,200}\}", "{redacted}", message)
    return message[:_MAX_SANITIZED_MESSAGE_LENGTH]


def sanitize_import_error_message_v1(exc: Exception) -> str:
    """Return bounded import diagnostics without echoing workbook cell values."""
    message = " ".join(str(exc).split())
    sheets = tuple(sorted(set(_SAFE_IMPORT_SHEET_PATTERN.findall(message))))
    fields = tuple(sorted(set(_SAFE_IMPORT_FIELD_PATTERN.findall(message))))
    details = ["Workbook content or structure is invalid."]
    if sheets:
        details.append(f"Sheet: {', '.join(sheets)}.")
    if fields:
        details.append(f"Field: {', '.join(fields)}.")
    return f"{exc.__class__.__name__}: {' '.join(details)}"[:_MAX_SANITIZED_MESSAGE_LENGTH]


def _build_trip_ridership_analysis_failure_v1(
    *,
    imported: ImportedWorkbook,
    scenario_b_fingerprint: str,
    exc: Exception,
) -> TripRidershipAnalysisFailureV1:
    dataset_id = (
        imported.trip_ridership_metadata.dataset_id
        if imported.trip_ridership_metadata is not None
        else None
    )
    exception_class = exc.__class__.__name__
    payload = json.dumps(
        {
            "code": TRIP_RIDERSHIP_ANALYSIS_FAILED,
            "dataset_id": dataset_id,
            "scenario_b_fingerprint": scenario_b_fingerprint,
            "exception_class": exception_class,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    failure = TripRidershipAnalysisFailureV1(
        code=TRIP_RIDERSHIP_ANALYSIS_FAILED,
        correlation_id=f"m6a1-{hashlib.sha256(payload).hexdigest()[:20]}",
        sanitized_message=(f"{exception_class}: supplemental trip-ridership analysis failed")[
            :_MAX_SANITIZED_MESSAGE_LENGTH
        ],
        dataset_id=dataset_id,
        scenario_b_timetable_fingerprint=scenario_b_fingerprint,
    )
    LOGGER.error(
        "trip_ridership_analysis_failure correlation_id=%s code=%s "
        "exception_class=%s dataset_id=%s b_fingerprint=%s",
        failure.correlation_id,
        failure.code,
        exception_class,
        failure.dataset_id,
        failure.scenario_b_timetable_fingerprint,
    )
    return failure


def _build_protected_service_floor_failure_v1(
    *,
    imported: ImportedWorkbook,
    scenario_b_fingerprint: str,
    exc: Exception,
) -> ProtectedServiceFloorFailureV1:
    try:
        input_fingerprint = trip_ridership_input_fingerprint_v1(
            imported,
            scenario_b_fingerprint,
        )
    except Exception:
        input_fingerprint = None
    exception_class = exc.__class__.__name__
    payload = json.dumps(
        {
            "code": PROTECTED_SERVICE_FLOOR_ASSESSMENT_FAILED,
            "scenario_b_fingerprint": scenario_b_fingerprint,
            "trip_ridership_input_fingerprint": input_fingerprint,
            "exception_class": exception_class,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    failure = ProtectedServiceFloorFailureV1(
        code=PROTECTED_SERVICE_FLOOR_ASSESSMENT_FAILED,
        correlation_id=f"m6a2a-{hashlib.sha256(payload).hexdigest()[:20]}",
        sanitized_message=(
            f"{exception_class}: supplemental protected-service-floor assessment failed"
        )[:_MAX_SANITIZED_MESSAGE_LENGTH],
        scenario_b_fingerprint=scenario_b_fingerprint,
        trip_ridership_input_fingerprint=input_fingerprint,
    )
    LOGGER.error(
        "protected_service_floor_failure correlation_id=%s code=%s "
        "exception_class=%s b_fingerprint=%s trip_input_fingerprint=%s",
        failure.correlation_id,
        failure.code,
        exception_class,
        failure.scenario_b_fingerprint,
        failure.trip_ridership_input_fingerprint,
    )
    return failure


def _build_protected_service_floor_enforcement_failure_v1(
    *,
    scenario_b_fingerprint: str,
    assessment_fingerprint: str | None,
    exc: Exception,
) -> ProtectedServiceFloorEnforcementFailureV1:
    exception_class = exc.__class__.__name__
    payload = json.dumps(
        {
            "code": PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID,
            "scenario_b_fingerprint": scenario_b_fingerprint,
            "assessment_fingerprint": assessment_fingerprint,
            "exception_class": exception_class,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    failure = ProtectedServiceFloorEnforcementFailureV1(
        code=PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID,
        correlation_id=f"m6a2b-{hashlib.sha256(payload).hexdigest()[:20]}",
        sanitized_message=(
            f"{exception_class}: protected-service-floor enforcement authority invalid"
        )[:_MAX_SANITIZED_MESSAGE_LENGTH],
        scenario_b_fingerprint=scenario_b_fingerprint,
        assessment_fingerprint=assessment_fingerprint,
    )
    LOGGER.error(
        "protected_service_floor_enforcement_failure correlation_id=%s code=%s "
        "exception_class=%s b_fingerprint=%s assessment_fingerprint=%s",
        failure.correlation_id,
        failure.code,
        exception_class,
        failure.scenario_b_fingerprint,
        failure.assessment_fingerprint,
    )
    return failure


def _result_status_codes(
    result: BusScheduleOptimizationResult | None,
) -> tuple[str, ...]:
    if result is None:
        return ()
    codes = {
        outcome.result_status.value
        for outcome in (result.heuristic_outcome, result.ortools_outcome)
        if outcome is not None
    }
    return tuple(sorted(codes))


def build_unified_runtime_failure_v1(
    *,
    code: str,
    stage: str,
    exc: Exception,
    retryable: bool,
    solver_choice: SolverChoice,
    source_id: str,
    imported_at: datetime,
    input_readiness: WorkbookInputReadinessV1,
    result: BusScheduleOptimizationResult | None = None,
    presentation: UnifiedPresentationBundleV1 | None = None,
) -> UnifiedRuntimeFailureV1:
    """Build and log bounded, deterministic failure evidence."""
    sanitized_message = _sanitize_failure_message(exc)
    exception_class = getattr(
        exc,
        "original_exception_type",
        exc.__class__.__name__,
    )
    correlation_payload = json.dumps(
        {
            "source_id": source_id,
            "imported_at": imported_at.isoformat(),
            "stage": stage,
            "exception_class": exception_class,
            "sanitized_message": sanitized_message,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    correlation_id = f"m5c2-{hashlib.sha256(correlation_payload).hexdigest()[:20]}"
    b_fingerprint = result.normalized_inputs.scenario_b_fingerprint if result is not None else None
    outcome = result.recommended_outcome if result is not None else None
    result_accepted_solution_fingerprint = (
        outcome.solution.solution_fingerprint
        if outcome is not None
        and outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
        and outcome.solution is not None
        else None
    )
    accepted_solution_fingerprint = (
        presentation.accepted_solution_fingerprint
        if presentation is not None
        else result_accepted_solution_fingerprint
    )
    presentation_fingerprint = (
        presentation.presentation_fingerprint if presentation is not None else None
    )
    failure = UnifiedRuntimeFailureV1(
        code=code,
        stage=stage,
        correlation_id=correlation_id,
        sanitized_message=sanitized_message,
        retryable=retryable,
        solver_choice=solver_choice.value,
        source_id=source_id,
        presentation_fingerprint=presentation_fingerprint,
        b_fingerprint=b_fingerprint,
        accepted_solution_fingerprint=accepted_solution_fingerprint,
    )
    target_commit = os.environ.get("TARGET_COMMIT") or os.environ.get("GITHUB_SHA") or "unavailable"
    readiness_codes = tuple(
        sorted(
            {
                *input_readiness.blocking_import_codes,
                *input_readiness.missing_optimization_authority_codes,
            }
        )
    )
    LOGGER.error(
        "unified_runtime_failure correlation_id=%s target_commit=%s stage=%s "
        "code=%s exception_class=%s message=%s source_id=%s readiness_codes=%s "
        "solver_choice=%s result_status_codes=%s presentation_fingerprint=%s "
        "b_fingerprint=%s accepted_solution_fingerprint=%s",
        failure.correlation_id,
        target_commit,
        failure.stage,
        failure.code,
        exception_class,
        failure.sanitized_message,
        failure.source_id,
        readiness_codes,
        failure.solver_choice,
        _result_status_codes(result),
        failure.presentation_fingerprint,
        failure.b_fingerprint,
        failure.accepted_solution_fingerprint,
    )
    return failure


class ParallelRuntimeStatusV1(StrEnum):
    INPUT_NOT_READY = "INPUT_NOT_READY"
    PARALLEL_VALIDATION_COMPLETE = "PARALLEL_VALIDATION_COMPLETE"
    UNIFIED_RUNTIME_FAILED = "UNIFIED_RUNTIME_FAILED"


@dataclass(frozen=True, slots=True)
class ParallelApplicationRunV1:
    status: ParallelRuntimeStatusV1
    legacy_bundle: AnalysisBundle
    legacy_figure: object
    legacy_artifacts: Mapping[str, bytes]
    input_readiness: WorkbookInputReadinessV1 | None
    unified_result: BusScheduleOptimizationResult | None
    side_by_side_report: SideBySideValidationReportV1 | None
    unified_presentation: UnifiedPresentationBundleV1 | None
    unified_demand_supply_figure: object | None
    unified_departure_figure: object | None
    unified_xlsx_bytes: bytes | None
    source_id: str
    imported_at: datetime
    failure_code: str | None
    failure_message: str | None


class UnifiedArtifactAlignmentError(ValueError):
    """Raised when independently built unified artifacts do not share one identity."""


def _figure_metadata(figure: object, *, label: str) -> Mapping[str, object]:
    layout = getattr(figure, "layout", None)
    metadata = getattr(layout, "meta", None)
    if metadata is None:
        raise UnifiedArtifactAlignmentError(f"{label} figure metadata is missing")
    return dict(metadata)


def _verify_unified_artifact_alignment_v1(
    result: BusScheduleOptimizationResult,
    presentation: UnifiedPresentationBundleV1,
    demand_supply_figure: object,
    departure_figure: object,
    xlsx_path: Path,
    *,
    source_id: str,
) -> None:
    figure_metadata = (
        _figure_metadata(demand_supply_figure, label="demand/supply"),
        _figure_metadata(departure_figure, label="departure"),
    )
    xlsx_metadata = read_unified_export_metadata_v1(xlsx_path)

    presentation_fingerprints = {
        presentation.presentation_fingerprint,
        xlsx_metadata.presentation_fingerprint,
        *(str(metadata.get("presentation_fingerprint")) for metadata in figure_metadata),
    }
    if len(presentation_fingerprints) != 1:
        raise UnifiedArtifactAlignmentError("unified presentation fingerprints do not align")

    normalized_b_fingerprint = result.normalized_inputs.scenario_b_fingerprint
    b_fingerprints = {
        normalized_b_fingerprint,
        presentation.source_b_fingerprint,
        xlsx_metadata.b_fingerprint,
        *(str(metadata.get("source_b_fingerprint")) for metadata in figure_metadata),
    }
    if len(b_fingerprints) != 1:
        raise UnifiedArtifactAlignmentError("unified Scenario B fingerprints do not align")

    outcome = result.recommended_outcome
    result_accepted_fingerprint = (
        outcome.solution.solution_fingerprint
        if outcome is not None
        and outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
        and outcome.solution is not None
        else None
    )
    accepted_fingerprint = presentation.accepted_solution_fingerprint
    accepted_fingerprints = {
        result_accepted_fingerprint,
        accepted_fingerprint,
        xlsx_metadata.accepted_solution_fingerprint,
        *(metadata.get("accepted_solution_fingerprint") for metadata in figure_metadata),
    }
    if len(accepted_fingerprints) != 1:
        raise UnifiedArtifactAlignmentError("unified accepted-C fingerprints do not align")

    scenario_c = presentation.scenario("C")
    if accepted_fingerprint is None and scenario_c is not None:
        raise UnifiedArtifactAlignmentError(
            "unified Scenario C facts exist without an accepted solution fingerprint"
        )
    if accepted_fingerprint is not None and scenario_c is None:
        raise UnifiedArtifactAlignmentError(
            "accepted unified Scenario C fingerprint has no presentation timetable"
        )
    if presentation.source_id != source_id or xlsx_metadata.source_id != source_id:
        raise UnifiedArtifactAlignmentError("unified source identities do not align")


def _failed_unified_run(
    *,
    input_readiness: WorkbookInputReadinessV1,
    source_id: str,
    imported_at: datetime,
    solver_choice: SolverChoice,
    code: str,
    stage: str,
    exc: Exception,
    retryable: bool,
    result: BusScheduleOptimizationResult | None = None,
    presentation: UnifiedPresentationBundleV1 | None = None,
    retain_verified_presentation: bool = False,
    trip_ridership_analysis: TripRidershipAnalysisV1 | None = None,
    trip_ridership_failure: TripRidershipAnalysisFailureV1 | None = None,
    protected_service_floor_assessment: ProtectedServiceFloorAssessmentV1 | None = None,
    protected_service_floor_failure: ProtectedServiceFloorFailureV1 | None = None,
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
    protected_service_floor_enforcement_failure: (
        ProtectedServiceFloorEnforcementFailureV1 | None
    ) = None,
) -> UnifiedApplicationRunV1:
    failure = build_unified_runtime_failure_v1(
        code=code,
        stage=stage,
        exc=exc,
        retryable=retryable,
        solver_choice=solver_choice,
        source_id=source_id,
        imported_at=imported_at,
        input_readiness=input_readiness,
        result=result,
        presentation=presentation,
    )
    return UnifiedApplicationRunV1(
        status=(
            UnifiedApplicationStatusV1.ARTIFACT_FAILED
            if retain_verified_presentation
            else UnifiedApplicationStatusV1.FAILED
        ),
        input_readiness=input_readiness,
        unified_result=result if retain_verified_presentation else None,
        unified_presentation=presentation if retain_verified_presentation else None,
        unified_demand_supply_figure=None,
        unified_departure_figure=None,
        unified_xlsx_bytes=None,
        source_id=source_id,
        imported_at=imported_at,
        failure=failure,
        trip_ridership_analysis=(trip_ridership_analysis if retain_verified_presentation else None),
        trip_ridership_failure=(trip_ridership_failure if retain_verified_presentation else None),
        protected_service_floor_assessment=(
            protected_service_floor_assessment if retain_verified_presentation else None
        ),
        protected_service_floor_failure=(
            protected_service_floor_failure if retain_verified_presentation else None
        ),
        protected_service_floor_enforcement_authority=(
            protected_service_floor_enforcement_authority if retain_verified_presentation else None
        ),
        protected_service_floor_enforcement_failure=(
            protected_service_floor_enforcement_failure if retain_verified_presentation else None
        ),
    )


def _execution_failure_code(stage: OptimizationExecutionStageV1) -> str:
    if stage == OptimizationExecutionStageV1.NORMALIZATION:
        return CONTRACT_V1_NORMALIZATION_FAILED
    if stage in {
        OptimizationExecutionStageV1.HEURISTIC_SOLVER,
        OptimizationExecutionStageV1.OR_TOOLS_SOLVER,
        OptimizationExecutionStageV1.SOLVER_COMPARISON,
    }:
        return CONTRACT_V1_SOLVER_FAILED
    return CONTRACT_V1_APPLICATION_ERROR


def run_unified_application_pipeline_v1(
    imported: ImportedWorkbook,
    *,
    source_id: str,
    imported_at: datetime,
    solver_choice: SolverChoice = SolverChoice.HEURISTIC,
) -> UnifiedApplicationRunV1:
    """Run the ordinary application path using Contract V1 only."""
    unified_input = deepcopy(imported)
    input_readiness = assess_workbook_input_readiness_v1(unified_input)
    if not input_readiness.optimization_ready:
        return UnifiedApplicationRunV1(
            status=UnifiedApplicationStatusV1.INPUT_NOT_READY,
            input_readiness=input_readiness,
            unified_result=None,
            unified_presentation=None,
            unified_demand_supply_figure=None,
            unified_departure_figure=None,
            unified_xlsx_bytes=None,
            source_id=source_id,
            imported_at=imported_at,
            failure=None,
        )

    try:
        normalization_options = normalization_options_from_workbook_v1(
            unified_input,
            source_id=source_id,
            imported_at=imported_at,
        )
        normalized_inputs = normalize_imported_workbook_v1(
            unified_input,
            normalization_options,
        )
    except Exception as exc:
        return _failed_unified_run(
            input_readiness=input_readiness,
            source_id=source_id,
            imported_at=imported_at,
            solver_choice=solver_choice,
            code=CONTRACT_V1_NORMALIZATION_FAILED,
            stage=OptimizationExecutionStageV1.NORMALIZATION.value,
            exc=exc,
            retryable=False,
        )

    scenario_b_fingerprint = normalized_inputs.scenario_b_fingerprint
    trip_ridership_analysis: TripRidershipAnalysisV1 | None = None
    trip_ridership_failure: TripRidershipAnalysisFailureV1 | None = None
    if unified_input.trip_ridership_observations:
        try:
            trip_ridership_analysis = analyze_trip_ridership_v1(
                unified_input,
                normalized_inputs.scenario_b,
            )
            if trip_ridership_analysis.scenario_b_timetable_fingerprint != (scenario_b_fingerprint):
                raise ValueError(
                    "Supplemental trip-ridership analysis is not bound to "
                    "the normalized Scenario B fingerprint"
                )
        except Exception as exc:
            trip_ridership_analysis = None
            trip_ridership_failure = _build_trip_ridership_analysis_failure_v1(
                imported=unified_input,
                scenario_b_fingerprint=scenario_b_fingerprint,
                exc=exc,
            )

    protected_service_floor_assessment: ProtectedServiceFloorAssessmentV1 | None = None
    protected_service_floor_failure: ProtectedServiceFloorFailureV1 | None = None
    try:
        protected_service_floor_assessment = assess_protected_service_floors_v1(
            unified_input,
            normalized_inputs.scenario_b,
            trip_ridership_analysis,
            protected_service_floor_policy_from_workbook_v1(unified_input),
        )
        if protected_service_floor_assessment.scenario_b_fingerprint != (scenario_b_fingerprint):
            raise ValueError(
                "Protected-service-floor assessment is not bound to "
                "the normalized Scenario B fingerprint"
            )
    except Exception as exc:
        protected_service_floor_assessment = None
        protected_service_floor_failure = _build_protected_service_floor_failure_v1(
            imported=unified_input,
            scenario_b_fingerprint=scenario_b_fingerprint,
            exc=exc,
        )

    protected_service_floor_enforcement_authority = None
    protected_service_floor_enforcement_failure = None
    try:
        if trip_ridership_failure is not None:
            raise ProtectedServiceFloorEnforcementAuthorityError(
                f"{PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID}: "
                "trip-ridership analysis failed"
            )
        if protected_service_floor_assessment is None:
            raise ProtectedServiceFloorEnforcementAuthorityError(
                f"{PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID}: "
                "the 6A2A assessment is unavailable"
            )
        if not protected_service_floor_assessment_is_current_v1(
            protected_service_floor_assessment,
            unified_input,
            normalized_inputs.scenario_b,
            trip_ridership_analysis,
        ):
            raise ProtectedServiceFloorEnforcementAuthorityError(
                f"{PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID}: "
                "the 6A2A assessment is not current"
            )
        protected_service_floor_enforcement_authority = (
            build_protected_service_floor_enforcement_authority_v1(
                unified_input,
                normalized_inputs.scenario_b,
                trip_ridership_analysis,
                protected_service_floor_assessment,
            )
        )
    except Exception as exc:
        protected_service_floor_enforcement_authority = None
        protected_service_floor_enforcement_failure = (
            _build_protected_service_floor_enforcement_failure_v1(
                scenario_b_fingerprint=scenario_b_fingerprint,
                assessment_fingerprint=(
                    protected_service_floor_assessment.assessment_fingerprint
                    if protected_service_floor_assessment is not None
                    else None
                ),
                exc=exc,
            )
        )

    try:
        unified_result = analyze_and_optimize_schedule_v1(
            unified_input,
            normalization_options,
            solver_choice=solver_choice,
            protected_service_floor_enforcement_authority=(
                protected_service_floor_enforcement_authority
            ),
            protected_service_floor_enforcement_failure_code=(
                protected_service_floor_enforcement_failure.code
                if protected_service_floor_enforcement_failure is not None
                else None
            ),
            _normalized_inputs=normalized_inputs,
        )
    except OptimizationExecutionErrorV1 as exc:
        return _failed_unified_run(
            input_readiness=input_readiness,
            source_id=source_id,
            imported_at=imported_at,
            solver_choice=solver_choice,
            code=_execution_failure_code(exc.stage),
            stage=exc.stage.value,
            exc=exc,
            retryable=exc.stage
            in {
                OptimizationExecutionStageV1.HEURISTIC_SOLVER,
                OptimizationExecutionStageV1.OR_TOOLS_SOLVER,
                OptimizationExecutionStageV1.SOLVER_COMPARISON,
            },
        )
    except Exception as exc:
        return _failed_unified_run(
            input_readiness=input_readiness,
            source_id=source_id,
            imported_at=imported_at,
            solver_choice=solver_choice,
            code=CONTRACT_V1_APPLICATION_ERROR,
            stage="UNKNOWN",
            exc=exc,
            retryable=True,
        )

    try:
        presentation = build_unified_application_presentation_v1(unified_result)
        verify_unified_presentation_integrity_v1(presentation)
        normalized_source_id = unified_result.normalized_inputs.scenario_b.source_metadata.source_id
        if normalized_source_id != source_id or presentation.source_id != source_id:
            raise UnifiedPresentationConsistencyError(
                "SOURCE_IDENTITY_MISMATCH: normalized Scenario B and presentation "
                "must share the submitted source identity"
            )
    except UnifiedPresentationConsistencyError as exc:
        return _failed_unified_run(
            input_readiness=input_readiness,
            source_id=source_id,
            imported_at=imported_at,
            solver_choice=solver_choice,
            code=CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH,
            stage=OptimizationExecutionStageV1.PRESENTATION.value,
            exc=exc,
            retryable=False,
            result=unified_result,
        )
    except Exception as exc:
        return _failed_unified_run(
            input_readiness=input_readiness,
            source_id=source_id,
            imported_at=imported_at,
            solver_choice=solver_choice,
            code=CONTRACT_V1_APPLICATION_ERROR,
            stage=OptimizationExecutionStageV1.PRESENTATION.value,
            exc=exc,
            retryable=True,
            result=unified_result,
        )

    try:
        demand_supply_figure = build_unified_demand_supply_figure_v1(presentation)
        departure_figure = build_unified_departure_figure_v1(presentation)
        with TemporaryDirectory(prefix="bus_schedule_contract_v1_") as directory:
            xlsx_path = export_unified_result_workbook_v1(
                presentation,
                Path(directory) / "Bus_Schedule_Contract_V1_Result.xlsx",
                overwrite=False,
            )
            _verify_unified_artifact_alignment_v1(
                unified_result,
                presentation,
                demand_supply_figure,
                departure_figure,
                xlsx_path,
                source_id=source_id,
            )
            xlsx_bytes = xlsx_path.read_bytes()
    except (UnifiedPresentationConsistencyError, UnifiedArtifactAlignmentError) as exc:
        return _failed_unified_run(
            input_readiness=input_readiness,
            source_id=source_id,
            imported_at=imported_at,
            solver_choice=solver_choice,
            code=CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH,
            stage=OptimizationExecutionStageV1.ARTIFACTS.value,
            exc=exc,
            retryable=False,
            result=unified_result,
            presentation=presentation,
            trip_ridership_analysis=trip_ridership_analysis,
            trip_ridership_failure=trip_ridership_failure,
            protected_service_floor_assessment=protected_service_floor_assessment,
            protected_service_floor_failure=protected_service_floor_failure,
            protected_service_floor_enforcement_authority=(
                protected_service_floor_enforcement_authority
            ),
            protected_service_floor_enforcement_failure=(
                protected_service_floor_enforcement_failure
            ),
        )
    except Exception as exc:
        return _failed_unified_run(
            input_readiness=input_readiness,
            source_id=source_id,
            imported_at=imported_at,
            solver_choice=solver_choice,
            code=CONTRACT_V1_ARTIFACT_FAILED,
            stage=OptimizationExecutionStageV1.ARTIFACTS.value,
            exc=exc,
            retryable=True,
            result=unified_result,
            presentation=presentation,
            retain_verified_presentation=True,
            trip_ridership_analysis=trip_ridership_analysis,
            trip_ridership_failure=trip_ridership_failure,
            protected_service_floor_assessment=protected_service_floor_assessment,
            protected_service_floor_failure=protected_service_floor_failure,
            protected_service_floor_enforcement_authority=(
                protected_service_floor_enforcement_authority
            ),
            protected_service_floor_enforcement_failure=(
                protected_service_floor_enforcement_failure
            ),
        )

    return UnifiedApplicationRunV1(
        status=UnifiedApplicationStatusV1.COMPLETE,
        input_readiness=input_readiness,
        unified_result=unified_result,
        unified_presentation=presentation,
        unified_demand_supply_figure=demand_supply_figure,
        unified_departure_figure=departure_figure,
        unified_xlsx_bytes=xlsx_bytes,
        source_id=source_id,
        imported_at=imported_at,
        failure=None,
        trip_ridership_analysis=trip_ridership_analysis,
        trip_ridership_failure=trip_ridership_failure,
        protected_service_floor_assessment=protected_service_floor_assessment,
        protected_service_floor_failure=protected_service_floor_failure,
        protected_service_floor_enforcement_authority=(
            protected_service_floor_enforcement_authority
        ),
        protected_service_floor_enforcement_failure=(protected_service_floor_enforcement_failure),
    )


def _failed_shadow_run(
    *,
    legacy_bundle: AnalysisBundle,
    legacy_figure: object,
    legacy_artifacts: Mapping[str, bytes],
    input_readiness: WorkbookInputReadinessV1 | None,
    source_id: str,
    imported_at: datetime,
    exc: Exception,
) -> ParallelApplicationRunV1:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    return ParallelApplicationRunV1(
        status=ParallelRuntimeStatusV1.UNIFIED_RUNTIME_FAILED,
        legacy_bundle=legacy_bundle,
        legacy_figure=legacy_figure,
        legacy_artifacts=legacy_artifacts,
        input_readiness=input_readiness,
        unified_result=None,
        side_by_side_report=None,
        unified_presentation=None,
        unified_demand_supply_figure=None,
        unified_departure_figure=None,
        unified_xlsx_bytes=None,
        source_id=source_id,
        imported_at=imported_at,
        failure_code=UNIFIED_SHADOW_RUNTIME_FAILURE,
        failure_message=message,
    )


def run_parallel_application_pipeline_v1(
    imported: ImportedWorkbook,
    *,
    source_id: str,
    imported_at: datetime,
    solver_choice: SolverChoice = SolverChoice.HEURISTIC,
) -> ParallelApplicationRunV1:
    """Run legacy once, then build non-authoritative unified evidence when ready."""
    legacy_input = deepcopy(imported)
    unified_input = deepcopy(imported)
    legacy_bundle, legacy_figure, legacy_artifacts = run_and_build_artifacts(legacy_input)
    input_readiness: WorkbookInputReadinessV1 | None = None

    try:
        input_readiness = assess_workbook_input_readiness_v1(unified_input)
        if not input_readiness.optimization_ready:
            return ParallelApplicationRunV1(
                status=ParallelRuntimeStatusV1.INPUT_NOT_READY,
                legacy_bundle=legacy_bundle,
                legacy_figure=legacy_figure,
                legacy_artifacts=legacy_artifacts,
                input_readiness=input_readiness,
                unified_result=None,
                side_by_side_report=None,
                unified_presentation=None,
                unified_demand_supply_figure=None,
                unified_departure_figure=None,
                unified_xlsx_bytes=None,
                source_id=source_id,
                imported_at=imported_at,
                failure_code=None,
                failure_message=None,
            )
        normalization_options = normalization_options_from_workbook_v1(
            unified_input,
            source_id=source_id,
            imported_at=imported_at,
        )
        unified_result = analyze_and_optimize_schedule_v1(
            unified_input,
            normalization_options,
            solver_choice=solver_choice,
        )
        side_by_side_report = build_side_by_side_validation_report_v1(
            legacy_bundle,
            unified_result,
        )
        presentation = build_unified_presentation_v1(
            unified_result,
            side_by_side_report,
        )
        demand_supply_figure = build_unified_demand_supply_figure_v1(presentation)
        departure_figure = build_unified_departure_figure_v1(presentation)
        with TemporaryDirectory(prefix="bus_schedule_unified_shadow_") as directory:
            xlsx_path = export_unified_result_workbook_v1(
                presentation,
                Path(directory) / "Bus_Schedule_Contract_V1_Validation.xlsx",
                overwrite=False,
            )
            _verify_unified_artifact_alignment_v1(
                unified_result,
                presentation,
                demand_supply_figure,
                departure_figure,
                xlsx_path,
                source_id=source_id,
            )
            xlsx_bytes = xlsx_path.read_bytes()
    except Exception as exc:
        return _failed_shadow_run(
            legacy_bundle=legacy_bundle,
            legacy_figure=legacy_figure,
            legacy_artifacts=legacy_artifacts,
            input_readiness=input_readiness,
            source_id=source_id,
            imported_at=imported_at,
            exc=exc,
        )

    return ParallelApplicationRunV1(
        status=ParallelRuntimeStatusV1.PARALLEL_VALIDATION_COMPLETE,
        legacy_bundle=legacy_bundle,
        legacy_figure=legacy_figure,
        legacy_artifacts=legacy_artifacts,
        input_readiness=input_readiness,
        unified_result=unified_result,
        side_by_side_report=side_by_side_report,
        unified_presentation=presentation,
        unified_demand_supply_figure=demand_supply_figure,
        unified_departure_figure=departure_figure,
        unified_xlsx_bytes=xlsx_bytes,
        source_id=source_id,
        imported_at=imported_at,
        failure_code=None,
        failure_message=None,
    )


__all__ = [
    "CONTRACT_V1_APPLICATION_ERROR",
    "CONTRACT_V1_ARTIFACT_FAILED",
    "CONTRACT_V1_NORMALIZATION_FAILED",
    "CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH",
    "CONTRACT_V1_SOLVER_FAILED",
    "ParallelApplicationRunV1",
    "ParallelRuntimeStatusV1",
    "UNIFIED_SHADOW_RUNTIME_FAILURE",
    "UnifiedApplicationRunV1",
    "UnifiedApplicationStatusV1",
    "UnifiedArtifactAlignmentError",
    "UnifiedRuntimeFailureV1",
    "WORKBOOK_IMPORT_INVALID",
    "WORKBOOK_OPTIMIZATION_NOT_READY",
    "build_unified_runtime_failure_v1",
    "run_parallel_application_pipeline_v1",
    "run_unified_application_pipeline_v1",
    "sanitize_import_error_message_v1",
]

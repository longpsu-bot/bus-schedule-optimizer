"""Application-layer orchestration for the legacy-authoritative shadow runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory

from .contracts_v1 import GenerationResultStatus
from .importer import ImportedWorkbook
from .input_authority import (
    WorkbookInputReadinessV1,
    assess_workbook_input_readiness_v1,
    normalization_options_from_workbook_v1,
)
from .models import AnalysisBundle
from .optimization_service import (
    BusScheduleOptimizationResult,
    SolverChoice,
    analyze_and_optimize_schedule_v1,
)
from .side_by_side_validation import (
    SideBySideValidationReportV1,
    build_side_by_side_validation_report_v1,
)
from .ui_utils import run_and_build_artifacts
from .unified_diagram import (
    build_unified_demand_supply_figure_v1,
    build_unified_departure_figure_v1,
)
from .unified_presentation import (
    UnifiedPresentationBundleV1,
    build_unified_presentation_v1,
)
from .unified_result_exporter import (
    export_unified_result_workbook_v1,
    read_unified_export_metadata_v1,
)

UNIFIED_SHADOW_RUNTIME_FAILURE = "UNIFIED_SHADOW_RUNTIME_FAILED"


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
    input_readiness: WorkbookInputReadinessV1
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


def _failed_shadow_run(
    *,
    legacy_bundle: AnalysisBundle,
    legacy_figure: object,
    legacy_artifacts: Mapping[str, bytes],
    input_readiness: WorkbookInputReadinessV1,
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
    legacy_bundle, legacy_figure, legacy_artifacts = run_and_build_artifacts(imported)
    input_readiness = assess_workbook_input_readiness_v1(imported)

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

    try:
        normalization_options = normalization_options_from_workbook_v1(
            imported,
            source_id=source_id,
            imported_at=imported_at,
        )
        unified_result = analyze_and_optimize_schedule_v1(
            imported,
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
    "ParallelApplicationRunV1",
    "ParallelRuntimeStatusV1",
    "UNIFIED_SHADOW_RUNTIME_FAILURE",
    "UnifiedArtifactAlignmentError",
    "run_parallel_application_pipeline_v1",
]

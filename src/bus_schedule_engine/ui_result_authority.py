"""Pure visible-result authority resolution for Streamlit result pages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .application_pipeline import (
    UNIFIED_SHADOW_RUNTIME_FAILURE,
    ParallelRuntimeStatusV1,
)
from .contracts_v1 import GenerationResultStatus
from .input_authority import WorkbookInputReadinessV1
from .models import AnalysisBundle
from .optimization_service import BusScheduleOptimizationResult
from .side_by_side_validation import SideBySideValidationReportV1
from .unified_presentation import (
    PRESENTATION_MODE_VALIDATION_ONLY,
    UnifiedPresentationBundleV1,
    UnifiedPresentationConsistencyError,
    verify_unified_presentation_integrity_v1,
)

UNIFIED_VISIBLE_STATE_INCOMPLETE = "UNIFIED_VISIBLE_STATE_INCOMPLETE"

_UNIFIED_BANNER = (
    "Nguồn kết quả hiển thị: Contract V1.\n\n"
    "Kết quả hỗ trợ chuyên gia và không tự động thay thế quyết định khai thác."
)
_LEGACY_BANNER_PREFIX = "Nguồn kết quả hiển thị: pipeline legacy."
_NO_RESULT_MESSAGE = "Chưa có kết quả. Hãy chạy phân tích ở trang Nhập dữ liệu."


class VisibleResultModeV1(StrEnum):
    """The single visible authority selected for result Pages 02–04."""

    NO_RESULT = "NO_RESULT"
    UNIFIED_CONTRACT_V1 = "UNIFIED_CONTRACT_V1"
    LEGACY_INPUT_NOT_READY = "LEGACY_INPUT_NOT_READY"
    LEGACY_UNIFIED_FAILED = "LEGACY_UNIFIED_FAILED"
    LEGACY_CUTOVER_BLOCKED = "LEGACY_CUTOVER_BLOCKED"
    LEGACY_INCOMPLETE_SHADOW_STATE = "LEGACY_INCOMPLETE_SHADOW_STATE"


@dataclass(frozen=True, slots=True)
class VisibleResultContextV1:
    """Resolved visible authority and the only unified objects pages may consume."""

    mode: VisibleResultModeV1
    uses_unified: bool
    presentation: UnifiedPresentationBundleV1 | None
    unified_result: BusScheduleOptimizationResult | None
    report: SideBySideValidationReportV1 | None
    banner_level: str
    banner_message: str
    reason_codes: tuple[str, ...]


def _no_result_context() -> VisibleResultContextV1:
    return VisibleResultContextV1(
        mode=VisibleResultModeV1.NO_RESULT,
        uses_unified=False,
        presentation=None,
        unified_result=None,
        report=None,
        banner_level="warning",
        banner_message=_NO_RESULT_MESSAGE,
        reason_codes=(),
    )


def _legacy_context(
    mode: VisibleResultModeV1,
    *,
    reason: str,
    reason_codes: tuple[str, ...],
) -> VisibleResultContextV1:
    return VisibleResultContextV1(
        mode=mode,
        uses_unified=False,
        presentation=None,
        unified_result=None,
        report=None,
        banner_level="warning",
        banner_message=f"{_LEGACY_BANNER_PREFIX}\n\n{reason}",
        reason_codes=reason_codes,
    )


def _input_not_ready_context(
    readiness: WorkbookInputReadinessV1 | None,
) -> VisibleResultContextV1:
    codes = (
        tuple(readiness.missing_optimization_authority_codes)
        if isinstance(readiness, WorkbookInputReadinessV1)
        else ()
    )
    code_text = "\n".join(f"- {code}" for code in codes) or "- Không có mã thẩm quyền được trả về."
    return _legacy_context(
        VisibleResultModeV1.LEGACY_INPUT_NOT_READY,
        reason=(
            "Đang hiển thị kết quả chẩn đoán legacy.\n\n"
            "Dữ liệu chưa đủ thẩm quyền để chạy Contract V1:\n"
            f"{code_text}"
        ),
        reason_codes=codes,
    )


def _runtime_failed_context(
    failure: Mapping[str, object] | None,
) -> VisibleResultContextV1:
    code = UNIFIED_SHADOW_RUNTIME_FAILURE
    message = "Contract V1 không hoàn tất; không sử dụng bất kỳ trạng thái unified từng phần nào."
    if isinstance(failure, Mapping):
        supplied_code = failure.get("code")
        supplied_message = failure.get("message")
        if isinstance(supplied_code, str) and supplied_code:
            code = supplied_code
        if isinstance(supplied_message, str) and supplied_message:
            message = supplied_message
    return _legacy_context(
        VisibleResultModeV1.LEGACY_UNIFIED_FAILED,
        reason=(
            "Đang hiển thị kết quả chẩn đoán legacy vì runtime Contract V1 thất bại.\n\n"
            f"Mã: {code}\n\nThông tin: {message}"
        ),
        reason_codes=(code,),
    )


def _cutover_blocked_context(codes: tuple[str, ...]) -> VisibleResultContextV1:
    code_text = "\n".join(f"- {code}" for code in codes)
    return _legacy_context(
        VisibleResultModeV1.LEGACY_CUTOVER_BLOCKED,
        reason=(f"Cutover Contract V1 bị chặn bởi các sai lệch đối chiếu sau:\n{code_text}"),
        reason_codes=codes,
    )


def _incomplete_context() -> VisibleResultContextV1:
    return _legacy_context(
        VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE,
        reason=(
            "Bằng chứng shadow Contract V1 chưa đầy đủ hoặc không nhất quán.\n\n"
            f"Mã: {UNIFIED_VISIBLE_STATE_INCOMPLETE}"
        ),
        reason_codes=(UNIFIED_VISIBLE_STATE_INCOMPLETE,),
    )


def _figure_metadata(figure: object) -> Mapping[str, object] | None:
    try:
        metadata = figure.layout.meta
    except (AttributeError, TypeError):
        return None
    if isinstance(metadata, Mapping):
        return metadata
    try:
        converted = dict(metadata)
    except (TypeError, ValueError):
        return None
    return converted


def _blocking_codes(
    report: SideBySideValidationReportV1 | None,
    presentation: UnifiedPresentationBundleV1 | None,
) -> tuple[str, ...]:
    values: list[str] = []
    if isinstance(report, SideBySideValidationReportV1):
        values.extend(report.blocking_discrepancy_codes)
    if isinstance(presentation, UnifiedPresentationBundleV1):
        values.extend(presentation.blocking_discrepancy_codes)
    return tuple(dict.fromkeys(values))


def _accepted_result_fingerprint(
    result: BusScheduleOptimizationResult,
) -> tuple[bool, str | None]:
    outcome = result.recommended_outcome
    if outcome is None or outcome.result_status != GenerationResultStatus.SOLUTION_ACCEPTED:
        return True, None
    solution = outcome.solution
    if solution is None or not isinstance(solution.solution_fingerprint, str):
        return False, None
    return bool(solution.solution_fingerprint), solution.solution_fingerprint


def _presentation_shape_is_consistent(
    presentation: UnifiedPresentationBundleV1,
    *,
    b_fingerprint: str,
    accepted_fingerprint: str | None,
) -> bool:
    scenario_ids = tuple(item.scenario_id for item in presentation.scenarios)
    if len(scenario_ids) != len(set(scenario_ids)):
        return False
    scenario_b = presentation.scenario("B")
    scenario_c = presentation.scenario("C")
    if scenario_b is None or scenario_b.source_fingerprint != b_fingerprint:
        return False

    for dimension in presentation.dimensions:
        issue_count = len(dimension.issue_codes)
        if not (
            len(dimension.issue_severities) == issue_count
            and len(dimension.issue_messages) == issue_count
        ):
            return False

    outcome = presentation.outcome
    if outcome.accepted_solution_fingerprint != accepted_fingerprint:
        return False
    if accepted_fingerprint is None:
        if (
            outcome.accepted_c_exists
            or scenario_c is not None
            or presentation.initial_fleet is not None
            or presentation.fleet_assignments
            or presentation.headway_regimes
        ):
            return False
        c_fields = (
            "c_actual_trip_count",
            "c_nominal_capacity",
            "c_load_factor",
            "c_shortage",
            "c_status",
            "c_allocation_reason",
        )
        return all(
            getattr(block, field_name) is None
            for block in presentation.blocks
            for field_name in c_fields
        )

    return bool(
        outcome.accepted_c_exists
        and outcome.accepted_c_authority
        and scenario_c is not None
        and scenario_c.source_fingerprint == accepted_fingerprint
        and presentation.initial_fleet is not None
    )


def _completed_state_is_aligned(
    *,
    input_readiness: WorkbookInputReadinessV1 | None,
    unified_result: BusScheduleOptimizationResult | None,
    report: SideBySideValidationReportV1 | None,
    presentation: UnifiedPresentationBundleV1 | None,
    unified_demand_supply_figure: object | None,
    unified_departure_figure: object | None,
    unified_download_artifacts: Mapping[str, object] | None,
) -> bool:
    if not (
        isinstance(input_readiness, WorkbookInputReadinessV1)
        and input_readiness.optimization_ready is True
        and isinstance(unified_result, BusScheduleOptimizationResult)
        and isinstance(report, SideBySideValidationReportV1)
        and isinstance(presentation, UnifiedPresentationBundleV1)
        and unified_demand_supply_figure is not None
        and unified_departure_figure is not None
        and isinstance(unified_download_artifacts, Mapping)
    ):
        return False
    try:
        verify_unified_presentation_integrity_v1(presentation)
    except (UnifiedPresentationConsistencyError, TypeError):
        return False
    if presentation.presentation_mode != PRESENTATION_MODE_VALIDATION_ONLY:
        return False
    if presentation.cutover_blocked:
        return False
    if report.blocking_discrepancy_codes != presentation.blocking_discrepancy_codes:
        return False

    required_download_keys = {
        "xlsx",
        "presentation_fingerprint",
        "b_fingerprint",
        "accepted_solution_fingerprint",
    }
    if not required_download_keys.issubset(unified_download_artifacts):
        return False
    xlsx = unified_download_artifacts["xlsx"]
    if not isinstance(xlsx, bytes | bytearray | memoryview) or not xlsx:
        return False

    demand_metadata = _figure_metadata(unified_demand_supply_figure)
    departure_metadata = _figure_metadata(unified_departure_figure)
    if demand_metadata is None or departure_metadata is None:
        return False
    required_figure_keys = {
        "presentation_fingerprint",
        "source_b_fingerprint",
        "accepted_solution_fingerprint",
    }
    if not (
        required_figure_keys.issubset(demand_metadata)
        and required_figure_keys.issubset(departure_metadata)
    ):
        return False

    presentation_fingerprint = presentation.presentation_fingerprint
    if not isinstance(presentation_fingerprint, str) or not presentation_fingerprint:
        return False
    if any(
        value != presentation_fingerprint
        for value in (
            demand_metadata["presentation_fingerprint"],
            departure_metadata["presentation_fingerprint"],
            unified_download_artifacts["presentation_fingerprint"],
        )
    ):
        return False

    normalized = unified_result.normalized_inputs
    b_fingerprint = normalized.scenario_b_fingerprint
    if not isinstance(b_fingerprint, str) or not b_fingerprint:
        return False
    if any(
        value != b_fingerprint
        for value in (
            presentation.source_b_fingerprint,
            report.unified_snapshot.normalized_scenario_b_fingerprint,
            demand_metadata["source_b_fingerprint"],
            departure_metadata["source_b_fingerprint"],
            unified_download_artifacts["b_fingerprint"],
        )
    ):
        return False

    accepted_state_valid, accepted_fingerprint = _accepted_result_fingerprint(unified_result)
    if not accepted_state_valid:
        return False
    if any(
        value != accepted_fingerprint
        for value in (
            presentation.accepted_solution_fingerprint,
            report.unified_snapshot.solution_fingerprint,
            demand_metadata["accepted_solution_fingerprint"],
            departure_metadata["accepted_solution_fingerprint"],
            unified_download_artifacts["accepted_solution_fingerprint"],
        )
    ):
        return False

    scenario_b = normalized.scenario_b
    source_metadata = scenario_b.source_metadata
    if (
        presentation.source_id != source_metadata.source_id
        or presentation.imported_at != source_metadata.imported_at.isoformat()
        or presentation.route_id != scenario_b.route_id
        or presentation.route_name != scenario_b.route_name
        or presentation.terminal_1_name != scenario_b.terminal_1_name
        or presentation.terminal_2_name != scenario_b.terminal_2_name
    ):
        return False
    return _presentation_shape_is_consistent(
        presentation,
        b_fingerprint=b_fingerprint,
        accepted_fingerprint=accepted_fingerprint,
    )


def resolve_visible_result_context_v1(
    *,
    legacy_bundle: AnalysisBundle | None,
    parallel_runtime_status: ParallelRuntimeStatusV1 | None,
    input_readiness: WorkbookInputReadinessV1 | None,
    unified_result: BusScheduleOptimizationResult | None,
    report: SideBySideValidationReportV1 | None,
    presentation: UnifiedPresentationBundleV1 | None,
    unified_demand_supply_figure: object | None,
    unified_departure_figure: object | None,
    unified_download_artifacts: Mapping[str, object] | None,
    unified_runtime_failure: Mapping[str, object] | None,
) -> VisibleResultContextV1:
    """Choose one visible authority from existing Milestone 5B1 session evidence only."""
    if legacy_bundle is None:
        return _no_result_context()
    if parallel_runtime_status == ParallelRuntimeStatusV1.INPUT_NOT_READY:
        return _input_not_ready_context(input_readiness)
    if parallel_runtime_status == ParallelRuntimeStatusV1.UNIFIED_RUNTIME_FAILED:
        return _runtime_failed_context(unified_runtime_failure)
    if parallel_runtime_status != ParallelRuntimeStatusV1.PARALLEL_VALIDATION_COMPLETE:
        return _incomplete_context()

    blockers = _blocking_codes(report, presentation)
    if blockers:
        return _cutover_blocked_context(blockers)
    if not _completed_state_is_aligned(
        input_readiness=input_readiness,
        unified_result=unified_result,
        report=report,
        presentation=presentation,
        unified_demand_supply_figure=unified_demand_supply_figure,
        unified_departure_figure=unified_departure_figure,
        unified_download_artifacts=unified_download_artifacts,
    ):
        return _incomplete_context()

    assert isinstance(unified_result, BusScheduleOptimizationResult)
    assert isinstance(report, SideBySideValidationReportV1)
    assert isinstance(presentation, UnifiedPresentationBundleV1)
    return VisibleResultContextV1(
        mode=VisibleResultModeV1.UNIFIED_CONTRACT_V1,
        uses_unified=True,
        presentation=presentation,
        unified_result=unified_result,
        report=report,
        banner_level="info",
        banner_message=_UNIFIED_BANNER,
        reason_codes=tuple(presentation.expert_review_required_codes),
    )


__all__ = [
    "UNIFIED_VISIBLE_STATE_INCOMPLETE",
    "VisibleResultContextV1",
    "VisibleResultModeV1",
    "resolve_visible_result_context_v1",
]

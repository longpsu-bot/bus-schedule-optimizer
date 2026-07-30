"""Pure visible-result authority resolution for unified Streamlit pages."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .application_pipeline import (
    CONTRACT_V1_ARTIFACT_FAILED,
    CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH,
    WORKBOOK_OPTIMIZATION_NOT_READY,
    UnifiedApplicationStatusV1,
    UnifiedRuntimeFailureV1,
)
from .contracts_v1 import GenerationResultStatus
from .input_authority import WorkbookInputReadinessV1
from .optimization_service import BusScheduleOptimizationResult
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
_NO_RESULT_MESSAGE = "Chưa có kết quả. Hãy chạy phân tích ở trang Nhập dữ liệu."


class VisibleResultModeV1(StrEnum):
    """The only visible authority states supported by ordinary Streamlit."""

    NO_RESULT = "NO_RESULT"
    INPUT_NOT_READY = "INPUT_NOT_READY"
    UNIFIED_CONTRACT_V1 = "UNIFIED_CONTRACT_V1"
    UNIFIED_ARTIFACT_FAILED = "UNIFIED_ARTIFACT_FAILED"
    CONTRACT_V1_FAILED = "CONTRACT_V1_FAILED"


@dataclass(frozen=True, slots=True)
class VisibleResultContextV1:
    """Resolved visible authority and the unified objects pages may consume."""

    mode: VisibleResultModeV1
    uses_unified: bool
    artifacts_available: bool
    presentation: UnifiedPresentationBundleV1 | None
    unified_result: BusScheduleOptimizationResult | None
    input_readiness: WorkbookInputReadinessV1 | None
    failure: UnifiedRuntimeFailureV1 | None
    banner_level: str
    banner_message: str
    reason_codes: tuple[str, ...]


def _context(
    mode: VisibleResultModeV1,
    *,
    uses_unified: bool = False,
    artifacts_available: bool = False,
    presentation: UnifiedPresentationBundleV1 | None = None,
    unified_result: BusScheduleOptimizationResult | None = None,
    input_readiness: WorkbookInputReadinessV1 | None = None,
    failure: UnifiedRuntimeFailureV1 | None = None,
    banner_level: str = "warning",
    banner_message: str,
    reason_codes: tuple[str, ...] = (),
) -> VisibleResultContextV1:
    return VisibleResultContextV1(
        mode=mode,
        uses_unified=uses_unified,
        artifacts_available=artifacts_available,
        presentation=presentation,
        unified_result=unified_result,
        input_readiness=input_readiness,
        failure=failure,
        banner_level=banner_level,
        banner_message=banner_message,
        reason_codes=reason_codes,
    )


def _no_result_context() -> VisibleResultContextV1:
    return _context(
        VisibleResultModeV1.NO_RESULT,
        banner_message=_NO_RESULT_MESSAGE,
    )


def _input_not_ready_context(
    readiness: WorkbookInputReadinessV1 | None,
) -> VisibleResultContextV1:
    codes = (
        tuple(readiness.missing_optimization_authority_codes)
        if isinstance(readiness, WorkbookInputReadinessV1)
        else ()
    )
    code_text = "\n".join(f"- {code}" for code in codes) or "- Không có mã được trả về."
    return _context(
        VisibleResultModeV1.INPUT_NOT_READY,
        input_readiness=readiness,
        banner_message=(
            f"{WORKBOOK_OPTIMIZATION_NOT_READY}\n\n"
            "Workbook đã nhập được nhưng còn thiếu thẩm quyền tối ưu hóa:\n"
            f"{code_text}\n\n"
            "Hãy tải mẫu đầu vào mới ở trang Nhập dữ liệu, bổ sung đúng các trường "
            "được nêu, rồi chạy lại."
        ),
        reason_codes=(WORKBOOK_OPTIMIZATION_NOT_READY, *codes),
    )


def _failure_context(
    failure: UnifiedRuntimeFailureV1,
    *,
    readiness: WorkbookInputReadinessV1 | None,
) -> VisibleResultContextV1:
    return _context(
        VisibleResultModeV1.CONTRACT_V1_FAILED,
        input_readiness=readiness,
        failure=failure,
        banner_level="error",
        banner_message=(
            f"{failure.code}\n\n"
            f"Giai đoạn: {failure.stage}\n\n"
            f"Mã đối chiếu: {failure.correlation_id}\n\n"
            f"Thông tin: {failure.sanitized_message}"
        ),
        reason_codes=(failure.code,),
    )


def _figure_metadata(figure: object) -> Mapping[str, object] | None:
    try:
        metadata = figure.layout.meta
    except (AttributeError, TypeError):
        return None
    if isinstance(metadata, Mapping):
        return metadata
    try:
        return dict(metadata)
    except (TypeError, ValueError):
        return None


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


def _verified_analysis_is_aligned(
    *,
    input_readiness: WorkbookInputReadinessV1 | None,
    unified_result: BusScheduleOptimizationResult | None,
    presentation: UnifiedPresentationBundleV1 | None,
) -> bool:
    if not (
        isinstance(input_readiness, WorkbookInputReadinessV1)
        and input_readiness.optimization_ready is True
        and isinstance(unified_result, BusScheduleOptimizationResult)
        and isinstance(presentation, UnifiedPresentationBundleV1)
    ):
        return False
    try:
        verify_unified_presentation_integrity_v1(presentation)
    except (UnifiedPresentationConsistencyError, TypeError):
        return False
    if (
        presentation.presentation_mode != PRESENTATION_MODE_VALIDATION_ONLY
        or presentation.cutover_blocked
        or presentation.blocking_discrepancy_codes
        or presentation.discrepancies
    ):
        return False
    normalized = unified_result.normalized_inputs
    b_fingerprint = normalized.scenario_b_fingerprint
    accepted_state_valid, accepted_fingerprint = _accepted_result_fingerprint(unified_result)
    if not accepted_state_valid:
        return False
    scenario_b = normalized.scenario_b
    source_metadata = scenario_b.source_metadata
    if (
        presentation.source_b_fingerprint != b_fingerprint
        or presentation.accepted_solution_fingerprint != accepted_fingerprint
        or presentation.source_id != source_metadata.source_id
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


def _completed_artifacts_are_aligned(
    *,
    unified_result: BusScheduleOptimizationResult,
    presentation: UnifiedPresentationBundleV1,
    unified_demand_supply_figure: object | None,
    unified_departure_figure: object | None,
    unified_download_artifacts: Mapping[str, object] | None,
) -> bool:
    if (
        unified_demand_supply_figure is None
        or unified_departure_figure is None
        or not isinstance(unified_download_artifacts, Mapping)
    ):
        return False
    required_download_keys = {
        "xlsx",
        "source_id",
        "presentation_fingerprint",
        "b_fingerprint",
        "accepted_solution_fingerprint",
    }
    if not required_download_keys.issubset(unified_download_artifacts):
        return False
    xlsx = unified_download_artifacts["xlsx"]
    if not isinstance(xlsx, bytes | bytearray | memoryview) or not xlsx:
        return False
    figure_metadata = (
        _figure_metadata(unified_demand_supply_figure),
        _figure_metadata(unified_departure_figure),
    )
    required_figure_keys = {
        "presentation_fingerprint",
        "source_b_fingerprint",
        "accepted_solution_fingerprint",
    }
    if any(
        metadata is None or not required_figure_keys.issubset(metadata)
        for metadata in figure_metadata
    ):
        return False
    b_fingerprint = unified_result.normalized_inputs.scenario_b_fingerprint
    _, accepted_fingerprint = _accepted_result_fingerprint(unified_result)
    assert all(metadata is not None for metadata in figure_metadata)
    return bool(
        all(
            metadata["presentation_fingerprint"] == presentation.presentation_fingerprint
            and metadata["source_b_fingerprint"] == b_fingerprint
            and metadata["accepted_solution_fingerprint"] == accepted_fingerprint
            for metadata in figure_metadata
        )
        and unified_download_artifacts["source_id"] == presentation.source_id
        and unified_download_artifacts["presentation_fingerprint"]
        == presentation.presentation_fingerprint
        and unified_download_artifacts["b_fingerprint"] == b_fingerprint
        and unified_download_artifacts["accepted_solution_fingerprint"] == accepted_fingerprint
    )


def _semantic_state_failure(
    *,
    result: BusScheduleOptimizationResult | None,
    presentation: UnifiedPresentationBundleV1 | None,
) -> UnifiedRuntimeFailureV1:
    source_id = presentation.source_id if presentation is not None else "unavailable"
    payload = (
        f"{source_id}|SESSION_STATE_ALIGNMENT|"
        f"{getattr(presentation, 'presentation_fingerprint', None)}"
    ).encode()
    return UnifiedRuntimeFailureV1(
        code=CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH,
        stage="SESSION_STATE_ALIGNMENT",
        correlation_id=f"m5c2-{hashlib.sha256(payload).hexdigest()[:20]}",
        sanitized_message=("Trạng thái kết quả Contract V1 không đầy đủ hoặc không nhất quán."),
        retryable=False,
        solver_choice=(result.solver_choice.value if result is not None else "HEURISTIC"),
        source_id=source_id,
        presentation_fingerprint=(
            presentation.presentation_fingerprint if presentation is not None else None
        ),
        b_fingerprint=(
            result.normalized_inputs.scenario_b_fingerprint if result is not None else None
        ),
        accepted_solution_fingerprint=(
            presentation.accepted_solution_fingerprint if presentation is not None else None
        ),
    )


def resolve_visible_result_context_v1(
    *,
    runtime_status: UnifiedApplicationStatusV1 | None,
    input_readiness: WorkbookInputReadinessV1 | None,
    unified_result: BusScheduleOptimizationResult | None,
    presentation: UnifiedPresentationBundleV1 | None,
    unified_demand_supply_figure: object | None,
    unified_departure_figure: object | None,
    unified_download_artifacts: Mapping[str, object] | None,
    unified_runtime_failure: UnifiedRuntimeFailureV1 | None,
) -> VisibleResultContextV1:
    """Resolve one fail-closed visible state from unified session evidence."""
    if runtime_status is None:
        return _no_result_context()
    if runtime_status == UnifiedApplicationStatusV1.INPUT_NOT_READY:
        return _input_not_ready_context(input_readiness)
    if runtime_status == UnifiedApplicationStatusV1.FAILED:
        failure = (
            unified_runtime_failure
            if isinstance(unified_runtime_failure, UnifiedRuntimeFailureV1)
            else _semantic_state_failure(
                result=None,
                presentation=None,
            )
        )
        return _failure_context(failure, readiness=input_readiness)

    analysis_aligned = _verified_analysis_is_aligned(
        input_readiness=input_readiness,
        unified_result=unified_result,
        presentation=presentation,
    )
    if runtime_status == UnifiedApplicationStatusV1.ARTIFACT_FAILED:
        if (
            analysis_aligned
            and isinstance(unified_result, BusScheduleOptimizationResult)
            and isinstance(presentation, UnifiedPresentationBundleV1)
            and isinstance(unified_runtime_failure, UnifiedRuntimeFailureV1)
            and unified_runtime_failure.code == CONTRACT_V1_ARTIFACT_FAILED
            and unified_demand_supply_figure is None
            and unified_departure_figure is None
            and unified_download_artifacts is None
        ):
            return _context(
                VisibleResultModeV1.UNIFIED_ARTIFACT_FAILED,
                uses_unified=True,
                artifacts_available=False,
                presentation=presentation,
                unified_result=unified_result,
                input_readiness=input_readiness,
                failure=unified_runtime_failure,
                banner_message=(
                    f"{CONTRACT_V1_ARTIFACT_FAILED}\n\n"
                    f"Mã đối chiếu: {unified_runtime_failure.correlation_id}\n\n"
                    "Kết quả xác minh vẫn dùng được ở Trang 02–04; biểu đồ và "
                    "tệp tải xuống ở Trang 05 đã bị vô hiệu hóa."
                ),
                reason_codes=(CONTRACT_V1_ARTIFACT_FAILED,),
            )
    elif (
        runtime_status == UnifiedApplicationStatusV1.COMPLETE
        and analysis_aligned
        and isinstance(unified_result, BusScheduleOptimizationResult)
        and isinstance(presentation, UnifiedPresentationBundleV1)
        and unified_runtime_failure is None
        and _completed_artifacts_are_aligned(
            unified_result=unified_result,
            presentation=presentation,
            unified_demand_supply_figure=unified_demand_supply_figure,
            unified_departure_figure=unified_departure_figure,
            unified_download_artifacts=unified_download_artifacts,
        )
    ):
        return _context(
            VisibleResultModeV1.UNIFIED_CONTRACT_V1,
            uses_unified=True,
            artifacts_available=True,
            presentation=presentation,
            unified_result=unified_result,
            input_readiness=input_readiness,
            banner_level="info",
            banner_message=_UNIFIED_BANNER,
            reason_codes=tuple(presentation.expert_review_required_codes),
        )

    failure = _semantic_state_failure(
        result=unified_result,
        presentation=presentation,
    )
    return _failure_context(failure, readiness=input_readiness)


__all__ = [
    "UNIFIED_VISIBLE_STATE_INCOMPLETE",
    "VisibleResultContextV1",
    "VisibleResultModeV1",
    "resolve_visible_result_context_v1",
]

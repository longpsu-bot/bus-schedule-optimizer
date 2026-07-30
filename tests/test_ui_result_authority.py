from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest
from presentation_support import build_result_and_report

import bus_schedule_engine
from bus_schedule_engine.application_pipeline import (
    CONTRACT_V1_ARTIFACT_FAILED,
    CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH,
    UnifiedApplicationStatusV1,
    UnifiedRuntimeFailureV1,
)
from bus_schedule_engine.input_authority import WorkbookInputReadinessV1
from bus_schedule_engine.ui_result_authority import (
    VisibleResultContextV1,
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.unified_diagram import (
    build_unified_demand_supply_figure_v1,
    build_unified_departure_figure_v1,
)
from bus_schedule_engine.unified_presentation import (
    build_unified_application_presentation_v1,
)


def _readiness(*, ready: bool = True, missing: tuple[str, ...] = ()):
    return WorkbookInputReadinessV1(
        import_ready=True,
        optimization_ready=ready,
        blocking_import_codes=(),
        missing_optimization_authority_codes=missing,
        optional_limitations=(),
    )


def _failure(
    code: str = CONTRACT_V1_ARTIFACT_FAILED,
) -> UnifiedRuntimeFailureV1:
    return UnifiedRuntimeFailureV1(
        code=code,
        stage="ARTIFACT_CONSTRUCTION",
        correlation_id="m5c2-0123456789abcdef0123",
        sanitized_message="Bounded failure.",
        retryable=True,
        solver_choice="HEURISTIC",
        source_id="fixture-source",
        presentation_fingerprint=None,
        b_fingerprint=None,
        accepted_solution_fingerprint=None,
    )


def _aligned_state() -> dict[str, object]:
    result, _report = build_result_and_report()
    presentation = build_unified_application_presentation_v1(result)
    return {
        "runtime_status": UnifiedApplicationStatusV1.COMPLETE,
        "input_readiness": _readiness(),
        "unified_result": result,
        "presentation": presentation,
        "unified_demand_supply_figure": build_unified_demand_supply_figure_v1(presentation),
        "unified_departure_figure": build_unified_departure_figure_v1(presentation),
        "unified_download_artifacts": {
            "xlsx": b"unified-xlsx",
            "source_id": presentation.source_id,
            "presentation_fingerprint": presentation.presentation_fingerprint,
            "b_fingerprint": presentation.source_b_fingerprint,
            "accepted_solution_fingerprint": (presentation.accepted_solution_fingerprint),
        },
        "unified_runtime_failure": None,
    }


@pytest.fixture(scope="module")
def aligned_state():
    return _aligned_state()


def _resolve(state: dict[str, object]) -> VisibleResultContextV1:
    return resolve_visible_result_context_v1(**state)


def test_public_authority_model_is_frozen_slotted_and_exported(aligned_state) -> None:
    context = _resolve(aligned_state)

    assert VisibleResultContextV1.__dataclass_params__.frozen is True
    assert "__slots__" in VisibleResultContextV1.__dict__
    assert bus_schedule_engine.VisibleResultContextV1 is VisibleResultContextV1
    with pytest.raises(FrozenInstanceError):
        context.uses_unified = False


def test_no_runtime_state_resolves_to_no_result(aligned_state) -> None:
    context = _resolve({**aligned_state, "runtime_status": None})

    assert context.mode == VisibleResultModeV1.NO_RESULT
    assert context.uses_unified is False
    assert context.artifacts_available is False


def test_complete_aligned_state_resolves_to_unified(aligned_state) -> None:
    context = _resolve(aligned_state)

    assert context.mode == VisibleResultModeV1.UNIFIED_CONTRACT_V1
    assert context.uses_unified is True
    assert context.artifacts_available is True
    assert context.presentation is aligned_state["presentation"]
    assert context.unified_result is aligned_state["unified_result"]
    assert context.failure is None


def test_input_not_ready_preserves_every_missing_authority_code(
    aligned_state,
) -> None:
    codes = ("AUTHORITY_ONE", "AUTHORITY_TWO")
    context = _resolve(
        {
            **aligned_state,
            "runtime_status": UnifiedApplicationStatusV1.INPUT_NOT_READY,
            "input_readiness": _readiness(ready=False, missing=codes),
            "unified_result": None,
            "presentation": None,
            "unified_demand_supply_figure": None,
            "unified_departure_figure": None,
            "unified_download_artifacts": None,
        }
    )

    assert context.mode == VisibleResultModeV1.INPUT_NOT_READY
    assert context.reason_codes == ("WORKBOOK_OPTIMIZATION_NOT_READY", *codes)
    assert all(code in context.banner_message for code in codes)
    assert context.presentation is None


def test_runtime_failure_exposes_stable_failure_evidence_only(aligned_state) -> None:
    failure = _failure("CONTRACT_V1_SOLVER_FAILED")
    context = _resolve(
        {
            **aligned_state,
            "runtime_status": UnifiedApplicationStatusV1.FAILED,
            "unified_result": None,
            "presentation": None,
            "unified_demand_supply_figure": None,
            "unified_departure_figure": None,
            "unified_download_artifacts": None,
            "unified_runtime_failure": failure,
        }
    )

    assert context.mode == VisibleResultModeV1.CONTRACT_V1_FAILED
    assert context.failure is failure
    assert failure.correlation_id in context.banner_message
    assert context.presentation is None
    assert context.unified_result is None


def test_artifact_failure_keeps_verified_pages_02_to_04_only(aligned_state) -> None:
    failure = _failure()
    context = _resolve(
        {
            **aligned_state,
            "runtime_status": UnifiedApplicationStatusV1.ARTIFACT_FAILED,
            "unified_demand_supply_figure": None,
            "unified_departure_figure": None,
            "unified_download_artifacts": None,
            "unified_runtime_failure": failure,
        }
    )

    assert context.mode == VisibleResultModeV1.UNIFIED_ARTIFACT_FAILED
    assert context.uses_unified is True
    assert context.artifacts_available is False
    assert context.presentation is aligned_state["presentation"]
    assert context.failure is failure


@pytest.mark.parametrize(
    "missing_key",
    (
        "unified_result",
        "presentation",
        "unified_demand_supply_figure",
        "unified_departure_figure",
        "unified_download_artifacts",
    ),
)
def test_partial_complete_state_fails_closed(aligned_state, missing_key) -> None:
    context = _resolve({**aligned_state, missing_key: None})

    assert context.mode == VisibleResultModeV1.CONTRACT_V1_FAILED
    assert context.reason_codes == (CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH,)
    assert context.presentation is None
    assert context.unified_result is None


def test_figure_fingerprint_mismatch_fails_closed(aligned_state) -> None:
    demand_figure = deepcopy(aligned_state["unified_demand_supply_figure"])
    metadata = dict(demand_figure.layout.meta)
    metadata["presentation_fingerprint"] = "mismatched"
    demand_figure.update_layout(meta=metadata)

    context = _resolve(
        {
            **aligned_state,
            "unified_demand_supply_figure": demand_figure,
        }
    )

    assert context.mode == VisibleResultModeV1.CONTRACT_V1_FAILED
    assert context.presentation is None


def test_stale_presentation_contents_fail_closed(aligned_state) -> None:
    original = aligned_state["presentation"]
    blocks = list(original.blocks)
    blocks[0] = replace(
        blocks[0],
        passenger_demand=blocks[0].passenger_demand + 1,
    )
    stale = replace(original, blocks=tuple(blocks))

    context = _resolve({**aligned_state, "presentation": stale})

    assert context.mode == VisibleResultModeV1.CONTRACT_V1_FAILED
    assert context.failure is not None
    assert context.failure.code == CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH

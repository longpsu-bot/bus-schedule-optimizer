from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest
from presentation_support import build_corpus_result_and_report, build_result_and_report

import bus_schedule_engine
import bus_schedule_engine.optimization_service as optimization_service
from bus_schedule_engine.application_pipeline import ParallelRuntimeStatusV1
from bus_schedule_engine.input_authority import WorkbookInputReadinessV1
from bus_schedule_engine.ui_result_authority import (
    UNIFIED_VISIBLE_STATE_INCOMPLETE,
    VisibleResultContextV1,
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.unified_diagram import (
    build_unified_demand_supply_figure_v1,
    build_unified_departure_figure_v1,
)
from bus_schedule_engine.unified_presentation import build_unified_presentation_v1


def _readiness(*, ready: bool = True, missing: tuple[str, ...] = ()):
    return WorkbookInputReadinessV1(
        import_ready=True,
        optimization_ready=ready,
        blocking_import_codes=(),
        missing_optimization_authority_codes=missing,
        optional_limitations=(),
    )


def _aligned_state(pair=None) -> dict[str, object]:
    result, report = pair or build_result_and_report()
    presentation = build_unified_presentation_v1(result, report)
    return {
        "legacy_bundle": object(),
        "parallel_runtime_status": ParallelRuntimeStatusV1.PARALLEL_VALIDATION_COMPLETE,
        "input_readiness": _readiness(),
        "unified_result": result,
        "report": report,
        "presentation": presentation,
        "unified_demand_supply_figure": build_unified_demand_supply_figure_v1(presentation),
        "unified_departure_figure": build_unified_departure_figure_v1(presentation),
        "unified_download_artifacts": {
            "xlsx": b"unified-xlsx",
            "presentation_fingerprint": presentation.presentation_fingerprint,
            "b_fingerprint": presentation.source_b_fingerprint,
            "accepted_solution_fingerprint": presentation.accepted_solution_fingerprint,
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
    assert bus_schedule_engine.resolve_visible_result_context_v1 is (
        resolve_visible_result_context_v1
    )
    with pytest.raises(FrozenInstanceError):
        context.uses_unified = False


def test_no_legacy_result_resolves_to_no_result(aligned_state) -> None:
    context = _resolve({**aligned_state, "legacy_bundle": None})

    assert context.mode == VisibleResultModeV1.NO_RESULT
    assert context.uses_unified is False
    assert context.presentation is None


def test_complete_aligned_state_resolves_to_unified(aligned_state) -> None:
    context = _resolve(aligned_state)

    assert context.mode == VisibleResultModeV1.UNIFIED_CONTRACT_V1
    assert context.uses_unified is True
    assert context.presentation is aligned_state["presentation"]
    assert context.unified_result is aligned_state["unified_result"]
    assert context.report is aligned_state["report"]
    assert "Contract V1" in context.banner_message


def test_input_not_ready_preserves_every_missing_authority_code(aligned_state) -> None:
    codes = ("AUTHORITY_ONE", "AUTHORITY_TWO")
    context = _resolve(
        {
            **aligned_state,
            "parallel_runtime_status": ParallelRuntimeStatusV1.INPUT_NOT_READY,
            "input_readiness": _readiness(ready=False, missing=codes),
        }
    )

    assert context.mode == VisibleResultModeV1.LEGACY_INPUT_NOT_READY
    assert context.reason_codes == codes
    assert all(code in context.banner_message for code in codes)
    assert context.presentation is None


def test_unified_runtime_failure_exposes_only_stable_code_and_message(
    aligned_state,
) -> None:
    context = _resolve(
        {
            **aligned_state,
            "parallel_runtime_status": ParallelRuntimeStatusV1.UNIFIED_RUNTIME_FAILED,
            "unified_runtime_failure": {
                "code": "STABLE_FAILURE",
                "message": "Concise failure message.",
            },
        }
    )

    assert context.mode == VisibleResultModeV1.LEGACY_UNIFIED_FAILED
    assert context.reason_codes == ("STABLE_FAILURE",)
    assert "Concise failure message." in context.banner_message
    assert context.presentation is None
    assert context.unified_result is None


def test_blocking_codes_from_report_or_presentation_force_legacy(aligned_state) -> None:
    report = replace(
        aligned_state["report"],
        blocking_discrepancy_codes=("REPORT_BLOCK",),
    )
    presentation = replace(
        aligned_state["presentation"],
        cutover_blocked=True,
        blocking_discrepancy_codes=("PRESENTATION_BLOCK",),
    )
    context = _resolve(
        {
            **aligned_state,
            "report": report,
            "presentation": presentation,
        }
    )

    assert context.mode == VisibleResultModeV1.LEGACY_CUTOVER_BLOCKED
    assert context.reason_codes == ("REPORT_BLOCK", "PRESENTATION_BLOCK")
    assert all(code in context.banner_message for code in context.reason_codes)
    assert context.presentation is None


def test_expert_review_without_blockers_permits_unified(aligned_state) -> None:
    presentation = aligned_state["presentation"]
    assert presentation.requires_expert_review is True
    assert presentation.blocking_discrepancy_codes == ()

    context = _resolve(aligned_state)

    assert context.mode == VisibleResultModeV1.UNIFIED_CONTRACT_V1
    assert context.reason_codes == presentation.expert_review_required_codes


@pytest.mark.parametrize(
    "missing_key",
    (
        "unified_result",
        "report",
        "presentation",
        "unified_demand_supply_figure",
        "unified_departure_figure",
    ),
)
def test_missing_required_shadow_object_falls_back(aligned_state, missing_key) -> None:
    context = _resolve({**aligned_state, missing_key: None})

    assert context.mode == VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE
    assert context.reason_codes == (UNIFIED_VISIBLE_STATE_INCOMPLETE,)


def test_missing_unified_xlsx_metadata_falls_back(aligned_state) -> None:
    artifacts = dict(aligned_state["unified_download_artifacts"])
    artifacts.pop("presentation_fingerprint")

    context = _resolve({**aligned_state, "unified_download_artifacts": artifacts})

    assert context.mode == VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE


def test_presentation_fingerprint_mismatch_falls_back(aligned_state) -> None:
    demand_figure = deepcopy(aligned_state["unified_demand_supply_figure"])
    metadata = dict(demand_figure.layout.meta)
    metadata["presentation_fingerprint"] = "mismatched-presentation"
    demand_figure.update_layout(meta=metadata)

    context = _resolve(
        {
            **aligned_state,
            "unified_demand_supply_figure": demand_figure,
        }
    )

    assert context.mode == VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE


@pytest.mark.parametrize(
    "mutation",
    (
        "block_fact",
        "technical_issue",
        "outcome_field",
        "discrepancy",
        "stored_fingerprint",
        "presentation_mode",
    ),
)
def test_stale_or_invalid_presentation_contents_fail_closed(
    aligned_state,
    mutation: str,
) -> None:
    original = aligned_state["presentation"]
    state = dict(aligned_state)

    if mutation == "block_fact":
        blocks = list(original.blocks)
        blocks[0] = replace(
            blocks[0],
            passenger_demand=blocks[0].passenger_demand + 1,
        )
        presentation = replace(original, blocks=tuple(blocks))
    elif mutation == "technical_issue":
        dimensions = list(original.dimensions)
        index = next(
            index for index, dimension in enumerate(dimensions) if dimension.issue_messages
        )
        dimension = dimensions[index]
        dimensions[index] = replace(
            dimension,
            issue_messages=(
                f"{dimension.issue_messages[0]} Altered.",
                *dimension.issue_messages[1:],
            ),
        )
        presentation = replace(original, dimensions=tuple(dimensions))
    elif mutation == "outcome_field":
        presentation = replace(
            original,
            outcome=replace(original.outcome, selected_action="ALTERED_ACTION"),
        )
    elif mutation == "discrepancy":
        discrepancies = list(original.discrepancies)
        discrepancies[0] = replace(
            discrepancies[0],
            explanation=f"{discrepancies[0].explanation} Altered.",
        )
        presentation = replace(original, discrepancies=tuple(discrepancies))
    elif mutation == "stored_fingerprint":
        changed_fingerprint = "f" * 64
        presentation = replace(
            original,
            presentation_fingerprint=changed_fingerprint,
        )
        for figure_key in (
            "unified_demand_supply_figure",
            "unified_departure_figure",
        ):
            figure = deepcopy(aligned_state[figure_key])
            metadata = dict(figure.layout.meta)
            metadata["presentation_fingerprint"] = changed_fingerprint
            figure.update_layout(meta=metadata)
            state[figure_key] = figure
        state["unified_download_artifacts"] = {
            **aligned_state["unified_download_artifacts"],
            "presentation_fingerprint": changed_fingerprint,
        }
    else:
        presentation = replace(original, presentation_mode="AUTHORITATIVE")

    if mutation != "stored_fingerprint":
        assert presentation.presentation_fingerprint == original.presentation_fingerprint
    state["presentation"] = presentation

    context = _resolve(state)

    assert context.mode == VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE
    assert context.reason_codes == (UNIFIED_VISIBLE_STATE_INCOMPLETE,)
    assert context.presentation is None


def test_normalized_b_fingerprint_mismatch_falls_back(aligned_state) -> None:
    artifacts = {
        **aligned_state["unified_download_artifacts"],
        "b_fingerprint": "mismatched-b",
    }

    context = _resolve({**aligned_state, "unified_download_artifacts": artifacts})

    assert context.mode == VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE


def test_accepted_c_fingerprint_mismatch_falls_back(aligned_state) -> None:
    artifacts = {
        **aligned_state["unified_download_artifacts"],
        "accepted_solution_fingerprint": "mismatched-c",
    }

    context = _resolve({**aligned_state, "unified_download_artifacts": artifacts})

    assert context.mode == VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE


def test_absent_c_none_fingerprints_align() -> None:
    state = _aligned_state(
        build_corpus_result_and_report("corpus_alpha_80.json"),
    )
    presentation = state["presentation"]

    assert presentation.accepted_solution_fingerprint is None
    assert state["unified_download_artifacts"]["accepted_solution_fingerprint"] is None
    assert _resolve(state).mode == VisibleResultModeV1.UNIFIED_CONTRACT_V1


def test_source_identity_mismatch_falls_back(aligned_state) -> None:
    presentation = replace(aligned_state["presentation"], source_id="different-source")
    artifacts = {
        **aligned_state["unified_download_artifacts"],
        "presentation_fingerprint": presentation.presentation_fingerprint,
    }

    context = _resolve(
        {
            **aligned_state,
            "presentation": presentation,
            "unified_download_artifacts": artifacts,
        }
    )

    assert context.mode == VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE


def test_resolver_invokes_no_analysis_or_solver_path(
    aligned_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("visible authority must consume stored evidence only")

    monkeypatch.setattr(optimization_service, "analyze_and_optimize_schedule_v1", forbidden)

    assert _resolve(aligned_state).mode == VisibleResultModeV1.UNIFIED_CONTRACT_V1

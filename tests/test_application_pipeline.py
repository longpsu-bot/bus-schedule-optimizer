from __future__ import annotations

import inspect
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

import bus_schedule_engine
import bus_schedule_engine.application_pipeline as application
import bus_schedule_engine.optimization_service as optimization_service
import bus_schedule_engine.service as legacy_service
import bus_schedule_engine.side_by_side_validation as side_by_side
from bus_schedule_engine.application_pipeline import (
    CONTRACT_V1_ARTIFACT_FAILED,
    CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH,
    CONTRACT_V1_SOLVER_FAILED,
    UnifiedApplicationRunV1,
    UnifiedApplicationStatusV1,
    UnifiedRuntimeFailureV1,
    run_unified_application_pipeline_v1,
)
from bus_schedule_engine.contracts_v1 import ContractValidationError
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import ImportedWorkbook, import_workbook
from bus_schedule_engine.input_authority import (
    AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION,
    WorkbookInputReadinessV1,
)
from bus_schedule_engine.optimization_service import (
    OptimizationExecutionErrorV1,
    OptimizationExecutionStageV1,
)

IMPORTED_AT = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
SOURCE_ID = "streamlit-upload-sha256:" + "a" * 64


def _template_import(tmp_path: Path, name: str = "input.xlsx") -> ImportedWorkbook:
    return import_workbook(create_input_template(tmp_path / name))


def test_unified_application_public_model_shape_and_default_solver() -> None:
    assert bus_schedule_engine.run_unified_application_pipeline_v1 is (
        run_unified_application_pipeline_v1
    )
    assert UnifiedApplicationRunV1.__dataclass_params__.frozen is True
    assert "__slots__" in UnifiedApplicationRunV1.__dict__
    assert {field.name for field in fields(UnifiedApplicationRunV1)} == {
        "status",
        "input_readiness",
        "unified_result",
        "unified_presentation",
        "unified_demand_supply_figure",
        "unified_departure_figure",
        "unified_xlsx_bytes",
        "source_id",
        "imported_at",
        "failure",
        "trip_ridership_analysis",
        "trip_ridership_failure",
        "protected_service_floor_assessment",
        "protected_service_floor_failure",
        "protected_service_floor_enforcement_authority",
        "protected_service_floor_enforcement_failure",
    }
    assert UnifiedRuntimeFailureV1.__dataclass_params__.frozen is True
    assert tuple(status.value for status in UnifiedApplicationStatusV1) == (
        "INPUT_NOT_READY",
        "COMPLETE",
        "ARTIFACT_FAILED",
        "FAILED",
    )
    assert (
        inspect.signature(run_unified_application_pipeline_v1)
        .parameters["solver_choice"]
        .default.value
        == "HEURISTIC"
    )


def test_unified_pipeline_stops_at_readiness_without_any_analysis_or_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path)
    imported = replace(
        imported,
        parameters_b=replace(
            imported.parameters_b,
            available_fleet_limit=None,
        ),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("readiness blocker must stop the pipeline")

    monkeypatch.setattr(application, "normalization_options_from_workbook_v1", forbidden)
    monkeypatch.setattr(
        application,
        "_analyze_normalized_and_optimize_schedule_v1",
        forbidden,
    )
    monkeypatch.setattr(application, "build_unified_demand_supply_figure_v1", forbidden)
    monkeypatch.setattr(application, "export_unified_result_workbook_v1", forbidden)

    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.INPUT_NOT_READY
    assert AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION in (
        run.input_readiness.missing_optimization_authority_codes
    )
    assert run.unified_result is None
    assert run.unified_presentation is None
    assert run.unified_xlsx_bytes is None
    assert run.failure is None


def test_unified_pipeline_completes_without_loading_or_running_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path)
    unified_calls = 0
    real_unified = application._analyze_normalized_and_optimize_schedule_v1

    def unified_spy(*args, **kwargs):
        nonlocal unified_calls
        unified_calls += 1
        return real_unified(*args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("ordinary unified runtime must not execute the oracle")

    monkeypatch.setattr(
        application,
        "_analyze_normalized_and_optimize_schedule_v1",
        unified_spy,
    )
    monkeypatch.setattr(legacy_service, "run_analysis", forbidden)
    monkeypatch.setattr(side_by_side, "run_side_by_side_validation_v1", forbidden)

    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert unified_calls == 1
    assert run.status == UnifiedApplicationStatusV1.COMPLETE
    assert run.unified_result is not None
    assert run.unified_presentation is not None
    assert run.unified_presentation.discrepancies == ()
    assert run.unified_presentation.validation_explanations == ()
    assert run.unified_presentation.validation_limitations == ()
    assert run.unified_xlsx_bytes
    assert run.failure is None


def test_solver_exception_is_staged_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path)

    def fail(*args, **kwargs):
        original = RuntimeError("solver exploded")
        wrapped = OptimizationExecutionErrorV1(
            OptimizationExecutionStageV1.HEURISTIC_SOLVER,
            original,
        )
        raise wrapped from original

    monkeypatch.setattr(
        application,
        "_analyze_normalized_and_optimize_schedule_v1",
        fail,
    )
    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.FAILED
    assert run.failure is not None
    assert run.failure.code == CONTRACT_V1_SOLVER_FAILED
    assert run.failure.stage == "HEURISTIC_SOLVER"
    assert run.unified_result is None
    assert run.unified_presentation is None


def test_normalization_contract_validation_error_fails_at_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path)
    issue_error = ContractValidationError(())

    def fail(*args, **kwargs):
        raise issue_error

    monkeypatch.setattr(
        application,
        "normalize_imported_workbook_v1",
        fail,
    )
    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.FAILED
    assert run.failure is not None
    assert run.failure.code == application.CONTRACT_V1_NORMALIZATION_FAILED
    assert run.failure.stage == OptimizationExecutionStageV1.NORMALIZATION.value
    assert run.unified_result is None
    assert run.unified_presentation is None
    assert run.unified_demand_supply_figure is None
    assert run.unified_departure_figure is None
    assert run.unified_xlsx_bytes is None


def test_evaluation_contract_validation_error_fails_at_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path)
    issue_error = ContractValidationError(())

    def fail(*args, **kwargs):
        raise issue_error

    monkeypatch.setattr(
        optimization_service,
        "build_service_adjustment_evaluation_context_v1",
        fail,
    )
    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.FAILED
    assert run.failure is not None
    assert run.failure.code == application.CONTRACT_V1_APPLICATION_ERROR
    assert run.failure.stage == OptimizationExecutionStageV1.EVALUATION.value
    assert run.unified_result is None
    assert run.unified_presentation is None
    assert run.unified_demand_supply_figure is None
    assert run.unified_departure_figure is None
    assert run.unified_xlsx_bytes is None


def test_artifact_failure_retains_only_verified_result_and_presentation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path)

    def fail(_presentation):
        raise RuntimeError("chart renderer unavailable")

    monkeypatch.setattr(application, "build_unified_demand_supply_figure_v1", fail)
    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.ARTIFACT_FAILED
    assert run.failure is not None
    assert run.failure.code == CONTRACT_V1_ARTIFACT_FAILED
    assert run.failure.stage == OptimizationExecutionStageV1.ARTIFACTS.value
    assert run.unified_result is not None
    assert run.unified_presentation is not None
    assert run.unified_demand_supply_figure is None
    assert run.unified_departure_figure is None
    assert run.unified_xlsx_bytes is None


def test_semantic_mismatch_exposes_no_analytical_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path)

    def fail(_presentation):
        raise application.UnifiedPresentationConsistencyError("PRESENTATION_FINGERPRINT_MISMATCH")

    monkeypatch.setattr(
        application,
        "verify_unified_presentation_integrity_v1",
        fail,
    )
    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.FAILED
    assert run.failure is not None
    assert run.failure.code == CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH
    assert run.failure.stage == OptimizationExecutionStageV1.PRESENTATION.value
    assert run.unified_result is None
    assert run.unified_presentation is None
    assert run.unified_xlsx_bytes is None


def test_failure_correlation_is_deterministic_and_local_paths_are_removed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    readiness = WorkbookInputReadinessV1(
        import_ready=True,
        optimization_ready=True,
        blocking_import_codes=(),
        missing_optimization_authority_codes=(),
        optional_limitations=(),
    )
    kwargs = {
        "code": CONTRACT_V1_ARTIFACT_FAILED,
        "stage": OptimizationExecutionStageV1.ARTIFACTS.value,
        "exc": RuntimeError(r"failed at C:\Users\private\workbook.xlsx"),
        "retryable": True,
        "solver_choice": application.SolverChoice.HEURISTIC,
        "source_id": SOURCE_ID,
        "imported_at": IMPORTED_AT,
        "input_readiness": readiness,
    }
    first = application.build_unified_runtime_failure_v1(**kwargs)
    second = application.build_unified_runtime_failure_v1(**kwargs)

    assert first == second
    assert first.correlation_id.startswith("m5c2-")
    assert r"C:\Users" not in first.sanitized_message
    assert "[path]" in first.sanitized_message

    caplog.clear()
    sensitive = application.build_unified_runtime_failure_v1(
        **{
            **kwargs,
            "exc": RuntimeError("raw workbook rows: SECRET_PASSENGER_OBSERVATION"),
        }
    )
    assert "SECRET_PASSENGER_OBSERVATION" not in sensitive.sanitized_message
    assert "SECRET_PASSENGER_OBSERVATION" not in caplog.text


def test_import_error_sanitizer_retains_safe_location_but_not_cell_value() -> None:
    message = application.sanitize_import_error_message_v1(
        ValueError(
            r"BIEU_DO_B, dòng Excel 4: direction không hợp lệ: "
            r"SECRET_PASSENGER_ROW C:\Users\private\workbook.xlsx"
        )
    )

    assert "BIEU_DO_B" in message
    assert "direction" in message
    assert "SECRET_PASSENGER_ROW" not in message
    assert r"C:\Users" not in message

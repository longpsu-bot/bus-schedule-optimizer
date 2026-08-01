from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

import bus_schedule_engine.application_pipeline as application
import bus_schedule_engine.legacy_retirement_evidence as evidence_module
import bus_schedule_engine.service as legacy_service
import bus_schedule_engine.side_by_side_validation as side_by_side
import bus_schedule_engine.ui_utils as ui_utils
from bus_schedule_engine.application_pipeline import (
    CONTRACT_V1_ARTIFACT_FAILED,
    CONTRACT_V1_SOLVER_FAILED,
    UnifiedApplicationStatusV1,
    run_unified_application_pipeline_v1,
)
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import import_workbook
from bus_schedule_engine.legacy_retirement_audit import main, run_legacy_retirement_audit_v1
from bus_schedule_engine.legacy_retirement_evidence import (
    APPROVED_PAGE5_FILENAMES,
    EVIDENCE_PROFILE_V1,
    RETIRED_SESSION_KEYS,
    DependencyClassificationV1,
    ImplementationConclusionV1,
    ProductionApprovalStatusV1,
    build_legacy_retirement_evidence_v1,
    evidence_to_dict_v1,
    evidence_to_json_v1,
    verify_evidence_fingerprint_v1,
)
from bus_schedule_engine.optimization_service import (
    OptimizationExecutionErrorV1,
    OptimizationExecutionStageV1,
)

ROOT = Path(__file__).resolve().parents[1]
IMPORTED_AT = datetime(2026, 8, 1, tzinfo=UTC)
SOURCE_ID = "streamlit-upload-sha256:" + "b" * 64
RELEASE_AUDIT_BASELINE_SOURCE_SHA256 = (
    "97304e3bdebfb9b255269c28dab0bdc396c06b80788da5c5bbd4e85fd790e283"
)


def _head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(scope="module")
def report():
    return build_legacy_retirement_evidence_v1(ROOT, target_commit=_head_commit())


def _template_import(tmp_path: Path, filename: str):
    return import_workbook(create_input_template(tmp_path / filename))


def _forbid_legacy_entrypoints(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("ordinary Contract V1 runtime reached a legacy entry point")

    monkeypatch.setattr(application, "run_and_build_artifacts", forbidden)
    monkeypatch.setattr(application, "build_side_by_side_validation_report_v1", forbidden)
    monkeypatch.setattr(ui_utils, "run_and_build_artifacts", forbidden)
    monkeypatch.setattr(legacy_service, "run_analysis", forbidden)
    monkeypatch.setattr(side_by_side, "run_side_by_side_validation_v1", forbidden)


def test_m5c2r_report_is_deterministic_and_model_is_frozen(report) -> None:
    second = build_legacy_retirement_evidence_v1(ROOT, target_commit=_head_commit())

    assert report == second
    assert evidence_to_json_v1(report) == evidence_to_json_v1(second)
    assert report.evidence_profile == EVIDENCE_PROFILE_V1
    assert report.__dataclass_params__.frozen is True
    assert "__slots__" in type(report).__dict__
    with pytest.raises(FrozenInstanceError):
        report.production_approval_status = ProductionApprovalStatusV1.APPROVED


def test_m5c2r_fingerprint_detects_tampering(report) -> None:
    payload = evidence_to_dict_v1(report)
    assert verify_evidence_fingerprint_v1(payload)

    payload["implementation_conclusion"] = "BLOCKED_FROM_FORMAL_APPROVAL"
    assert not verify_evidence_fingerprint_v1(payload)


def test_m5c2r_current_ordinary_roots_have_no_forbidden_legacy_import_path(report) -> None:
    ordinary = report.ordinary_runtime_evidence

    assert ordinary.forbidden_imports == ()
    assert ordinary.forbidden_calls == ()
    assert ordinary.analysis_bundle_is_result_authority is False
    assert ordinary.authoritative_entrypoint.endswith("run_unified_application_pipeline_v1")


def test_m5c2r_ready_input_invokes_no_legacy_entry_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path, "ready.xlsx")
    _forbid_legacy_entrypoints(monkeypatch)

    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.COMPLETE
    assert run.unified_result is not None
    assert run.unified_presentation is not None


def test_m5c2r_not_ready_input_invokes_no_legacy_entry_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path, "not-ready.xlsx")
    imported = replace(
        imported,
        parameters_b=replace(imported.parameters_b, available_fleet_limit=None),
    )
    _forbid_legacy_entrypoints(monkeypatch)

    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.INPUT_NOT_READY
    assert run.unified_result is None


def test_m5c2r_unified_failure_invokes_no_legacy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path, "failure.xlsx")
    _forbid_legacy_entrypoints(monkeypatch)

    def fail(*args, **kwargs):
        error = RuntimeError("synthetic solver failure")
        raise OptimizationExecutionErrorV1(
            OptimizationExecutionStageV1.HEURISTIC_SOLVER,
            error,
        ) from error

    monkeypatch.setattr(application, "_analyze_normalized_and_optimize_schedule_v1", fail)
    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.FAILED
    assert run.failure is not None
    assert run.failure.code == CONTRACT_V1_SOLVER_FAILED
    assert run.unified_result is None


def test_m5c2r_artifact_failure_invokes_no_legacy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _template_import(tmp_path, "artifact-failure.xlsx")
    _forbid_legacy_entrypoints(monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic artifact failure")

    monkeypatch.setattr(application, "build_unified_demand_supply_figure_v1", fail)
    run = run_unified_application_pipeline_v1(
        imported,
        source_id=SOURCE_ID,
        imported_at=IMPORTED_AT,
    )

    assert run.status == UnifiedApplicationStatusV1.ARTIFACT_FAILED
    assert run.failure is not None
    assert run.failure.code == CONTRACT_V1_ARTIFACT_FAILED
    assert run.unified_result is not None
    assert run.unified_xlsx_bytes is None


def test_m5c2r_pages_02_to_05_have_no_legacy_rendering_mode(report) -> None:
    ordinary = report.ordinary_runtime_evidence

    assert ordinary.visible_result_modes == (
        "CONTRACT_V1_FAILED",
        "INPUT_NOT_READY",
        "NO_RESULT",
        "UNIFIED_ARTIFACT_FAILED",
        "UNIFIED_CONTRACT_V1",
    )
    assert all("LEGACY" not in mode for mode in ordinary.page_modes_referenced)
    assert ordinary.page5_download_filenames == APPROVED_PAGE5_FILENAMES


def test_m5c2r_ordinary_session_state_does_not_write_or_read_retired_keys(report) -> None:
    session = report.session_state_evidence

    assert session.retired_keys == RETIRED_SESSION_KEYS
    assert session.retired_key_write_sites == ()
    assert session.retired_key_read_sites == ()


def test_m5c2r_stale_legacy_session_keys_may_be_cleared_safely(report) -> None:
    session = report.session_state_evidence

    assert session.stale_keys_are_clear_only is True
    for key in RETIRED_SESSION_KEYS:
        assert any(site.endswith(f":{key}") for site in session.retired_key_clear_sites)


def test_m5c2r_release_audit_remains_offline_only(report) -> None:
    offline = report.offline_oracle_evidence

    assert offline.cli_entrypoint == "python -m bus_schedule_engine.release_audit"
    assert offline.reachable_from_ordinary_runtime is False
    assert offline.deterministic_serialization is True
    assert offline.blocker_exit_is_nonzero is True
    assert offline.network_imports == ()


def test_m5c2r_evidence_json_omits_sensitive_content_and_absolute_paths(report) -> None:
    serialized = evidence_to_json_v1(report)

    for prohibited in (
        '"legacy_value"',
        '"unified_value"',
        '"workbook_bytes"',
        '"raw_rows"',
        '"trip_records"',
    ):
        assert prohibited not in serialized
    assert ":\\\\" not in serialized
    assert "/Users/" not in serialized
    assert "/home/" not in serialized


def test_m5c2r_shared_heuristic_dependencies_must_remain(report) -> None:
    inventory = {entry.target: entry for entry in report.retained_dependency_inventory}
    required = (
        "src/bus_schedule_engine/c_generator.py::generate_scenario_c",
        "src/bus_schedule_engine/c_generator.py::_balanced_values",
        "src/bus_schedule_engine/c_generator.py::_material_boundaries",
        "src/bus_schedule_engine/c_generator.py::_regime_drafts",
        "src/bus_schedule_engine/demand.py::evaluate_scenario",
        "src/bus_schedule_engine/fleet.py::assign_fleet",
        "src/bus_schedule_engine/validator.py::validate_schedule",
    )

    for target in required:
        assert inventory[target].classification == (
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY
        )
        assert target in report.required_shared_dependencies
        assert target not in report.proposed_5c3_deletion_candidates


def test_m5c2r_true_legacy_candidates_are_distinct_from_shared_dependencies(report) -> None:
    candidates = set(report.proposed_5c3_deletion_candidates)
    shared = set(report.required_shared_dependencies)

    assert candidates.isdisjoint(shared)
    assert "src/bus_schedule_engine/diagram.py::<module>" in candidates
    assert "src/bus_schedule_engine/comparison_exporter.py::<module>" in candidates
    assert "src/bus_schedule_engine/service.py::run_analysis" not in candidates
    assert "src/bus_schedule_engine/excel_exporter.py::<module>" not in candidates


def test_m5c2r_post_5c2_protected_floor_paths_remain_unified_only(report) -> None:
    symbols = report.ordinary_runtime_evidence.protected_floor_unified_symbols

    assert any("assess_protected_service_floors_v1" in symbol for symbol in symbols)
    assert any(
        "build_protected_service_floor_enforcement_authority_v1" in symbol for symbol in symbols
    )
    assert any("heuristic_solver" in symbol for symbol in symbols)
    assert any("ortools_quality_solver" in symbol for symbol in symbols)
    assert report.ordinary_runtime_evidence.forbidden_calls == ()


def test_m5c2r_cli_exits_zero_for_current_checkout(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"

    exit_code = run_legacy_retirement_audit_v1(
        ROOT,
        target_commit=_head_commit(),
        output=output,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["implementation_conclusion"] == "READY_FOR_FORMAL_APPROVAL"
    assert payload["blocker_codes"] == []


def test_m5c2r_injected_forbidden_import_makes_cli_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "blocked.json"
    real_read_source = evidence_module._read_source
    injected_path = (ROOT / "app_pages" / "01_nhap_du_lieu.py").resolve()

    def injected_read_source(path: Path) -> str:
        source = real_read_source(path)
        if path.resolve() == injected_path:
            return "from bus_schedule_engine.service import run_analysis\n" + source
        return source

    monkeypatch.setattr(evidence_module, "_read_source", injected_read_source)
    exit_code = main(
        [
            "--repo-root",
            str(ROOT),
            "--target-commit",
            _head_commit(),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["implementation_conclusion"] == "BLOCKED_FROM_FORMAL_APPROVAL"
    assert "M5C2R_ORDINARY_RUNTIME_LEGACY_ANALYSIS_REACHABLE" in payload["blocker_codes"]


def test_m5c2r_production_approval_and_signoffs_remain_pending(report) -> None:
    assert report.implementation_conclusion == ImplementationConclusionV1.READY_FOR_FORMAL_APPROVAL
    assert report.production_approval_status == ProductionApprovalStatusV1.PENDING
    assert {signoff.role for signoff in report.required_human_signoffs} == {
        "Engineering Owner",
        "QA/Release Owner",
    }
    assert all(
        signoff.status == ProductionApprovalStatusV1.PENDING
        for signoff in report.required_human_signoffs
    )


def test_m5c2r_no_production_code_declares_legacy_code_deleted(report) -> None:
    production_sources = [ROOT / "streamlit_app.py"]
    production_sources.extend((ROOT / "app_pages").glob("*.py"))
    production_sources.extend((ROOT / "src" / "bus_schedule_engine").rglob("*.py"))

    assert all(
        "LEGACY_CODE_DELETED" not in path.read_text(encoding="utf-8") for path in production_sources
    )
    assert "LEGACY_CODE_DELETED" not in evidence_to_json_v1(report)


def test_m5c2r_existing_release_audit_behavior_source_is_unchanged() -> None:
    current = (ROOT / "src" / "bus_schedule_engine" / "release_audit.py").read_text(
        encoding="utf-8"
    )

    normalized = current.replace("\r\n", "\n").encode("utf-8")
    assert hashlib.sha256(normalized).hexdigest() == RELEASE_AUDIT_BASELINE_SOURCE_SHA256

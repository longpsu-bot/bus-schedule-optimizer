from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

import bus_schedule_engine
import bus_schedule_engine.application_pipeline as application_pipeline
import bus_schedule_engine.excel_exporter as excel_exporter
import bus_schedule_engine.service as legacy_service
import bus_schedule_engine.ui_utils as ui_utils
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import import_workbook
from bus_schedule_engine.input_authority import normalization_options_from_workbook_v1
from bus_schedule_engine.legacy_retirement_evidence import verify_evidence_fingerprint_v1
from bus_schedule_engine.optimization_service import SolverChoice
from bus_schedule_engine.release_audit import run_release_audit_v1
from bus_schedule_engine.side_by_side_validation import run_side_by_side_validation_v1
from bus_schedule_engine.unified_page5_artifacts import (
    UNIFIED_PAGE5_HTML_FILENAME,
    UNIFIED_PAGE5_PNG_FILENAME,
    UNIFIED_PAGE5_XLSX_FILENAME,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "45b49791b1be734b89271e5700e8eeeb64deb2d4"
EVIDENCE_PATH = (
    ROOT / "docs" / "engine" / "evidence" / "M5C2R_LEGACY_RUNTIME_RETIREMENT_EVIDENCE_45B49791.json"
)
REMOVED_FILES = (
    "scripts/build_sample_artifacts.py",
    "src/bus_schedule_engine/block_supply.py",
    "src/bus_schedule_engine/comparison_exporter.py",
    "src/bus_schedule_engine/diagram.py",
)
REMOVED_MODULES = (
    "bus_schedule_engine.block_supply",
    "bus_schedule_engine.comparison_exporter",
    "bus_schedule_engine.diagram",
)
REMOVED_APPLICATION_SYMBOLS = (
    "ParallelRuntimeStatusV1",
    "ParallelApplicationRunV1",
    "run_and_build_artifacts",
    "build_side_by_side_validation_report_v1",
    "_failed_shadow_run",
    "run_parallel_application_pipeline_v1",
    "UNIFIED_SHADOW_RUNTIME_FAILURE",
)
REMOVED_UI_SYMBOLS = (
    "run_and_build_artifacts",
    "validation_frame",
    "block_frame",
    "scenario_frame",
    "supply_summary_frame",
    "regime_frame",
)
REMOVED_PACKAGE_EXPORTS = (
    "ParallelApplicationRunV1",
    "ParallelRuntimeStatusV1",
    "run_parallel_application_pipeline_v1",
    "UNIFIED_SHADOW_RUNTIME_FAILURE",
)
RETIRED_RESULT_KEYS = (
    "analysis_bundle",
    "diagram_figure",
    "download_artifacts",
    "scenario_c_fingerprint",
    "parallel_runtime_status",
    "side_by_side_validation_report",
)
TEMPLATE_SEMANTIC_FINGERPRINT = "96f9f240613f4ec511855e085a8a1a791bb9c50993b7e4338620d7a8ead809c7"
BASELINE_MANIFEST_FINGERPRINTS = {
    "heuristic_core": "c96009627d669e4ec2387ea28a5af0ba14d8bea4761066cfb21bc284c234be1f",
    "protected_solver_core": "6210fd7ee121bef91a92cdf6be47f97647bc61321584ddb3281eee00081a327d",
    "contract_schemas": "27c42bc441aa035bc1db47865f925257f5c3ce9e5f3308ec40e4dc8d5aeb9584",
    "route_corpus": "4e50c1c1dad4c805ce7d1fc89323782eac02161c79d777659ab1fff890472294",
}
_TEXT_MANIFEST_SUFFIXES = {
    ".csv",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _template_semantic_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            content = archive.read(name)
            if name == "docProps/core.xml":
                content = re.sub(
                    rb"<dcterms:(?:created|modified)[^>]*>.*?</dcterms:(?:created|modified)>",
                    b"",
                    content,
                )
            digest.update(name.encode("utf-8") + b"\0" + content + b"\0")
    return digest.hexdigest()


def _manifest_content(path: Path) -> bytes:
    content = path.read_bytes()
    if path.suffix.lower() in _TEXT_MANIFEST_SUFFIXES:
        return content.replace(b"\r\n", b"\n")
    return content


def _manifest_fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda candidate: candidate.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8") + b"\0" + _manifest_content(path) + b"\0")
    return digest.hexdigest()


def test_authorized_legacy_application_files_and_modules_are_absent() -> None:
    assert all(not (ROOT / relative).exists() for relative in REMOVED_FILES)
    for module_name in REMOVED_MODULES:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)


def test_authorized_mixed_file_symbols_and_package_exports_are_absent() -> None:
    assert all(not hasattr(application_pipeline, name) for name in REMOVED_APPLICATION_SYMBOLS)
    assert all(not hasattr(ui_utils, name) for name in REMOVED_UI_SYMBOLS)
    assert not hasattr(excel_exporter, "export_results")
    assert all(not hasattr(bus_schedule_engine, name) for name in REMOVED_PACKAGE_EXPORTS)

    assert bus_schedule_engine.run_unified_application_pipeline_v1 is (
        application_pipeline.run_unified_application_pipeline_v1
    )
    assert callable(bus_schedule_engine.run_side_by_side_validation_v1)
    assert bus_schedule_engine.AnalysisBundle is not None


def test_executable_production_imports_and_exports_do_not_restore_removed_code() -> None:
    removed_names = {
        *REMOVED_APPLICATION_SYMBOLS,
        *REMOVED_UI_SYMBOLS,
        "export_results",
    }
    removed_module_leaves = {name.rsplit(".", 1)[-1] for name in REMOVED_MODULES}
    production_paths = [ROOT / "streamlit_app.py"]
    production_paths.extend((ROOT / "app_pages").glob("*.py"))
    production_paths.extend((ROOT / "src" / "bus_schedule_engine").rglob("*.py"))
    production_paths.extend((ROOT / "scripts").glob("*.py"))

    for path in production_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (
                path.name in {"application_pipeline.py", "ui_utils.py", "excel_exporter.py"}
            ):
                assert node.name not in removed_names
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {*REMOVED_MODULES, *removed_module_leaves}
                assert all(
                    alias.name not in {*removed_names, *removed_module_leaves}
                    for alias in node.names
                )
            if isinstance(node, ast.Import):
                assert all(alias.name not in REMOVED_MODULES for alias in node.names)
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            ):
                exported = {
                    item.value
                    for item in ast.walk(node.value)
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
                assert exported.isdisjoint(REMOVED_PACKAGE_EXPORTS)
                assert exported.isdisjoint(removed_module_leaves)


def test_streamlit_is_unified_only_and_retired_result_state_is_clear_only() -> None:
    page_sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "app_pages").glob("*.py"))
    }
    combined_pages = "\n".join(page_sources.values())
    assert "run_unified_application_pipeline_v1" in page_sources["01_nhap_du_lieu.py"]
    assert "run_analysis" not in combined_pages
    assert "run_side_by_side_validation_v1" not in combined_pages
    assert "release_audit" not in combined_pages

    startup = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    for key in RETIRED_RESULT_KEYS:
        assert f'"{key}",' in startup
        assert f'"{key}": None' not in startup
        assert f'get("{key}"' not in combined_pages
        assert f'["{key}"]' not in combined_pages
    assert "st.session_state.pop(legacy_key, None)" in startup


def test_page05_still_exposes_exactly_three_contract_v1_files() -> None:
    assert {
        UNIFIED_PAGE5_XLSX_FILENAME,
        UNIFIED_PAGE5_HTML_FILENAME,
        UNIFIED_PAGE5_PNG_FILENAME,
    } == {
        "Bus_Schedule_Contract_V1_Result.xlsx",
        "Bus_Schedule_Contract_V1_Charts.html",
        "Bus_Schedule_Contract_V1_Overview.png",
    }

    source = (ROOT / "app_pages" / "05_xuat_file.py").read_text(encoding="utf-8")
    assert source.count("st.download_button(") == 3


def test_input_template_semantics_are_frozen(tmp_path: Path) -> None:
    template = create_input_template(tmp_path / "input.xlsx")
    assert _template_semantic_fingerprint(template) == TEMPLATE_SEMANTIC_FINGERPRINT


def test_offline_release_audit_and_side_by_side_oracle_remain_operational(
    tmp_path: Path,
) -> None:
    workbook = create_input_template(tmp_path / "oracle.xlsx")
    imported = import_workbook(workbook)
    options = normalization_options_from_workbook_v1(
        imported,
        source_id="m5c3-offline-oracle",
        imported_at=datetime(2026, 8, 2, tzinfo=UTC),
    )
    report = run_side_by_side_validation_v1(imported, options)
    assert report.legacy_snapshot.scenario_b is not None
    assert report.unified_snapshot.scenario_b is not None

    output = tmp_path / "release-audit.json"
    exit_code = run_release_audit_v1(
        workbook,
        solver_choice=SolverChoice.HEURISTIC,
        output=output,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code in {0, 1}
    assert payload["schema"] == "BUS_SCHEDULE_RELEASE_AUDIT_V1"
    assert payload["comparisons"]


def test_service_analysis_is_callable_only_from_offline_or_test_paths() -> None:
    assert callable(legacy_service.run_analysis)
    ordinary_sources = [ROOT / "streamlit_app.py", *(ROOT / "app_pages").glob("*.py")]
    ordinary_sources.append(ROOT / "src" / "bus_schedule_engine" / "application_pipeline.py")
    assert all("run_analysis" not in path.read_text(encoding="utf-8") for path in ordinary_sources)
    assert "run_analysis" in (
        ROOT / "src" / "bus_schedule_engine" / "side_by_side_validation.py"
    ).read_text(encoding="utf-8")
    assert "run_side_by_side_validation_v1" in (
        ROOT / "src" / "bus_schedule_engine" / "release_audit.py"
    ).read_text(encoding="utf-8")


def test_unchanged_solver_core_contract_and_corpus_manifests_are_frozen() -> None:
    groups = {
        "heuristic_core": [
            ROOT / "src" / "bus_schedule_engine" / name
            for name in (
                "c_config.py",
                "c_generator.py",
                "demand.py",
                "fleet.py",
                "validator.py",
            )
        ],
        "protected_solver_core": [
            ROOT / relative
            for relative in (
                "src/bus_schedule_engine/protected_service_floor_codes.py",
                "src/bus_schedule_engine/protected_service_floor_enforcement.py",
                "src/bus_schedule_engine/contracts_v1/heuristic_solver.py",
                "src/bus_schedule_engine/contracts_v1/ortools_solver.py",
                "src/bus_schedule_engine/contracts_v1/ortools_quality_solver.py",
                "src/bus_schedule_engine/contracts_v1/ortools_protected_floor.py",
            )
        ],
        "contract_schemas": [path for path in (ROOT / "contracts").rglob("*") if path.is_file()]
        + [path for path in (ROOT / "examples" / "contracts").rglob("*") if path.is_file()],
        "route_corpus": [
            path
            for path in (ROOT / "tests" / "fixtures" / "route_corpus").rglob("*")
            if path.is_file()
        ],
    }
    assert {
        name: _manifest_fingerprint(paths) for name, paths in groups.items()
    } == BASELINE_MANIFEST_FINGERPRINTS


def test_archived_pre_deletion_evidence_fingerprint_still_verifies() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert payload["audited_target_commit"] == BASELINE_COMMIT
    assert payload["implementation_conclusion"] == "READY_FOR_FORMAL_APPROVAL"
    assert payload["production_approval_status"] == "PENDING"
    assert verify_evidence_fingerprint_v1(payload)

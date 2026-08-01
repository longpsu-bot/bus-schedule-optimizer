"""Deterministic evidence for the Milestone 5C2R retirement approval review."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path

EVIDENCE_PROFILE_V1 = "m5c2r_legacy_runtime_retirement_approval_evidence_v1"
AUTHORITATIVE_BASELINE_COMMIT = "f4971c0d6255d69f5ee3135f083b5637e85ffd86"

GOVERNING_DOCUMENT_PATHS = (
    "docs/engine/MILESTONE_5C1_LEGACY_RUNTIME_RETIREMENT_DECISION.md",
    "docs/engine/MILESTONE_5C2_UNIFIED_FIRST_RUNTIME.md",
    "docs/engine/MILESTONE_6A1_TRIP_RIDERSHIP_ANALYSIS.md",
    "docs/engine/MILESTONE_6A2A_PROTECTED_SERVICE_FLOOR_AUTHORITY.md",
    "docs/engine/MILESTONE_6A2B_PROTECTED_SERVICE_FLOOR_ACCEPTANCE_ENFORCEMENT.md",
    "docs/engine/MILESTONE_6A2C_PROTECTED_SERVICE_FLOOR_HEURISTIC_SEARCH.md",
    "docs/engine/MILESTONE_6A2D_PROTECTED_SERVICE_FLOOR_ORTOOLS_CONSTRAINTS.md",
)

ORDINARY_RUNTIME_ROOTS = (
    "streamlit_app.py",
    "app_pages/01_nhap_du_lieu.py",
    "app_pages/02_kiem_tra.py",
    "app_pages/03_nhu_cau.py",
    "app_pages/04_khuyen_nghi.py",
    "app_pages/05_xuat_file.py",
)

RETIRED_SESSION_KEYS = (
    "analysis_bundle",
    "diagram_figure",
    "download_artifacts",
    "scenario_c_fingerprint",
    "parallel_runtime_status",
    "side_by_side_validation_report",
)

APPROVED_PAGE5_FILENAMES = (
    "Bus_Schedule_Contract_V1_Charts.html",
    "Bus_Schedule_Contract_V1_Overview.png",
    "Bus_Schedule_Contract_V1_Result.xlsx",
)


class ImplementationConclusionV1(StrEnum):
    READY_FOR_FORMAL_APPROVAL = "READY_FOR_FORMAL_APPROVAL"
    BLOCKED_FROM_FORMAL_APPROVAL = "BLOCKED_FROM_FORMAL_APPROVAL"


class ProductionApprovalStatusV1(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DependencyClassificationV1(StrEnum):
    REQUIRED_RUNTIME = "REQUIRED_RUNTIME"
    OFFLINE_VALIDATION = "OFFLINE_VALIDATION"
    REGRESSION_ORACLE = "REGRESSION_ORACLE"
    TEST_SUPPORT = "TEST_SUPPORT"
    MUST_REMAIN_SHARED_DEPENDENCY = "MUST_REMAIN_SHARED_DEPENDENCY"
    AUTHORIZED_5C3_DELETION_CANDIDATE = "AUTHORIZED_5C3_DELETION_CANDIDATE"
    BLOCKED_DELETION_CANDIDATE = "BLOCKED_DELETION_CANDIDATE"


@dataclass(frozen=True, slots=True)
class OrdinaryRuntimeEvidenceV1:
    root_files: tuple[str, ...]
    authoritative_entrypoint: str
    forbidden_imports: tuple[str, ...]
    forbidden_calls: tuple[str, ...]
    unified_local_call_closure: tuple[str, ...]
    readiness_precedes_analysis: bool
    failure_paths_are_fail_closed: bool
    analysis_bundle_is_result_authority: bool
    visible_result_modes: tuple[str, ...]
    page_modes_referenced: tuple[str, ...]
    page5_download_filenames: tuple[str, ...]
    protected_floor_unified_symbols: tuple[str, ...]
    characterization_test_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SessionStateEvidenceV1:
    retired_keys: tuple[str, ...]
    retired_key_write_sites: tuple[str, ...]
    retired_key_read_sites: tuple[str, ...]
    retired_key_clear_sites: tuple[str, ...]
    stale_keys_are_clear_only: bool


@dataclass(frozen=True, slots=True)
class OfflineOracleEvidenceV1:
    cli_entrypoint: str
    legacy_entrypoints: tuple[str, ...]
    reachable_from_ordinary_runtime: bool
    deterministic_serialization: bool
    fixed_import_identity_time: bool
    bounded_comparison_fields: bool
    sensitive_content_absent: bool
    blocker_exit_is_nonzero: bool
    network_imports: tuple[str, ...]
    characterization_test_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DependencyInventoryEntryV1:
    target: str
    classification: DependencyClassificationV1
    consumers: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class HumanSignoffV1:
    role: str
    required_decision: str
    status: ProductionApprovalStatusV1


@dataclass(frozen=True, slots=True)
class LegacyRuntimeRetirementEvidenceV1:
    evidence_profile: str
    authoritative_baseline_commit: str
    audited_target_commit: str
    audited_head_commit: str | None
    target_commit_matches_head: bool
    audited_source_tree_fingerprint: str
    governing_document_paths: tuple[str, ...]
    implementation_conclusion: ImplementationConclusionV1
    production_approval_status: ProductionApprovalStatusV1
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    ordinary_runtime_evidence: OrdinaryRuntimeEvidenceV1
    session_state_evidence: SessionStateEvidenceV1
    offline_oracle_evidence: OfflineOracleEvidenceV1
    retained_dependency_inventory: tuple[DependencyInventoryEntryV1, ...]
    proposed_5c3_deletion_candidates: tuple[str, ...]
    required_shared_dependencies: tuple[str, ...]
    required_human_signoffs: tuple[HumanSignoffV1, ...]
    report_fingerprint: str


_FORBIDDEN_ANALYSIS_SYMBOLS = {
    "bus_schedule_engine.application_pipeline.run_and_build_artifacts",
    "bus_schedule_engine.application_pipeline.run_parallel_application_pipeline_v1",
    "bus_schedule_engine.service.run_analysis",
    "bus_schedule_engine.ui_utils.run_and_build_artifacts",
}
_FORBIDDEN_ARTIFACT_SYMBOLS = {
    "bus_schedule_engine.comparison_exporter.export_bc_comparison",
    "bus_schedule_engine.diagram.build_comparison_diagram",
    "bus_schedule_engine.diagram.build_departure_detail_diagram",
    "bus_schedule_engine.diagram.diagram_png_bytes",
    "bus_schedule_engine.excel_exporter.export_results",
}
_FORBIDDEN_COMPARISON_SYMBOLS = {
    "bus_schedule_engine.application_pipeline.build_side_by_side_validation_report_v1",
    "bus_schedule_engine.side_by_side_validation.build_side_by_side_validation_report_v1",
    "bus_schedule_engine.side_by_side_validation.run_side_by_side_validation_v1",
}
_FORBIDDEN_AUTHORITY_SYMBOLS = {
    "bus_schedule_engine.models.AnalysisBundle",
}
_FORBIDDEN_RELEASE_MODULES = {
    "bus_schedule_engine.release_audit",
}
_FORBIDDEN_CALL_LEAVES = {
    *(symbol.rsplit(".", 1)[-1] for symbol in _FORBIDDEN_ANALYSIS_SYMBOLS),
    *(symbol.rsplit(".", 1)[-1] for symbol in _FORBIDDEN_ARTIFACT_SYMBOLS),
    *(symbol.rsplit(".", 1)[-1] for symbol in _FORBIDDEN_COMPARISON_SYMBOLS),
}

_BLOCKER_CODES = {
    "analysis": "M5C2R_ORDINARY_RUNTIME_LEGACY_ANALYSIS_REACHABLE",
    "artifacts": "M5C2R_ORDINARY_RUNTIME_LEGACY_ARTIFACT_REACHABLE",
    "comparison": "M5C2R_ORDINARY_RUNTIME_SIDE_BY_SIDE_REACHABLE",
    "fallback": "M5C2R_LEGACY_FALLBACK_REACHABLE",
    "authority": "M5C2R_LEGACY_RESULT_STATE_AUTHORITATIVE",
    "page5": "M5C2R_PAGE05_LEGACY_DOWNLOAD_REACHABLE",
    "release": "M5C2R_RELEASE_AUDIT_REACHABLE_FROM_ORDINARY_RUNTIME",
    "nondeterministic": "M5C2R_OFFLINE_EVIDENCE_NONDETERMINISTIC",
    "sensitive": "M5C2R_OFFLINE_EVIDENCE_PROHIBITED_DATA",
    "shared": "M5C2R_SHARED_DEPENDENCY_MARKED_FOR_DELETION",
    "runtime_fallback": "M5C2R_RUNTIME_FAILURE_LEGACY_FALLBACK",
    "readiness": "M5C2R_INCOMPLETE_READINESS_RUNS_ANALYSIS",
    "coverage": "M5C2R_REQUIRED_CHARACTERIZATION_COVERAGE_MISSING",
    "target": "M5C2R_TARGET_COMMIT_MISMATCH",
    "documents": "M5C2R_GOVERNING_DOCUMENT_MISSING",
    "inventory": "M5C2R_DEPENDENCY_INVENTORY_STALE",
}

_REQUIRED_CHARACTERIZATION_TESTS = (
    "tests/test_application_pipeline.py::test_unified_pipeline_completes_without_loading_or_running_legacy",
    "tests/test_application_pipeline.py::test_unified_pipeline_stops_at_readiness_without_any_analysis_or_artifact",
    "tests/test_application_pipeline.py::test_solver_exception_is_staged_and_fails_closed",
    "tests/test_application_pipeline.py::test_artifact_failure_retains_only_verified_result_and_presentation",
    "tests/test_application_pipeline.py::test_unified_pipeline_treats_candidate_rejection_as_complete",
    "tests/test_release_audit.py::test_release_audit_is_deterministic_and_omits_raw_comparison_values",
    "tests/test_release_audit.py::test_release_audit_exits_nonzero_when_comparison_has_blocker",
    "tests/test_runtime_cutover.py::test_streamlit_pages_have_no_ordinary_legacy_runtime_calls",
    "tests/test_runtime_cutover.py::test_streamlit_session_initialization_only_retains_unified_result_state",
    "tests/test_ui.py::test_import_invalid_is_stable_and_only_template_is_downloadable",
    "tests/test_ui.py::test_input_page_runs_unified_only_with_default_solver",
    "tests/test_ui.py::test_page01_not_ready_stores_only_readiness_and_exact_codes",
    "tests/test_ui.py::test_artifact_failure_keeps_pages_02_to_04_but_disables_page05",
    "tests/test_ui.py::test_page05_complete_has_two_figures_and_exactly_three_contract_downloads",
    "tests/test_unified_presentation.py::test_report_free_mixed_both_keeps_accepted_c_and_other_rejection",
    "tests/test_protected_service_floor.py::test_supplemental_assessment_failure_blocks_unprotected_c_but_retains_b",
    "tests/test_protected_service_floor_heuristic_search.py::test_compliant_native_candidate_still_passes_common_independent_validator",
    "tests/test_protected_service_floor_ortools_constraints.py::test_normal_protected_run_passes_common_validation_and_carries_fingerprints",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_report_is_deterministic_and_model_is_frozen",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_fingerprint_detects_tampering",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_current_ordinary_roots_have_no_forbidden_legacy_import_path",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_ready_input_invokes_no_legacy_entry_point",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_not_ready_input_invokes_no_legacy_entry_point",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_unified_failure_invokes_no_legacy_fallback",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_artifact_failure_invokes_no_legacy_fallback",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_pages_02_to_05_have_no_legacy_rendering_mode",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_ordinary_session_state_does_not_write_or_read_retired_keys",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_stale_legacy_session_keys_may_be_cleared_safely",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_release_audit_remains_offline_only",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_evidence_json_omits_sensitive_content_and_absolute_paths",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_shared_heuristic_dependencies_must_remain",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_true_legacy_candidates_are_distinct_from_shared_dependencies",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_post_5c2_protected_floor_paths_remain_unified_only",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_cli_exits_zero_for_current_checkout",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_injected_forbidden_import_makes_cli_nonzero",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_production_approval_and_signoffs_remain_pending",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_no_production_code_declares_legacy_code_deleted",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_existing_release_audit_behavior_source_is_unchanged",
)


def _inventory() -> tuple[DependencyInventoryEntryV1, ...]:
    items = (
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/application_pipeline.py::run_unified_application_pipeline_v1",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("app_pages/01_nhap_du_lieu.py",),
            "The sole ordinary analysis orchestrator.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/application_pipeline.py::UnifiedApplicationRunV1",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("ordinary Streamlit", "visible-result authority"),
            "Atomic Contract V1 runtime result.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/application_pipeline.py::ParallelRuntimeStatusV1",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("offline compatibility tests",),
            "Retired parallel status has no ordinary consumer.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/application_pipeline.py::ParallelApplicationRunV1",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("offline compatibility tests",),
            "Retired parallel result has no ordinary consumer.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/application_pipeline.py::run_parallel_application_pipeline_v1",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("offline compatibility tests",),
            "The release audit uses the side-by-side adapter directly.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/application_pipeline.py::run_and_build_artifacts",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("parallel compatibility adapter",),
            "Lazy bridge for the retired parallel adapter.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/application_pipeline.py::build_side_by_side_validation_report_v1",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("parallel compatibility adapter",),
            "Lazy comparison bridge unused by the release-audit CLI.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/application_pipeline.py::_failed_shadow_run",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("parallel compatibility adapter",),
            "Retired shadow failure projection.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/release_audit.py::run_release_audit_v1",
            DependencyClassificationV1.OFFLINE_VALIDATION,
            ("explicit release-audit CLI",),
            "Deterministic bounded offline comparison entry point.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/side_by_side_validation.py::run_side_by_side_validation_v1",
            DependencyClassificationV1.OFFLINE_VALIDATION,
            ("release audit", "regression tests"),
            "Explicitly executes both paths outside Streamlit.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/side_by_side_validation.py::build_side_by_side_validation_report_v1",
            DependencyClassificationV1.OFFLINE_VALIDATION,
            ("offline adapter", "regression tests"),
            "Builds comparison evidence from already computed results.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/service.py::run_analysis",
            DependencyClassificationV1.REGRESSION_ORACLE,
            ("side-by-side validation", "legacy regression tests"),
            "Retained legacy computation oracle; never product fallback.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/generator.py::generate_recommendations",
            DependencyClassificationV1.REGRESSION_ORACLE,
            ("service.py::run_analysis",),
            "Retained legacy recommendation wrapper for oracle characterization.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/comparator.py::score_scenario",
            DependencyClassificationV1.REGRESSION_ORACLE,
            ("service.py::run_analysis",),
            "Retained legacy weighted scoring for oracle characterization.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/models.py::AnalysisBundle",
            DependencyClassificationV1.REGRESSION_ORACLE,
            ("side-by-side validation", "legacy artifact tests"),
            "Legacy result envelope is absent from unified application results.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/models.py::ScenarioResult",
            DependencyClassificationV1.REGRESSION_ORACLE,
            ("legacy oracle", "side-by-side validation"),
            "Legacy scenario projection retained for comparison evidence.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::run_and_build_artifacts",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy artifact tests", "parallel compatibility adapter"),
            "Legacy application artifact bundle has no ordinary consumer.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::validation_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy UI tests",),
            "Legacy-only presentation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::block_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy UI tests",),
            "Legacy-only presentation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::scenario_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy UI tests",),
            "Legacy-only presentation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::supply_summary_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy UI tests",),
            "Legacy-only presentation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::regime_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy UI tests",),
            "Legacy-only presentation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::<module>",
            DependencyClassificationV1.BLOCKED_DELETION_CANDIDATE,
            ("app_pages/01_nhap_du_lieu.py",),
            "The file also owns current input helpers and cannot be deleted wholesale.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::apply_overrides",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("app_pages/01_nhap_du_lieu.py",),
            "Current input preparation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::template_bytes",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("app_pages/01_nhap_du_lieu.py",),
            "Current migration-template download helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::preview_sheet",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("app_pages/01_nhap_du_lieu.py",),
            "Current input preview helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::workbook_sheet_names",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("app_pages/01_nhap_du_lieu.py",),
            "Current input preview helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/diagram.py::<module>",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy artifact tests", "developer sample script"),
            "Legacy charts are not used by the offline release report or ordinary UI.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/comparison_exporter.py::<module>",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy artifact tests", "developer sample script"),
            "Legacy B/C workbook export is not a current product or release-audit artifact.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/block_supply.py::<module>",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy chart/export tests",),
            "Legacy supply presentation module has no current production consumer.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/excel_exporter.py::export_results",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("legacy artifact tests", "developer sample script"),
            "Legacy result export is separate from the required input template.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/excel_exporter.py::<module>",
            DependencyClassificationV1.BLOCKED_DELETION_CANDIDATE,
            ("ui_utils.py::template_bytes", "import and readiness tests"),
            "The mixed file cannot be deleted until template creation is split safely.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/excel_exporter.py::create_input_template",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("ui_utils.py::template_bytes",),
            "Canonical migration template must remain supported.",
        ),
        DependencyInventoryEntryV1(
            "scripts/build_sample_artifacts.py::<module>",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("explicit developer workflow",),
            "Developer-only legacy artifact script.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/c_generator.py::<module>",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/heuristic_solver.py", "contracts_v1/headway_regimes.py"),
            "Current Contract V1 production imports this file directly.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/c_generator.py::generate_scenario_c",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/heuristic_solver.py",),
            "Default Contract V1 heuristic implementation.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/c_generator.py::_balanced_values",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/headway_regimes.py",),
            "Shared Contract V1 headway-generation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/c_generator.py::_material_boundaries",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/headway_regimes.py",),
            "Shared Contract V1 headway-generation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/c_generator.py::_regime_drafts",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/headway_regimes.py",),
            "Shared Contract V1 headway-generation helper.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/c_generator.py::build_heuristic_protected_floor_search_projection_v1",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/heuristic_solver.py",),
            "Milestone 6A2C native-search projection.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/c_generator.py::validate_heuristic_protected_floor_search_projection_v1",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/heuristic_solver.py",),
            "Milestone 6A2C native-search authority check.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/demand.py::<module>",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("c_generator.py",),
            "Transitive production dependency of the default heuristic.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/demand.py::evaluate_scenario",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("c_generator.py::generate_scenario_c",),
            "Current heuristic candidate evaluation.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/fleet.py::assign_fleet",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("c_generator.py::generate_scenario_c",),
            "Current heuristic fixed-fleet evaluation.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/validator.py::validate_schedule",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("c_generator.py::generate_scenario_c",),
            "Current heuristic technical validation.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/c_config.py::ScenarioCConfig",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/heuristic_context.py", "contracts_v1/solver_adapter.py"),
            "Current Contract V1 heuristic configuration type.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/models.py::<module>",
            DependencyClassificationV1.BLOCKED_DELETION_CANDIDATE,
            ("ordinary runtime", "contracts_v1 production modules"),
            "The mixed model file contains current production types.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/models.py::Trip",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/adapters.py", "contracts_v1/heuristic_context.py"),
            "Shared timetable source type.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/models.py::ScenarioParameters",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1/adapters.py", "contracts_v1/heuristic_context.py"),
            "Shared source-parameter type.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/models.py::ProtectedServiceFloorEnforcementAuthorityV1",
            DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY,
            ("contracts_v1 solver modules", "ordinary application pipeline"),
            "Milestones 6A2B-6A2D production authority type.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/protected_service_floor_enforcement.py::<module>",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("ordinary application pipeline", "contracts_v1 solver modules"),
            "Common 6A2B authority and final validation.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/contracts_v1/ortools_protected_floor.py::<module>",
            DependencyClassificationV1.REQUIRED_RUNTIME,
            ("contracts_v1/ortools_quality_solver.py",),
            "Milestone 6A2D hard-constraint projection.",
        ),
        DependencyInventoryEntryV1(
            "tests/test_application_pipeline.py::<module>",
            DependencyClassificationV1.TEST_SUPPORT,
            ("runtime characterization", "offline compatibility characterization"),
            "Retains both current unified and historical parallel coverage.",
        ),
        DependencyInventoryEntryV1(
            "tests/test_side_by_side_validation.py::<module>",
            DependencyClassificationV1.TEST_SUPPORT,
            ("offline oracle characterization",),
            "Protects the retained comparison boundary.",
        ),
        DependencyInventoryEntryV1(
            "tests/test_integration.py::<module>",
            DependencyClassificationV1.TEST_SUPPORT,
            ("legacy oracle and shared-dependency regression",),
            "Protects retained oracle behavior during the compatibility period.",
        ),
    )
    return tuple(sorted(items, key=lambda item: item.target))


_REQUIRED_SHARED_TARGETS = (
    "src/bus_schedule_engine/c_config.py::ScenarioCConfig",
    "src/bus_schedule_engine/c_generator.py::<module>",
    "src/bus_schedule_engine/c_generator.py::_balanced_values",
    "src/bus_schedule_engine/c_generator.py::_material_boundaries",
    "src/bus_schedule_engine/c_generator.py::_regime_drafts",
    "src/bus_schedule_engine/c_generator.py::build_heuristic_protected_floor_search_projection_v1",
    "src/bus_schedule_engine/c_generator.py::generate_scenario_c",
    "src/bus_schedule_engine/c_generator.py::validate_heuristic_protected_floor_search_projection_v1",
    "src/bus_schedule_engine/demand.py::<module>",
    "src/bus_schedule_engine/demand.py::evaluate_scenario",
    "src/bus_schedule_engine/fleet.py::assign_fleet",
    "src/bus_schedule_engine/models.py::ProtectedServiceFloorEnforcementAuthorityV1",
    "src/bus_schedule_engine/models.py::ScenarioParameters",
    "src/bus_schedule_engine/models.py::Trip",
    "src/bus_schedule_engine/validator.py::validate_schedule",
)


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tree(repo_root: Path, relative_path: str) -> ast.Module:
    return ast.parse(_read_source(repo_root / relative_path), filename=relative_path)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _imports_and_calls(tree: ast.AST) -> tuple[set[str], set[str]]:
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            dotted = _dotted_name(node.func)
            if dotted:
                calls.add(dotted)
    return imports, calls


def _ordinary_source_audit(repo_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    imports: set[str] = set()
    calls: set[str] = set()
    for relative_path in ORDINARY_RUNTIME_ROOTS:
        file_imports, file_calls = _imports_and_calls(_tree(repo_root, relative_path))
        imports.update(file_imports)
        calls.update(file_calls)
    forbidden_symbols = (
        _FORBIDDEN_ANALYSIS_SYMBOLS
        | _FORBIDDEN_ARTIFACT_SYMBOLS
        | _FORBIDDEN_COMPARISON_SYMBOLS
        | _FORBIDDEN_AUTHORITY_SYMBOLS
    )
    forbidden_imports = {
        imported
        for imported in imports
        if imported in forbidden_symbols
        or any(
            imported == module or imported.startswith(f"{module}.")
            for module in _FORBIDDEN_RELEASE_MODULES
        )
        or imported
        in {"bus_schedule_engine.service", "bus_schedule_engine.side_by_side_validation"}
    }
    forbidden_calls = {call for call in calls if call.rsplit(".", 1)[-1] in _FORBIDDEN_CALL_LEAVES}
    return tuple(sorted(forbidden_imports)), tuple(sorted(forbidden_calls))


def _function_definitions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _local_call_closure(tree: ast.Module, root_name: str) -> tuple[str, ...]:
    definitions = _function_definitions(tree)
    pending = [root_name]
    reached: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reached or name not in definitions:
            continue
        reached.add(name)
        for node in ast.walk(definitions[name]):
            if not isinstance(node, ast.Call):
                continue
            dotted = _dotted_name(node.func)
            leaf = dotted.rsplit(".", 1)[-1] if dotted else None
            if leaf in definitions and leaf not in reached:
                pending.append(leaf)
    return tuple(sorted(reached))


def _calls_in_functions(tree: ast.Module, names: Iterable[str]) -> set[str]:
    definitions = _function_definitions(tree)
    calls: set[str] = set()
    for name in names:
        definition = definitions.get(name)
        if definition is None:
            continue
        for node in ast.walk(definition):
            if isinstance(node, ast.Call):
                dotted = _dotted_name(node.func)
                if dotted:
                    calls.add(dotted)
    return calls


def _readiness_precedes_analysis(tree: ast.Module) -> bool:
    function = _function_definitions(tree).get("run_unified_application_pipeline_v1")
    if function is None:
        return False
    assess_lines: list[int] = []
    analysis_lines: list[int] = []
    early_return_lines: list[int] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            called = _dotted_name(node.func)
            leaf = called.rsplit(".", 1)[-1] if called else ""
            if leaf == "assess_workbook_input_readiness_v1":
                assess_lines.append(node.lineno)
            if leaf in {
                "normalize_imported_workbook_v1",
                "_analyze_normalized_and_optimize_schedule_v1",
                "analyze_and_optimize_schedule_v1",
            }:
                analysis_lines.append(node.lineno)
        if isinstance(node, ast.If):
            condition = ast.unparse(node.test)
            if "input_readiness.optimization_ready" in condition and any(
                isinstance(child, ast.Return) for child in ast.walk(node)
            ):
                early_return_lines.append(node.lineno)
    return bool(
        assess_lines
        and early_return_lines
        and analysis_lines
        and min(assess_lines) < min(early_return_lines) < min(analysis_lines)
    )


def _enum_values(tree: ast.Module, enum_name: str) -> tuple[str, ...]:
    values: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != enum_name:
            continue
        for statement in node.body:
            if (
                isinstance(statement, ast.Assign)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                values.append(statement.value.value)
    return tuple(sorted(values))


def _referenced_visible_modes(repo_root: Path) -> tuple[str, ...]:
    modes: set[str] = set()
    for relative_path in ORDINARY_RUNTIME_ROOTS[2:]:
        for node in ast.walk(_tree(repo_root, relative_path)):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "VisibleResultModeV1"
            ):
                modes.add(node.attr)
    return tuple(sorted(modes))


def _assignment_string(tree: ast.Module, name: str) -> str | None:
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _literal_string_tuple(node: ast.AST) -> tuple[str, ...] | None:
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return None
    values: list[str] = []
    for element in node.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        values.append(element.value)
    return tuple(values)


def _session_state_accesses(
    repo_root: Path,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    writes: set[str] = set()
    reads: set[str] = set()
    clears: set[str] = set()
    for relative_path in ORDINARY_RUNTIME_ROOTS:
        tree = _tree(repo_root, relative_path)
        constants: dict[str, tuple[str, ...]] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                values = _literal_string_tuple(node.value)
                if isinstance(target, ast.Name) and values is not None:
                    constants[target.id] = values
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and _dotted_name(node.value) == "st.session_state":
                if node.attr in RETIRED_SESSION_KEYS:
                    site = f"{relative_path}:{node.lineno}:{node.attr}"
                    (writes if isinstance(node.ctx, ast.Store) else reads).add(site)
            elif isinstance(node, ast.Subscript) and _dotted_name(node.value) == "st.session_state":
                key_node = node.slice
                if isinstance(key_node, ast.Constant) and key_node.value in RETIRED_SESSION_KEYS:
                    site = f"{relative_path}:{node.lineno}:{key_node.value}"
                    (writes if isinstance(node.ctx, ast.Store) else reads).add(site)
            elif isinstance(node, ast.Call):
                called = _dotted_name(node.func)
                if (
                    called
                    not in {
                        "st.session_state.get",
                        "st.session_state.pop",
                        "st.session_state.setdefault",
                    }
                    or not node.args
                ):
                    continue
                key_node = node.args[0]
                if isinstance(key_node, ast.Constant) and key_node.value in RETIRED_SESSION_KEYS:
                    site = f"{relative_path}:{node.lineno}:{key_node.value}"
                    if called.endswith(".pop"):
                        clears.add(site)
                    elif called.endswith(".get"):
                        reads.add(site)
                    else:
                        writes.add(site)
            elif isinstance(node, ast.For):
                if not isinstance(node.target, ast.Name):
                    continue
                values = (
                    constants.get(node.iter.id)
                    if isinstance(node.iter, ast.Name)
                    else _literal_string_tuple(node.iter)
                )
                if values is None:
                    continue
                for child in ast.walk(node):
                    if not isinstance(child, ast.Call):
                        continue
                    if _dotted_name(child.func) != "st.session_state.pop" or not child.args:
                        continue
                    argument = child.args[0]
                    if isinstance(argument, ast.Name) and argument.id == node.target.id:
                        for key in values:
                            if key in RETIRED_SESSION_KEYS:
                                clears.add(f"{relative_path}:{node.lineno}:{key}")
    return tuple(sorted(writes)), tuple(sorted(reads)), tuple(sorted(clears))


def _test_functions(repo_root: Path) -> set[str]:
    functions: set[str] = set()
    for path in sorted((repo_root / "tests").glob("test_*.py")):
        relative_path = path.relative_to(repo_root).as_posix()
        tree = ast.parse(_read_source(path), filename=relative_path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.add(f"{relative_path}::{node.name}")
    return functions


def _dict_key_strings(tree: ast.AST) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
    return keys


def _offline_oracle_evidence(
    repo_root: Path,
    ordinary_imports: Sequence[str],
) -> OfflineOracleEvidenceV1:
    release_tree = _tree(repo_root, "src/bus_schedule_engine/release_audit.py")
    release_source = _read_source(repo_root / "src/bus_schedule_engine/release_audit.py")
    imports, calls = _imports_and_calls(release_tree)
    network_imports = tuple(
        sorted(
            imported
            for imported in imports
            if imported.split(".", 1)[0] in {"httpx", "requests", "socket", "urllib"}
        )
    )
    comparison_import = (
        "side_by_side_validation.run_side_by_side_validation_v1" in imports
        or "bus_schedule_engine.side_by_side_validation.run_side_by_side_validation_v1" in imports
    )
    sort_keys = False
    blocker_exit = False
    for node in ast.walk(release_tree):
        if isinstance(node, ast.Call) and _dotted_name(node.func) == "json.dumps":
            sort_keys = any(
                keyword.arg == "sort_keys"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
        if isinstance(node, ast.Return) and isinstance(node.value, ast.IfExp):
            blocker_exit = blocker_exit or (
                "has_blocking_discrepancies" in ast.unparse(node.value.test)
                and isinstance(node.value.body, ast.Constant)
                and node.value.body.value != 0
            )
    fixed_time = (
        "datetime.now" not in calls
        and "datetime.utcnow" not in calls
        and bool(
            re.search(r"_DETERMINISTIC_IMPORTED_AT\s*=\s*datetime\(2000,\s*1,\s*1", release_source)
        )
    )
    output_keys = _dict_key_strings(release_tree)
    prohibited_output_keys = {
        "legacy_value",
        "unified_value",
        "workbook_bytes",
        "source_path",
        "raw_rows",
        "trip_records",
    }
    bounded = comparison_import and not (output_keys & {"legacy_value", "unified_value"})
    sensitive_absent = not (output_keys & prohibited_output_keys)
    ordinary_reachable = any(
        imported == "bus_schedule_engine.release_audit"
        or imported.startswith("bus_schedule_engine.release_audit.")
        for imported in ordinary_imports
    )
    return OfflineOracleEvidenceV1(
        cli_entrypoint="python -m bus_schedule_engine.release_audit",
        legacy_entrypoints=(
            "bus_schedule_engine.service.run_analysis",
            "bus_schedule_engine.side_by_side_validation.run_side_by_side_validation_v1",
        ),
        reachable_from_ordinary_runtime=ordinary_reachable,
        deterministic_serialization=sort_keys and fixed_time and not network_imports,
        fixed_import_identity_time=fixed_time,
        bounded_comparison_fields=bounded,
        sensitive_content_absent=sensitive_absent,
        blocker_exit_is_nonzero=blocker_exit,
        network_imports=network_imports,
        characterization_test_ids=tuple(
            test_id
            for test_id in _REQUIRED_CHARACTERIZATION_TESTS
            if test_id.startswith("tests/test_release_audit.py::")
        ),
    )


def _target_exists(repo_root: Path, target: str) -> bool:
    relative_path, separator, symbol = target.partition("::")
    path = repo_root / relative_path
    if not path.is_file():
        return False
    if not separator or symbol == "<module>" or path.suffix != ".py":
        return True
    tree = ast.parse(_read_source(path), filename=relative_path)
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == symbol
        for node in tree.body
    ) or any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target_node, ast.Name) and target_node.id == symbol
            for target_node in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        for node in tree.body
    )


def _git_output(repo_root: Path, *args: str) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _audited_paths(repo_root: Path) -> tuple[Path, ...]:
    paths: set[Path] = {repo_root / path for path in GOVERNING_DOCUMENT_PATHS}
    paths.update(repo_root / path for path in ORDINARY_RUNTIME_ROOTS)
    paths.add(repo_root / "README.md")
    paths.update((repo_root / "src" / "bus_schedule_engine").rglob("*.py"))
    paths.update((repo_root / "tests").glob("*.py"))
    return tuple(
        sorted((path for path in paths if path.is_file()), key=lambda path: path.as_posix())
    )


def _source_tree_fingerprint(repo_root: Path) -> str:
    digest = hashlib.sha256()
    for path in _audited_paths(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_payload(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def evidence_to_dict_v1(
    report: LegacyRuntimeRetirementEvidenceV1,
) -> dict[str, object]:
    """Return the deterministic JSON-compatible evidence mapping."""
    return asdict(report)


def evidence_to_json_v1(report: LegacyRuntimeRetirementEvidenceV1) -> str:
    """Serialize evidence with stable ordering and newline behavior."""
    return (
        json.dumps(
            evidence_to_dict_v1(report),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _fingerprint_payload(report: LegacyRuntimeRetirementEvidenceV1) -> dict[str, object]:
    payload = evidence_to_dict_v1(report)
    payload.pop("report_fingerprint", None)
    return payload


def _report_fingerprint(report: LegacyRuntimeRetirementEvidenceV1) -> str:
    return hashlib.sha256(_canonical_payload(_fingerprint_payload(report))).hexdigest()


def verify_evidence_fingerprint_v1(payload: Mapping[str, object]) -> bool:
    """Verify a serialized report fingerprint without trusting its contents."""
    candidate = payload.get("report_fingerprint")
    if not isinstance(candidate, str) or re.fullmatch(r"[0-9a-f]{64}", candidate) is None:
        return False
    canonical = dict(payload)
    canonical.pop("report_fingerprint", None)
    return hashlib.sha256(_canonical_payload(canonical)).hexdigest() == candidate


def build_legacy_retirement_evidence_v1(
    repo_root: Path,
    *,
    target_commit: str,
) -> LegacyRuntimeRetirementEvidenceV1:
    """Inspect one checkout and return bounded, deterministic approval evidence."""
    repo_root = repo_root.resolve()
    blockers: set[str] = set()
    warnings = {
        "M5C2R_APPROVER_IDENTITIES_PENDING",
        "M5C2R_PRODUCTION_APPROVAL_PENDING",
        "M5C2R_ROLLBACK_REHEARSAL_CONFIRMATION_PENDING",
    }

    missing_documents = tuple(
        path for path in GOVERNING_DOCUMENT_PATHS if not (repo_root / path).is_file()
    )
    if missing_documents:
        blockers.add(_BLOCKER_CODES["documents"])

    head_commit = _git_output(repo_root, "rev-parse", "HEAD")
    target_matches_head = head_commit == target_commit and bool(
        re.fullmatch(r"[0-9a-f]{40}", target_commit)
    )
    if not target_matches_head:
        blockers.add(_BLOCKER_CODES["target"])
    if _git_output(repo_root, "status", "--porcelain"):
        warnings.add("M5C2R_WORKTREE_HAS_UNCOMMITTED_CHANGES")

    forbidden_imports, forbidden_calls = _ordinary_source_audit(repo_root)
    all_ordinary_imports: set[str] = set()
    for relative_path in ORDINARY_RUNTIME_ROOTS:
        imports, _calls = _imports_and_calls(_tree(repo_root, relative_path))
        all_ordinary_imports.update(imports)

    analysis_pipeline_tree = _tree(repo_root, "src/bus_schedule_engine/application_pipeline.py")
    call_closure = _local_call_closure(
        analysis_pipeline_tree,
        "run_unified_application_pipeline_v1",
    )
    reachable_calls = _calls_in_functions(analysis_pipeline_tree, call_closure)
    reachable_forbidden = {
        call for call in reachable_calls if call.rsplit(".", 1)[-1] in _FORBIDDEN_CALL_LEAVES
    }
    forbidden_calls = tuple(sorted({*forbidden_calls, *reachable_forbidden}))

    analysis_findings = {
        finding
        for finding in (*forbidden_imports, *forbidden_calls)
        if finding.rsplit(".", 1)[-1]
        in {symbol.rsplit(".", 1)[-1] for symbol in _FORBIDDEN_ANALYSIS_SYMBOLS}
    }
    artifact_findings = {
        finding
        for finding in (*forbidden_imports, *forbidden_calls)
        if finding.rsplit(".", 1)[-1]
        in {symbol.rsplit(".", 1)[-1] for symbol in _FORBIDDEN_ARTIFACT_SYMBOLS}
    }
    comparison_findings = {
        finding
        for finding in (*forbidden_imports, *forbidden_calls)
        if finding.rsplit(".", 1)[-1]
        in {symbol.rsplit(".", 1)[-1] for symbol in _FORBIDDEN_COMPARISON_SYMBOLS}
    }
    authority_findings = {
        finding for finding in forbidden_imports if finding in _FORBIDDEN_AUTHORITY_SYMBOLS
    }
    release_findings = {
        finding
        for finding in forbidden_imports
        if any(
            finding == module or finding.startswith(f"{module}.")
            for module in _FORBIDDEN_RELEASE_MODULES
        )
    }
    if analysis_findings:
        blockers.add(_BLOCKER_CODES["analysis"])
    if artifact_findings:
        blockers.add(_BLOCKER_CODES["artifacts"])
    if comparison_findings:
        blockers.add(_BLOCKER_CODES["comparison"])
    if authority_findings:
        blockers.add(_BLOCKER_CODES["authority"])
    if release_findings:
        blockers.add(_BLOCKER_CODES["release"])

    readiness_first = _readiness_precedes_analysis(analysis_pipeline_tree)
    if not readiness_first:
        blockers.add(_BLOCKER_CODES["readiness"])

    authority_tree = _tree(repo_root, "src/bus_schedule_engine/ui_result_authority.py")
    visible_modes = _enum_values(authority_tree, "VisibleResultModeV1")
    authority_imports, authority_calls = _imports_and_calls(authority_tree)
    legacy_authority = any("LEGACY" in mode for mode in visible_modes) or any(
        item.rsplit(".", 1)[-1] in _FORBIDDEN_CALL_LEAVES
        for item in (*authority_imports, *authority_calls)
    )
    if legacy_authority:
        blockers.update({_BLOCKER_CODES["fallback"], _BLOCKER_CODES["runtime_fallback"]})

    page_modes = _referenced_visible_modes(repo_root)
    if any("LEGACY" in mode for mode in page_modes):
        blockers.add(_BLOCKER_CODES["fallback"])

    page5_tree = _tree(repo_root, "src/bus_schedule_engine/unified_page5_artifacts.py")
    page5_filenames = tuple(
        sorted(
            filter(
                None,
                (
                    _assignment_string(page5_tree, "UNIFIED_PAGE5_XLSX_FILENAME"),
                    _assignment_string(page5_tree, "UNIFIED_PAGE5_HTML_FILENAME"),
                    _assignment_string(page5_tree, "UNIFIED_PAGE5_PNG_FILENAME"),
                ),
            )
        )
    )
    page5_root_imports, page5_root_calls = _imports_and_calls(
        _tree(repo_root, "app_pages/05_xuat_file.py")
    )
    if page5_filenames != APPROVED_PAGE5_FILENAMES or any(
        item.rsplit(".", 1)[-1]
        in {
            *(symbol.rsplit(".", 1)[-1] for symbol in _FORBIDDEN_ARTIFACT_SYMBOLS),
            "run_and_build_artifacts",
        }
        for item in (*page5_root_imports, *page5_root_calls)
    ):
        blockers.add(_BLOCKER_CODES["page5"])

    retired_writes, retired_reads, retired_clears = _session_state_accesses(repo_root)
    stale_clear_only = (
        not retired_writes
        and not retired_reads
        and all(
            any(site.endswith(f":{key}") for site in retired_clears) for key in RETIRED_SESSION_KEYS
        )
    )
    if retired_writes or retired_reads:
        blockers.add(_BLOCKER_CODES["authority"])

    offline = _offline_oracle_evidence(repo_root, tuple(sorted(all_ordinary_imports)))
    if offline.reachable_from_ordinary_runtime:
        blockers.add(_BLOCKER_CODES["release"])
    if not (
        offline.deterministic_serialization
        and offline.fixed_import_identity_time
        and offline.bounded_comparison_fields
        and offline.blocker_exit_is_nonzero
        and not offline.network_imports
    ):
        blockers.add(_BLOCKER_CODES["nondeterministic"])
    if not offline.sensitive_content_absent:
        blockers.add(_BLOCKER_CODES["sensitive"])

    inventory = _inventory()
    inventory_by_target = {item.target: item for item in inventory}
    missing_inventory_targets = tuple(
        item.target for item in inventory if not _target_exists(repo_root, item.target)
    )
    if missing_inventory_targets:
        blockers.add(_BLOCKER_CODES["inventory"])
    shared_misclassified = tuple(
        target
        for target in _REQUIRED_SHARED_TARGETS
        if target not in inventory_by_target
        or inventory_by_target[target].classification
        != DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY
    )
    if shared_misclassified:
        blockers.add(_BLOCKER_CODES["shared"])

    test_functions = _test_functions(repo_root)
    missing_tests = tuple(
        test_id for test_id in _REQUIRED_CHARACTERIZATION_TESTS if test_id not in test_functions
    )
    if missing_tests:
        blockers.add(_BLOCKER_CODES["coverage"])

    protected_symbols = (
        "application_pipeline.assess_protected_service_floors_v1",
        "application_pipeline.build_protected_service_floor_enforcement_authority_v1",
        "application_pipeline._analyze_normalized_and_optimize_schedule_v1",
        "contracts_v1.heuristic_solver.build_heuristic_protected_floor_search_projection_v1",
        "contracts_v1.ortools_quality_solver.ortools_protected_floor",
        "contracts_v1.solver_orchestration.validate_candidate_against_protected_service_floors_v1",
    )
    required_protected_call_leaves = {
        "assess_protected_service_floors_v1",
        "build_protected_service_floor_enforcement_authority_v1",
        "_analyze_normalized_and_optimize_schedule_v1",
    }
    if not required_protected_call_leaves.issubset(
        {call.rsplit(".", 1)[-1] for call in reachable_calls}
    ):
        blockers.add(_BLOCKER_CODES["coverage"])

    ordinary = OrdinaryRuntimeEvidenceV1(
        root_files=ORDINARY_RUNTIME_ROOTS,
        authoritative_entrypoint=(
            "bus_schedule_engine.application_pipeline.run_unified_application_pipeline_v1"
        ),
        forbidden_imports=forbidden_imports,
        forbidden_calls=forbidden_calls,
        unified_local_call_closure=call_closure,
        readiness_precedes_analysis=readiness_first,
        failure_paths_are_fail_closed=not reachable_forbidden and not legacy_authority,
        analysis_bundle_is_result_authority=bool(authority_findings),
        visible_result_modes=visible_modes,
        page_modes_referenced=page_modes,
        page5_download_filenames=page5_filenames,
        protected_floor_unified_symbols=protected_symbols,
        characterization_test_ids=tuple(
            test_id
            for test_id in _REQUIRED_CHARACTERIZATION_TESTS
            if not test_id.startswith("tests/test_release_audit.py::")
        ),
    )
    session = SessionStateEvidenceV1(
        retired_keys=RETIRED_SESSION_KEYS,
        retired_key_write_sites=retired_writes,
        retired_key_read_sites=retired_reads,
        retired_key_clear_sites=retired_clears,
        stale_keys_are_clear_only=stale_clear_only,
    )

    deletion_candidates = tuple(
        item.target
        for item in inventory
        if item.classification == DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE
    )
    shared_dependencies = tuple(
        item.target
        for item in inventory
        if item.classification == DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY
    )
    signoffs = (
        HumanSignoffV1(
            role="Engineering Owner",
            required_decision="Approve production legacy-runtime retirement",
            status=ProductionApprovalStatusV1.PENDING,
        ),
        HumanSignoffV1(
            role="QA/Release Owner",
            required_decision="Approve evidence and rollback readiness",
            status=ProductionApprovalStatusV1.PENDING,
        ),
    )
    sorted_blockers = tuple(sorted(blockers))
    report = LegacyRuntimeRetirementEvidenceV1(
        evidence_profile=EVIDENCE_PROFILE_V1,
        authoritative_baseline_commit=AUTHORITATIVE_BASELINE_COMMIT,
        audited_target_commit=target_commit,
        audited_head_commit=head_commit,
        target_commit_matches_head=target_matches_head,
        audited_source_tree_fingerprint=_source_tree_fingerprint(repo_root),
        governing_document_paths=GOVERNING_DOCUMENT_PATHS,
        implementation_conclusion=(
            ImplementationConclusionV1.BLOCKED_FROM_FORMAL_APPROVAL
            if sorted_blockers
            else ImplementationConclusionV1.READY_FOR_FORMAL_APPROVAL
        ),
        production_approval_status=ProductionApprovalStatusV1.PENDING,
        blocker_codes=sorted_blockers,
        warning_codes=tuple(sorted(warnings)),
        ordinary_runtime_evidence=ordinary,
        session_state_evidence=session,
        offline_oracle_evidence=offline,
        retained_dependency_inventory=inventory,
        proposed_5c3_deletion_candidates=deletion_candidates,
        required_shared_dependencies=shared_dependencies,
        required_human_signoffs=signoffs,
        report_fingerprint="",
    )
    return replace(report, report_fingerprint=_report_fingerprint(report))


__all__ = [
    "APPROVED_PAGE5_FILENAMES",
    "AUTHORITATIVE_BASELINE_COMMIT",
    "DependencyClassificationV1",
    "DependencyInventoryEntryV1",
    "EVIDENCE_PROFILE_V1",
    "GOVERNING_DOCUMENT_PATHS",
    "HumanSignoffV1",
    "ImplementationConclusionV1",
    "LegacyRuntimeRetirementEvidenceV1",
    "OfflineOracleEvidenceV1",
    "ORDINARY_RUNTIME_ROOTS",
    "OrdinaryRuntimeEvidenceV1",
    "ProductionApprovalStatusV1",
    "RETIRED_SESSION_KEYS",
    "SessionStateEvidenceV1",
    "build_legacy_retirement_evidence_v1",
    "evidence_to_dict_v1",
    "evidence_to_json_v1",
    "verify_evidence_fingerprint_v1",
]

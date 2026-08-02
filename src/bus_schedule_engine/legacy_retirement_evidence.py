"""Deterministic evidence for the Milestone 5C2R retirement approval review."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from collections import defaultdict, deque
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
class UnresolvedCallGraphSiteV1:
    site: str
    construct: str
    risk: str


@dataclass(frozen=True, slots=True)
class ForbiddenWitnessPathV1:
    category: str
    target: str
    path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeletionCandidateConsumerEvidenceV1:
    target: str
    ordinary_production_consumers: tuple[str, ...]
    allowed_remaining_consumers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductionGraphEvidenceV1:
    root_symbols: tuple[str, ...]
    audited_production_module_count: int
    audited_production_modules: tuple[str, ...]
    reachable_production_symbol_count: int
    reachable_production_symbols: tuple[str, ...]
    resolved_edge_count: int
    unresolved_relevant_site_count: int
    unresolved_relevant_sites: tuple[UnresolvedCallGraphSiteV1, ...]
    forbidden_witness_path_count: int
    forbidden_witness_paths: tuple[ForbiddenWitnessPathV1, ...]
    ordinary_runtime_module_graph_fingerprint: str
    deletion_candidate_production_consumers: tuple[DeletionCandidateConsumerEvidenceV1, ...]


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
    production_graph_evidence: ProductionGraphEvidenceV1
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
    "unresolved_graph": "M5C2R_ORDINARY_RUNTIME_CALL_GRAPH_UNRESOLVED",
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
    "tests/test_legacy_retirement_audit.py::test_m5c2r_transitive_direct_import_is_blocked",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_transitive_module_alias_is_blocked",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_reexported_forbidden_symbol_is_blocked",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_wrapper_chain_has_complete_witness_path",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_deletion_candidate_production_consumer_is_blocked",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_unresolved_relevant_dispatch_fails_closed",
    "tests/test_legacy_retirement_audit.py::test_m5c2r_nonproduction_forbidden_calls_remain_isolated",
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
            ("no current repository consumers",),
            "Legacy-only presentation helper with no current source consumer.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::block_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("no current repository consumers",),
            "Legacy-only presentation helper with no current source consumer.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::scenario_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("no current repository consumers",),
            "Legacy-only presentation helper with no current source consumer.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::supply_summary_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("no current repository consumers",),
            "Legacy-only presentation helper with no current source consumer.",
        ),
        DependencyInventoryEntryV1(
            "src/bus_schedule_engine/ui_utils.py::regime_frame",
            DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE,
            ("no current repository consumers",),
            "Legacy-only presentation helper with no current source consumer.",
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


_GRAPH_MODULE_LIMIT = 512
_GRAPH_SYMBOL_LIMIT = 4096
_GRAPH_FINDING_LIMIT = 64
_GRAPH_CONSUMER_LIMIT = 128
_MODULE_SUFFIX = "::<module>"


@dataclass(slots=True)
class _DefinitionInfo:
    canonical: str
    module: str
    qualname: str
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    kind: str
    parent_class: str | None
    local_definitions: dict[str, str]


@dataclass(slots=True)
class _ModuleInfo:
    name: str
    relative_path: str
    tree: ast.Module
    is_package: bool
    bindings: dict[str, str]
    top_level_definitions: dict[str, str]
    definitions: dict[str, _DefinitionInfo]


@dataclass(frozen=True, order=True, slots=True)
class _GraphEdge:
    source: str
    target: str
    kind: str
    site: str


@dataclass(frozen=True, order=True, slots=True)
class _GraphFinding:
    category: str
    target: str
    source: str
    terminal: str
    kind: str


@dataclass(frozen=True, order=True, slots=True)
class _RepositoryReference:
    source: str
    target: str
    kind: str
    site: str


@dataclass(slots=True)
class _ProductionGraphAnalysis:
    modules: dict[str, _ModuleInfo]
    definitions: dict[str, _DefinitionInfo]
    roots: tuple[str, ...]
    reachable: set[str]
    edges: set[_GraphEdge]
    findings: set[_GraphFinding]
    unresolved: set[UnresolvedCallGraphSiteV1]
    references: tuple[_RepositoryReference, ...]


def _module_node(module: str) -> str:
    return f"{module}{_MODULE_SUFFIX}"


def _module_from_node(node: str) -> str | None:
    return node[: -len(_MODULE_SUFFIX)] if node.endswith(_MODULE_SUFFIX) else None


def _module_name_for_path(repo_root: Path, path: Path) -> str | None:
    relative = path.relative_to(repo_root)
    parts = list(relative.parts)
    if parts[0] == "src":
        parts = parts[1:]
    elif relative.as_posix() in ORDINARY_RUNTIME_ROOTS:
        return relative.with_suffix("").as_posix().replace("/", ".")
    elif len(parts) == 1 and path.suffix == ".py":
        return path.stem
    elif not any(
        (repo_root / Path(*parts[:index]) / "__init__.py").is_file()
        for index in range(1, len(parts))
    ):
        return None
    if not parts or Path(parts[-1]).suffix != ".py":
        return None
    parts[-1] = Path(parts[-1]).stem
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else None


def _production_python_paths(repo_root: Path) -> tuple[Path, ...]:
    paths = {repo_root / relative_path for relative_path in ORDINARY_RUNTIME_ROOTS}
    paths.update((repo_root / "src").rglob("*.py"))
    excluded = {
        ".git",
        ".github",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "docs",
        "examples",
        "outputs",
        "scripts",
        "tests",
        "tools",
    }
    for child in repo_root.iterdir():
        if not child.is_dir() or child.name in excluded or not (child / "__init__.py").is_file():
            continue
        paths.update(child.rglob("*.py"))
    return tuple(
        sorted((path for path in paths if path.is_file()), key=lambda item: item.as_posix())
    )


def _statement_child_blocks(statement: ast.stmt) -> Iterable[list[ast.stmt]]:
    for _field, value in ast.iter_fields(statement):
        if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
            yield value


def _register_definitions(info: _ModuleInfo) -> None:
    def visit_statements(
        statements: Sequence[ast.stmt],
        *,
        owner: _DefinitionInfo | None,
        class_qualname: str | None,
    ) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if class_qualname is not None and owner is None:
                    qualname = f"{class_qualname}.{statement.name}"
                    parent_class = f"{info.name}.{class_qualname}"
                elif owner is not None:
                    qualname = f"{owner.qualname}.<locals>.{statement.name}"
                    parent_class = owner.parent_class
                else:
                    qualname = statement.name
                    parent_class = None
                canonical = f"{info.name}.{qualname}"
                definition = _DefinitionInfo(
                    canonical=canonical,
                    module=info.name,
                    qualname=qualname,
                    node=statement,
                    kind="function",
                    parent_class=parent_class,
                    local_definitions={},
                )
                info.definitions[canonical] = definition
                if owner is not None:
                    owner.local_definitions[statement.name] = canonical
                elif class_qualname is None:
                    info.top_level_definitions[statement.name] = canonical
                visit_statements(statement.body, owner=definition, class_qualname=None)
                continue
            if isinstance(statement, ast.ClassDef):
                if class_qualname is not None and owner is None:
                    qualname = f"{class_qualname}.{statement.name}"
                elif owner is not None:
                    qualname = f"{owner.qualname}.<locals>.{statement.name}"
                else:
                    qualname = statement.name
                canonical = f"{info.name}.{qualname}"
                definition = _DefinitionInfo(
                    canonical=canonical,
                    module=info.name,
                    qualname=qualname,
                    node=statement,
                    kind="class",
                    parent_class=None,
                    local_definitions={},
                )
                info.definitions[canonical] = definition
                if owner is not None:
                    owner.local_definitions[statement.name] = canonical
                elif class_qualname is None:
                    info.top_level_definitions[statement.name] = canonical
                visit_statements(statement.body, owner=None, class_qualname=qualname)
                continue
            for block in _statement_child_blocks(statement):
                visit_statements(block, owner=owner, class_qualname=class_qualname)

    visit_statements(info.tree.body, owner=None, class_qualname=None)


def _relative_import_module(info: _ModuleInfo, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    package_parts = info.name.split(".") if info.is_package else info.name.split(".")[:-1]
    retained = max(0, len(package_parts) - (node.level - 1))
    parts = package_parts[:retained]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _import_bindings(
    info: _ModuleInfo,
    node: ast.Import | ast.ImportFrom,
    modules: Mapping[str, _ModuleInfo],
) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    bindings: dict[str, str] = {}
    loaded: set[str] = set()
    imported_symbols: set[str] = set()
    wildcards: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            module = alias.name
            if module in modules:
                loaded.add(module)
            local_name = alias.asname or module.split(".", 1)[0]
            binding_module = module if alias.asname else module.split(".", 1)[0]
            bindings[local_name] = (
                _module_node(binding_module)
                if binding_module in modules
                else f"external:{binding_module}"
            )
    else:
        module = _relative_import_module(info, node)
        if module in modules:
            loaded.add(module)
        for alias in node.names:
            if alias.name == "*":
                wildcards.add(module)
                continue
            submodule = f"{module}.{alias.name}" if module else alias.name
            if submodule in modules:
                target = _module_node(submodule)
                loaded.add(submodule)
            elif module in modules:
                target = f"{module}.{alias.name}"
                imported_symbols.add(target)
            else:
                target = f"external:{submodule}"
            bindings[alias.asname or alias.name] = target
    expanded_loaded: set[str] = set()
    for module in loaded:
        parts = module.split(".")
        for index in range(1, len(parts) + 1):
            candidate = ".".join(parts[:index])
            if candidate in modules:
                expanded_loaded.add(candidate)
    return (
        bindings,
        tuple(sorted(expanded_loaded)),
        tuple(sorted(imported_symbols)),
        tuple(sorted(wildcards)),
    )


def _is_nonruntime_guard(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if (
        isinstance(test, ast.Attribute)
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
        and test.attr == "TYPE_CHECKING"
    ):
        return True
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    operands = (test.left, test.comparators[0])
    return any(isinstance(item, ast.Name) and item.id == "__name__" for item in operands) and any(
        isinstance(item, ast.Constant) and item.value == "__main__" for item in operands
    )


class _ExecutableScopeVisitor(ast.NodeVisitor):
    def __init__(self, root: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.root = root
        self.nodes: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        if node is not self.root and isinstance(
            node,
            (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.Call),
        ):
            self.nodes.append(node)
        super().generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        branches = node.orelse if _is_nonruntime_guard(node) else [*node.body, *node.orelse]
        for statement in branches:
            self.visit(statement)

    def _visit_definition_header(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self.root:
            for statement in node.body:
                self.visit(statement)
        else:
            self._visit_definition_header(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self.root:
            for statement in node.body:
                self.visit(statement)
        else:
            self._visit_definition_header(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for statement in node.body:
            self.visit(statement)


def _scope_nodes(
    node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ast.AST, ...]:
    visitor = _ExecutableScopeVisitor(node)
    visitor.visit(node)
    return tuple(
        sorted(
            visitor.nodes,
            key=lambda item: (
                getattr(item, "lineno", 0),
                getattr(item, "col_offset", 0),
                type(item).__name__,
            ),
        )
    )


def _index_production_modules(
    repo_root: Path,
) -> tuple[dict[str, _ModuleInfo], dict[str, _DefinitionInfo]]:
    modules: dict[str, _ModuleInfo] = {}
    for path in _production_python_paths(repo_root):
        module = _module_name_for_path(repo_root, path)
        if module is None:
            continue
        relative_path = path.relative_to(repo_root).as_posix()
        info = _ModuleInfo(
            name=module,
            relative_path=relative_path,
            tree=ast.parse(_read_source(path), filename=relative_path),
            is_package=path.name == "__init__.py",
            bindings={},
            top_level_definitions={},
            definitions={},
        )
        _register_definitions(info)
        modules[module] = info
    for info in modules.values():
        for node in _scope_nodes(info.tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bindings, _loaded, _symbols, _wildcards = _import_bindings(info, node, modules)
                info.bindings.update(bindings)
        info.bindings.update(info.top_level_definitions)
    definitions = {
        canonical: definition
        for info in modules.values()
        for canonical, definition in info.definitions.items()
    }
    ordered_modules = dict(sorted(modules.items(), key=lambda item: (-len(item[0]), item[0])))
    return ordered_modules, definitions


def _canonicalize_target(
    target: str | None,
    modules: Mapping[str, _ModuleInfo],
    definitions: Mapping[str, _DefinitionInfo],
    *,
    seen: frozenset[str] = frozenset(),
) -> str | None:
    if not target or target.startswith("external:") or target in seen:
        return None
    if target in definitions:
        return target
    module_target = _module_from_node(target)
    if module_target is not None:
        return target if module_target in modules else None
    for module in modules:
        if target == module:
            return _module_node(module)
        if not target.startswith(f"{module}."):
            continue
        remainder = target[len(module) + 1 :]
        exact_module = f"{module}.{remainder}"
        if exact_module in modules:
            return _module_node(exact_module)
        exact_definition = f"{module}.{remainder}"
        if exact_definition in definitions:
            return exact_definition
        first, separator, rest = remainder.partition(".")
        binding = modules[module].bindings.get(first)
        if binding is None:
            return None
        substituted = binding
        if separator:
            bound_module = _module_from_node(binding)
            substituted = (
                f"{bound_module}.{rest}" if bound_module is not None else f"{binding}.{rest}"
            )
        return _canonicalize_target(
            substituted,
            modules,
            definitions,
            seen=seen | {target},
        )
    return None


def _expression_target(
    node: ast.AST,
    environment: Mapping[str, str],
    modules: Mapping[str, _ModuleInfo],
    definitions: Mapping[str, _DefinitionInfo],
) -> str | None:
    if isinstance(node, ast.Name):
        raw = environment.get(node.id, node.id)
        return _canonicalize_target(raw, modules, definitions) or raw
    if isinstance(node, ast.Attribute):
        base = _expression_target(node.value, environment, modules, definitions)
        if base is None:
            return None
        base_module = _module_from_node(base)
        raw = f"{base_module}.{node.attr}" if base_module is not None else f"{base}.{node.attr}"
        return _canonicalize_target(raw, modules, definitions) or raw
    return None


def _assigned_names(node: ast.Assign | ast.AnnAssign | ast.NamedExpr) -> tuple[str, ...]:
    targets: Sequence[ast.AST] = node.targets if isinstance(node, ast.Assign) else (node.target,)
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.extend(item.id for item in target.elts if isinstance(item, ast.Name))
    return tuple(names)


def _forbidden_candidates_for_module(
    module: str,
    modules: Mapping[str, _ModuleInfo],
    definitions: Mapping[str, _DefinitionInfo],
) -> tuple[str, ...]:
    candidates = {
        symbol
        for symbol in (
            _FORBIDDEN_ANALYSIS_SYMBOLS
            | _FORBIDDEN_ARTIFACT_SYMBOLS
            | _FORBIDDEN_COMPARISON_SYMBOLS
            | _FORBIDDEN_AUTHORITY_SYMBOLS
        )
        if symbol.startswith(f"{module}.")
    }
    info = modules.get(module)
    if info is not None:
        for binding in info.bindings.values():
            canonical = _canonicalize_target(binding, modules, definitions)
            if canonical in (
                _FORBIDDEN_ANALYSIS_SYMBOLS
                | _FORBIDDEN_ARTIFACT_SYMBOLS
                | _FORBIDDEN_COMPARISON_SYMBOLS
                | _FORBIDDEN_AUTHORITY_SYMBOLS
            ):
                candidates.add(canonical)
    return tuple(sorted(candidates))


def _node_environment(
    info: _ModuleInfo,
    definition: _DefinitionInfo | None,
    scope_nodes: Sequence[ast.AST],
    modules: Mapping[str, _ModuleInfo],
    definitions: Mapping[str, _DefinitionInfo],
) -> tuple[dict[str, str], dict[str, dict[object, str]], dict[str, tuple[str, ...]]]:
    environment = dict(info.bindings)
    environment.update(info.top_level_definitions)
    if definition is not None:
        environment.update(definition.local_definitions)
        if definition.parent_class is not None:
            environment.update({"self": definition.parent_class, "cls": definition.parent_class})
    for node in scope_nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            bindings, _loaded, _symbols, _wildcards = _import_bindings(info, node, modules)
            environment.update(bindings)

    mappings: dict[str, dict[object, str]] = {}
    opaque: dict[str, tuple[str, ...]] = {}
    assignments = [
        node
        for node in scope_nodes
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None
    ]
    for _pass in range(4):
        changed = False
        for assignment in assignments:
            names = _assigned_names(assignment)
            if not names:
                continue
            value = assignment.value
            if isinstance(value, ast.Dict):
                resolved: dict[object, str] = {}
                for key, item in zip(value.keys, value.values, strict=True):
                    if key is None:
                        continue
                    target = _expression_target(item, environment, modules, definitions)
                    canonical = _canonicalize_target(target, modules, definitions)
                    if canonical is None:
                        continue
                    literal_key = key.value if isinstance(key, ast.Constant) else None
                    resolved[literal_key] = canonical
                for name in names:
                    if resolved and mappings.get(name) != resolved:
                        mappings[name] = resolved
                        changed = True
                continue
            if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
                choices = mappings.get(value.value.id, {})
                literal_key = value.slice.value if isinstance(value.slice, ast.Constant) else None
                selected = choices.get(literal_key)
                for name in names:
                    if selected is not None and environment.get(name) != selected:
                        environment[name] = selected
                        changed = True
                    elif choices and literal_key is None:
                        candidates = tuple(sorted(set(choices.values())))
                        if opaque.get(name) != candidates:
                            opaque[name] = candidates
                            changed = True
                continue
            if (
                isinstance(value, ast.Call)
                and _dotted_name(value.func) is not None
                and _dotted_name(value.func).rsplit(".", 1)[-1] == "getattr"
                and len(value.args) >= 2
                and not isinstance(value.args[1], ast.Constant)
            ):
                base = _expression_target(value.args[0], environment, modules, definitions)
                base_module = _module_from_node(base or "")
                if base_module is not None:
                    candidates = _forbidden_candidates_for_module(base_module, modules, definitions)
                    for name in names:
                        if candidates and opaque.get(name) != candidates:
                            opaque[name] = candidates
                            changed = True
                continue
            target = _expression_target(value, environment, modules, definitions)
            canonical = _canonicalize_target(target, modules, definitions)
            if canonical is None and isinstance(value, ast.Call):
                called = _expression_target(value.func, environment, modules, definitions)
                called = _canonicalize_target(called, modules, definitions)
                called_definition = definitions.get(called or "")
                if called_definition is not None and called_definition.kind == "class":
                    canonical = called
            if canonical is None:
                continue
            for name in names:
                if environment.get(name) != canonical:
                    environment[name] = canonical
                    changed = True
        if not changed:
            break
    return environment, mappings, opaque


def _category_for_target(target: str) -> str | None:
    if target in _FORBIDDEN_ANALYSIS_SYMBOLS:
        return "legacy_analysis"
    if target in _FORBIDDEN_ARTIFACT_SYMBOLS:
        return "legacy_artifact"
    if target in _FORBIDDEN_COMPARISON_SYMBOLS:
        return "side_by_side"
    if target in _FORBIDDEN_AUTHORITY_SYMBOLS:
        return "legacy_authority"
    if target == "bus_schedule_engine.release_audit" or target.startswith(
        "bus_schedule_engine.release_audit."
    ):
        return "release_audit"
    return None


def _category_for_imported_module(module: str) -> str | None:
    if module == "bus_schedule_engine.service":
        return "legacy_analysis"
    if module == "bus_schedule_engine.side_by_side_validation":
        return "side_by_side"
    if module == "bus_schedule_engine.release_audit":
        return "release_audit"
    if module in {
        "bus_schedule_engine.block_supply",
        "bus_schedule_engine.comparison_exporter",
        "bus_schedule_engine.diagram",
    }:
        return "legacy_artifact"
    return None


def _site(info: _ModuleInfo, owner: str, node: ast.AST) -> str:
    return f"{info.name}::{owner}:{getattr(node, 'lineno', 0)}"


def _unresolved_site(
    info: _ModuleInfo,
    owner: str,
    node: ast.AST,
    construct: str,
    risk: str,
) -> UnresolvedCallGraphSiteV1:
    return UnresolvedCallGraphSiteV1(
        site=_site(info, owner, node),
        construct=construct,
        risk=risk,
    )


def _dynamic_call_unresolved(
    call: ast.Call,
    *,
    info: _ModuleInfo,
    owner: str,
    environment: Mapping[str, str],
    mappings: Mapping[str, Mapping[object, str]],
    opaque: Mapping[str, tuple[str, ...]],
    modules: Mapping[str, _ModuleInfo],
    definitions: Mapping[str, _DefinitionInfo],
) -> UnresolvedCallGraphSiteV1 | None:
    dotted = _dotted_name(call.func) or ""
    leaf = dotted.rsplit(".", 1)[-1]
    if leaf in {"import_module", "__import__"} and (
        not call.args
        or not isinstance(call.args[0], ast.Constant)
        or not isinstance(call.args[0].value, str)
    ):
        return _unresolved_site(
            info,
            owner,
            call,
            "dynamic-import",
            "runtime module selection could load a forbidden legacy or release-audit target",
        )
    if leaf == "getattr" and len(call.args) >= 2 and not isinstance(call.args[1], ast.Constant):
        base = _expression_target(call.args[0], environment, modules, definitions)
        base_module = _module_from_node(base or "")
        if base_module is not None and _forbidden_candidates_for_module(
            base_module, modules, definitions
        ):
            return _unresolved_site(
                info,
                owner,
                call,
                "nonliteral-getattr",
                f"dynamic attribute selection on {base_module} could select a forbidden target",
            )
    if isinstance(call.func, ast.Name) and call.func.id in opaque:
        candidates = opaque[call.func.id]
        if any(_category_for_target(candidate) is not None for candidate in candidates):
            return _unresolved_site(
                info,
                owner,
                call,
                "opaque-callable-alias",
                "runtime callable selection includes a forbidden target candidate",
            )
    if isinstance(call.func, ast.Subscript) and isinstance(call.func.value, ast.Name):
        choices = mappings.get(call.func.value.id, {})
        literal_key = call.func.slice.value if isinstance(call.func.slice, ast.Constant) else None
        if literal_key is None and any(
            _category_for_target(candidate) is not None for candidate in choices.values()
        ):
            return _unresolved_site(
                info,
                owner,
                call,
                "opaque-callable-mapping",
                "runtime mapping selection includes a forbidden target candidate",
            )
    if leaf == "setattr" and len(call.args) >= 2:
        base = _expression_target(call.args[0], environment, modules, definitions)
        base_module = _module_from_node(base or "")
        name = call.args[1].value if isinstance(call.args[1], ast.Constant) else None
        candidates = (
            _forbidden_candidates_for_module(base_module, modules, definitions)
            if base_module is not None
            else ()
        )
        if candidates and (
            not isinstance(name, str)
            or any(candidate.endswith(f".{name}") for candidate in candidates)
        ):
            return _unresolved_site(
                info,
                owner,
                call,
                "callable-global-mutation",
                "runtime mutation could redirect a forbidden production callable",
            )
    return None


def _literal_dynamic_module(call: ast.Call) -> str | None:
    dotted = _dotted_name(call.func) or ""
    if dotted.rsplit(".", 1)[-1] not in {"import_module", "__import__"} or not call.args:
        return None
    value = call.args[0]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def _collect_repository_references(
    repo_root: Path,
    modules: Mapping[str, _ModuleInfo],
    definitions: Mapping[str, _DefinitionInfo],
) -> tuple[_RepositoryReference, ...]:
    def source_for_node(info: _ModuleInfo, node: ast.AST) -> str:
        line = getattr(node, "lineno", 0)
        owners = [
            definition
            for definition in info.definitions.values()
            if definition.kind == "function"
            and getattr(definition.node, "lineno", 0)
            <= line
            <= getattr(definition.node, "end_lineno", 0)
        ]
        if not owners:
            return _module_node(info.name)
        return min(
            owners,
            key=lambda item: (
                getattr(item.node, "end_lineno", 0) - getattr(item.node, "lineno", 0),
                item.canonical,
            ),
        ).canonical

    references: set[_RepositoryReference] = set()
    for info in modules.values():
        environment = {**info.bindings, **info.top_level_definitions}
        for node in ast.walk(info.tree):
            source = source_for_node(info, node)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bindings, loaded, imported, _wildcards = _import_bindings(info, node, modules)
                for module in loaded:
                    references.add(
                        _RepositoryReference(
                            source,
                            _module_node(module),
                            "import-module",
                            _site(info, "<repository-reference>", node),
                        )
                    )
                for raw in (*bindings.values(), *imported):
                    canonical = _canonicalize_target(raw, modules, definitions)
                    if canonical is None or _module_from_node(canonical) is not None:
                        continue
                    kind = (
                        "compatibility-reexport"
                        if info.is_package and node in info.tree.body
                        else "import-symbol"
                    )
                    references.add(
                        _RepositoryReference(
                            source,
                            canonical,
                            kind,
                            _site(info, "<repository-reference>", node),
                        )
                    )
            elif isinstance(node, ast.Call):
                target = _expression_target(node.func, environment, modules, definitions)
                canonical = _canonicalize_target(target, modules, definitions)
                if canonical is not None:
                    references.add(
                        _RepositoryReference(
                            source,
                            canonical,
                            "call-reference",
                            _site(info, "<repository-reference>", node),
                        )
                    )

    for directory, kind in (("tests", "test-support"), ("scripts", "developer-script")):
        base = repo_root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            relative_path = path.relative_to(repo_root).as_posix()
            tree = ast.parse(_read_source(path), filename=relative_path)
            pseudo = _ModuleInfo(
                name=relative_path.removesuffix(".py").replace("/", "."),
                relative_path=relative_path,
                tree=tree,
                is_package=path.name == "__init__.py",
                bindings={},
                top_level_definitions={},
                definitions={},
            )
            source = f"{kind}:{relative_path}::<module>"
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                bindings, loaded, imported, _wildcards = _import_bindings(pseudo, node, modules)
                pseudo.bindings.update(bindings)
                site = f"{relative_path}:<module>:{node.lineno}"
                for module in loaded:
                    references.add(_RepositoryReference(source, _module_node(module), kind, site))
                for raw in (*bindings.values(), *imported):
                    canonical = _canonicalize_target(raw, modules, definitions)
                    if canonical is not None:
                        references.add(_RepositoryReference(source, canonical, kind, site))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                target = _expression_target(node.func, pseudo.bindings, modules, definitions)
                canonical = _canonicalize_target(target, modules, definitions)
                if canonical is not None:
                    references.add(
                        _RepositoryReference(
                            source,
                            canonical,
                            kind,
                            f"{relative_path}:<module>:{node.lineno}",
                        )
                    )
    return tuple(sorted(references))


def _build_production_graph(repo_root: Path) -> _ProductionGraphAnalysis:
    modules, definitions = _index_production_modules(repo_root)
    root_modules = tuple(
        sorted(
            filter(
                None,
                (
                    _module_name_for_path(repo_root, repo_root / relative_path)
                    for relative_path in ORDINARY_RUNTIME_ROOTS
                ),
            )
        )
    )
    roots = tuple(_module_node(module) for module in root_modules)
    reachable: set[str] = set(roots)
    edges: set[_GraphEdge] = set()
    findings: set[_GraphFinding] = set()
    unresolved: set[UnresolvedCallGraphSiteV1] = set()
    pending = deque(roots)
    processed: set[str] = set()

    def add_edge(edge: _GraphEdge, *, traversable: bool = True) -> None:
        edges.add(edge)
        if traversable and edge.target not in reachable:
            reachable.add(edge.target)
            pending.append(edge.target)

    while pending:
        current = min(pending)
        pending.remove(current)
        if current in processed:
            continue
        processed.add(current)
        module_name = _module_from_node(current)
        definition = definitions.get(current)
        if module_name is None and definition is not None:
            module_name = definition.module
        info = modules.get(module_name or "")
        if info is None:
            continue
        if definition is not None and definition.kind == "class":
            initializer = f"{definition.canonical}.__init__"
            if initializer in definitions:
                add_edge(
                    _GraphEdge(
                        current,
                        initializer,
                        "constructor",
                        f"{info.name}::{definition.qualname}:0",
                    )
                )
            continue
        scope = info.tree if definition is None else definition.node
        nodes = _scope_nodes(scope)
        environment, mappings, opaque = _node_environment(
            info, definition, nodes, modules, definitions
        )
        owner = "<module>" if definition is None else definition.qualname
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _bindings, loaded, imported, wildcards = _import_bindings(info, node, modules)
                for loaded_module in loaded:
                    terminal = _module_node(loaded_module)
                    add_edge(_GraphEdge(current, terminal, "import", _site(info, owner, node)))
                    category = _category_for_imported_module(loaded_module)
                    if category is not None:
                        findings.add(
                            _GraphFinding(category, loaded_module, current, terminal, "import")
                        )
                for imported_target in imported:
                    canonical = _canonicalize_target(imported_target, modules, definitions)
                    category = _category_for_target(canonical or imported_target)
                    compatibility_reexport = (
                        definition is None
                        and info.name == "bus_schedule_engine"
                        and info.is_package
                    )
                    type_import_without_root_authority = (
                        category == "legacy_authority" and current not in roots
                    )
                    if (
                        category is not None
                        and not compatibility_reexport
                        and not type_import_without_root_authority
                    ):
                        terminal = canonical or imported_target
                        add_edge(
                            _GraphEdge(
                                current,
                                terminal,
                                "forbidden-import",
                                _site(info, owner, node),
                            ),
                            traversable=False,
                        )
                        findings.add(_GraphFinding(category, terminal, current, terminal, "import"))
                for wildcard_module in wildcards:
                    if wildcard_module in modules and _forbidden_candidates_for_module(
                        wildcard_module, modules, definitions
                    ):
                        unresolved.add(
                            _unresolved_site(
                                info,
                                owner,
                                node,
                                "wildcard-import",
                                f"wildcard import from {wildcard_module} can bind a forbidden target",
                            )
                        )
                continue
            if not isinstance(node, ast.Call):
                continue
            dynamic_unresolved = _dynamic_call_unresolved(
                node,
                info=info,
                owner=owner,
                environment=environment,
                mappings=mappings,
                opaque=opaque,
                modules=modules,
                definitions=definitions,
            )
            if dynamic_unresolved is not None:
                unresolved.add(dynamic_unresolved)
            literal_module = _literal_dynamic_module(node)
            if literal_module in modules:
                add_edge(
                    _GraphEdge(
                        current,
                        _module_node(literal_module),
                        "literal-dynamic-import",
                        _site(info, owner, node),
                    )
                )
            target = _expression_target(node.func, environment, modules, definitions)
            canonical = _canonicalize_target(target, modules, definitions)
            if canonical is not None and canonical in definitions:
                add_edge(_GraphEdge(current, canonical, "call", _site(info, owner, node)))
                category = _category_for_target(canonical)
                if category is not None:
                    findings.add(_GraphFinding(category, canonical, current, canonical, "call"))
                continue
            raw = target or _dotted_name(node.func)
            if raw and raw.rsplit(".", 1)[-1] in _FORBIDDEN_CALL_LEAVES:
                terminal = f"unresolved:{raw}"
                add_edge(
                    _GraphEdge(
                        current,
                        terminal,
                        "conservative-leaf-call",
                        _site(info, owner, node),
                    ),
                    traversable=False,
                )
                leaf = raw.rsplit(".", 1)[-1]
                category = next(
                    (
                        candidate_category
                        for candidate_category, symbols in (
                            ("legacy_analysis", _FORBIDDEN_ANALYSIS_SYMBOLS),
                            ("legacy_artifact", _FORBIDDEN_ARTIFACT_SYMBOLS),
                            ("side_by_side", _FORBIDDEN_COMPARISON_SYMBOLS),
                        )
                        if leaf in {symbol.rsplit(".", 1)[-1] for symbol in symbols}
                    ),
                    "legacy_analysis",
                )
                findings.add(_GraphFinding(category, terminal, current, terminal, "call"))

    references = _collect_repository_references(repo_root, modules, definitions)
    return _ProductionGraphAnalysis(
        modules=modules,
        definitions=definitions,
        roots=roots,
        reachable=reachable,
        edges=edges,
        findings=findings,
        unresolved=unresolved,
        references=references,
    )


def _shortest_witness_paths(graph: _ProductionGraphAnalysis) -> dict[str, tuple[str, ...]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adjacency[edge.source].add(edge.target)
    paths: dict[str, tuple[str, ...]] = {root: (root,) for root in graph.roots}
    pending = deque(sorted(graph.roots))
    while pending:
        source = pending.popleft()
        for target in sorted(adjacency.get(source, ())):
            candidate = (*paths[source], target)
            existing = paths.get(target)
            if existing is None or (len(candidate), candidate) < (len(existing), existing):
                paths[target] = candidate
                pending.append(target)
    return paths


def _inventory_target_canonical(
    target: str,
    modules: Mapping[str, _ModuleInfo],
) -> str:
    relative_path, _separator, symbol = target.partition("::")
    module = next(
        (info.name for info in modules.values() if info.relative_path == relative_path),
        None,
    )
    if module is None:
        return target
    return _module_node(module) if symbol == "<module>" else f"{module}.{symbol}"


def _reference_matches_inventory_target(reference: str, target: str) -> bool:
    module = _module_from_node(target)
    if module is not None:
        reference_module = _module_from_node(reference)
        return reference_module == module or reference.startswith(f"{module}.")
    return reference == target


def _consumer_label(reference: _RepositoryReference) -> str:
    return f"{reference.source} [{reference.kind} at {reference.site}]"


def _reconcile_inventory_consumers(
    graph: _ProductionGraphAnalysis,
    inventory: Sequence[DependencyInventoryEntryV1],
) -> tuple[
    tuple[DeletionCandidateConsumerEvidenceV1, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    candidate_targets = {
        _inventory_target_canonical(item.target, graph.modules): item.target
        for item in inventory
        if item.classification == DependencyClassificationV1.AUTHORIZED_5C3_DELETION_CANDIDATE
    }
    evidence: list[DeletionCandidateConsumerEvidenceV1] = []
    unsafe: set[str] = set()
    overflow: set[str] = set()
    for canonical, target in sorted(candidate_targets.items(), key=lambda item: item[1]):
        ordinary = {
            f"{edge.source} [{edge.kind} at {edge.site}]"
            for edge in graph.edges
            if edge.source in graph.reachable
            and _reference_matches_inventory_target(edge.target, canonical)
            and not _reference_matches_inventory_target(edge.source, canonical)
        }
        allowed: set[str] = set()
        for reference in graph.references:
            if not _reference_matches_inventory_target(reference.target, canonical):
                continue
            if _reference_matches_inventory_target(reference.source, canonical):
                continue
            label = _consumer_label(reference)
            source_is_candidate = any(
                _reference_matches_inventory_target(reference.source, candidate)
                for candidate in candidate_targets
            )
            if reference.kind == "compatibility-reexport" or source_is_candidate:
                allowed.add(f"compatibility-wrapper:{label}")
            elif reference.source.startswith(("test-support:", "developer-script:")):
                allowed.add(label)
            else:
                allowed.add(f"nonordinary-production:{label}")
        if ordinary:
            unsafe.add(target)
        if len(ordinary) > _GRAPH_CONSUMER_LIMIT or len(allowed) > _GRAPH_CONSUMER_LIMIT:
            overflow.add(target)
        evidence.append(
            DeletionCandidateConsumerEvidenceV1(
                target=target,
                ordinary_production_consumers=tuple(sorted(ordinary))[:_GRAPH_CONSUMER_LIMIT],
                allowed_remaining_consumers=tuple(sorted(allowed))[:_GRAPH_CONSUMER_LIMIT],
            )
        )
    return tuple(evidence), tuple(sorted(unsafe)), tuple(sorted(overflow))


def _missing_shared_consumers(
    graph: _ProductionGraphAnalysis,
    inventory: Sequence[DependencyInventoryEntryV1],
) -> tuple[str, ...]:
    missing: list[str] = []
    for item in inventory:
        if item.classification != DependencyClassificationV1.MUST_REMAIN_SHARED_DEPENDENCY:
            continue
        canonical = _inventory_target_canonical(item.target, graph.modules)
        has_consumer = canonical in graph.reachable or any(
            _reference_matches_inventory_target(reference.target, canonical)
            and not _reference_matches_inventory_target(reference.source, canonical)
            and not reference.source.startswith(("test-support:", "developer-script:"))
            for reference in graph.references
        )
        if not has_consumer:
            missing.append(item.target)
    return tuple(sorted(missing))


def _graph_evidence(
    graph: _ProductionGraphAnalysis,
    consumer_evidence: tuple[DeletionCandidateConsumerEvidenceV1, ...],
) -> ProductionGraphEvidenceV1:
    audited_modules = tuple(
        sorted(module for module in graph.modules if _module_node(module) in graph.reachable)
    )
    reachable_symbols = tuple(sorted(graph.reachable))
    unresolved = tuple(
        sorted(graph.unresolved, key=lambda item: (item.site, item.construct, item.risk))
    )
    paths = _shortest_witness_paths(graph)
    witnesses = tuple(
        sorted(
            (
                ForbiddenWitnessPathV1(
                    category=finding.category,
                    target=finding.target,
                    path=(
                        (*paths[finding.source], finding.terminal)
                        if finding.source in paths
                        else (finding.terminal,)
                    ),
                )
                for finding in graph.findings
            ),
            key=lambda item: (item.category, item.target, item.path),
        )
    )
    fingerprint_payload = {
        "roots": graph.roots,
        "modules": audited_modules,
        "reachable": reachable_symbols,
        "edges": [(edge.source, edge.target, edge.kind, edge.site) for edge in sorted(graph.edges)],
        "unresolved": [asdict(item) for item in unresolved],
        "findings": [asdict(item) for item in witnesses],
    }
    fingerprint = hashlib.sha256(_canonical_payload(fingerprint_payload)).hexdigest()
    return ProductionGraphEvidenceV1(
        root_symbols=graph.roots,
        audited_production_module_count=len(audited_modules),
        audited_production_modules=audited_modules[:_GRAPH_MODULE_LIMIT],
        reachable_production_symbol_count=len(reachable_symbols),
        reachable_production_symbols=reachable_symbols[:_GRAPH_SYMBOL_LIMIT],
        resolved_edge_count=len(graph.edges),
        unresolved_relevant_site_count=len(unresolved),
        unresolved_relevant_sites=unresolved[:_GRAPH_FINDING_LIMIT],
        forbidden_witness_path_count=len(witnesses),
        forbidden_witness_paths=witnesses[:_GRAPH_FINDING_LIMIT],
        ordinary_runtime_module_graph_fingerprint=fingerprint,
        deletion_candidate_production_consumers=consumer_evidence,
    )


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

    graph = _build_production_graph(repo_root)
    if graph.unresolved:
        blockers.add(_BLOCKER_CODES["unresolved_graph"])
    reachable_module_count = sum(
        _module_node(module) in graph.reachable for module in graph.modules
    )
    if len(graph.reachable) > _GRAPH_SYMBOL_LIMIT or reachable_module_count > _GRAPH_MODULE_LIMIT:
        graph.unresolved.add(
            UnresolvedCallGraphSiteV1(
                site="ordinary-runtime::<graph>:0",
                construct="reachable-symbol-evidence-limit",
                risk="the bounded evidence representation cannot retain every reachable symbol",
            )
        )
        blockers.add(_BLOCKER_CODES["unresolved_graph"])

    forbidden_imports = tuple(
        sorted(finding.target for finding in graph.findings if finding.kind == "import")
    )
    forbidden_calls = tuple(
        sorted(finding.target for finding in graph.findings if finding.kind == "call")
    )
    analysis_pipeline_tree = _tree(repo_root, "src/bus_schedule_engine/application_pipeline.py")
    call_closure = _local_call_closure(
        analysis_pipeline_tree,
        "run_unified_application_pipeline_v1",
    )
    reachable_forbidden = set(forbidden_calls)

    analysis_findings = {
        finding for finding in graph.findings if finding.category == "legacy_analysis"
    }
    artifact_findings = {
        finding for finding in graph.findings if finding.category == "legacy_artifact"
    }
    comparison_findings = {
        finding for finding in graph.findings if finding.category == "side_by_side"
    }
    authority_findings = {
        finding for finding in graph.findings if finding.category == "legacy_authority"
    }
    release_findings = {
        finding for finding in graph.findings if finding.category == "release_audit"
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

    ordinary_modules = tuple(
        sorted(module for module in graph.modules if _module_node(module) in graph.reachable)
    )
    offline = _offline_oracle_evidence(repo_root, ordinary_modules)
    offline = replace(offline, reachable_from_ordinary_runtime=bool(release_findings))
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

    consumer_evidence, unsafe_candidates, consumer_overflow = _reconcile_inventory_consumers(
        graph, inventory
    )
    if unsafe_candidates:
        blockers.add(_BLOCKER_CODES["shared"])
    missing_shared_consumers = _missing_shared_consumers(graph, inventory)
    if missing_shared_consumers:
        blockers.add(_BLOCKER_CODES["shared"])
    if consumer_overflow:
        blockers.add(_BLOCKER_CODES["inventory"])
    production_graph = _graph_evidence(graph, consumer_evidence)

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
    reachable_graph_leaves = {symbol.rsplit(".", 1)[-1] for symbol in graph.reachable}
    if not required_protected_call_leaves.issubset(reachable_graph_leaves):
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
        production_graph_evidence=production_graph,
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
    "DeletionCandidateConsumerEvidenceV1",
    "DependencyInventoryEntryV1",
    "EVIDENCE_PROFILE_V1",
    "GOVERNING_DOCUMENT_PATHS",
    "HumanSignoffV1",
    "ImplementationConclusionV1",
    "LegacyRuntimeRetirementEvidenceV1",
    "ForbiddenWitnessPathV1",
    "OfflineOracleEvidenceV1",
    "ORDINARY_RUNTIME_ROOTS",
    "OrdinaryRuntimeEvidenceV1",
    "ProductionApprovalStatusV1",
    "ProductionGraphEvidenceV1",
    "RETIRED_SESSION_KEYS",
    "SessionStateEvidenceV1",
    "UnresolvedCallGraphSiteV1",
    "build_legacy_retirement_evidence_v1",
    "evidence_to_dict_v1",
    "evidence_to_json_v1",
    "verify_evidence_fingerprint_v1",
]

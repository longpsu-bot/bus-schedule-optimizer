from __future__ import annotations

import hashlib
import json
from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from presentation_support import build_result_and_report, rejected_result_and_report
from route_corpus_support import (
    imported_workbook_from_fixture,
    load_corpus_fixture,
    normalization_options_from_fixture,
)

import bus_schedule_engine.operational_review as review_module
from bus_schedule_engine.application_pipeline import (
    UnifiedApplicationRunV1,
    UnifiedApplicationStatusV1,
)
from bus_schedule_engine.contracts_v1 import (
    DemandConfidence,
    DemandResponseMode,
    DemandSourceType,
)
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import WorkbookAuthorityMetadata
from bus_schedule_engine.input_authority import WorkbookInputReadinessV1
from bus_schedule_engine.operational_review import (
    EXPERT_REVIEW_REQUIRED,
    REVIEW_PROFILE_V1,
    NextDecisionCategoryV1,
    OperationalReviewPackageV1,
    RealRouteOperationalReviewV1,
    ReviewDispositionV1,
    ReviewPipelineStatusV1,
    build_operational_review_v1,
    calculate_operational_review_fingerprint_v1,
    create_operational_review_package_v1,
    operational_review_to_dict_v1,
    render_operational_review_markdown_v1,
    serialize_operational_review_v1,
    verify_operational_review_fingerprint_v1,
    verify_operational_review_json_bytes_v1,
    write_operational_review_package_v1,
)
from bus_schedule_engine.optimization_service import (
    OptimizationAction,
    SolverChoice,
    analyze_and_optimize_schedule_v1,
)
from bus_schedule_engine.real_route_review import main as cli_main
from bus_schedule_engine.unified_page5_artifacts import (
    UNIFIED_PAGE5_HTML_FILENAME,
    UNIFIED_PAGE5_PNG_FILENAME,
    UNIFIED_PAGE5_XLSX_FILENAME,
    UnifiedPage5ArtifactsV1,
)
from bus_schedule_engine.unified_presentation import build_unified_application_presentation_v1

READY = WorkbookInputReadinessV1(
    import_ready=True,
    optimization_ready=True,
    blocking_import_codes=(),
    missing_optimization_authority_codes=(),
    optional_limitations=(),
)
APPROVED_ARTIFACT_FILENAMES = (
    UNIFIED_PAGE5_XLSX_FILENAME,
    UNIFIED_PAGE5_HTML_FILENAME,
    UNIFIED_PAGE5_PNG_FILENAME,
)
APPROVED_OUTPUT_FILENAMES = {
    "operational-review.json",
    "operational-review.md",
    *APPROVED_ARTIFACT_FILENAMES,
}
APPROVED_ARTIFACT_METADATA_FILES = (
    {"filename": UNIFIED_PAGE5_XLSX_FILENAME, "kind": "XLSX"},
    {"filename": UNIFIED_PAGE5_HTML_FILENAME, "kind": "HTML"},
    {"filename": UNIFIED_PAGE5_PNG_FILENAME, "kind": "PNG"},
)


def _run_from_result(result) -> UnifiedApplicationRunV1:
    presentation = build_unified_application_presentation_v1(result)
    return UnifiedApplicationRunV1(
        status=UnifiedApplicationStatusV1.COMPLETE,
        input_readiness=READY,
        unified_result=result,
        unified_presentation=presentation,
        unified_demand_supply_figure=None,
        unified_departure_figure=None,
        unified_xlsx_bytes=None,
        source_id=presentation.source_id,
        imported_at=datetime(2026, 8, 2, tzinfo=UTC),
        failure=None,
    )


def _review_from_result(result, *, requested: SolverChoice | None = None):
    run = _run_from_result(result)
    return build_operational_review_v1(
        source_id=run.source_id,
        requested_solver=requested or result.solver_choice,
        readiness=READY,
        run=run,
        artifacts=None,
    )


def _fast_artifacts(presentation, demand_figure, departure_figure, xlsx_bytes, **kwargs):
    return UnifiedPage5ArtifactsV1(
        selected_direction=kwargs["selected_direction"],
        demand_supply_figure=demand_figure,
        departure_figure=departure_figure,
        xlsx_bytes=xlsx_bytes,
        html_bytes=b"<html>bounded review</html>",
        png_bytes=b"png",
        presentation_fingerprint=presentation.presentation_fingerprint,
        b_fingerprint=presentation.source_b_fingerprint,
        accepted_solution_fingerprint=presentation.accepted_solution_fingerprint,
        xlsx_filename=UNIFIED_PAGE5_XLSX_FILENAME,
        html_filename=UNIFIED_PAGE5_HTML_FILENAME,
        png_filename=UNIFIED_PAGE5_PNG_FILENAME,
    )


def _artifacts_with_filename(field: str, value: str):
    def builder(*args, **kwargs):
        return replace(_fast_artifacts(*args, **kwargs), **{field: value})

    return builder


def _canonical_test_json_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _recomputed_json_with_source(package: OperationalReviewPackageV1, source_id: str) -> bytes:
    payload = json.loads(package.json_bytes)
    payload.pop("review_fingerprint")
    payload["source_id"] = source_id
    payload["review_fingerprint"] = hashlib.sha256(_canonical_test_json_bytes(payload)).hexdigest()
    return _canonical_test_json_bytes(payload)


def _rebind_package_to_review(
    package: OperationalReviewPackageV1,
    review: RealRouteOperationalReviewV1,
) -> OperationalReviewPackageV1:
    review = replace(
        review,
        review_fingerprint=calculate_operational_review_fingerprint_v1(review),
    )
    return replace(
        package,
        review=review,
        json_bytes=serialize_operational_review_v1(review),
        markdown_bytes=render_operational_review_markdown_v1(review),
    )


def _assert_writer_rejects_without_mutation(
    package: OperationalReviewPackageV1,
    tmp_path: Path,
    *outside_candidates: Path,
) -> None:
    output = tmp_path / "review"
    output.mkdir()
    for index, name in enumerate(sorted(APPROVED_OUTPUT_FILENAMES)):
        (output / name).write_bytes(f"sentinel-{index}".encode())
    unrelated = output / "unrelated.keep"
    unrelated.write_bytes(b"preserve me")
    before = {path.name: path.read_bytes() for path in output.iterdir()}

    with pytest.raises((TypeError, ValueError)):
        write_operational_review_package_v1(package, output, overwrite=True)

    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    assert not (output / "subdir").exists()
    for candidate in (
        tmp_path / "outside.xlsx",
        tmp_path / "outside.html",
        tmp_path / "outside.png",
        *outside_candidates,
    ):
        assert not candidate.exists()


@pytest.fixture(scope="module")
def review_workbook(tmp_path_factory):
    root = tmp_path_factory.mktemp("m6a2e-workbook")
    return create_input_template(root / "input.xlsx")


@pytest.fixture(scope="module")
def completed_package(review_workbook):
    return create_operational_review_package_v1(
        review_workbook,
        source_id="synthetic-complete-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=_fast_artifacts,
    )


@pytest.fixture(scope="module")
def alternate_completed_package(review_workbook):
    return create_operational_review_package_v1(
        review_workbook,
        source_id="alternate-complete-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=_fast_artifacts,
    )


@pytest.fixture(scope="module")
def input_not_ready_package():
    return create_operational_review_package_v1(
        b"not an xlsx",
        source_id="fixture-input-not-ready-review",
        solver_choice=SolverChoice.HEURISTIC,
    )


@pytest.fixture(scope="module")
def pipeline_failed_package(review_workbook):
    def fail_pipeline(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("bounded pipeline failure")

    return create_operational_review_package_v1(
        review_workbook,
        source_id="fixture-pipeline-failed-review",
        solver_choice=SolverChoice.OR_TOOLS,
        pipeline_runner=fail_pipeline,
    )


@pytest.fixture(scope="module")
def artifact_failed_package(review_workbook):
    def fail_artifacts(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("bounded artifact failure")

    return create_operational_review_package_v1(
        review_workbook,
        source_id="fixture-artifact-failed-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=fail_artifacts,
    )


def test_review_model_is_frozen_slotted_and_has_required_top_level_fields(
    completed_package,
) -> None:
    review = completed_package.review
    assert RealRouteOperationalReviewV1.__dataclass_params__.frozen is True
    assert "__slots__" in RealRouteOperationalReviewV1.__dict__
    assert review.profile == REVIEW_PROFILE_V1
    assert review.expert_review_status == EXPERT_REVIEW_REQUIRED
    assert {
        "input_readiness_summary",
        "route_facts",
        "demand_authority_summary",
        "scenario_b_operational_summary",
        "heuristic_outcome_summary",
        "ortools_outcome_summary",
        "recommendation_summary",
        "b_to_accepted_c_comparison",
        "protected_service_floor_summary",
        "artifact_metadata",
        "expert_review_checklist",
        "review_fingerprint",
    }.issubset({item.name for item in fields(RealRouteOperationalReviewV1)})


def test_canonical_serializer_is_deterministic_and_tamper_evident(completed_package) -> None:
    review = completed_package.review
    assert verify_operational_review_fingerprint_v1(review)
    assert verify_operational_review_json_bytes_v1(completed_package.json_bytes)
    assert operational_review_to_dict_v1(review)["review_fingerprint"] == review.review_fingerprint

    tampered_model = replace(review, source_id="tampered-source")
    assert not verify_operational_review_fingerprint_v1(tampered_model)

    payload = json.loads(completed_package.json_bytes)
    payload["review_disposition"] = ReviewDispositionV1.CURRENT_B_RETAINED.value
    tampered_bytes = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    assert not verify_operational_review_json_bytes_v1(tampered_bytes)


def test_complete_package_writes_exact_bounded_outputs(completed_package, tmp_path) -> None:
    written = write_operational_review_package_v1(completed_package, tmp_path)
    assert completed_package.exit_code == 0
    assert completed_package.review.pipeline_status == ReviewPipelineStatusV1.REVIEW_COMPLETE
    assert {item.name for item in written} == APPROVED_OUTPUT_FILENAMES
    assert completed_package.review.artifact_metadata["files"] == APPROVED_ARTIFACT_METADATA_FILES
    assert verify_operational_review_json_bytes_v1(
        (tmp_path / "operational-review.json").read_bytes()
    )
    markdown = (tmp_path / "operational-review.md").read_text(encoding="utf-8")
    for heading in (
        "1. Review conclusion",
        "2. Input readiness and authority",
        "3. Current Scenario B",
        "4. Demand and service gaps",
        "5. Fleet, turnaround, and terminal operations",
        "6. Heuristic result",
        "7. OR-Tools result",
        "8. Recommended existing outcome",
        "9. B-to-C operational comparison",
        "10. Protected service floors",
        "11. Solver divergence",
        "12. Expert checklist",
        "13. Limitations",
        "14. Artifact and fingerprint references",
    ):
        assert heading in markdown


def test_parent_traversal_artifact_builder_fails_closed(review_workbook, tmp_path) -> None:
    outside = tmp_path / "outside.xlsx"
    output = tmp_path / "review"
    package = create_operational_review_package_v1(
        review_workbook,
        source_id="parent-traversal-artifact-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=_artifacts_with_filename("xlsx_filename", "../outside.xlsx"),
    )

    assert package.exit_code == 4
    assert package.review.pipeline_status == ReviewPipelineStatusV1.ARTIFACT_FAILED
    assert package.artifacts is None
    assert package.review.artifact_metadata["files"] == ()
    written = write_operational_review_package_v1(package, output)
    assert {path.name for path in written} == {
        "operational-review.json",
        "operational-review.md",
    }
    assert {path.name for path in output.iterdir()} == {
        "operational-review.json",
        "operational-review.md",
    }
    assert not outside.exists()


def test_absolute_artifact_filename_fails_closed(review_workbook, tmp_path) -> None:
    outside = (tmp_path / "absolute-result.xlsx").resolve()
    package = create_operational_review_package_v1(
        review_workbook,
        source_id="absolute-artifact-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=_artifacts_with_filename("xlsx_filename", str(outside)),
    )

    assert package.exit_code == 4
    assert package.review.pipeline_status == ReviewPipelineStatusV1.ARTIFACT_FAILED
    assert package.artifacts is None
    assert package.review.artifact_metadata["files"] == ()
    assert not outside.exists()


@pytest.mark.parametrize(
    ("field", "value", "candidate"),
    (
        ("xlsx_filename", "subdir/result.xlsx", Path("review/subdir/result.xlsx")),
        ("html_filename", "subdir/result.html", Path("review/subdir/result.html")),
        ("png_filename", "../outside.png", Path("outside.png")),
    ),
    ids=("nested-xlsx", "invalid-html", "invalid-png"),
)
def test_invalid_artifact_filename_fields_fail_identically(
    review_workbook,
    tmp_path,
    field: str,
    value: str,
    candidate: Path,
) -> None:
    output = tmp_path / "review"
    package = create_operational_review_package_v1(
        review_workbook,
        source_id=f"invalid-{field}-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=_artifacts_with_filename(field, value),
    )

    assert package.exit_code == 4
    assert package.review.pipeline_status == ReviewPipelineStatusV1.ARTIFACT_FAILED
    assert package.artifacts is None
    assert package.review.artifact_metadata["files"] == ()
    written = write_operational_review_package_v1(package, output)
    assert {path.name for path in written} == {
        "operational-review.json",
        "operational-review.md",
    }
    assert not (tmp_path / candidate).exists()


def test_writer_rejects_tampered_artifact_filename_before_mutation(
    completed_package, tmp_path
) -> None:
    assert completed_package.artifacts is not None
    outside = tmp_path / "outside.xlsx"
    tampered = replace(
        completed_package,
        artifacts=replace(
            completed_package.artifacts,
            xlsx_filename="../outside.xlsx",
        ),
    )

    _assert_writer_rejects_without_mutation(tampered, tmp_path, outside)


def test_writer_rejects_json_from_another_valid_review(
    completed_package, alternate_completed_package, tmp_path
) -> None:
    tampered = replace(completed_package, json_bytes=alternate_completed_package.json_bytes)

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


def test_writer_rejects_markdown_from_another_valid_review(
    completed_package, alternate_completed_package, tmp_path
) -> None:
    tampered = replace(
        completed_package,
        markdown_bytes=alternate_completed_package.markdown_bytes,
    )

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


@pytest.mark.parametrize(
    "markdown_bytes",
    (b"# arbitrary review\n", b"# operationally_approved\n"),
    ids=("arbitrary-markdown", "forbidden-approval-markdown"),
)
def test_writer_rejects_noncanonical_markdown(
    completed_package, tmp_path, markdown_bytes: bytes
) -> None:
    tampered = replace(completed_package, markdown_bytes=markdown_bytes)

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


@pytest.mark.parametrize(
    "prohibited_value",
    (r"C:\private\route\review.xlsx", "/private/route/review.xlsx", "operationally_approved"),
    ids=("absolute-windows-path", "absolute-posix-path", "forbidden-approval-json"),
)
def test_recomputed_prohibited_json_fails_privacy_and_package_verification(
    completed_package,
    tmp_path,
    prohibited_value: str,
) -> None:
    tampered_json = _recomputed_json_with_source(completed_package, prohibited_value)
    tampered = replace(completed_package, json_bytes=tampered_json)

    assert not verify_operational_review_json_bytes_v1(tampered_json)
    _assert_writer_rejects_without_mutation(tampered, tmp_path)


def test_writer_rejects_stale_review_fingerprint(completed_package, tmp_path) -> None:
    stale_review = replace(completed_package.review, source_id="stale-review-model")
    tampered = replace(completed_package, review=stale_review)

    assert not verify_operational_review_fingerprint_v1(stale_review)
    _assert_writer_rejects_without_mutation(tampered, tmp_path)


@pytest.mark.parametrize(
    ("fixture_name", "wrong_exit_code"),
    (
        ("completed_package", 2),
        ("input_not_ready_package", 0),
    ),
    ids=("completed-as-input-not-ready", "input-not-ready-as-completed"),
)
def test_writer_rejects_exit_code_status_mismatch(
    request,
    tmp_path,
    fixture_name: str,
    wrong_exit_code: int,
) -> None:
    package = request.getfixturevalue(fixture_name)
    tampered = replace(package, exit_code=wrong_exit_code)

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


def test_writer_rejects_artifact_free_completed_package(completed_package, tmp_path) -> None:
    tampered = replace(completed_package, artifacts=None)

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


@pytest.mark.parametrize(
    "fixture_name",
    ("input_not_ready_package", "pipeline_failed_package", "artifact_failed_package"),
    ids=("input-not-ready", "pipeline-failed", "artifact-failed"),
)
def test_writer_rejects_artifact_bearing_failed_packages(
    request,
    completed_package,
    tmp_path,
    fixture_name: str,
) -> None:
    assert completed_package.artifacts is not None
    failed_package = request.getfixturevalue(fixture_name)
    tampered = replace(failed_package, artifacts=completed_package.artifacts)

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


@pytest.mark.parametrize(
    "metadata_mismatch",
    ("unavailable", "empty-files", "different-filename"),
    ids=("artifacts-marked-unavailable", "artifacts-without-files", "unapproved-file-list"),
)
def test_writer_rejects_completed_artifact_metadata_mismatch(
    completed_package,
    tmp_path,
    metadata_mismatch: str,
) -> None:
    metadata = dict(completed_package.review.artifact_metadata)
    if metadata_mismatch == "unavailable":
        metadata["contract_v1_artifacts_available"] = False
    elif metadata_mismatch == "empty-files":
        metadata["files"] = ()
    else:
        metadata["files"] = (
            {"filename": "different.xlsx", "kind": "XLSX"},
            *APPROVED_ARTIFACT_METADATA_FILES[1:],
        )
    review = replace(completed_package.review, artifact_metadata=metadata)
    tampered = _rebind_package_to_review(completed_package, review)

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


def test_writer_rejects_artifact_filename_metadata_when_artifacts_are_absent(
    artifact_failed_package, tmp_path
) -> None:
    metadata = dict(artifact_failed_package.review.artifact_metadata)
    metadata["files"] = APPROVED_ARTIFACT_METADATA_FILES
    review = replace(artifact_failed_package.review, artifact_metadata=metadata)
    tampered = _rebind_package_to_review(artifact_failed_package, review)

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


@pytest.mark.parametrize(
    "fingerprint_field",
    ("presentation_fingerprint", "scenario_b_fingerprint", "accepted_solution_fingerprint"),
    ids=("presentation", "scenario-b", "accepted-solution"),
)
def test_writer_rejects_artifact_fingerprint_metadata_mismatch(
    completed_package,
    tmp_path,
    fingerprint_field: str,
) -> None:
    metadata = dict(completed_package.review.artifact_metadata)
    metadata[fingerprint_field] = "tampered-fingerprint"
    review = replace(completed_package.review, artifact_metadata=metadata)
    tampered = _rebind_package_to_review(completed_package, review)

    _assert_writer_rejects_without_mutation(tampered, tmp_path)


def test_overwrite_replaces_only_five_approved_bounded_files(completed_package, tmp_path) -> None:
    output = tmp_path / "review"
    output.mkdir()
    for name in APPROVED_OUTPUT_FILENAMES:
        (output / name).write_bytes(b"stale")
    unrelated = output / "outside.xlsx"
    unrelated.write_bytes(b"preserve me")

    written = write_operational_review_package_v1(completed_package, output, overwrite=True)

    assert {path.name for path in written} == APPROVED_OUTPUT_FILENAMES
    assert unrelated.read_bytes() == b"preserve me"
    assert {path.name for path in output.iterdir()} == {
        *APPROVED_OUTPUT_FILENAMES,
        unrelated.name,
    }
    assert all((output / name).read_bytes() != b"stale" for name in APPROVED_OUTPUT_FILENAMES)


def test_same_workbook_source_solver_and_controls_repeat_review_bytes(tmp_path) -> None:
    workbook = create_input_template(tmp_path / "input.xlsx")
    first = create_operational_review_package_v1(
        workbook,
        source_id="repeatable-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=_fast_artifacts,
    )
    second = create_operational_review_package_v1(
        workbook.read_bytes(),
        source_id="repeatable-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=_fast_artifacts,
    )
    assert first.json_bytes == second.json_bytes
    assert first.markdown_bytes == second.markdown_bytes
    assert first.review.review_fingerprint == second.review.review_fingerprint


def test_input_not_ready_writes_only_review_files_and_returns_two(tmp_path) -> None:
    package = create_operational_review_package_v1(
        b"not an xlsx",
        source_id="invalid-input-review",
        solver_choice=SolverChoice.HEURISTIC,
    )
    written = write_operational_review_package_v1(package, tmp_path)
    assert package.exit_code == 2
    assert package.review.pipeline_status == ReviewPipelineStatusV1.INPUT_NOT_READY
    assert {item.name for item in written} == {"operational-review.json", "operational-review.md"}
    assert package.review.input_readiness_summary["blocking_import_codes"] == (
        "WORKBOOK_IMPORT_INVALID",
    )


def test_pipeline_failure_is_sanitized_and_returns_three(tmp_path) -> None:
    workbook = create_input_template(tmp_path / "input.xlsx")

    def failed(imported, **kwargs):
        del imported, kwargs
        raise RuntimeError(f"pipeline failed at {tmp_path}")

    package = create_operational_review_package_v1(
        workbook,
        source_id="pipeline-failure-review",
        solver_choice=SolverChoice.OR_TOOLS,
        pipeline_runner=failed,
    )
    assert package.exit_code == 3
    assert package.review.pipeline_status == ReviewPipelineStatusV1.PIPELINE_FAILED
    assert "CONTRACT_V1_APPLICATION_ERROR" in package.review.reason_codes
    # No solver-semantic change is authorized until the sanitized failure is diagnosed.
    assert package.review.next_decision_category == NextDecisionCategoryV1.NO_ENGINE_CHANGE_REQUIRED
    assert package.review.next_decision_reason == (
        "The sanitized pipeline failure requires diagnosis before an engine-change category is chosen."
    )
    written = write_operational_review_package_v1(package, tmp_path / "review")
    assert {item.name for item in written} == {"operational-review.json", "operational-review.md"}
    assert str(tmp_path) not in package.json_bytes.decode()


def test_artifact_failure_after_verified_result_keeps_review_and_returns_four(tmp_path) -> None:
    workbook = create_input_template(tmp_path / "input.xlsx")

    def fail_artifacts(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(f"renderer failed at {tmp_path}")

    package = create_operational_review_package_v1(
        workbook,
        source_id="artifact-failure-review",
        solver_choice=SolverChoice.BOTH,
        artifact_builder=fail_artifacts,
    )
    written = write_operational_review_package_v1(package, tmp_path / "review")
    assert package.exit_code == 4
    assert package.review.pipeline_status == ReviewPipelineStatusV1.ARTIFACT_FAILED
    assert package.artifacts is None
    assert "CONTRACT_V1_ARTIFACT_FAILED" in package.review.reason_codes
    assert package.review.scenario_b_operational_summary["total_trips"] == 24
    assert package.review.artifact_metadata["contract_v1_artifacts_available"] is False
    assert package.review.artifact_metadata["files"] == ()
    assert {item.name for item in written} == {"operational-review.json", "operational-review.md"}
    assert str(tmp_path) not in package.json_bytes.decode()


def test_cli_status_codes_and_overwrite_collision(tmp_path) -> None:
    workbook = tmp_path / "invalid.xlsx"
    workbook.write_bytes(b"invalid")
    output = tmp_path / "output"
    args = [
        "--workbook",
        str(workbook),
        "--source-id",
        "cli-input-not-ready",
        "--solver",
        "HEURISTIC",
        "--output-dir",
        str(output),
    ]
    assert cli_main(args) == 2
    assert cli_main(args) == 5
    assert cli_main([*args, "--overwrite"]) == 2


def _reviewed_corpus_result(filename: str):
    fixture = load_corpus_fixture(filename)
    imported = imported_workbook_from_fixture(fixture)
    options = normalization_options_from_fixture(fixture)
    imported = replace(
        imported,
        parameters_a=replace(
            imported.parameters_a,
            available_fleet_limit=options.available_fleet_limit_a,
            operating_day_type=options.operating_day_type_a.value.lower(),
        ),
        parameters_b=replace(
            imported.parameters_b,
            available_fleet_limit=options.available_fleet_limit_b,
            operating_day_type=options.operating_day_type_b.value.lower(),
        ),
        authority_metadata=WorkbookAuthorityMetadata(
            demand_dataset_id=options.demand_dataset_id,
            demand_source_type=DemandSourceType.AGGREGATE_REPORT,
            demand_confidence=DemandConfidence.LOW,
            demand_response_mode=DemandResponseMode.STATIC,
        ),
    )
    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.BOTH,
    )
    return _review_from_result(result, requested=SolverChoice.BOTH)


def test_alpha_review_is_complete_low_confidence_and_never_approves_operations() -> None:
    review = _reviewed_corpus_result("corpus_alpha_80.json")
    payload = json.dumps(operational_review_to_dict_v1(review), sort_keys=True)
    assert review.pipeline_status == ReviewPipelineStatusV1.REVIEW_COMPLETE
    assert review.demand_authority_summary["coverage_status"] == "COMPLETE"
    assert review.demand_authority_summary["confidence"] == "low"
    assert review.scenario_b_operational_summary["terminal_occupancy"]["limitation_codes"] == (
        "TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED",
    )
    assert ("operationally" + "_approved") not in payload.lower()


def test_beta_interior_gap_remains_fail_closed_without_solver_recommendation() -> None:
    review = _reviewed_corpus_result("corpus_beta_46.json")
    demand = review.demand_authority_summary
    assert demand["coverage_status"] == "INCOMPLETE"
    assert demand["uncovered_intervals"] == (
        {
            "code": "DEMAND_TEMPORAL_COVERAGE_GAP",
            "direction": "outbound",
            "start": {"seconds": 61200, "hhmm": "17:00"},
            "end": {"seconds": 64800, "hhmm": "18:00"},
        },
    )
    assert demand["interpolation_used"] is False
    assert demand["fabricated_zero_demand_used"] is False
    assert review.review_disposition == ReviewDispositionV1.DEMAND_AUTHORITY_INCOMPLETE
    assert review.recommendation_summary["accepted_candidate_available"] is False
    assert review.next_decision_category == NextDecisionCategoryV1.DATA_AUTHORITY_GAP


def test_low_frequency_unequal_windows_fleet_turnaround_and_terminal_cases() -> None:
    result, _ = build_result_and_report(
        solver_choice=SolverChoice.BOTH,
        terminal_1_occupancy=2,
        terminal_2_occupancy=2,
    )
    review = _review_from_result(result)
    b = review.scenario_b_operational_summary
    route = review.route_facts
    assert b["largest_service_gap_minutes"] >= 30
    windows = route["service_windows"]["value"]
    assert windows["outbound"] != windows["inbound"]
    assert b["minimum_required_fleet"] <= b["available_fleet_limit"]
    assert b["minimum_observed_turnaround_slack_minutes"] is not None
    assert b["terminal_occupancy"]["terminal_1"]["limit"] == 2
    assert b["terminal_occupancy"]["terminal_2"]["limit"] == 2

    no_limit_result, _ = build_result_and_report(solver_choice=SolverChoice.BOTH)
    no_limit = _review_from_result(no_limit_result).scenario_b_operational_summary
    assert no_limit["terminal_occupancy"]["limitation_codes"] == (
        "TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED",
    )


def test_no_enforceable_floor_is_explicit_and_transition_gaps_stay_excluded() -> None:
    result, _ = build_result_and_report(solver_choice=SolverChoice.BOTH)
    protected = _review_from_result(result).protected_service_floor_summary
    assert protected["no_enforceable_regime"] is True
    assert protected["protected_regime_count"] == 0
    assert protected["transition_gaps_excluded_from_protected_internal_headways"] is True
    assert protected["non_protected_regimes_are_not_classified_as_low_demand"] is True


@pytest.mark.parametrize(
    ("heuristic_accepted", "ortools_accepted", "vectors_differ", "expected"),
    (
        (True, False, False, True),
        (False, True, False, True),
        (True, True, True, True),
        (False, False, False, False),
    ),
    ids=(
        "heuristic-accepted-ortools-rejected",
        "ortools-accepted-heuristic-rejected",
        "both-accepted-different-objectives",
        "neither-accepted",
    ),
)
def test_solver_divergence_and_no_accepted_c_cases(
    heuristic_accepted: bool,
    ortools_accepted: bool,
    vectors_differ: bool,
    expected: bool,
) -> None:
    both, _ = build_result_and_report(solver_choice=SolverChoice.BOTH)
    rejected, _ = rejected_result_and_report()
    accepted_h = both.heuristic_outcome
    accepted_o = both.ortools_outcome
    rejected_outcome = rejected.heuristic_outcome
    assert accepted_h is not None and accepted_o is not None and rejected_outcome is not None
    heuristic = accepted_h if heuristic_accepted else rejected_outcome
    ortools = (
        accepted_o
        if ortools_accepted
        else replace(
            rejected_outcome,
            solver_adapter=accepted_o.solver_adapter,
        )
    )
    comparison = both.comparison
    assert comparison is not None
    if vectors_differ:
        comparison = replace(
            comparison,
            ortools_vector=tuple(value + 1 for value in comparison.ortools_vector or ()),
        )
    synthetic = replace(
        both,
        heuristic_outcome=heuristic,
        ortools_outcome=ortools,
        comparison=comparison,
        recommended_outcome=(
            heuristic if heuristic_accepted else ortools if ortools_accepted else None
        ),
    )
    review = _review_from_result(synthetic)
    divergence = review.review_disposition == ReviewDispositionV1.SOLVER_DIVERGENCE_REVIEW_REQUIRED
    assert divergence is expected
    if not heuristic_accepted and not ortools_accepted:
        assert review.review_disposition == ReviewDispositionV1.NO_ACCEPTED_CANDIDATE


def test_structural_trip_decision_maps_to_fixed_resource_scope_gap() -> None:
    package_review = _review_from_result(build_result_and_report()[0])
    result = _run_from_result(build_result_and_report()[0]).unified_result
    assert result is not None
    structural = replace(result, selected_action=OptimizationAction.TRIP_INCREASE_RECOMMENDED)
    review = _review_from_result(structural)
    assert review.next_decision_category == NextDecisionCategoryV1.FIXED_RESOURCE_SCOPE_GAP
    assert review.b_to_accepted_c_comparison is not None
    assert review.b_to_accepted_c_comparison["trip_count_delta"] == 0
    assert package_review.expert_review_status == EXPERT_REVIEW_REQUIRED


def test_review_module_does_not_modify_solver_or_artifact_boundaries() -> None:
    source = Path(review_module.__file__).read_text(encoding="utf-8")
    assert "build_unified_page5_artifacts_v1" in source
    assert "run_unified_application_pipeline_v1" in source
    assert "CpModel" not in source
    assert "Workbook(" not in source
    assert "streamlit" not in source.lower()

from __future__ import annotations

import json
from dataclasses import fields, replace

import pytest
from presentation_support import (
    build_corpus_result_and_report,
    build_result_and_report,
    rejected_result_and_report,
)

import bus_schedule_engine.side_by_side_validation as side_by_side
import bus_schedule_engine.unified_presentation as unified_presentation
from bus_schedule_engine.optimization_service import SolverChoice
from bus_schedule_engine.unified_presentation import (
    PRESENTATION_MODE_VALIDATION_ONLY,
    PresentationBlockV1,
    PresentationDemandGapV1,
    PresentationDimensionV1,
    PresentationDiscrepancyV1,
    PresentationFleetAssignmentV1,
    PresentationHeadwayRegimeV1,
    PresentationInitialFleetV1,
    PresentationOutcomeV1,
    PresentationScenarioV1,
    PresentationTripV1,
    UnifiedPresentationBundleV1,
    UnifiedPresentationConsistencyError,
    build_unified_presentation_v1,
    unified_presentation_to_dict,
)


@pytest.fixture(scope="module")
def accepted_pair():
    return build_result_and_report()


@pytest.fixture(scope="module")
def accepted_presentation(accepted_pair):
    return build_unified_presentation_v1(*accepted_pair)


@pytest.fixture(scope="module")
def alpha_pair():
    return build_corpus_result_and_report("corpus_alpha_80.json")


@pytest.fixture(scope="module")
def beta_pair():
    return build_corpus_result_and_report("corpus_beta_46.json")


def test_presentation_models_are_frozen_and_slotted() -> None:
    model_types = (
        PresentationTripV1,
        PresentationScenarioV1,
        PresentationBlockV1,
        PresentationDimensionV1,
        PresentationOutcomeV1,
        PresentationFleetAssignmentV1,
        PresentationInitialFleetV1,
        PresentationHeadwayRegimeV1,
        PresentationDemandGapV1,
        PresentationDiscrepancyV1,
        UnifiedPresentationBundleV1,
    )
    assert all(model.__dataclass_params__.frozen for model in model_types)
    assert all("__slots__" in model.__dict__ for model in model_types)


def test_serialization_and_fingerprint_are_deterministic_and_json_compatible(
    accepted_pair,
    accepted_presentation,
) -> None:
    repeated = build_unified_presentation_v1(*accepted_pair)
    first = unified_presentation_to_dict(accepted_presentation)
    second = unified_presentation_to_dict(repeated)

    assert first == second
    assert accepted_presentation.presentation_fingerprint == repeated.presentation_fingerprint
    assert len(accepted_presentation.presentation_fingerprint) == 64
    assert json.loads(json.dumps(first, sort_keys=True)) == first


def test_public_identity_and_contract_fingerprints_are_preserved(
    accepted_pair,
    accepted_presentation,
) -> None:
    result, _report = accepted_pair
    solution = result.recommended_outcome.solution
    assert solution is not None
    assert accepted_presentation.presentation_mode == PRESENTATION_MODE_VALIDATION_ONLY
    assert accepted_presentation.source_b_fingerprint == (
        result.normalized_inputs.scenario_b_fingerprint
    )
    assert accepted_presentation.accepted_solution_fingerprint == (solution.solution_fingerprint)
    assert accepted_presentation.scenario("B").source_fingerprint == (
        result.normalized_inputs.scenario_b_fingerprint
    )
    assert accepted_presentation.scenario("C").source_fingerprint == (solution.solution_fingerprint)


def test_result_report_b_fingerprint_mismatch_raises(accepted_pair) -> None:
    result, report = accepted_pair
    changed_snapshot = replace(
        report.unified_snapshot,
        normalized_scenario_b_fingerprint="different-b-fingerprint",
    )
    changed_report = replace(report, unified_snapshot=changed_snapshot)
    with pytest.raises(
        UnifiedPresentationConsistencyError,
        match="SOURCE_B_FINGERPRINT_MISMATCH",
    ):
        build_unified_presentation_v1(result, changed_report)


def test_result_report_c_fingerprint_mismatch_raises(accepted_pair) -> None:
    result, report = accepted_pair
    changed_snapshot = replace(
        report.unified_snapshot,
        solution_fingerprint="different-c-fingerprint",
    )
    changed_report = replace(report, unified_snapshot=changed_snapshot)
    with pytest.raises(
        UnifiedPresentationConsistencyError,
        match="ACCEPTED_SOLUTION_FINGERPRINT_MISMATCH",
    ):
        build_unified_presentation_v1(result, changed_report)


def test_blocking_legacy_discrepancy_remains_renderable(accepted_pair) -> None:
    result, report = accepted_pair
    changed_legacy = replace(report.legacy_snapshot, route_id="LEGACY-OTHER-ROUTE")
    blocking_report = side_by_side._report(changed_legacy, report.unified_snapshot)
    presentation = build_unified_presentation_v1(result, blocking_report)

    assert presentation.cutover_blocked is True
    assert presentation.requires_expert_review is True
    assert presentation.blocking_discrepancy_codes
    assert any(item.disposition == "BLOCKS_CUTOVER" for item in presentation.discrepancies)


def test_no_automatic_approval_surface_exists(accepted_presentation) -> None:
    names = {field.name for field in fields(UnifiedPresentationBundleV1)}
    assert {
        "approved",
        "cutover_authorized",
        "ready_for_production",
        "readiness_score",
    }.isdisjoint(names)
    assert not hasattr(accepted_presentation, "approved")


def test_accepted_c_uses_exact_solution_trace_and_returned_fleet(
    accepted_pair,
    accepted_presentation,
) -> None:
    result, _report = accepted_pair
    solution = result.recommended_outcome.solution
    assert solution is not None
    scenario_c = accepted_presentation.scenario("C")
    assert scenario_c is not None
    expected = {trip.c_trip_id: trip for trip in solution.c_exact_timetable}
    assignments = {item.c_trip_id: item for item in solution.fleet_assignment}

    assert {trip.source_b_trip_id for trip in scenario_c.trips} == {
        trip.trip_id for trip in result.normalized_inputs.scenario_b.exact_timetable
    }
    for trip in scenario_c.trips:
        source = expected[trip.trip_id]
        assignment = assignments[trip.trip_id]
        assert trip.b_departure_time_seconds == source.b_departure_time
        assert trip.departure_time_seconds == assignment.departure_time
        assert trip.arrival_time_seconds == assignment.arrival_time
        assert trip.vehicle_assignment == assignment.vehicle_id
        assert trip.shift_minutes == source.shift_minutes


@pytest.mark.parametrize(
    "fixture_name",
    ("corpus_alpha_80.json", "corpus_beta_46.json"),
)
def test_corpus_without_accepted_c_never_substitutes_b(fixture_name: str) -> None:
    result, report = build_corpus_result_and_report(fixture_name)
    presentation = build_unified_presentation_v1(result, report)

    assert presentation.scenario("B") is not None
    assert presentation.scenario("C") is None
    assert presentation.accepted_solution_fingerprint is None
    assert presentation.fleet_assignments == ()
    assert presentation.headway_regimes == ()
    assert presentation.outcome.accepted_c_authority is None


def test_alpha_and_beta_characterization(alpha_pair, beta_pair) -> None:
    alpha = build_unified_presentation_v1(*alpha_pair)
    beta = build_unified_presentation_v1(*beta_pair)

    assert alpha.outcome.adjustment_decision == "INSUFFICIENT_DATA"
    assert alpha.outcome.solver_attempted is False
    assert any(
        item.reason_code == "LEGACY_C_WITHOUT_UNIFIED_AUTHORITY" for item in alpha.discrepancies
    )
    assert beta.outcome.solver_attempted is False
    assert beta.outcome.comparison_objective_names is None
    assert any(
        gap.direction == "outbound"
        and gap.start_time_seconds == 17 * 3600
        and gap.end_time_seconds == 18 * 3600
        for gap in beta.demand_gaps
    )


def test_rejected_candidate_codes_are_visible_but_timetable_is_absent() -> None:
    result, report = rejected_result_and_report()
    presentation = build_unified_presentation_v1(result, report)

    assert presentation.scenario("C") is None
    assert presentation.accepted_solution_fingerprint is None
    assert presentation.outcome.validator_rejection_codes == ("SYNTHETIC_DOMAIN_REJECTION",)
    serialized = json.dumps(
        unified_presentation_to_dict(presentation),
        sort_keys=True,
    )
    assert "rejected-diagnostic-candidate" not in serialized
    assert "SYNTHETIC_DOMAIN_REJECTION" in serialized


def test_block_order_and_exact_keys_match_returned_contract_plans(
    accepted_pair,
    accepted_presentation,
) -> None:
    result, _report = accepted_pair
    solution = result.recommended_outcome.solution
    assert solution is not None
    expected_order = sorted(
        result.b_evaluation.b_block_supply,
        key=lambda item: (
            {"outbound": 0, "inbound": 1, "combined": 2}[item.direction.value],
            item.block_start,
            item.block_end,
            item.block_id,
        ),
    )
    expected_keys = [
        (item.block_id, item.direction.value, item.block_start, item.block_end)
        for item in expected_order
    ]
    actual_keys = [
        (
            item.block_id,
            item.direction,
            item.block_start_seconds,
            item.block_end_seconds,
        )
        for item in accepted_presentation.blocks
    ]
    assert actual_keys == expected_keys
    assert len(actual_keys) == len(set(actual_keys))

    b_by_key = {
        (item.block_id, item.direction.value, item.block_start, item.block_end): item
        for item in result.b_evaluation.b_block_supply
    }
    c_by_key = {
        (item.block_id, item.direction.value, item.block_start, item.block_end): item
        for item in solution.c_block_supply_plan
    }
    for block in accepted_presentation.blocks:
        key = (
            block.block_id,
            block.direction,
            block.block_start_seconds,
            block.block_end_seconds,
        )
        assert block.b_trip_count == b_by_key[key].b_trip_count
        assert block.b_load_factor == b_by_key[key].load_factor
        assert block.required_trips_85 == b_by_key[key].required_trips_85
        assert block.required_trips_90 == b_by_key[key].required_trips_90
        assert block.c_actual_trip_count == c_by_key[key].c_actual_trip_count
        assert block.c_load_factor == c_by_key[key].load_factor


def test_different_block_grains_fail_instead_of_merging(accepted_pair) -> None:
    result, report = accepted_pair
    changed = replace(
        result.b_evaluation.b_block_supply[0],
        block_end=result.b_evaluation.b_block_supply[0].block_end - 60,
    )
    changed_evaluation = replace(
        result.b_evaluation,
        b_block_supply=(changed, *result.b_evaluation.b_block_supply[1:]),
    )
    changed_result = replace(result, b_evaluation=changed_evaluation)
    with pytest.raises(UnifiedPresentationConsistencyError, match="B_BLOCK_GRAIN_MISMATCH"):
        build_unified_presentation_v1(changed_result, report)


def test_combined_demand_remains_combined_without_directional_fabrication() -> None:
    result, report = build_result_and_report(combined_demand=True)
    presentation = build_unified_presentation_v1(result, report)

    assert presentation.blocks
    assert {block.direction for block in presentation.blocks} == {"combined"}
    assert presentation.scenario("C") is None


def test_dimensions_preserve_fixed_order_status_issues_and_evidence(
    accepted_pair,
    accepted_presentation,
) -> None:
    result, _report = accepted_pair
    expected_names = (
        "input_validity",
        "parameter_consistency",
        "technical_feasibility",
        "demand_suitability",
        "fleet_feasibility",
        "headway_quality",
    )
    assert tuple(item.dimension_name for item in accepted_presentation.dimensions) == (
        expected_names
    )
    for projected in accepted_presentation.dimensions:
        returned = getattr(result.b_evaluation.evaluation, projected.dimension_name)
        assert projected.status == returned.status.value
        assert projected.confidence == returned.confidence.value
        assert set(projected.issue_codes) == {item.code for item in returned.issues}
        assert set(projected.evidence) == set(returned.evidence)


def test_both_solver_vectors_and_recommendation_are_preserved() -> None:
    result, report = build_result_and_report(solver_choice=SolverChoice.BOTH)
    presentation = build_unified_presentation_v1(result, report)
    comparison = result.comparison
    assert comparison is not None

    assert presentation.outcome.comparison_objective_names == comparison.objective_names
    assert presentation.outcome.heuristic_objective_vector == comparison.heuristic_vector
    assert presentation.outcome.ortools_objective_vector == comparison.ortools_vector
    assert presentation.outcome.recommended_solver == comparison.recommended_solver.value
    assert presentation.outcome.comparison_reason == comparison.reason_code


def test_partial_terminal_capacity_status_and_limitation_are_preserved() -> None:
    result, report = build_result_and_report(terminal_1_occupancy=10)
    presentation = build_unified_presentation_v1(result, report)

    assert presentation.terminal_occupancy_status == "PARTIALLY_EVALUATED"
    assert dict(presentation.terminal_occupancy_terminal_statuses) == {
        "terminal_1": "PASS",
        "terminal_2": "NOT_EVALUATED",
    }
    assert any("NOT_EVALUATED" in code for code in presentation.terminal_occupancy_issue_codes)


def test_builder_has_no_execution_path_dependencies(monkeypatch, accepted_pair) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("presentation builder must not rerun either execution path")

    monkeypatch.setattr(side_by_side, "run_analysis", forbidden)
    monkeypatch.setattr(side_by_side, "analyze_and_optimize_schedule_v1", forbidden)
    presentation = unified_presentation.build_unified_presentation_v1(*accepted_pair)
    assert presentation.presentation_mode == PRESENTATION_MODE_VALIDATION_ONLY

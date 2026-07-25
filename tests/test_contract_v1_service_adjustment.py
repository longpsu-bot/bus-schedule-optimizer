from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from bus_schedule_engine.contracts_v1 import (
    BlockSupplyStatus,
    ContractDirection,
    DemandConfidence,
    DemandObservation,
    DemandResolutionType,
    DemandResponseMode,
    DemandSourceType,
    DepartureTerminal,
    ExactTimetableTrip,
    HeadwayRegularityClassificationV1,
    InputSourceType,
    NormalizedInputBundleV1,
    ObservedDemandInput,
    OperatingDayType,
    RepeatabilityEvidenceV1,
    ScenarioAInput,
    ScenarioBEvaluationPolicyV1,
    ScenarioBInput,
    ServiceAdjustmentDecisionV1,
    ServiceAdjustmentPolicyV1,
    SourceMetadata,
    TerminalDepartureTimes,
    TripsByDirection,
    TurnaroundMinutes,
    VolumeClassification,
    build_schedule_generation_context_v1,
    build_schedule_problem_v1,
    evaluate_scenario_b_v1,
    evaluate_service_adjustment_need_v1,
    observed_demand_fingerprint,
    scenario_fingerprint,
)
from bus_schedule_engine.models import RouteType


def _minutes(value: int) -> int:
    return value * 60


def _directional_rows(
    outbound: tuple[float, float],
    inbound: tuple[float, float],
) -> tuple[tuple[ContractDirection, int, int, float], ...]:
    return (
        (ContractDirection.OUTBOUND, 360, 420, outbound[0]),
        (ContractDirection.OUTBOUND, 420, 480, outbound[1]),
        (ContractDirection.INBOUND, 360, 420, inbound[0]),
        (ContractDirection.INBOUND, 420, 480, inbound[1]),
    )


def _context(
    demand_rows: tuple[tuple[ContractDirection, int, int, float], ...],
    *,
    outbound_times: tuple[int, ...] = (360, 390, 420, 450),
    inbound_times: tuple[int, ...] = (365, 395, 425, 455),
    fleet_limit: int = 4,
    source_imported_at: datetime = datetime(2026, 7, 25, 8, 0, tzinfo=UTC),
    source_notes: str | None = None,
    observation_notes: str | None = None,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
):
    source = SourceMetadata(
        source_type=InputSourceType.API,
        source_id="v1-d1-test",
        imported_at=source_imported_at,
        notes=source_notes,
    )
    trips = tuple(
        [
            ExactTimetableTrip(
                trip_id=f"OUT-{index:02d}",
                direction=ContractDirection.OUTBOUND,
                departure_terminal=DepartureTerminal.TERMINAL_1,
                departure_time=_minutes(departure),
                runtime_minutes=20,
                arrival_time=_minutes(departure + 20),
            )
            for index, departure in enumerate(outbound_times, start=1)
        ]
        + [
            ExactTimetableTrip(
                trip_id=f"IN-{index:02d}",
                direction=ContractDirection.INBOUND,
                departure_terminal=DepartureTerminal.TERMINAL_2,
                departure_time=_minutes(departure),
                runtime_minutes=20,
                arrival_time=_minutes(departure + 20),
            )
            for index, departure in enumerate(inbound_times, start=1)
        ]
    )
    scenario = ScenarioBInput(
        route_id="D1-01",
        route_name="V1-D1 evaluator test",
        route_type=RouteType.INTRA_PROVINCIAL,
        terminal_1_name="Terminal 1",
        terminal_2_name="Terminal 2",
        trip_runtime_minutes=20,
        turnaround_minutes=TurnaroundMinutes(terminal_1=5, terminal_2=5),
        total_daily_trips=len(trips),
        trips_by_direction=TripsByDirection(
            outbound=len(outbound_times),
            inbound=len(inbound_times),
        ),
        first_departures=TerminalDepartureTimes(
            terminal_1=_minutes(outbound_times[0]),
            terminal_2=_minutes(inbound_times[0]),
        ),
        last_departures=TerminalDepartureTimes(
            terminal_1=_minutes(outbound_times[-1]),
            terminal_2=_minutes(inbound_times[-1]),
        ),
        vehicle_capacity=100,
        available_fleet_limit=fleet_limit,
        operating_day_type=OperatingDayType.WEEKDAY,
        exact_timetable=trips,
        source_metadata=source,
    )
    scenario_a = ScenarioAInput(
        route_id=scenario.route_id,
        route_name=scenario.route_name,
        route_type=scenario.route_type,
        terminal_1_name=scenario.terminal_1_name,
        terminal_2_name=scenario.terminal_2_name,
        trip_runtime_minutes=scenario.trip_runtime_minutes,
        turnaround_minutes=scenario.turnaround_minutes,
        total_daily_trips=scenario.total_daily_trips,
        trips_by_direction=scenario.trips_by_direction,
        first_departures=scenario.first_departures,
        last_departures=scenario.last_departures,
        vehicle_capacity=scenario.vehicle_capacity,
        available_fleet_limit=scenario.available_fleet_limit,
        operating_day_type=scenario.operating_day_type,
        exact_timetable=scenario.exact_timetable,
        source_metadata=source,
    )
    demand = None
    if demand_rows:
        observations = tuple(
            DemandObservation(
                observation_id=f"OBS-{index:03d}",
                direction=direction,
                interval_start=_minutes(start),
                interval_end=_minutes(end),
                passenger_count=passengers,
                source_resolution_type=DemandResolutionType.IRREGULAR_INTERVAL,
                source_type=DemandSourceType.APC,
                volume_classification=VolumeClassification.AVERAGE_DAY,
                demand_confidence=DemandConfidence.HIGH,
                sample_count=10,
                notes=observation_notes,
            )
            for index, (direction, start, end, passengers) in enumerate(
                demand_rows,
                start=1,
            )
        )
        demand = ObservedDemandInput(
            demand_dataset_id="D1-DEMAND",
            observation_period_start=date(2026, 7, 1),
            observation_period_end=date(2026, 7, 10),
            observation_days=10,
            observations=observations,
            source_metadata=source,
            demand_response_mode=DemandResponseMode.STATIC,
        )
    bundle = NormalizedInputBundleV1(
        scenario_a=scenario_a,
        scenario_b=scenario,
        observed_demand=demand,
        scenario_a_fingerprint=scenario_fingerprint(scenario_a),
        scenario_b_fingerprint=scenario_fingerprint(scenario),
        observed_demand_fingerprint=(
            observed_demand_fingerprint(demand) if demand is not None else None
        ),
    )
    effective_evaluation_policy = evaluation_policy or ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(bundle, effective_evaluation_policy)
    problem = build_schedule_problem_v1(
        bundle,
        evaluation,
        solver_adapter="legacy_heuristic_v1",
        adapter_context_fingerprint="a" * 64,
        evaluation_policy=effective_evaluation_policy,
        adapter_operating_lock_values={
            "heuristic_turnaround_bridge_mode": "conservative_max_terminal_turnaround",
            "heuristic_turnaround_bridge_value_minutes": 5,
        },
    )
    return build_schedule_generation_context_v1(
        problem,
        bundle,
        evaluation,
        effective_evaluation_policy,
    )


def _repeatability(
    daily_surplus: tuple[int, ...] = (4, 4, 3),
) -> RepeatabilityEvidenceV1:
    return RepeatabilityEvidenceV1(
        valid_observed_day_count=len(daily_surplus),
        configured_minimum_valid_day_count=3,
        surplus_day_count=sum(value > 0 for value in daily_surplus),
        surplus_consistency_rate=(sum(value > 0 for value in daily_surplus) / len(daily_surplus)),
        configured_minimum_surplus_consistency_rate=0.80,
        daily_required_trip_sequence=tuple(8 - value for value in daily_surplus),
        daily_surplus_sequence=daily_surplus,
        representative_day_type_or_provenance="weekday APC sample",
    )


def test_exact_load_factor_and_required_trip_ceilings() -> None:
    policy = ScenarioBEvaluationPolicyV1(
        planning_load_factor_ceiling=0.80,
        critical_load_factor_ceiling=0.90,
    )
    context = _context(
        _directional_rows((161, 170), (170, 170)),
        evaluation_policy=policy,
    )

    result = evaluate_service_adjustment_need_v1(context)
    block = result.block_evidence[0]

    assert block.load_factor == pytest.approx(161 / 200)
    assert block.nominal_capacity == 200
    assert block.required_trips_at_planning_ceiling == 3
    assert block.required_trips_at_critical_ceiling == 2
    assert block.shortage_trips == 1


def test_positive_demand_without_service_remains_visible() -> None:
    rows = (
        (ContractDirection.OUTBOUND, 300, 360, 10),
        (ContractDirection.OUTBOUND, 360, 420, 170),
        (ContractDirection.OUTBOUND, 420, 480, 170),
        (ContractDirection.INBOUND, 300, 360, 0),
        (ContractDirection.INBOUND, 360, 420, 170),
        (ContractDirection.INBOUND, 420, 480, 170),
    )

    result = evaluate_service_adjustment_need_v1(_context(rows))

    assert any(
        item.block_status == BlockSupplyStatus.NO_SERVICE_WITH_DEMAND and item.shortage_trips == 1
        for item in result.block_evidence
    )
    assert result.daily_evidence.no_service_with_demand_block_count == 1
    assert result.primary_decision == ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS


def test_daily_shortage_requires_more_total_trips_and_disallows_heuristic() -> None:
    context = _context(_directional_rows((171, 171), (171, 171)))

    result = evaluate_service_adjustment_need_v1(context)

    assert result.daily_evidence.required_daily_trips == 12
    assert result.daily_evidence.daily_trip_gap == 4
    assert result.primary_decision == ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS
    assert not result.heuristic_authorized
    assert result.authorized_generation_action is None


def test_combined_only_evidence_can_identify_aggregate_total_shortage() -> None:
    rows = (
        (ContractDirection.COMBINED, 360, 420, 341),
        (ContractDirection.COMBINED, 420, 480, 341),
    )

    result = evaluate_service_adjustment_need_v1(_context(rows))

    assert result.daily_evidence.required_daily_trips == 10
    assert result.daily_evidence.daily_trip_gap == 2
    assert result.primary_decision == ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS
    assert "DIRECTIONAL_ACTION_NOT_SUPPORTED_BY_COMBINED_DEMAND" in result.reason_codes
    assert not result.heuristic_authorized


def test_shortage_and_same_direction_eligible_donor_redistributes() -> None:
    context = _context(_directional_rows((171, 85), (170, 170)))

    result = evaluate_service_adjustment_need_v1(context)

    donor = next(
        item
        for item in result.block_evidence
        if item.direction == ContractDirection.OUTBOUND and item.block_start == _minutes(420)
    )
    assert result.daily_evidence.daily_trip_gap == 0
    assert donor.donor_eligible
    assert donor.maximum_eligible_donor_trips == 1
    assert result.primary_decision == ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS
    assert result.heuristic_authorized
    assert result.authorized_generation_action == "fixed_resource_trip_redistribution"


def test_nominal_surplus_without_endpoint_safe_donor_does_not_redistribute() -> None:
    context = _context(
        _directional_rows((86, 0), (85, 85)),
        outbound_times=(360, 420),
        inbound_times=(365, 425),
    )

    result = evaluate_service_adjustment_need_v1(context)

    assert any(item.potential_surplus_trips == 1 for item in result.block_evidence)
    assert not any(item.donor_eligible for item in result.block_evidence)
    assert result.primary_decision != ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS
    assert not result.heuristic_authorized


def test_low_load_without_repeatability_is_review_only() -> None:
    context = _context(_directional_rows((85, 85), (85, 85)))

    result = evaluate_service_adjustment_need_v1(context)

    assert result.daily_evidence.daily_trip_gap == -4
    assert result.primary_decision != ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS
    assert "LOW_LOAD_REVIEW_ONLY" in result.reason_codes
    assert "INSUFFICIENT_DAYS_FOR_REDUCTION_DECISION" in result.reason_codes
    assert not result.heuristic_authorized


def test_sufficient_repeatability_supports_bounded_reduction() -> None:
    context = _context(_directional_rows((85, 85), (85, 85)))

    result = evaluate_service_adjustment_need_v1(
        context,
        repeatability_evidence=_repeatability(),
    )

    assert result.primary_decision == ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS
    assert result.maximum_supported_reduction_quantity == 3
    assert "STABLE_RESIDUAL_TRIP_SURPLUS" in result.reason_codes
    assert not result.heuristic_authorized


def test_insufficient_repeatability_days_cannot_support_reduction() -> None:
    context = _context(_directional_rows((85, 85), (85, 85)))

    result = evaluate_service_adjustment_need_v1(
        context,
        repeatability_evidence=_repeatability((4, 4)),
    )

    assert result.primary_decision != ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS
    assert "INSUFFICIENT_DAYS_FOR_REDUCTION_DECISION" in result.reason_codes
    assert result.maximum_supported_reduction_quantity == 0


def test_shortage_and_critical_evidence_prevent_reduction() -> None:
    context = _context(_directional_rows((181, 85), (170, 170)))

    result = evaluate_service_adjustment_need_v1(
        context,
        repeatability_evidence=_repeatability(),
    )

    assert any(
        item.block_status == BlockSupplyStatus.CRITICAL_ABOVE_90 for item in result.block_evidence
    )
    assert result.primary_decision != ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS
    assert result.maximum_supported_reduction_quantity == 0


def test_allocation_mismatch_is_explanatory_not_an_independent_trigger() -> None:
    context = _context(_directional_rows((90, 170), (90, 170)))

    result = evaluate_service_adjustment_need_v1(context)

    outbound = next(
        item for item in result.allocation_evidence if item.direction == ContractDirection.OUTBOUND
    )
    assert outbound.allocation_mismatch_index == pytest.approx(abs(90 / 260 - 0.5))
    assert result.primary_decision == ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE
    assert "TEMPORAL_TRIP_ALLOCATION_MISMATCH" in result.reason_codes


def test_balanced_22_23_sequence_is_conforming() -> None:
    context = _context(
        _directional_rows((255, 170), (255, 170)),
        outbound_times=(360, 382, 405, 427, 450),
        inbound_times=(365, 387, 410, 432, 455),
    )

    result = evaluate_service_adjustment_need_v1(context)
    outbound = result.headway_evidence[0]

    assert outbound.actual_headway_sequence == (22, 23, 22, 23)
    assert outbound.balanced_target_sequence == (22, 23, 22, 23)
    assert outbound.regular_headway_rate == 1
    assert outbound.regularity_classification == HeadwayRegularityClassificationV1.BALANCED_ROUNDING
    assert result.primary_decision == ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE


def test_irregular_adequate_headways_require_departure_redistribution() -> None:
    context = _context(
        _directional_rows((170, 170), (170, 170)),
        outbound_times=(360, 375, 420, 450),
    )

    result = evaluate_service_adjustment_need_v1(context)

    assert (
        result.headway_evidence[0].regularity_classification
        == HeadwayRegularityClassificationV1.IRREGULAR
    )
    assert result.primary_decision == ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES
    assert result.heuristic_authorized


def test_zero_headway_remains_exact_and_exceptional() -> None:
    context = _context(
        _directional_rows((170, 170), (170, 170)),
        outbound_times=(360, 360, 420, 450),
        fleet_limit=5,
    )

    result = evaluate_service_adjustment_need_v1(context)
    outbound = result.headway_evidence[0]

    assert outbound.actual_headway_sequence[0] == 0
    assert outbound.zero_headway_count == 1
    assert outbound.regularity_classification == HeadwayRegularityClassificationV1.EXCEPTIONAL
    assert "ZERO_HEADWAY_EXCEPTION_PRESENT" in result.reason_codes


def test_technical_infeasibility_precedes_demand_shortage() -> None:
    context = _context(
        _directional_rows((171, 171), (171, 171)),
        fleet_limit=1,
    )

    result = evaluate_service_adjustment_need_v1(context)

    assert result.primary_decision == ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED
    assert result.technical_evidence.fleet_ratio > 1
    assert "FLEET_RATIO_ABOVE_ONE" in result.reason_codes
    assert not result.heuristic_authorized


def test_combined_only_demand_cannot_authorize_directional_redistribution() -> None:
    rows = (
        (ContractDirection.COMBINED, 360, 420, 341),
        (ContractDirection.COMBINED, 420, 480, 255),
    )

    result = evaluate_service_adjustment_need_v1(_context(rows))

    assert result.daily_evidence.daily_trip_gap == 0
    assert result.allocation_evidence == ()
    assert result.primary_decision != ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS
    assert "DIRECTIONAL_ACTION_NOT_SUPPORTED_BY_COMBINED_DEMAND" in result.reason_codes
    assert not result.heuristic_authorized


def test_incomplete_coverage_is_insufficient_but_preserves_local_findings() -> None:
    rows = (
        (ContractDirection.OUTBOUND, 360, 420, 171),
        (ContractDirection.OUTBOUND, 420, 480, 85),
        (ContractDirection.INBOUND, 360, 420, 170),
    )

    result = evaluate_service_adjustment_need_v1(_context(rows))

    assert result.primary_decision == ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA
    assert result.daily_evidence.required_daily_trips is None
    assert result.daily_evidence.total_shortage_trips is None
    assert any(item.shortage_trips > 0 for item in result.block_evidence)
    assert "ADJUSTMENT_DECISION_DATA_INSUFFICIENT" in result.reason_codes


def test_absent_observed_demand_returns_insufficient_without_fabricated_blocks() -> None:
    result = evaluate_service_adjustment_need_v1(_context(()))

    assert result.primary_decision == ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA
    assert result.block_evidence == ()
    assert result.daily_evidence.required_daily_trips is None
    assert result.daily_evidence.total_shortage_trips is None


def test_keep_current_when_all_quantitative_gates_pass() -> None:
    result = evaluate_service_adjustment_need_v1(
        _context(_directional_rows((170, 170), (170, 170)))
    )

    assert result.primary_decision == ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE
    assert result.daily_evidence.daily_trip_gap == 0
    assert all(
        item.regularity_classification == HeadwayRegularityClassificationV1.REGULAR
        for item in result.headway_evidence
    )
    assert not result.heuristic_authorized
    assert result.authorized_generation_action is None


def test_reason_evidence_order_and_fingerprint_are_deterministic() -> None:
    context = _context(_directional_rows((171, 85), (170, 170)))

    first = evaluate_service_adjustment_need_v1(context)
    second = evaluate_service_adjustment_need_v1(context)

    assert first == second
    assert first.reason_codes == second.reason_codes
    assert first.evidence == second.evidence
    assert [item.direction for item in first.block_evidence] == [
        ContractDirection.OUTBOUND,
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
        ContractDirection.INBOUND,
    ]


def test_decision_relevant_demand_changes_evaluator_fingerprint() -> None:
    first = evaluate_service_adjustment_need_v1(_context(_directional_rows((170, 170), (170, 170))))
    second = evaluate_service_adjustment_need_v1(
        _context(_directional_rows((169, 170), (170, 170)))
    )

    assert first.primary_decision == second.primary_decision
    assert first.evaluator_fingerprint != second.evaluator_fingerprint


def test_repeatability_change_changes_evaluator_fingerprint() -> None:
    context = _context(_directional_rows((85, 85), (85, 85)))
    first = evaluate_service_adjustment_need_v1(
        context,
        repeatability_evidence=_repeatability((4, 4, 3)),
    )
    second = evaluate_service_adjustment_need_v1(
        context,
        repeatability_evidence=_repeatability((4, 3, 3)),
    )

    assert first.primary_decision == second.primary_decision
    assert first.evaluator_fingerprint != second.evaluator_fingerprint


def test_import_time_and_unrelated_source_notes_do_not_change_fingerprint() -> None:
    rows = _directional_rows((170, 170), (170, 170))
    first_context = _context(rows)
    second_context = _context(
        rows,
        source_imported_at=datetime(2026, 7, 25, 8, 0, tzinfo=UTC) + timedelta(days=3),
        source_notes="unrelated source note",
    )

    first = evaluate_service_adjustment_need_v1(first_context)
    second = evaluate_service_adjustment_need_v1(second_context)

    assert first.evaluator_fingerprint == second.evaluator_fingerprint


def test_policy_change_changes_policy_and_evaluator_fingerprints() -> None:
    context = _context(_directional_rows((170, 170), (170, 170)))
    first = evaluate_service_adjustment_need_v1(context)
    second = evaluate_service_adjustment_need_v1(
        context,
        ServiceAdjustmentPolicyV1(headway_rounding_tolerance_minutes=2),
    )

    assert first.adjustment_policy_fingerprint != second.adjustment_policy_fingerprint
    assert first.evaluator_fingerprint != second.evaluator_fingerprint


def test_context_and_scenario_b_are_not_mutated() -> None:
    context = _context(_directional_rows((171, 85), (170, 170)))
    before = deepcopy(context)

    evaluate_service_adjustment_need_v1(context)

    assert context == before
    assert context.normalized_inputs.scenario_b == before.normalized_inputs.scenario_b
    assert context.problem == before.problem


def test_repeatability_evidence_validates_derived_counts_and_rate() -> None:
    with pytest.raises(ValueError, match="surplus_day_count"):
        replace(_repeatability(), surplus_day_count=2)

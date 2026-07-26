from __future__ import annotations

import ast
import inspect
from copy import deepcopy
from dataclasses import fields, replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bus_schedule_engine.contracts_v1 import (
    AdjustmentCapabilityRoutingPolicyV1,
    AdjustmentCapabilityRoutingV1,
    AdjustmentCapabilityV1,
    BoundaryConvention,
    ContractDirection,
    ContractValidationError,
    DemandConfidence,
    DemandObservation,
    DemandResolutionType,
    DemandResponseMode,
    DemandSourceType,
    DepartureTerminal,
    DirectionTripLockMode,
    ExactTimetableTrip,
    FixedResourceAuthorizationProfileV1,
    FleetConstraintMode,
    InitialFleetPositioningMode,
    InputSourceType,
    NormalizedInputBundleV1,
    ObservedDemandInput,
    OperatingDayType,
    RepeatabilityDayEvidenceV1,
    RepeatabilityEvidenceV1,
    ScenarioAInput,
    ScenarioBEvaluationPolicyV1,
    ScenarioBInput,
    ServiceAdjustmentDecisionPolicyV1,
    ServiceAdjustmentDecisionV1,
    ServiceAdjustmentPolicyV1,
    SourceMetadata,
    TerminalDepartureTimes,
    TripsByDirection,
    TurnaroundMinutes,
    VolumeClassification,
    build_adjustment_capability_routing_policy_v1,
    build_current_fixed_resource_authorization_profile_v1,
    build_service_adjustment_evaluation_context_v1,
    evaluate_scenario_b_v1,
    evaluate_service_adjustment_need_v1,
    observed_demand_fingerprint,
    project_service_adjustment_decision_policy_v1,
    route_adjustment_capability_v1,
    scenario_fingerprint,
)
from bus_schedule_engine.contracts_v1.adjustment_routing import (
    ADJUSTMENT_CAPABILITY_NOT_AUTHORIZED_INSUFFICIENT_DATA,
    CURRENT_SOLVER_CAN_IMPLEMENT,
    CURRENT_SOLVER_CAPABILITY_INSUFFICIENT,
    FIXED_RESOURCE_DEPARTURE_RESPACE_ACTION,
    FIXED_RESOURCE_TRIP_REDISTRIBUTION_ACTION,
    NO_GENERATION_REQUIRED,
    TECHNICAL_PARAMETER_CHANGE_REQUIRED,
    VARIABLE_TRIP_INCREASE_CAPABILITY_REQUIRED,
    VARIABLE_TRIP_REDUCTION_CAPABILITY_REQUIRED,
    FixedResourceCapabilityBindingV1,
    LegacyServiceAdjustmentAssessmentProjectionV1,
    build_legacy_service_adjustment_assessment_projection_v1,
    calculate_adjustment_capability_routing_fingerprint_v1,
    calculate_adjustment_capability_routing_policy_fingerprint_v1,
    calculate_fixed_resource_authorization_profile_fingerprint_v1,
    calculate_legacy_service_adjustment_assessment_projection_fingerprint_v1,
    derive_adjustment_capability_routing_id_v1,
    project_adjustment_capability_routing_policy_v1,
    validate_adjustment_capability_routing_policy_v1,
    validate_adjustment_capability_routing_v1,
    validate_fixed_resource_authorization_profile_v1,
    validate_legacy_service_adjustment_assessment_projection_v1,
)
from bus_schedule_engine.contracts_v1.service_adjustment import (
    HeadwayRegularityClassificationV1,
    calculate_service_adjustment_assessment_fingerprint_v1,
    validate_service_adjustment_assessment_v1,
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


def _repeatability() -> RepeatabilityEvidenceV1:
    return RepeatabilityEvidenceV1(
        days=tuple(
            RepeatabilityDayEvidenceV1(
                day_reference=f"2026-07-{index:02d}",
                fully_supported=True,
                current_daily_trips=8,
                required_daily_trips=8 - surplus,
                shortage_block_count=0,
                no_service_with_demand_block_count=0,
                critical_block_count=0,
                authoritative_evidence_fingerprint=f"day-{index}",
            )
            for index, surplus in enumerate((4, 4, 3), 1)
        ),
        configured_minimum_valid_day_count=3,
        configured_minimum_surplus_consistency_rate=0.80,
        representative_day_type_or_provenance="weekday APC sample",
    )


def _context(
    demand_rows: tuple[tuple[ContractDirection, int, int, float], ...],
    *,
    outbound_times: tuple[int, ...] = (360, 390, 420, 450),
    inbound_times: tuple[int, ...] = (365, 395, 425, 455),
    fleet_limit: int = 4,
    repeatability: RepeatabilityEvidenceV1 | None = None,
):
    source = SourceMetadata(
        source_type=InputSourceType.API,
        source_id="v1-d2b-test",
        imported_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
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
            for index, departure in enumerate(outbound_times, 1)
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
            for index, departure in enumerate(inbound_times, 1)
        ]
    )
    scenario = ScenarioBInput(
        route_id="D2B-01",
        route_name="V1-D2B routing test",
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
        demand = ObservedDemandInput(
            demand_dataset_id="D2B-DEMAND",
            observation_period_start=date(2026, 7, 1),
            observation_period_end=date(2026, 7, 10),
            observation_days=10,
            observations=tuple(
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
                )
                for index, (direction, start, end, passengers) in enumerate(demand_rows, 1)
            ),
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
    evaluation_policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(bundle, evaluation_policy)
    decision_policy = ServiceAdjustmentDecisionPolicyV1(
        planning_load_factor_ceiling=(evaluation_policy.planning_load_factor_ceiling),
        critical_load_factor_ceiling=(evaluation_policy.critical_load_factor_ceiling),
        low_load_review_threshold=evaluation_policy.low_load_review_threshold,
        minimum_authoritative_demand_confidence=(
            evaluation_policy.minimum_authoritative_demand_confidence
        ),
    )
    return build_service_adjustment_evaluation_context_v1(
        bundle,
        evaluation_policy,
        decision_policy,
        repeatability,
        evaluation,
    )


def _assessment_for(
    decision: ServiceAdjustmentDecisionV1,
):
    if decision == ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA:
        context = _context(())
    elif decision == ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED:
        context = _context(
            _directional_rows((170, 170), (170, 170)),
            fleet_limit=1,
        )
    elif decision == ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS:
        context = _context(_directional_rows((171, 171), (171, 171)))
    elif decision == ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS:
        context = _context(_directional_rows((171, 85), (170, 170)))
    elif decision == ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS:
        context = _context(
            _directional_rows((85, 85), (85, 85)),
            repeatability=_repeatability(),
        )
    elif decision == ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES:
        context = _context(
            _directional_rows((170, 170), (170, 170)),
            outbound_times=(360, 375, 420, 450),
        )
    else:
        context = _context(_directional_rows((170, 170), (170, 170)))
    assessment = evaluate_service_adjustment_need_v1(context)
    assert assessment.primary_decision == decision
    return context, assessment


def _refingerprint_assessment(assessment, **changes):
    changed = replace(assessment, **changes)
    fingerprint = calculate_service_adjustment_assessment_fingerprint_v1(changed)
    return replace(
        changed,
        evaluator_fingerprint=fingerprint,
        assessment_id=f"ADJUSTMENT-{fingerprint[:16].upper()}",
    )


def _authorized_route(
    decision: ServiceAdjustmentDecisionV1 = (ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS),
):
    context, assessment = _assessment_for(decision)
    policy = build_adjustment_capability_routing_policy_v1()
    route = route_adjustment_capability_v1(assessment, context, policy)
    return context, assessment, policy, route


@pytest.mark.parametrize(
    ("decision", "capability"),
    (
        (
            ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA,
            AdjustmentCapabilityV1.NOT_AUTHORIZED_INSUFFICIENT_DATA,
        ),
        (
            ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED,
            AdjustmentCapabilityV1.TECHNICAL_PARAMETER_CHANGE_REQUIRED,
        ),
        (
            ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS,
            AdjustmentCapabilityV1.VARIABLE_TRIP_INCREASE_REQUIRED,
        ),
        (
            ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
            AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION,
        ),
        (
            ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS,
            AdjustmentCapabilityV1.VARIABLE_TRIP_REDUCTION_REQUIRED,
        ),
        (
            ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES,
            AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE,
        ),
        (
            ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
            AdjustmentCapabilityV1.NO_GENERATION_REQUIRED,
        ),
    ),
)
def test_all_decisions_map_deterministically_without_changing_decision(
    decision,
    capability,
) -> None:
    context, assessment = _assessment_for(decision)
    policy = build_adjustment_capability_routing_policy_v1()

    first = route_adjustment_capability_v1(assessment, context, policy)
    second = route_adjustment_capability_v1(assessment, context, policy)

    assert first == second
    assert first.primary_decision == assessment.primary_decision == decision
    assert first.routed_capability == capability
    assert first.routing_fingerprint == second.routing_fingerprint
    assert first.routing_id == derive_adjustment_capability_routing_id_v1(first.routing_fingerprint)


@pytest.mark.parametrize(
    ("decision", "reason"),
    (
        (
            ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA,
            ADJUSTMENT_CAPABILITY_NOT_AUTHORIZED_INSUFFICIENT_DATA,
        ),
        (
            ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED,
            TECHNICAL_PARAMETER_CHANGE_REQUIRED,
        ),
        (
            ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS,
            VARIABLE_TRIP_INCREASE_CAPABILITY_REQUIRED,
        ),
        (
            ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS,
            VARIABLE_TRIP_REDUCTION_CAPABILITY_REQUIRED,
        ),
        (
            ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
            NO_GENERATION_REQUIRED,
        ),
    ),
)
def test_non_fixed_routes_have_no_profile_action_adapter_or_authorization(
    decision,
    reason,
) -> None:
    context, assessment = _assessment_for(decision)
    route = route_adjustment_capability_v1(
        assessment,
        context,
        build_adjustment_capability_routing_policy_v1(),
    )

    assert route.required_fixed_resource_profile is None
    assert route.authorized_generation_action is None
    assert route.solver_adapter_id is None
    assert not route.problem_construction_authorized
    assert not route.solver_invocation_authorized
    assert route.reason_codes == (reason,)


@pytest.mark.parametrize(
    ("decision", "action"),
    (
        (
            ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
            FIXED_RESOURCE_TRIP_REDISTRIBUTION_ACTION,
        ),
        (
            ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES,
            FIXED_RESOURCE_DEPARTURE_RESPACE_ACTION,
        ),
    ),
)
def test_fixed_resource_routes_use_exact_profile_and_action(
    decision,
    action,
) -> None:
    context, assessment = _assessment_for(decision)
    route = route_adjustment_capability_v1(
        assessment,
        context,
        build_adjustment_capability_routing_policy_v1(),
    )

    assert (
        route.required_fixed_resource_profile
        == build_current_fixed_resource_authorization_profile_v1()
    )
    assert route.authorized_generation_action == action
    assert route.solver_adapter_id == "legacy_heuristic_v1"
    assert route.problem_construction_authorized
    assert route.solver_invocation_authorized
    assert route.reason_codes == (CURRENT_SOLVER_CAN_IMPLEMENT,)


def test_current_profile_uses_exact_h4_modes_and_all_required_locks() -> None:
    profile = build_current_fixed_resource_authorization_profile_v1()

    assert profile.direction_trip_lock_mode == (DirectionTripLockMode.FIXED_BY_DIRECTION)
    assert profile.fleet_constraint_mode == FleetConstraintMode.AVAILABLE_UPPER_BOUND
    assert profile.initial_fleet_positioning_mode == (InitialFleetPositioningMode.SOLVER_DETERMINED)
    assert profile.boundary_convention == BoundaryConvention.HALF_OPEN
    assert all(
        getattr(profile, field.name) is True
        for field in fields(FixedResourceAuthorizationProfileV1)
        if field.type == "bool"
    )
    assert validate_fixed_resource_authorization_profile_v1(profile).passed


@pytest.mark.parametrize(
    "field_name",
    (
        "total_daily_trip_count_locked",
        "directional_trip_counts_locked",
        "first_departures_locked",
        "last_departures_locked",
        "source_trip_runtime_locked",
        "arrival_terminal_turnaround_locked",
        "vehicle_capacity_locked",
        "available_fleet_limit_locked",
        "operating_window_locked",
        "minimum_service_locked",
        "terminal_stock_must_remain_non_negative",
    ),
)
def test_every_profile_boolean_binds_identity_and_cannot_be_weakened(
    field_name,
) -> None:
    profile = build_current_fixed_resource_authorization_profile_v1()
    weakened = replace(profile, **{field_name: False})

    assert (
        calculate_fixed_resource_authorization_profile_fingerprint_v1(weakened)
        != profile.profile_fingerprint
    )
    validation = validate_fixed_resource_authorization_profile_v1(weakened)
    assert not validation.passed
    assert {
        "FIXED_RESOURCE_PROFILE_REQUIRED_LOCK_WEAKENED",
        "FIXED_RESOURCE_PROFILE_FINGERPRINT_MISMATCH",
    }.issubset(set(validation.error_codes))


@pytest.mark.parametrize(
    ("field_name", "changed_mode"),
    (
        ("direction_trip_lock_mode", DirectionTripLockMode.TOTAL_ONLY),
        ("fleet_constraint_mode", FleetConstraintMode.EXACT_SCHEDULED_FLEET),
        ("initial_fleet_positioning_mode", InitialFleetPositioningMode.FIXED),
        (
            "boundary_convention",
            BoundaryConvention.HALF_OPEN_WITH_FINAL_SENTINEL,
        ),
    ),
)
def test_every_profile_mode_binds_identity_and_unsupported_modes_fail(
    field_name,
    changed_mode,
) -> None:
    profile = build_current_fixed_resource_authorization_profile_v1()
    changed = replace(profile, **{field_name: changed_mode})

    assert (
        calculate_fixed_resource_authorization_profile_fingerprint_v1(changed)
        != profile.profile_fingerprint
    )
    assert not validate_fixed_resource_authorization_profile_v1(changed).passed


@pytest.mark.parametrize("invalid", ("fixed_by_direction", {"locked": True}))
def test_free_form_profile_replacements_are_rejected(invalid) -> None:
    assert not validate_fixed_resource_authorization_profile_v1(invalid).passed


def test_manual_profile_fingerprint_tampering_is_rejected() -> None:
    profile = build_current_fixed_resource_authorization_profile_v1()
    assert not validate_fixed_resource_authorization_profile_v1(
        replace(profile, profile_fingerprint="0" * 64)
    ).passed


def test_policy_bindings_are_frozen_ordered_and_duplicate_free() -> None:
    policy = build_adjustment_capability_routing_policy_v1(
        (
            AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE,
            AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION,
        )
    )

    assert isinstance(policy.fixed_resource_bindings, tuple)
    assert tuple(binding.capability for binding in policy.fixed_resource_bindings) == (
        AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION,
        AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE,
    )
    with pytest.raises(AttributeError):
        policy.routing_policy_fingerprint = "changed"

    duplicate = replace(
        policy,
        fixed_resource_bindings=(
            policy.fixed_resource_bindings[0],
            policy.fixed_resource_bindings[0],
        ),
    )
    duplicate = replace(
        duplicate,
        routing_policy_fingerprint=(
            calculate_adjustment_capability_routing_policy_fingerprint_v1(duplicate)
        ),
    )
    assert not validate_adjustment_capability_routing_policy_v1(duplicate).passed


def test_capability_action_mismatch_is_rejected_even_when_refingerprinted() -> None:
    policy = build_adjustment_capability_routing_policy_v1()
    changed_binding = replace(
        policy.fixed_resource_bindings[0],
        generation_action=FIXED_RESOURCE_DEPARTURE_RESPACE_ACTION,
    )
    changed = replace(
        policy,
        fixed_resource_bindings=(
            changed_binding,
            policy.fixed_resource_bindings[1],
        ),
        routing_policy_fingerprint="",
    )
    changed = replace(
        changed,
        routing_policy_fingerprint=(
            calculate_adjustment_capability_routing_policy_fingerprint_v1(changed)
        ),
    )

    validation = validate_adjustment_capability_routing_policy_v1(changed)
    assert "ROUTING_POLICY_CAPABILITY_ACTION_MISMATCH" in validation.error_codes


@pytest.mark.parametrize(
    "decision",
    (
        ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA,
        ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED,
        ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS,
        ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS,
        ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
    ),
)
def test_legacy_projector_rejects_non_fixed_authorized_decisions(
    decision,
) -> None:
    legacy = ServiceAdjustmentPolicyV1(fixed_resource_authorized_decisions=(decision,))

    with pytest.raises(ContractValidationError) as error:
        project_adjustment_capability_routing_policy_v1(
            legacy,
            ("legacy_heuristic_v1",),
        )
    assert "LEGACY_ROUTING_AUTHORIZED_DECISION_UNSUPPORTED" in {
        issue.code for issue in error.value.issues
    }


@pytest.mark.parametrize(
    "available_ids",
    (
        ("legacy_heuristic_v1", "legacy_heuristic_v1"),
        ("z-adapter", "a-adapter"),
        ("",),
    ),
)
def test_legacy_projector_rejects_invalid_available_adapter_ids(
    available_ids,
) -> None:
    with pytest.raises(ContractValidationError):
        project_adjustment_capability_routing_policy_v1(
            ServiceAdjustmentPolicyV1(),
            available_ids,
        )


def test_adapter_id_and_availability_change_policy_and_route_not_assessment() -> None:
    context, assessment = _assessment_for(ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS)
    baseline_policy = project_adjustment_capability_routing_policy_v1(
        ServiceAdjustmentPolicyV1(),
        ("legacy_heuristic_v1",),
    )
    other_policy = project_adjustment_capability_routing_policy_v1(
        replace(
            ServiceAdjustmentPolicyV1(),
            fixed_resource_solver_adapter="other_adapter",
        ),
        ("other_adapter",),
    )
    unavailable_policy = project_adjustment_capability_routing_policy_v1(
        ServiceAdjustmentPolicyV1(),
        (),
    )

    baseline = route_adjustment_capability_v1(assessment, context, baseline_policy)
    other = route_adjustment_capability_v1(assessment, context, other_policy)
    unavailable = route_adjustment_capability_v1(assessment, context, unavailable_policy)

    assert (
        len(
            {
                baseline_policy.routing_policy_fingerprint,
                other_policy.routing_policy_fingerprint,
                unavailable_policy.routing_policy_fingerprint,
            }
        )
        == 3
    )
    assert (
        len(
            {
                baseline.routing_fingerprint,
                other.routing_fingerprint,
                unavailable.routing_fingerprint,
            }
        )
        == 3
    )
    assert (
        baseline.source_assessment_fingerprint
        == (other.source_assessment_fingerprint)
        == unavailable.source_assessment_fingerprint
        == assessment.evaluator_fingerprint
    )


def test_legacy_routing_changes_leave_phase_a_identity_untouched() -> None:
    context, assessment = _assessment_for(ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS)
    first_legacy = ServiceAdjustmentPolicyV1()
    second_legacy = replace(
        first_legacy,
        fixed_resource_solver_adapter="other_adapter",
        fixed_resource_authorized_decisions=(ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,),
    )

    assert project_service_adjustment_decision_policy_v1(
        first_legacy
    ) == project_service_adjustment_decision_policy_v1(second_legacy)
    first_policy = project_adjustment_capability_routing_policy_v1(
        first_legacy,
        ("legacy_heuristic_v1",),
    )
    second_policy = project_adjustment_capability_routing_policy_v1(
        second_legacy,
        ("other_adapter",),
    )
    first_route = route_adjustment_capability_v1(assessment, context, first_policy)
    second_route = route_adjustment_capability_v1(assessment, context, second_policy)

    assert first_route.primary_decision == second_route.primary_decision
    assert first_route.source_assessment_fingerprint == (second_route.source_assessment_fingerprint)
    assert first_policy.routing_policy_fingerprint != (second_policy.routing_policy_fingerprint)


def test_changed_supported_profile_changes_policy_payload_and_fails_closed() -> None:
    policy = build_adjustment_capability_routing_policy_v1()
    profile = policy.fixed_resource_bindings[0].supported_fixed_resource_profile
    weakened = replace(profile, minimum_service_locked=False)
    changed_binding = replace(
        policy.fixed_resource_bindings[0],
        supported_fixed_resource_profile=weakened,
    )
    changed = replace(
        policy,
        fixed_resource_bindings=(
            changed_binding,
            policy.fixed_resource_bindings[1],
        ),
    )

    assert (
        calculate_adjustment_capability_routing_policy_fingerprint_v1(changed)
        != policy.routing_policy_fingerprint
    )
    assert not validate_adjustment_capability_routing_policy_v1(changed).passed


@pytest.mark.parametrize(
    "mutation",
    ("incomplete", "insufficient", "missing"),
)
def test_trip_redistribution_requires_complete_joint_donor_proof(
    mutation,
) -> None:
    context, assessment = _assessment_for(ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS)
    proof = next(
        item
        for item in assessment.joint_donor_evidence
        if item.direction == ContractDirection.OUTBOUND
    )
    if mutation == "incomplete":
        changed_proof = replace(proof, search_complete=False)
        proofs = tuple(
            changed_proof if item is proof else item for item in assessment.joint_donor_evidence
        )
    elif mutation == "insufficient":
        changed_proof = replace(
            proof,
            proven_joint_capacity=0,
            selected_jointly_feasible_trip_ids=(),
        )
        proofs = tuple(
            changed_proof if item is proof else item for item in assessment.joint_donor_evidence
        )
    else:
        proofs = tuple(
            item
            for item in assessment.joint_donor_evidence
            if item.direction != ContractDirection.OUTBOUND
        )
    tampered = _refingerprint_assessment(
        assessment,
        joint_donor_evidence=proofs,
    )

    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(
            tampered,
            context,
            build_adjustment_capability_routing_policy_v1(),
        )


def test_combined_only_demand_cannot_authorize_trip_redistribution() -> None:
    context = _context(
        (
            (ContractDirection.COMBINED, 360, 420, 341),
            (ContractDirection.COMBINED, 420, 480, 255),
        )
    )
    assessment = evaluate_service_adjustment_need_v1(context)
    tampered = _refingerprint_assessment(
        assessment,
        primary_decision=ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )

    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(
            tampered,
            context,
            build_adjustment_capability_routing_policy_v1(),
        )


def test_technical_infeasibility_blocks_refingerprinted_fixed_route() -> None:
    context, assessment = _assessment_for(ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS)
    tampered = _refingerprint_assessment(
        assessment,
        technical_evidence=replace(
            assessment.technical_evidence,
            technically_feasible=False,
        ),
    )

    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(
            tampered,
            context,
            build_adjustment_capability_routing_policy_v1(),
        )


@pytest.mark.parametrize("mutation", ("missing", "failed", "impossible"))
def test_departure_respace_requires_complete_passing_diagnostics(
    mutation,
) -> None:
    context, assessment = _assessment_for(ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES)
    irregular = next(
        item
        for item in assessment.headway_evidence
        if item.regularity_classification
        in {
            HeadwayRegularityClassificationV1.IRREGULAR,
            HeadwayRegularityClassificationV1.EXCEPTIONAL,
        }
    )
    if mutation == "missing":
        changed = replace(irregular, respace_diagnostic=None)
    elif mutation == "failed":
        assert irregular.respace_diagnostic is not None
        changed = replace(
            irregular,
            respace_diagnostic=replace(
                irregular.respace_diagnostic,
                passed=False,
            ),
        )
    else:
        changed = replace(irregular, respace_technically_possible=False)
    tampered = _refingerprint_assessment(
        assessment,
        headway_evidence=tuple(
            changed if item is irregular else item for item in assessment.headway_evidence
        ),
    )

    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(
            tampered,
            context,
            build_adjustment_capability_routing_policy_v1(),
        )


def test_combined_only_demand_cannot_authorize_departure_respace() -> None:
    context = _context(
        (
            (ContractDirection.COMBINED, 360, 420, 340),
            (ContractDirection.COMBINED, 420, 480, 340),
        ),
        outbound_times=(360, 375, 420, 450),
    )
    assessment = evaluate_service_adjustment_need_v1(context)
    tampered = _refingerprint_assessment(
        assessment,
        primary_decision=(ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES),
    )

    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(
            tampered,
            context,
            build_adjustment_capability_routing_policy_v1(),
        )


@pytest.mark.parametrize(
    "decision",
    (
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES,
    ),
)
def test_unavailable_fixed_resource_route_retains_capability_and_profile(
    decision,
) -> None:
    context, assessment = _assessment_for(decision)
    policy = build_adjustment_capability_routing_policy_v1(available_adapter_ids=())

    route = route_adjustment_capability_v1(assessment, context, policy)

    assert route.routed_capability in {
        AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION,
        AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE,
    }
    assert route.required_fixed_resource_profile is not None
    assert route.authorized_generation_action is None
    assert route.solver_adapter_id is None
    assert not route.problem_construction_authorized
    assert not route.solver_invocation_authorized
    assert route.reason_codes == (CURRENT_SOLVER_CAPABILITY_INSUFFICIENT,)
    assert route.primary_decision == assessment.primary_decision


def test_stale_assessment_context_and_changed_assessment_fingerprint_reject() -> None:
    context, assessment = _assessment_for(ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS)
    other_context, _ = _assessment_for(ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE)
    policy = build_adjustment_capability_routing_policy_v1()

    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(assessment, other_context, policy)
    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(
            replace(assessment, evaluator_fingerprint="0" * 64),
            context,
            policy,
        )


def test_router_rejects_noncanonical_decision_type_as_validation_error() -> None:
    context, assessment = _assessment_for(ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE)

    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(
            replace(assessment, primary_decision="KEEP_CURRENT_TIMETABLE"),
            context,
            build_adjustment_capability_routing_policy_v1(),
        )


def test_changed_policy_rejects_old_route_even_if_assessment_is_unchanged() -> None:
    context, assessment, policy, route = _authorized_route()
    changed_policy = build_adjustment_capability_routing_policy_v1(
        solver_adapter_id="other_adapter",
        available_adapter_ids=("other_adapter",),
    )

    validation = validate_adjustment_capability_routing_v1(
        route,
        context,
        assessment,
        changed_policy,
    )

    assert not validation.passed
    assert "ADJUSTMENT_ROUTING_POLICY_MISMATCH" in validation.error_codes
    assert assessment.evaluator_fingerprint == route.source_assessment_fingerprint
    assert policy.routing_policy_fingerprint == route.routing_policy_fingerprint


@pytest.mark.parametrize(
    "changes",
    (
        {"problem_construction_authorized": False},
        {"solver_invocation_authorized": False},
        {"authorized_generation_action": "changed"},
        {"solver_adapter_id": "changed"},
    ),
)
def test_route_field_replacement_under_old_fingerprint_is_rejected(
    changes,
) -> None:
    context, assessment, policy, route = _authorized_route()

    validation = validate_adjustment_capability_routing_v1(
        replace(route, **changes),
        context,
        assessment,
        policy,
    )

    assert not validation.passed
    assert "ADJUSTMENT_ROUTING_FINGERPRINT_MISMATCH" in validation.error_codes


def test_changed_profile_under_old_route_fingerprint_is_rejected() -> None:
    context, assessment, policy, route = _authorized_route()
    assert route.required_fixed_resource_profile is not None
    changed_profile = replace(
        route.required_fixed_resource_profile,
        minimum_service_locked=False,
    )

    validation = validate_adjustment_capability_routing_v1(
        replace(route, required_fixed_resource_profile=changed_profile),
        context,
        assessment,
        policy,
    )

    assert not validation.passed
    assert "ADJUSTMENT_ROUTING_FINGERPRINT_MISMATCH" in validation.error_codes


def test_route_manual_fingerprint_and_id_tampering_is_rejected() -> None:
    context, assessment, policy, route = _authorized_route()

    for changed in (
        replace(route, routing_fingerprint="0" * 64),
        replace(route, routing_id="ROUTING-INVALID"),
    ):
        assert not validate_adjustment_capability_routing_v1(
            changed,
            context,
            assessment,
            policy,
        ).passed


def test_authorized_legacy_projection_is_deterministic_and_separate() -> None:
    context, assessment, _, route = _authorized_route()

    first = build_legacy_service_adjustment_assessment_projection_v1(
        assessment,
        context,
        route,
    )
    second = build_legacy_service_adjustment_assessment_projection_v1(
        assessment,
        context,
        route,
    )

    assert first == second
    assert type(first) is LegacyServiceAdjustmentAssessmentProjectionV1
    assert first.canonical_assessment is assessment
    assert first.canonical_assessment_fingerprint == (assessment.evaluator_fingerprint)
    assert first.source_routing_fingerprint == route.routing_fingerprint
    assert first.legacy_source_problem_fingerprint is None
    assert first.legacy_heuristic_authorized
    assert first.legacy_authorized_generation_action == (route.authorized_generation_action)
    assert first.projection_fingerprint != assessment.evaluator_fingerprint


@pytest.mark.parametrize(
    "decision",
    (
        ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    ),
)
def test_non_authorized_routes_project_false_and_no_action(decision) -> None:
    context, assessment = _assessment_for(decision)
    policy = build_adjustment_capability_routing_policy_v1(available_adapter_ids=())
    route = route_adjustment_capability_v1(assessment, context, policy)

    projection = build_legacy_service_adjustment_assessment_projection_v1(
        assessment,
        context,
        route,
    )

    assert not projection.legacy_heuristic_authorized
    assert projection.legacy_authorized_generation_action is None


@pytest.mark.parametrize(
    "changes",
    (
        {"legacy_source_problem_fingerprint": "a" * 64},
        {"legacy_heuristic_authorized": False},
        {"legacy_authorized_generation_action": None},
        {"source_routing_fingerprint": "b" * 64},
    ),
)
def test_projection_tampering_changes_only_projection_identity_and_rejects(
    changes,
) -> None:
    context, assessment, _, route = _authorized_route()
    projection = build_legacy_service_adjustment_assessment_projection_v1(
        assessment,
        context,
        route,
    )
    changed = replace(projection, **changes)

    assert (
        calculate_legacy_service_adjustment_assessment_projection_fingerprint_v1(changed)
        != projection.projection_fingerprint
    )
    assert assessment.evaluator_fingerprint == (projection.canonical_assessment_fingerprint)
    assert not validate_legacy_service_adjustment_assessment_projection_v1(
        changed,
        assessment,
        context,
        route,
    ).passed


def test_projection_cannot_replace_canonical_assessment_in_router_or_validator() -> None:
    context, assessment, policy, route = _authorized_route()
    projection = build_legacy_service_adjustment_assessment_projection_v1(
        assessment,
        context,
        route,
    )

    assert not validate_service_adjustment_assessment_v1(
        projection,
        context,
    ).passed
    with pytest.raises(ContractValidationError):
        route_adjustment_capability_v1(projection, context, policy)


def test_routing_and_projection_do_not_mutate_any_input() -> None:
    context, assessment = _assessment_for(ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS)
    policy = build_adjustment_capability_routing_policy_v1()
    profile = policy.fixed_resource_bindings[0].supported_fixed_resource_profile
    before = deepcopy((context, assessment, policy, profile))

    route = route_adjustment_capability_v1(assessment, context, policy)
    projection = build_legacy_service_adjustment_assessment_projection_v1(
        assessment,
        context,
        route,
    )

    assert (context, assessment, policy, profile) == before
    assert route.source_assessment_fingerprint == assessment.evaluator_fingerprint
    assert projection.canonical_assessment is assessment


def test_routing_module_has_no_problem_generation_or_solver_dependency() -> None:
    import bus_schedule_engine.contracts_v1.adjustment_routing as routing_module

    source = Path(inspect.getsourcefile(routing_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    prohibited = {
        "ScheduleProblemV1",
        "ScheduleGenerationContextV1",
        "build_schedule_problem_v1",
        "build_schedule_generation_context_v1",
        "build_heuristic_compatibility_context_v1",
        "build_heuristic_schedule_request_v1",
        "run_schedule_solver_v1",
        "ScheduleSolver",
    }

    assert not prohibited.intersection(imported_names)
    assert "ScheduleSolver.solve" not in source
    assert "candidate" not in {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }


def test_canonical_public_exports_exclude_transitional_projection() -> None:
    import bus_schedule_engine.contracts_v1 as contracts_v1

    assert contracts_v1.AdjustmentCapabilityV1 is AdjustmentCapabilityV1
    assert contracts_v1.AdjustmentCapabilityRoutingV1 is (AdjustmentCapabilityRoutingV1)
    assert contracts_v1.AdjustmentCapabilityRoutingPolicyV1 is (AdjustmentCapabilityRoutingPolicyV1)
    assert not hasattr(
        contracts_v1,
        "LegacyServiceAdjustmentAssessmentProjectionV1",
    )
    assert not hasattr(
        contracts_v1,
        "project_adjustment_capability_routing_policy_v1",
    )


def test_policy_and_route_types_are_frozen_and_slotted() -> None:
    _, _, policy, route = _authorized_route()
    profile = build_current_fixed_resource_authorization_profile_v1()

    for value in (policy, route, profile):
        assert not hasattr(value, "__dict__")
        with pytest.raises((AttributeError, TypeError)):
            value.contract_version = "changed"


def test_route_fingerprint_recomputes_from_complete_payload() -> None:
    context, assessment, policy, route = _authorized_route()

    assert route.routing_fingerprint == (
        calculate_adjustment_capability_routing_fingerprint_v1(route)
    )
    assert validate_adjustment_capability_routing_v1(
        route,
        context,
        assessment,
        policy,
    ).passed


def test_projection_is_not_a_canonical_assessment_shape() -> None:
    projection_fields = {
        field.name for field in fields(LegacyServiceAdjustmentAssessmentProjectionV1)
    }
    canonical_fields = {field.name for field in fields(type(_authorized_route()[1]))}

    assert projection_fields != canonical_fields
    assert "canonical_assessment" in projection_fields
    assert "primary_decision" not in projection_fields


def test_manual_policy_binding_profile_dictionary_fails_closed() -> None:
    profile = build_current_fixed_resource_authorization_profile_v1()
    binding = FixedResourceCapabilityBindingV1(
        capability=(AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION),
        generation_action=FIXED_RESOURCE_TRIP_REDISTRIBUTION_ACTION,
        solver_adapter_id="legacy_heuristic_v1",
        adapter_available=True,
        supported_fixed_resource_profile={"profile": profile},
        supported_direction_trip_lock_mode=DirectionTripLockMode.FIXED_BY_DIRECTION,
        supported_fleet_constraint_mode=FleetConstraintMode.AVAILABLE_UPPER_BOUND,
        supported_initial_fleet_positioning_mode=(InitialFleetPositioningMode.SOLVER_DETERMINED),
        supported_boundary_convention=BoundaryConvention.HALF_OPEN,
    )
    policy = AdjustmentCapabilityRoutingPolicyV1(
        fixed_resource_bindings=(binding,),
        routing_policy_fingerprint="false",
    )

    assert not validate_adjustment_capability_routing_policy_v1(policy).passed

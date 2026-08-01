from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import bus_schedule_engine.protected_service_floor as protected_service_floor
from bus_schedule_engine.application_pipeline import (
    UnifiedApplicationStatusV1,
    run_unified_application_pipeline_v1,
)
from bus_schedule_engine.contracts_v1.models import (
    ContractDirection,
    DepartureTerminal,
    ExactTimetableTrip,
    InputSourceType,
    OperatingDayType,
    ScenarioBInput,
    SourceMetadata,
    TerminalDepartureTimes,
    TripsByDirection,
    TurnaroundMinutes,
)
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import ImportedWorkbook, import_workbook
from bus_schedule_engine.models import (
    CurrentBServiceRegimeV1,
    Direction,
    ProtectedRegimeDecisionV1,
    ProtectedRegimeEvidenceV1,
    ProtectedServiceFloorAssessmentV1,
    ProtectedServiceFloorFailureV1,
    ProtectedServiceFloorPolicyV1,
    ProtectedServiceFloorPreviewV1,
    RouteType,
    ScenarioParameters,
    Trip,
    TripRidershipDatasetMetadataV1,
    TripRidershipDirectionV1,
    TripRidershipObservationV1,
)
from bus_schedule_engine.protected_service_floor import (
    assess_protected_service_floors_v1,
    derive_current_b_service_regimes_v1,
    protected_service_floor_assessment_is_current_v1,
    protected_service_floor_policy_from_workbook_v1,
)
from bus_schedule_engine.protected_service_floor_codes import (
    BALANCED_ROUNDING,
    IRREGULAR_HEADWAY_RANGE_EXCEEDS_TOLERANCE,
    IRREGULAR_NON_POSITIVE_HEADWAY,
    IRREGULAR_NON_WHOLE_MINUTE_HEADWAY,
    NOT_ENFORCED_IN_6A2A,
    NOT_EVALUATED_CONFIDENCE_BELOW_MINIMUM,
    NOT_EVALUATED_NO_TRIP_RIDERSHIP,
    NOT_EVALUATED_STALE_TRIP_RIDERSHIP,
    NOT_PROTECTED_B_REGIME_NOT_REGULAR,
    NOT_PROTECTED_HEADWAY_ABOVE_CEILING,
    NOT_PROTECTED_HEADWAY_NOT_MEASURABLE,
    NOT_PROTECTED_HIGH_LOAD_SHARE_BELOW_THRESHOLD,
    NOT_PROTECTED_INSUFFICIENT_TRIP_COVERAGE,
    NOT_PROTECTED_REGIME_TOO_SHORT,
    NOT_PROTECTED_TOO_FEW_DEPARTURES,
    PROTECTED_HIGH_DEMAND_SERVICE_FLOOR,
    PROTECTED_SERVICE_FLOOR_ASSESSMENT_FAILED,
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID,
    REGULAR,
)
from bus_schedule_engine.trip_ridership import analyze_trip_ridership_v1

BASE_SECONDS = 6 * 3600


def _scenario(
    outbound_minutes: tuple[float, ...],
    inbound_minutes: tuple[float, ...] = (),
) -> ScenarioBInput:
    exact: list[ExactTimetableTrip] = []
    for direction, prefix, terminal, offsets in (
        (
            ContractDirection.OUTBOUND,
            "O",
            DepartureTerminal.TERMINAL_1,
            outbound_minutes,
        ),
        (
            ContractDirection.INBOUND,
            "I",
            DepartureTerminal.TERMINAL_2,
            inbound_minutes,
        ),
    ):
        for index, offset in enumerate(offsets, start=1):
            departure = BASE_SECONDS + round(offset * 60)
            exact.append(
                ExactTimetableTrip(
                    trip_id=f"{prefix}{index:02d}",
                    direction=direction,
                    departure_terminal=terminal,
                    departure_time=departure,
                    runtime_minutes=30,
                    arrival_time=departure + 30 * 60,
                )
            )
    first_outbound = exact[0].departure_time if outbound_minutes else BASE_SECONDS
    first_inbound = (
        next(trip.departure_time for trip in exact if trip.direction == ContractDirection.INBOUND)
        if inbound_minutes
        else BASE_SECONDS
    )
    return ScenarioBInput(
        route_id="M6A2A",
        route_name="Protected floor fixture",
        route_type=RouteType.INTRA_PROVINCIAL,
        terminal_1_name="T1",
        terminal_2_name="T2",
        trip_runtime_minutes=30,
        turnaround_minutes=TurnaroundMinutes(terminal_1=5, terminal_2=5),
        total_daily_trips=len(exact),
        trips_by_direction=TripsByDirection(
            outbound=len(outbound_minutes),
            inbound=len(inbound_minutes),
        ),
        first_departures=TerminalDepartureTimes(
            terminal_1=first_outbound,
            terminal_2=first_inbound,
        ),
        last_departures=TerminalDepartureTimes(
            terminal_1=(
                BASE_SECONDS + round(outbound_minutes[-1] * 60)
                if outbound_minutes
                else BASE_SECONDS
            ),
            terminal_2=(
                BASE_SECONDS + round(inbound_minutes[-1] * 60) if inbound_minutes else BASE_SECONDS
            ),
        ),
        vehicle_capacity=100,
        available_fleet_limit=20,
        approved_active_fleet=10,
        operating_day_type=OperatingDayType.WEEKDAY,
        exact_timetable=tuple(exact),
        source_metadata=SourceMetadata(
            source_type=InputSourceType.XLSX,
            source_id="m6a2a-fixture",
            imported_at=datetime(2026, 7, 31, tzinfo=UTC),
            notes="Excluded from Scenario B fingerprint.",
        ),
    )


def _parameters(scenario: ScenarioBInput) -> ScenarioParameters:
    return ScenarioParameters(
        route_id=scenario.route_id,
        route_name=scenario.route_name,
        route_type=scenario.route_type,
        trip_runtime_minutes=scenario.trip_runtime_minutes,
        total_daily_trips=scenario.total_daily_trips,
        terminal_1_name=scenario.terminal_1_name,
        terminal_1_first_departure=scenario.first_departures.terminal_1,
        terminal_1_last_departure=scenario.last_departures.terminal_1,
        terminal_2_name=scenario.terminal_2_name,
        terminal_2_first_departure=scenario.first_departures.terminal_2,
        terminal_2_last_departure=scenario.last_departures.terminal_2,
        vehicle_capacity_passengers=scenario.vehicle_capacity,
        target_load_factor=0.85,
        maximum_load_factor=0.90,
        minimum_layover_minutes=5,
        allowed_trip_runtime_minutes=(30,),
        available_fleet_limit=scenario.available_fleet_limit,
        approved_active_fleet=scenario.approved_active_fleet,
        operating_day_type=scenario.operating_day_type.value,
    )


def _imported(
    scenario: ScenarioBInput,
    *,
    passenger_counts: dict[str, tuple[int, ...]] | None = None,
    confidence: str = "medium",
    configuration: dict[str, object] | None = None,
) -> ImportedWorkbook:
    parameters = _parameters(scenario)
    trips = [
        Trip(
            scenario="B",
            trip_id=trip.trip_id,
            departure_terminal=(
                scenario.terminal_1_name
                if trip.direction == ContractDirection.OUTBOUND
                else scenario.terminal_2_name
            ),
            direction=(
                Direction.TERMINAL_1_TO_2
                if trip.direction == ContractDirection.OUTBOUND
                else Direction.TERMINAL_2_TO_1
            ),
            departure_seconds=trip.departure_time,
            arrival_seconds=trip.resolved_arrival_time,
        )
        for trip in scenario.exact_timetable
    ]
    observations: list[TripRidershipObservationV1] = []
    if passenger_counts is not None:
        trip_by_id = {trip.trip_id: trip for trip in scenario.exact_timetable}
        for trip_id, counts in passenger_counts.items():
            trip = trip_by_id[trip_id]
            direction = (
                TripRidershipDirectionV1.OUTBOUND
                if trip.direction == ContractDirection.OUTBOUND
                else TripRidershipDirectionV1.INBOUND
            )
            for day_index, count in enumerate(counts):
                observations.append(
                    TripRidershipObservationV1(
                        observation_id=f"{trip_id}-D{day_index + 1:02d}",
                        service_date=date(2026, 7, 1) + timedelta(days=day_index),
                        source_trip_id=None,
                        scheduled_trip_id=trip_id,
                        direction=direction,
                        scheduled_departure_seconds=trip.departure_time,
                        actual_departure_seconds=None,
                        passenger_count=count,
                        vehicle_id=None,
                        notes="Free text excluded from fingerprints.",
                    )
                )
    metadata = (
        TripRidershipDatasetMetadataV1(
            dataset_id="M6A2A-RIDERSHIP",
            source_type="manual_count",
            confidence=confidence,
            observed_schedule_scenario="B",
            operating_day_type="weekday",
            match_tolerance_minutes=5,
            source_notes="Free text excluded from fingerprints.",
        )
        if observations
        else None
    )
    return ImportedWorkbook(
        parameters_a=None,
        trips_a=[],
        parameters_b=parameters,
        trips_b=trips,
        demand=[],
        configuration=configuration or {},
        trip_ridership_metadata=metadata,
        trip_ridership_observations=tuple(observations),
    )


def _assessment(
    minutes: tuple[float, ...] = (0, 15, 30),
    *,
    passenger_counts: dict[str, tuple[int, ...]] | None = None,
    confidence: str = "medium",
    policy: ProtectedServiceFloorPolicyV1 | None = None,
):
    scenario = _scenario(minutes)
    counts = passenger_counts
    if counts is None:
        counts = {trip.trip_id: (85, 85, 85) for trip in scenario.exact_timetable}
    imported = _imported(
        scenario,
        passenger_counts=counts,
        confidence=confidence,
    )
    analysis = analyze_trip_ridership_v1(imported, scenario) if counts else None
    result = assess_protected_service_floors_v1(
        imported,
        scenario,
        analysis,
        policy or ProtectedServiceFloorPolicyV1(),
    )
    return imported, scenario, analysis, result


def test_exact_uniform_short_regime_is_derived_deterministically() -> None:
    scenario = _scenario((0, 15, 30, 45))
    policy = ProtectedServiceFloorPolicyV1()

    first = derive_current_b_service_regimes_v1(scenario, policy)
    second = derive_current_b_service_regimes_v1(scenario, policy)

    assert first == second
    assert len(first) == 1
    assert first[0].internal_headway_sequence == (15.0, 15.0, 15.0)
    assert first[0].regularity_classification == REGULAR


def test_balanced_15_16_minute_regime_is_representable() -> None:
    regime = derive_current_b_service_regimes_v1(
        _scenario((0, 15, 31, 46)),
        ProtectedServiceFloorPolicyV1(),
    )[0]

    assert regime.internal_headway_sequence == (15.0, 16.0, 15.0)
    assert regime.regularity_classification == BALANCED_ROUNDING


def test_one_gap_fluctuation_does_not_automatically_create_a_regime() -> None:
    regimes = derive_current_b_service_regimes_v1(
        _scenario((0, 15, 30, 50, 65, 80)),
        ProtectedServiceFloorPolicyV1(),
    )

    assert len(regimes) == 1
    assert regimes[0].regularity_classification == (IRREGULAR_HEADWAY_RANGE_EXCEEDS_TOLERANCE)


def test_material_sustained_change_creates_nonoverlapping_boundary() -> None:
    regimes = derive_current_b_service_regimes_v1(
        _scenario((0, 15, 30, 45, 65, 85, 105)),
        ProtectedServiceFloorPolicyV1(),
    )

    assert len(regimes) == 2
    assert set(regimes[0].b_trip_ids).isdisjoint(regimes[1].b_trip_ids)
    assert regimes[0].transition_headway_after == regimes[1].transition_headway_before
    assert (
        regimes[0].transition_headway_after
        not in (
            *regimes[0].internal_headway_sequence,
            *regimes[1].internal_headway_sequence,
        )
        or regimes[0].transition_headway_after == 15.0
    )
    assert sum(regime.trip_count for regime in regimes) == 7


def test_directions_are_never_combined() -> None:
    regimes = derive_current_b_service_regimes_v1(
        _scenario((0, 15, 30), (5, 20, 35)),
        ProtectedServiceFloorPolicyV1(),
    )

    assert len(regimes) == 2
    assert {regime.direction for regime in regimes} == {
        TripRidershipDirectionV1.OUTBOUND,
        TripRidershipDirectionV1.INBOUND,
    }
    assert all(len({trip_id[0] for trip_id in regime.b_trip_ids}) == 1 for regime in regimes)


def test_timetable_tuple_order_does_not_change_regimes() -> None:
    scenario = _scenario((0, 15, 30), (5, 20, 35))
    shuffled = replace(
        scenario,
        exact_timetable=tuple(reversed(scenario.exact_timetable)),
    )
    policy = ProtectedServiceFloorPolicyV1()

    assert derive_current_b_service_regimes_v1(
        scenario,
        policy,
    ) == derive_current_b_service_regimes_v1(shuffled, policy)


@pytest.mark.parametrize(
    ("minutes", "classification"),
    (
        ((0, 0, 15), IRREGULAR_NON_POSITIVE_HEADWAY),
        ((0, 15.5, 31), IRREGULAR_NON_WHOLE_MINUTE_HEADWAY),
    ),
)
def test_invalid_headway_fails_regularity(
    minutes: tuple[float, ...],
    classification: str,
) -> None:
    regime = derive_current_b_service_regimes_v1(
        _scenario(minutes),
        ProtectedServiceFloorPolicyV1(),
    )[0]

    assert regime.regularity_classification == classification


@pytest.mark.parametrize(
    ("minutes", "expected_code"),
    (
        ((0, 15), NOT_PROTECTED_TOO_FEW_DEPARTURES),
        ((0, 10, 20), NOT_PROTECTED_REGIME_TOO_SHORT),
        ((0, 31, 62), NOT_PROTECTED_HEADWAY_ABOVE_CEILING),
    ),
)
def test_structural_protection_gates(
    minutes: tuple[float, ...],
    expected_code: str,
) -> None:
    _imported_value, _scenario_value, _analysis_value, assessment = _assessment(
        minutes,
    )

    assert expected_code in assessment.decisions[0].failed_gate_codes
    assert assessment.decisions[0].classification != (PROTECTED_HIGH_DEMAND_SERVICE_FLOOR)


def test_missing_trip_dataset_is_not_evaluated() -> None:
    scenario = _scenario((0, 15, 30))
    imported = _imported(scenario)
    assessment = assess_protected_service_floors_v1(
        imported,
        scenario,
        None,
        ProtectedServiceFloorPolicyV1(),
    )

    assert assessment.decisions[0].classification == (NOT_EVALUATED_NO_TRIP_RIDERSHIP)
    assert assessment.protected_previews == ()


def test_stale_trip_analysis_is_not_evaluated() -> None:
    imported, scenario, analysis, _current = _assessment()
    assert analysis is not None
    stale = replace(
        analysis,
        scenario_b_timetable_fingerprint="0" * 64,
    )

    assessment = assess_protected_service_floors_v1(
        imported,
        scenario,
        stale,
        ProtectedServiceFloorPolicyV1(),
    )

    assert assessment.decisions[0].classification == (NOT_EVALUATED_STALE_TRIP_RIDERSHIP)


def test_low_confidence_is_not_upgraded() -> None:
    _imported_value, _scenario_value, _analysis_value, assessment = _assessment(
        confidence="low",
    )

    assert assessment.decisions[0].classification == (NOT_EVALUATED_CONFIDENCE_BELOW_MINIMUM)


def test_coverage_and_high_load_share_use_repeated_p85_evidence() -> None:
    counts = {
        "O01": (85, 85, 85),
        "O02": (100, 20),
        "O03": (84, 84, 84),
    }
    _imported_value, _scenario_value, _analysis_value, assessment = _assessment(
        passenger_counts=counts,
    )
    evidence = assessment.decisions[0].evidence

    assert evidence.trips_with_any_usable_observation == 3
    assert evidence.coverage_eligible_trips == 2
    assert evidence.regime_trip_coverage_rate == pytest.approx(2 / 3)
    assert evidence.high_load_eligible_trips == 1
    assert evidence.high_load_trip_share == pytest.approx(0.5)
    assert NOT_PROTECTED_INSUFFICIENT_TRIP_COVERAGE in (assessment.decisions[0].failed_gate_codes)
    assert NOT_PROTECTED_HIGH_LOAD_SHARE_BELOW_THRESHOLD in (
        assessment.decisions[0].failed_gate_codes
    )


def test_missing_trip_observations_are_not_zero_or_coverage_eligible() -> None:
    counts = {"O01": (90, 90, 90)}
    _imported_value, _scenario_value, _analysis_value, assessment = _assessment(
        passenger_counts=counts,
    )
    evidence = assessment.decisions[0].evidence

    assert evidence.coverage_eligible_trip_ids == ("O01",)
    assert evidence.regime_trip_coverage_rate == pytest.approx(1 / 3)
    assert evidence.minimum_p85_load_factor == pytest.approx(0.9)


def test_p85_equal_to_target_passes_and_below_target_fails() -> None:
    passing = {
        "O01": (85, 85, 85),
        "O02": (85, 85, 85),
        "O03": (85, 85, 85),
    }
    _i1, _s1, _a1, passing_assessment = _assessment(
        passenger_counts=passing,
    )
    assert passing_assessment.decisions[0].classification == (PROTECTED_HIGH_DEMAND_SERVICE_FLOOR)

    failing = {trip_id: (84, 84, 84) for trip_id in passing}
    _i2, _s2, _a2, failing_assessment = _assessment(
        passenger_counts=failing,
    )
    assert failing_assessment.decisions[0].classification == (
        NOT_PROTECTED_HIGH_LOAD_SHARE_BELOW_THRESHOLD
    )


def test_long_headway_high_demand_and_short_headway_low_demand_do_not_protect() -> None:
    _i1, _s1, _a1, long_headway = _assessment((0, 31, 62))
    assert NOT_PROTECTED_HEADWAY_ABOVE_CEILING in (long_headway.decisions[0].failed_gate_codes)

    low_counts = {
        "O01": (20, 20, 20),
        "O02": (20, 20, 20),
        "O03": (20, 20, 20),
    }
    _i2, _s2, _a2, low_demand = _assessment(passenger_counts=low_counts)
    assert low_demand.decisions[0].classification == (NOT_PROTECTED_HIGH_LOAD_SHARE_BELOW_THRESHOLD)


def test_short_headway_sufficient_coverage_and_high_demand_is_protected() -> None:
    _imported_value, _scenario_value, _analysis_value, assessment = _assessment()

    decision = assessment.decisions[0]
    assert decision.classification == PROTECTED_HIGH_DEMAND_SERVICE_FLOOR
    assert decision.failed_gate_codes == ()


def test_every_applicable_failed_gate_is_returned() -> None:
    scenario = _scenario((0,))
    imported = _imported(scenario)
    assessment = assess_protected_service_floors_v1(
        imported,
        scenario,
        None,
        ProtectedServiceFloorPolicyV1(),
    )
    failed = set(assessment.decisions[0].failed_gate_codes)

    assert {
        NOT_EVALUATED_NO_TRIP_RIDERSHIP,
        NOT_PROTECTED_B_REGIME_NOT_REGULAR,
        NOT_PROTECTED_HEADWAY_NOT_MEASURABLE,
        NOT_PROTECTED_TOO_FEW_DEPARTURES,
        NOT_PROTECTED_REGIME_TOO_SHORT,
    }.issubset(failed)


def test_future_preview_preserves_exact_b_floor_facts_without_enforcement() -> None:
    _imported_value, _scenario_value, _analysis_value, assessment = _assessment()
    regime = assessment.regimes[0]
    preview = assessment.protected_previews[0]

    assert preview.maximum_future_c_headway_minutes == regime.maximum_b_headway
    assert preview.minimum_future_c_trip_count == regime.trip_count
    assert preview.protected_window_start == regime.first_departure
    assert preview.protected_window_end == regime.last_departure
    assert preview.donor_removal_prohibited is True
    assert preview.enforcement_status == NOT_ENFORCED_IN_6A2A


def test_policy_and_trip_data_changes_alter_assessment_fingerprint() -> None:
    imported, scenario, analysis, assessment = _assessment()
    changed_policy = replace(
        ProtectedServiceFloorPolicyV1(),
        minimum_high_load_trip_share=0.9,
    )
    policy_changed = assess_protected_service_floors_v1(
        imported,
        scenario,
        analysis,
        changed_policy,
    )
    assert policy_changed.assessment_fingerprint != assessment.assessment_fingerprint

    changed_observations = tuple(
        replace(
            observation,
            passenger_count=observation.passenger_count + 1,
        )
        if observation.observation_id == "O01-D01"
        else observation
        for observation in imported.trip_ridership_observations
    )
    changed_imported = replace(
        imported,
        trip_ridership_observations=changed_observations,
    )
    changed_analysis = analyze_trip_ridership_v1(changed_imported, scenario)
    trip_changed = assess_protected_service_floors_v1(
        changed_imported,
        scenario,
        changed_analysis,
        ProtectedServiceFloorPolicyV1(),
    )
    assert trip_changed.assessment_fingerprint != assessment.assessment_fingerprint


def test_b_timetable_change_alters_regime_and_assessment_fingerprints() -> None:
    imported, scenario, _analysis_value, assessment = _assessment()
    changed_trip = replace(
        scenario.exact_timetable[-1],
        departure_time=scenario.exact_timetable[-1].departure_time + 60,
        arrival_time=scenario.exact_timetable[-1].arrival_time + 60,
    )
    changed_scenario = replace(
        scenario,
        exact_timetable=(*scenario.exact_timetable[:-1], changed_trip),
        last_departures=replace(
            scenario.last_departures,
            terminal_1=scenario.last_departures.terminal_1 + 60,
        ),
    )
    changed_imported = _imported(
        changed_scenario,
        passenger_counts={trip.trip_id: (85, 85, 85) for trip in changed_scenario.exact_timetable},
    )
    changed_analysis = analyze_trip_ridership_v1(
        changed_imported,
        changed_scenario,
    )
    changed = assess_protected_service_floors_v1(
        changed_imported,
        changed_scenario,
        changed_analysis,
        ProtectedServiceFloorPolicyV1(),
    )

    assert changed.scenario_b_fingerprint != assessment.scenario_b_fingerprint
    assert changed.regime_derivation_fingerprint != (assessment.regime_derivation_fingerprint)
    assert changed.assessment_fingerprint != assessment.assessment_fingerprint
    assert imported.trip_ridership_observations


def test_unchanged_protected_service_floor_assessment_is_current() -> None:
    imported, scenario, analysis, assessment = _assessment()

    assert protected_service_floor_assessment_is_current_v1(
        assessment,
        imported,
        scenario,
        analysis,
    )


@pytest.mark.parametrize(
    ("policy_key", "changed_value"),
    (
        ("maximum_protected_b_headway_minutes", 25),
        ("minimum_observed_days_per_trip", 4),
    ),
)
def test_active_prefixed_policy_change_makes_assessment_stale(
    policy_key: str,
    changed_value: object,
) -> None:
    imported, scenario, analysis, assessment = _assessment()
    changed_imported = replace(
        imported,
        configuration={f"protected_service_floor_{policy_key}": changed_value},
    )

    assert not protected_service_floor_assessment_is_current_v1(
        assessment,
        changed_imported,
        scenario,
        analysis,
    )


@pytest.mark.parametrize(
    ("parameter_name", "changed_value"),
    (
        ("target_load_factor", 0.80),
        ("maximum_load_factor", 0.95),
    ),
)
def test_active_load_threshold_change_makes_assessment_stale(
    parameter_name: str,
    changed_value: float,
) -> None:
    imported, scenario, analysis, assessment = _assessment()
    changed_imported = replace(
        imported,
        parameters_b=replace(
            imported.parameters_b,
            **{parameter_name: changed_value},
        ),
    )

    assert not protected_service_floor_assessment_is_current_v1(
        assessment,
        changed_imported,
        scenario,
        analysis,
    )


def test_scenario_b_change_makes_assessment_stale() -> None:
    imported, scenario, analysis, assessment = _assessment()
    changed_last_trip = replace(
        scenario.exact_timetable[-1],
        departure_time=scenario.exact_timetable[-1].departure_time + 60,
        arrival_time=scenario.exact_timetable[-1].arrival_time + 60,
    )
    changed_scenario = replace(
        scenario,
        exact_timetable=(*scenario.exact_timetable[:-1], changed_last_trip),
        last_departures=replace(
            scenario.last_departures,
            terminal_1=scenario.last_departures.terminal_1 + 60,
        ),
    )

    assert not protected_service_floor_assessment_is_current_v1(
        assessment,
        imported,
        changed_scenario,
        analysis,
    )


def test_trip_ridership_input_or_analysis_change_makes_assessment_stale() -> None:
    imported, scenario, analysis, assessment = _assessment()
    changed_observations = tuple(
        replace(
            observation,
            passenger_count=observation.passenger_count + 1,
        )
        if observation.observation_id == "O01-D01"
        else observation
        for observation in imported.trip_ridership_observations
    )
    changed_imported = replace(
        imported,
        trip_ridership_observations=changed_observations,
    )
    changed_analysis = analyze_trip_ridership_v1(changed_imported, scenario)

    assert not protected_service_floor_assessment_is_current_v1(
        assessment,
        changed_imported,
        scenario,
        analysis,
    )
    assert not protected_service_floor_assessment_is_current_v1(
        assessment,
        changed_imported,
        scenario,
        changed_analysis,
    )


@pytest.mark.parametrize(
    "assessment_fingerprint",
    (None, "malformed", "0" * 64),
)
def test_invalid_or_mismatched_assessment_fingerprint_is_stale(
    assessment_fingerprint: str | None,
) -> None:
    imported, scenario, analysis, assessment = _assessment()
    invalid = replace(
        assessment,
        assessment_fingerprint=assessment_fingerprint,
    )

    assert not protected_service_floor_assessment_is_current_v1(
        invalid,
        imported,
        scenario,
        analysis,
    )


def test_assessment_component_or_derivation_profile_change_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, scenario, analysis, assessment = _assessment()
    inconsistent = replace(
        assessment,
        issue_codes=(*assessment.issue_codes, "TAMPERED_ASSESSMENT_COMPONENT"),
    )

    assert not protected_service_floor_assessment_is_current_v1(
        inconsistent,
        imported,
        scenario,
        analysis,
    )

    monkeypatch.setattr(
        protected_service_floor,
        "CURRENT_B_REGIME_DERIVATION_PROFILE",
        "m6a2a_current_b_service_regimes_v2",
    )
    assert not protected_service_floor_assessment_is_current_v1(
        assessment,
        imported,
        scenario,
        analysis,
    )


def test_missing_required_analysis_binding_makes_assessment_stale() -> None:
    imported, scenario, analysis, assessment = _assessment()
    missing_binding = replace(
        assessment,
        trip_ridership_analysis_fingerprint=None,
    )

    assert not protected_service_floor_assessment_is_current_v1(
        missing_binding,
        imported,
        scenario,
        analysis,
    )


def test_notes_and_source_row_order_do_not_change_fingerprints() -> None:
    imported, scenario, analysis, assessment = _assessment()
    reordered = replace(
        imported,
        trips_b=list(reversed(imported.trips_b)),
        trip_ridership_metadata=replace(
            imported.trip_ridership_metadata,
            source_notes="Different free text.",
        ),
        trip_ridership_observations=tuple(
            replace(observation, notes="Different free text.")
            for observation in reversed(imported.trip_ridership_observations)
        ),
    )
    reordered_analysis = analyze_trip_ridership_v1(reordered, scenario)
    reordered_assessment = assess_protected_service_floors_v1(
        reordered,
        scenario,
        reordered_analysis,
        ProtectedServiceFloorPolicyV1(),
    )

    assert reordered_analysis.analysis_fingerprint == analysis.analysis_fingerprint
    assert reordered_assessment.assessment_fingerprint == (assessment.assessment_fingerprint)


@pytest.mark.parametrize(
    "model",
    (
        CurrentBServiceRegimeV1,
        ProtectedServiceFloorPolicyV1,
        ProtectedRegimeEvidenceV1,
        ProtectedRegimeDecisionV1,
        ProtectedServiceFloorPreviewV1,
        ProtectedServiceFloorAssessmentV1,
        ProtectedServiceFloorFailureV1,
    ),
)
def test_models_are_frozen_and_slotted(model: type[object]) -> None:
    assert model.__dataclass_params__.frozen is True
    assert "__slots__" in model.__dict__


def test_assessment_does_not_mutate_inputs() -> None:
    imported, scenario, analysis, _assessment_value = _assessment()
    before_imported = deepcopy(imported)
    before_scenario = deepcopy(scenario)
    before_analysis = deepcopy(analysis)

    assess_protected_service_floors_v1(
        imported,
        scenario,
        analysis,
        ProtectedServiceFloorPolicyV1(),
    )

    assert imported == before_imported
    assert scenario == before_scenario
    assert analysis == before_analysis
    frozen_policy = ProtectedServiceFloorPolicyV1()
    with pytest.raises(FrozenInstanceError):
        frozen_policy.minimum_observed_days_per_trip = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"maximum_protected_b_headway_minutes": 0}, "positive integer"),
        ({"headway_rounding_tolerance_minutes": -1}, "non-negative integer"),
        ({"minimum_departures_per_regime": 1}, "integer >= 2"),
        ({"minimum_regime_duration_minutes": 0}, "positive integer"),
        ({"minimum_observed_days_per_trip": 0}, "positive integer"),
        ({"minimum_regime_trip_coverage_rate": 1.1}, "within"),
        ({"minimum_high_load_trip_share": -0.1}, "within"),
        ({"protected_load_statistic": "P90"}, "must be P85"),
        ({"minimum_trip_ridership_confidence": "very high"}, "unknown"),
    ),
)
def test_policy_validation(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ProtectedServiceFloorPolicyV1(**changes)


def test_workbook_policy_uses_explicit_optional_values() -> None:
    scenario = _scenario((0, 15, 30))
    imported = _imported(
        scenario,
        configuration={
            "protected_service_floor_maximum_protected_b_headway_minutes": 25,
            "protected_service_floor_minimum_regime_duration_minutes": 45,
            "protected_service_floor_minimum_observed_days_per_trip": 4,
            "protected_service_floor_minimum_high_load_trip_share": 0.75,
            "protected_service_floor_protected_load_statistic": "p85",
            "protected_service_floor_minimum_trip_ridership_confidence": "HIGH",
        },
    )

    policy = protected_service_floor_policy_from_workbook_v1(imported)

    assert policy.maximum_protected_b_headway_minutes == 25
    assert policy.minimum_regime_duration_minutes == 45
    assert policy.minimum_observed_days_per_trip == 4
    assert policy.minimum_high_load_trip_share == 0.75
    assert policy.protected_load_statistic == "P85"
    assert policy.minimum_trip_ridership_confidence == "high"


@pytest.mark.parametrize(
    ("unprefixed_name", "unprefixed_value", "policy_field", "expected_default"),
    (
        ("maximum_protected_b_headway_minutes", 45, "maximum_protected_b_headway_minutes", 30),
        ("headway_rounding_tolerance_minutes", 4, "headway_rounding_tolerance_minutes", 1),
        ("minimum_departures_per_regime", 5, "minimum_departures_per_regime", 3),
        ("minimum_regime_duration_minutes", 75, "minimum_regime_duration_minutes", 30),
        ("minimum_observed_days_per_trip", 7, "minimum_observed_days_per_trip", 3),
        ("minimum_regime_trip_coverage_rate", 0.9, "minimum_regime_trip_coverage_rate", 0.8),
        ("minimum_high_load_trip_share", 0.95, "minimum_high_load_trip_share", 0.67),
        ("protected_load_statistic", "P90", "protected_load_statistic", "P85"),
        (
            "minimum_trip_ridership_confidence",
            "high",
            "minimum_trip_ridership_confidence",
            "medium",
        ),
        (
            "future_service_window_boundary_tolerance_minutes",
            9,
            "future_service_window_boundary_tolerance_minutes",
            0,
        ),
    ),
)
def test_unprefixed_configuration_does_not_control_6a2a_policy(
    unprefixed_name: str,
    unprefixed_value: object,
    policy_field: str,
    expected_default: object,
) -> None:
    scenario = _scenario((0, 15, 30))
    imported = _imported(
        scenario,
        configuration={unprefixed_name: unprefixed_value},
    )

    policy = protected_service_floor_policy_from_workbook_v1(imported)

    assert getattr(policy, policy_field) == expected_default


def test_explicit_prefixed_rounding_tolerance_controls_6a2a_policy() -> None:
    scenario = _scenario((0, 15, 30))
    imported = _imported(
        scenario,
        configuration={
            "headway_rounding_tolerance_minutes": 4,
            "protected_service_floor_headway_rounding_tolerance_minutes": 2,
        },
    )

    policy = protected_service_floor_policy_from_workbook_v1(imported)

    assert policy.headway_rounding_tolerance_minutes == 2


def test_generated_template_declares_all_policy_defaults(tmp_path: Path) -> None:
    imported = import_workbook(create_input_template(tmp_path / "template.xlsx"))

    assert (
        protected_service_floor_policy_from_workbook_v1(imported) == ProtectedServiceFloorPolicyV1()
    )
    assert (
        len([key for key in imported.configuration if key.startswith("protected_service_floor_")])
        == 10
    )


def test_supplemental_assessment_failure_blocks_unprotected_c_but_retains_b(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = import_workbook(create_input_template(tmp_path / "pipeline.xlsx"))
    imported_at = datetime(2026, 7, 31, tzinfo=UTC)
    baseline = run_unified_application_pipeline_v1(
        imported,
        source_id="m6a2a-pipeline",
        imported_at=imported_at,
    )

    def fail_assessment(*_args, **_kwargs):
        raise ValueError("raw synthetic observation must not be exposed")

    monkeypatch.setattr(
        "bus_schedule_engine.application_pipeline.assess_protected_service_floors_v1",
        fail_assessment,
    )
    isolated = run_unified_application_pipeline_v1(
        imported,
        source_id="m6a2a-pipeline",
        imported_at=imported_at,
    )

    assert baseline.status == isolated.status == UnifiedApplicationStatusV1.COMPLETE
    assert isolated.unified_result.normalized_inputs == baseline.unified_result.normalized_inputs
    assert isolated.unified_result.b_evaluation == baseline.unified_result.b_evaluation
    assert isolated.unified_result.solver_attempted is False
    assert isolated.unified_result.recommended_outcome is None
    assert isolated.unified_result.protected_service_floor_enforcement_failure_code == (
        PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID
    )
    assert isolated.protected_service_floor_enforcement_authority is None
    assert isolated.protected_service_floor_enforcement_failure is not None
    assert isolated.protected_service_floor_assessment is None
    assert isolated.protected_service_floor_failure is not None
    assert isolated.protected_service_floor_failure.code == (
        PROTECTED_SERVICE_FLOOR_ASSESSMENT_FAILED
    )
    assert "raw synthetic observation" not in (
        isolated.protected_service_floor_failure.sanitized_message
    )


def test_public_assessment_shape_contains_required_fingerprints() -> None:
    names = {field.name for field in fields(ProtectedServiceFloorAssessmentV1)}

    assert {
        "scenario_b_fingerprint",
        "trip_ridership_input_fingerprint",
        "trip_ridership_analysis_fingerprint",
        "policy_fingerprint",
        "regime_derivation_fingerprint",
        "assessment_fingerprint",
        "regimes",
        "decisions",
        "protected_previews",
        "issue_codes",
        "limitations",
    }.issubset(names)


@pytest.mark.parametrize(
    "path",
    (
        "src/bus_schedule_engine/optimization_service.py",
        "src/bus_schedule_engine/c_generator.py",
        "src/bus_schedule_engine/generator.py",
        "src/bus_schedule_engine/service.py",
        "src/bus_schedule_engine/contracts_v1/solver_validation.py",
        "src/bus_schedule_engine/contracts_v1/ortools_solver.py",
        "src/bus_schedule_engine/contracts_v1/ortools_quality_solver.py",
    ),
)
def test_preview_is_not_used_by_solver_candidate_or_legacy_paths(path: str) -> None:
    source = Path(path).read_text(encoding="utf-8")

    assert "ProtectedServiceFloorPreviewV1" not in source
    assert "protected_service_floor_assessment" not in source
    assert "maximum_future_c_headway_minutes" not in source

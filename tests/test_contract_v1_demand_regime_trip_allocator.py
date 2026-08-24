from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

from bus_schedule_engine.contracts_v1.demand_regime_trip_allocator import (
    INFEASIBLE_SERVICE_FLOORS,
    NO_IMPROVING_CONSERVATIVE_ALLOCATION,
    TripAllocationSetStatusV1,
    allocate_validated_demand_regimes_v1,
    trip_allocation_candidate_set_to_dict_v1,
)
from bus_schedule_engine.contracts_v1.demand_regimes import (
    DemandRegimePlanV1,
    DemandRegimeScopeV1,
    DemandRegimeV1,
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
from bus_schedule_engine.models import RouteType

BASE = 6 * 3600


def _plan(
    durations: tuple[int, ...],
    demand: tuple[float, ...],
    *,
    direction: ContractDirection = ContractDirection.OUTBOUND,
) -> DemandRegimePlanV1:
    total_demand = sum(demand)
    regimes = []
    cursor = BASE
    for index, (duration, value) in enumerate(zip(durations, demand, strict=True), start=1):
        end = cursor + duration * 60
        regimes.append(
            DemandRegimeV1(
                regime_id=f"R-{index}",
                direction=direction,
                start_time=cursor,
                end_time=end,
                duration_minutes=duration,
                bucket_count=max(1, duration // 30),
                demand_sum=value,
                demand_mean=value,
                demand_share=value / total_demand,
                normalized_demand_mean=value,
                within_regime_error=0,
                current_b_trip_count=None,
                current_b_median_headway=None,
                current_b_max_headway=None,
            )
        )
        cursor = end
    return DemandRegimePlanV1(
        direction=direction,
        scope=DemandRegimeScopeV1.DIRECTION_SPECIFIC_REGIMES,
        service_start=BASE,
        service_end=cursor,
        bucket_granularity_minutes=30,
        minimum_regime_bucket_count=1,
        natural_max_regimes=len(regimes),
        selected_regime_count=len(regimes),
        total_demand=total_demand,
        total_within_regime_error=0,
        complexity_cost=0,
        objective_cost=0,
        regime_count_objectives=(),
        current_b_exact_timetable_trip_count=None,
        current_b_service_window_trip_count=None,
        current_b_regime_trip_count=None,
        current_b_outside_service_window_trip_count=None,
        current_b_service_window_reconciled=None,
        regimes=tuple(regimes),
        boundary_evidence=(),
    )


def _scenario(
    plan: DemandRegimePlanV1,
    counts: tuple[int, ...],
    *,
    inbound_counts: tuple[int, ...] | None = None,
    departures: tuple[tuple[int, ...], ...] | None = None,
) -> ScenarioBInput:
    inbound_counts = inbound_counts or tuple(0 for _ in counts)
    trips = []
    for direction, directional_counts, prefix, terminal in (
        (ContractDirection.OUTBOUND, counts, "O", DepartureTerminal.TERMINAL_1),
        (ContractDirection.INBOUND, inbound_counts, "I", DepartureTerminal.TERMINAL_2),
    ):
        ordinal = 0
        for regime_index, (regime, count) in enumerate(
            zip(plan.regimes, directional_counts, strict=True)
        ):
            if departures is not None and direction == ContractDirection.OUTBOUND:
                times = departures[regime_index]
            else:
                times = tuple(
                    regime.start_time
                    + ((index + 1) * (regime.end_time - regime.start_time)) // (count + 1)
                    for index in range(count)
                )
            for departure in times:
                ordinal += 1
                trips.append(
                    ExactTimetableTrip(
                        trip_id=f"{prefix}-{ordinal:03d}",
                        direction=direction,
                        departure_terminal=terminal,
                        departure_time=departure,
                        runtime_minutes=30,
                    )
                )
    outbound = sum(counts)
    inbound = sum(inbound_counts)
    return ScenarioBInput(
        route_id="fixture",
        route_name="fixture",
        route_type=RouteType.INTRA_PROVINCIAL,
        terminal_1_name="T1",
        terminal_2_name="T2",
        trip_runtime_minutes=30,
        turnaround_minutes=TurnaroundMinutes(5, 5),
        total_daily_trips=outbound + inbound,
        trips_by_direction=TripsByDirection(outbound, inbound),
        first_departures=TerminalDepartureTimes(BASE, BASE),
        last_departures=TerminalDepartureTimes(plan.service_end - 60, plan.service_end - 60),
        vehicle_capacity=80,
        available_fleet_limit=20,
        operating_day_type=OperatingDayType.ALL_DAYS,
        exact_timetable=tuple(trips),
        source_metadata=SourceMetadata(
            InputSourceType.OTHER,
            "allocator-test",
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )


def _allocate(
    durations: tuple[int, ...],
    demand: tuple[float, ...],
    counts: tuple[int, ...],
):
    plan = _plan(durations, demand)
    return allocate_validated_demand_regimes_v1(
        plan,
        _scenario(plan, counts),
        evidence_status="DAILY_VALIDATED",
    )


def test_all_candidates_preserve_exact_direction_total() -> None:
    result = _allocate((60, 60, 60, 60), (10, 20, 30, 40), (4, 2, 2, 2))

    for candidate in (
        result.b_reference,
        result.c1_demand_fit,
        result.c2_conservative,
        result.c3_balanced,
    ):
        assert candidate is not None
        assert sum(candidate.allocation_vector) == result.total_trips == 10
        assert all(isinstance(value, int) for value in candidate.allocation_vector)


def test_half_open_scenario_b_boundary_is_counted_exactly_once() -> None:
    plan = _plan((60, 60), (1, 1))
    boundary = plan.regimes[0].end_time
    scenario = _scenario(
        plan,
        (2, 2),
        departures=(
            (plan.service_start, plan.service_start + 30 * 60),
            (boundary, boundary + 30 * 60),
        ),
    )

    result = allocate_validated_demand_regimes_v1(
        plan,
        scenario,
        evidence_status="DAILY_VALIDATED",
    )

    assert result.b_reference is not None
    assert result.b_reference.allocation_vector == (2, 2)


def test_c1_moves_service_toward_higher_observed_demand() -> None:
    result = _allocate((60, 60, 60), (10, 10, 80), (3, 1, 2))

    assert result.c1_demand_fit is not None
    assert result.c1_demand_fit.allocation_vector[-1] > 2
    assert result.c1_demand_fit.demand_mismatch < result.b_reference.demand_mismatch


def test_baseline_derived_floor_protects_low_demand_long_regime() -> None:
    result = _allocate((60, 180), (90, 10), (4, 6))

    assert result.c1_demand_fit is not None
    long_regime = result.c1_demand_fit.regime_allocations[1]
    assert long_regime.min_trip_count == 6
    assert long_regime.allocated_trip_count >= 6


def test_service_floor_infeasibility_is_structured() -> None:
    plan = _plan((60, 60), (90, 10))
    result = allocate_validated_demand_regimes_v1(
        plan,
        _scenario(plan, (2, 0)),
        evidence_status="DAILY_VALIDATED",
    )

    assert result.status == TripAllocationSetStatusV1.INFEASIBLE
    assert result.failure_code == INFEASIBLE_SERVICE_FLOORS
    assert result.c1_demand_fit is None


def test_scenario_b_optimal_case_does_not_fabricate_conservative_change() -> None:
    result = _allocate((60, 60, 60), (20, 30, 50), (2, 3, 5))

    assert result.c1_demand_fit.allocation_vector == (2, 3, 5)
    assert result.c1_demand_fit.moved_trips == 0
    assert result.c2_conservative.allocation_vector == (2, 3, 5)
    assert result.c2_conservative.status.value == NO_IMPROVING_CONSERVATIVE_ALLOCATION
    assert result.c3_balanced.allocation_vector == (2, 3, 5)


def test_conservative_candidate_uses_minimum_one_moved_trip() -> None:
    result = _allocate((60, 60, 60, 60), (10, 20, 30, 40), (4, 2, 2, 2))

    assert result.c2_conservative.moved_trips == 1
    assert result.c2_conservative.demand_mismatch < result.b_reference.demand_mismatch


def test_balanced_candidate_selects_deterministic_pareto_knee() -> None:
    result = _allocate((60, 60, 60, 60), (10, 20, 30, 40), (4, 2, 2, 2))

    assert result.c1_demand_fit.moved_trips == 2
    assert result.c3_balanced.allocation_vector == result.c2_conservative.allocation_vector
    assert result.c3_balanced.moved_trips == 1


def test_compile_quality_breaks_equal_mismatch_and_movement_tie() -> None:
    result = _allocate(
        (100, 90, 90, 120),
        (5, 5, 2, 2),
        (2, 2, 2, 1),
    )

    assert result.c1_demand_fit.allocation_vector == (2, 3, 1, 1)
    assert result.c1_demand_fit.compile_quality_score == 0


def test_nominal_headway_uses_duration_over_trip_count_without_anchoring() -> None:
    result = _allocate((100, 120), (50, 50), (2, 2))
    row = result.b_reference.regime_allocations[0]

    assert row.nominal_headway == 100 / 2
    assert row.nominal_headway != 100 / (2 - 1)
    assert row.best_integer_headway_proxy == 50


def test_direction_totals_are_isolated() -> None:
    outbound_plan = _plan((60, 60), (40, 60))
    scenario = _scenario(outbound_plan, (2, 3), inbound_counts=(7, 4))
    outbound = allocate_validated_demand_regimes_v1(
        outbound_plan,
        scenario,
        evidence_status="DAILY_VALIDATED",
    )
    inbound_plan = replace(
        outbound_plan,
        direction=ContractDirection.INBOUND,
        regimes=tuple(
            replace(item, direction=ContractDirection.INBOUND) for item in outbound_plan.regimes
        ),
    )
    inbound = allocate_validated_demand_regimes_v1(
        inbound_plan,
        scenario,
        evidence_status="DAILY_VALIDATED",
    )

    assert outbound.total_trips == 5
    assert inbound.total_trips == 11
    assert sum(outbound.c1_demand_fit.allocation_vector) == 5
    assert sum(inbound.c1_demand_fit.allocation_vector) == 11


def test_complete_candidate_set_is_byte_identical_across_100_runs() -> None:
    plan = _plan((60, 60, 60, 60), (10, 20, 30, 40))
    scenario = _scenario(plan, (4, 2, 2, 2))

    serialized = {
        json.dumps(
            trip_allocation_candidate_set_to_dict_v1(
                allocate_validated_demand_regimes_v1(
                    plan,
                    scenario,
                    evidence_status="DAILY_VALIDATED",
                )
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        for _ in range(100)
    }

    assert len(serialized) == 1

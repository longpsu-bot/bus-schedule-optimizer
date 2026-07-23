from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace

from .demand_coverage import (
    DEMAND_COVERAGE_INCOMPLETE_FOR_AUTHORITATIVE_C,
    assess_demand_coverage_v1,
)
from .demand_resolution import DemandAnalysisBlockV1, InterpolationStatus
from .evaluation import (
    BlockEvaluationV1,
    BlockSupplyPlanV1,
    BlockSupplyStatus,
    ScenarioBEvaluationPolicyV1,
    assess_scenario_b_fleet_v1,
)
from .fleet_assignment import (
    ContractFleetAssignmentError,
    ContractFleetAssignmentResultV1,
    assign_contract_v1_fleet,
)
from .models import (
    ContractDirection,
    DemandConfidence,
    DepartureTerminal,
    ExactTimetableTrip,
    ScenarioBInput,
    ScenarioId,
)
from .problem_validation import validate_schedule_generation_context_v1
from .serialization import canonical_sha256
from .solver_fingerprints import candidate_fingerprint, solution_fingerprint_payload
from .solver_models import (
    CandidateValidationResultV1,
    CandidateValidationStatus,
    InitialFleetPositioningMode,
    NativeSolverStatus,
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    RawScheduleCandidateV1,
    ScheduleGenerationContextV1,
    ScheduleProblemV1,
    ScheduleSolutionV1,
    SolutionHeadwayRegimeV1,
    SolutionTripV1,
    StockProfileEventV1,
)
from .solver_problem import (
    NUMERIC_RECONCILIATION_TOLERANCE_MINUTES,
)
from .validation import validate_scenario_input

_CONFIDENCE_RANK = {
    DemandConfidence.UNKNOWN: 0,
    DemandConfidence.LOW: 1,
    DemandConfidence.MEDIUM: 2,
    DemandConfidence.HIGH: 3,
}


@dataclass(frozen=True, slots=True)
class _DerivedTripFacts:
    shift_minutes: float
    previous_b_headway: float | None
    previous_c_headway: float | None


@dataclass(frozen=True, slots=True)
class _ReconciledRegime:
    raw: RawHeadwayRegimeV1
    members: tuple[RawCandidateTripV1, ...]
    actual_headway_sequence: tuple[int, ...]
    regularity_status: str


def _numeric_matches(claim: float | int, expected: float | int) -> bool:
    if isinstance(claim, bool) or not isinstance(claim, (int, float)):
        return False
    numeric_claim = float(claim)
    return math.isfinite(numeric_claim) and (
        abs(numeric_claim - float(expected)) <= NUMERIC_RECONCILIATION_TOLERANCE_MINUTES
    )


def _optional_numeric_matches(
    claim: float | None,
    expected: float | None,
) -> bool:
    if expected is None:
        return claim is None
    return claim is not None and _numeric_matches(claim, expected)


def _directional_previous_headways(
    rows: list[tuple[ContractDirection, int, str]],
) -> dict[str, float | None]:
    by_direction: dict[ContractDirection, list[tuple[int, str]]] = {}
    for direction, departure, trip_id in rows:
        by_direction.setdefault(direction, []).append((departure, trip_id))
    output: dict[str, float | None] = {}
    for directional_rows in by_direction.values():
        ordered = sorted(directional_rows, key=lambda item: (item[0], item[1]))
        previous_departure: int | None = None
        for departure, trip_id in ordered:
            output[trip_id] = (
                None if previous_departure is None else (departure - previous_departure) / 60
            )
            previous_departure = departure
    return output


def _derive_trip_facts(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> tuple[dict[str, _DerivedTripFacts], list[str]]:
    b_by_id = {trip.trip_id: trip for trip in problem.scenario_b.exact_timetable}
    previous_b = _directional_previous_headways(
        [
            (trip.direction, trip.departure_time, trip.trip_id)
            for trip in problem.scenario_b.exact_timetable
        ]
    )
    previous_c = _directional_previous_headways(
        [
            (trip.direction, trip.c_departure_time, trip.c_trip_id)
            for trip in candidate.exact_timetable
        ]
    )
    facts: dict[str, _DerivedTripFacts] = {}
    errors: list[str] = []
    for trip in candidate.exact_timetable:
        source = b_by_id.get(trip.source_b_trip_id)
        if source is None:
            continue
        derived = _DerivedTripFacts(
            shift_minutes=(trip.c_departure_time - source.departure_time) / 60,
            previous_b_headway=previous_b[trip.source_b_trip_id],
            previous_c_headway=previous_c[trip.c_trip_id],
        )
        facts[trip.c_trip_id] = derived
        if not _numeric_matches(trip.shift_minutes, derived.shift_minutes):
            errors.append("SHIFT_MINUTES_MISMATCH")
        if not _optional_numeric_matches(
            trip.previous_b_headway,
            derived.previous_b_headway,
        ):
            errors.append("PREVIOUS_B_HEADWAY_MISMATCH")
        if not _optional_numeric_matches(
            trip.previous_c_headway,
            derived.previous_c_headway,
        ):
            errors.append("PREVIOUS_C_HEADWAY_MISMATCH")
    return facts, errors


def _regularity_status(actual: tuple[int, ...]) -> str:
    if any(item == 0 for item in actual):
        return "EXCEPTIONAL"
    if not actual or max(actual) == min(actual):
        return "REGULAR"
    if max(actual) - min(actual) <= 1:
        return "BALANCED_ROUNDING"
    return "EXCEPTIONAL"


def _sequence_matches(
    claim: tuple[float, ...],
    expected: tuple[int, ...],
) -> bool:
    return len(claim) == len(expected) and all(
        _numeric_matches(claimed, derived) for claimed, derived in zip(claim, expected, strict=True)
    )


def _reconcile_regimes(
    candidate: RawScheduleCandidateV1,
) -> tuple[tuple[_ReconciledRegime, ...], list[str]]:
    errors: list[str] = []
    regime_id_counts = Counter(item.regime_id for item in candidate.headway_regimes)
    if any(count > 1 for count in regime_id_counts.values()):
        errors.append("DUPLICATE_HEADWAY_REGIME_ID")
    regime_ids = set(regime_id_counts)
    if not regime_ids:
        errors.append("MISSING_HEADWAY_REGIMES")
    if any(trip.headway_regime_id not in regime_ids for trip in candidate.exact_timetable):
        errors.append("UNKNOWN_HEADWAY_REGIME_REFERENCE")

    members_by_regime: dict[str, list[RawCandidateTripV1]] = {}
    for trip in candidate.exact_timetable:
        members_by_regime.setdefault(trip.headway_regime_id, []).append(trip)

    reconciled: list[_ReconciledRegime] = []
    for regime in candidate.headway_regimes:
        members = tuple(
            sorted(
                members_by_regime.get(regime.regime_id, ()),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        if not members:
            errors.append("ORPHAN_HEADWAY_REGIME")
            continue
        if any(item.direction != regime.direction for item in members):
            errors.append("HEADWAY_REGIME_DIRECTION_MISMATCH")
        if regime.start_time != members[0].c_departure_time:
            errors.append("HEADWAY_REGIME_START_MISMATCH")
        if regime.end_time != members[-1].c_departure_time:
            errors.append("HEADWAY_REGIME_END_MISMATCH")
        if regime.trip_count != len(members):
            errors.append("HEADWAY_REGIME_TRIP_COUNT_MISMATCH")

        gaps_seconds = tuple(
            right.c_departure_time - left.c_departure_time
            for left, right in zip(members, members[1:], strict=False)
        )
        whole_minute_sequence = all(item >= 0 and item % 60 == 0 for item in gaps_seconds)
        actual = tuple(item // 60 for item in gaps_seconds) if whole_minute_sequence else ()
        if not whole_minute_sequence or not _sequence_matches(
            regime.actual_headway_sequence,
            actual,
        ):
            errors.append("HEADWAY_REGIME_SEQUENCE_MISMATCH")
        if (
            isinstance(regime.target_headway, bool)
            or not isinstance(regime.target_headway, (int, float))
            or not math.isfinite(float(regime.target_headway))
            or regime.target_headway <= 0
        ):
            errors.append("INVALID_HEADWAY_REGIME_TARGET")

        if whole_minute_sequence:
            reconciled.append(
                _ReconciledRegime(
                    raw=regime,
                    members=members,
                    actual_headway_sequence=actual,
                    regularity_status=_regularity_status(actual),
                )
            )
    return tuple(reconciled), errors


def _candidate_scenario(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> ScenarioBInput:
    b = problem.scenario_b
    source_by_id = {trip.trip_id: trip for trip in b.exact_timetable}
    exact = tuple(
        ExactTimetableTrip(
            trip_id=trip.c_trip_id,
            direction=trip.direction,
            departure_terminal=trip.departure_terminal,
            departure_time=trip.c_departure_time,
            runtime_minutes=(
                source_by_id[trip.source_b_trip_id].runtime_minutes
                if trip.source_b_trip_id in source_by_id
                else trip.runtime_minutes
            ),
            arrival_time=(
                trip.c_departure_time + source_by_id[trip.source_b_trip_id].runtime_minutes * 60
                if trip.source_b_trip_id in source_by_id
                else trip.arrival_time
            ),
        )
        for trip in candidate.exact_timetable
    )
    return replace(b, exact_timetable=exact)


def _confidence_at_least(
    value: DemandConfidence,
    minimum: DemandConfidence,
) -> bool:
    return _CONFIDENCE_RANK[value] >= _CONFIDENCE_RANK[minimum]


def _block_trip_count(
    candidate: RawScheduleCandidateV1,
    block: DemandAnalysisBlockV1,
) -> int:
    return sum(
        block.start_time <= trip.c_departure_time < block.end_time
        and (block.direction == ContractDirection.COMBINED or trip.direction == block.direction)
        for trip in candidate.exact_timetable
    )


def _required_trips(demand: float, capacity: int, ceiling: float) -> int:
    return math.ceil(demand / (capacity * ceiling)) if demand > 0 else 0


def _candidate_block_status(
    block: DemandAnalysisBlockV1,
    trip_count: int,
    load_factor: float | None,
    policy: ScenarioBEvaluationPolicyV1,
) -> BlockSupplyStatus:
    if block.interpolation_status == InterpolationStatus.UNSUPPORTED:
        return BlockSupplyStatus.INSUFFICIENT_DATA
    if block.observed_passengers > 0 and trip_count == 0:
        return BlockSupplyStatus.NO_SERVICE_WITH_DEMAND
    if not _confidence_at_least(
        block.confidence,
        policy.minimum_authoritative_demand_confidence,
    ):
        return BlockSupplyStatus.INSUFFICIENT_DATA
    if load_factor is None:
        return BlockSupplyStatus.WITHIN_PLANNING_CEILING
    if load_factor > policy.critical_load_factor_ceiling:
        return BlockSupplyStatus.CRITICAL_ABOVE_90
    if load_factor > policy.planning_load_factor_ceiling:
        return BlockSupplyStatus.WARNING_ABOVE_85
    if load_factor < policy.low_load_review_threshold:
        return BlockSupplyStatus.LOW_LOAD_REVIEW_ONLY
    return BlockSupplyStatus.WITHIN_PLANNING_CEILING


def _candidate_block_supply(
    context: ScheduleGenerationContextV1,
    candidate: RawScheduleCandidateV1,
) -> tuple[BlockSupplyPlanV1, ...]:
    problem = context.problem
    if problem.demand_resolution is None:
        return ()
    a_by_id = {item.block_id: item for item in context.b_evaluation.a_block_supply}
    b_by_id = {item.block_id: item for item in problem.block_requirements}
    capacity = problem.scenario_b.vehicle_capacity
    rows: list[BlockSupplyPlanV1] = []
    for block in problem.analysis_blocks:
        count = _block_trip_count(candidate, block)
        nominal = count * capacity
        load_factor = block.observed_passengers / nominal if nominal > 0 else None
        required_85 = _required_trips(
            block.observed_passengers,
            capacity,
            problem.planning_load_factor_ceiling,
        )
        required_90 = _required_trips(
            block.observed_passengers,
            capacity,
            problem.critical_load_factor_ceiling,
        )
        capacity_85 = nominal * problem.planning_load_factor_ceiling
        capacity_90 = nominal * problem.critical_load_factor_ceiling
        rows.append(
            BlockSupplyPlanV1(
                scenario=ScenarioId.C,
                direction=block.direction,
                block_id=block.block_id,
                block_start=block.start_time,
                block_end=block.end_time,
                duration_minutes=block.duration_minutes,
                passenger_demand=block.observed_passengers,
                demand_rate_per_hour=block.demand_rate_per_hour,
                vehicle_capacity=capacity,
                a_trip_count=(
                    a_by_id[block.block_id].a_trip_count if block.block_id in a_by_id else None
                ),
                b_trip_count=(
                    b_by_id[block.block_id].b_trip_count if block.block_id in b_by_id else None
                ),
                c_planned_trip_count=count,
                c_actual_trip_count=count,
                trip_rate_per_hour=count * 60 / block.duration_minutes,
                required_trips_85=required_85,
                required_trips_90=required_90,
                required_trip_rate_85=required_85 * 60 / block.duration_minutes,
                required_trip_rate_90=required_90 * 60 / block.duration_minutes,
                nominal_capacity=nominal,
                capacity_at_85=capacity_85,
                capacity_at_90=capacity_90,
                load_factor=load_factor,
                shortage=max(0.0, block.observed_passengers - capacity_85),
                status=_candidate_block_status(
                    block,
                    count,
                    load_factor,
                    context.evaluation_policy,
                ),
                allocation_reason=(
                    "Validated heuristic candidate: planned and actual C counts reconcile."
                ),
                confidence=block.confidence,
            )
        )
    return tuple(rows)


def _solution_regimes(
    problem: ScheduleProblemV1,
    reconciled_regimes: tuple[_ReconciledRegime, ...],
) -> tuple[SolutionHeadwayRegimeV1, ...]:
    blocks = problem.analysis_blocks
    output: list[SolutionHeadwayRegimeV1] = []
    for reconciled in reconciled_regimes:
        regime = reconciled.raw
        covered = tuple(
            block.block_id
            for block in blocks
            if (
                block.direction == ContractDirection.COMBINED or block.direction == regime.direction
            )
            and any(
                block.start_time <= member.c_departure_time < block.end_time
                for member in reconciled.members
            )
        ) or ("OUTSIDE_DEMAND_COVERAGE",)
        actual = reconciled.actual_headway_sequence
        output.append(
            SolutionHeadwayRegimeV1(
                regime_id=regime.regime_id,
                direction=regime.direction,
                start_time=reconciled.members[0].c_departure_time,
                end_time=reconciled.members[-1].c_departure_time,
                covered_analysis_blocks=covered,
                trip_count=len(reconciled.members),
                target_service_rate=60 / regime.target_headway,
                target_headway=regime.target_headway,
                actual_headway_sequence=actual,
                transition_headways=(),
                exceptional_headways=(
                    actual if reconciled.regularity_status == "EXCEPTIONAL" else ()
                ),
                boundary_reason=regime.boundary_reason,
                regularity_status=reconciled.regularity_status,
            )
        )
    return tuple(output)


def _stock_events(events) -> tuple[StockProfileEventV1, ...]:
    return tuple(
        StockProfileEventV1(
            event_time=event.event_time,
            event_type=("VEHICLE_READY" if event.event_type == "READY" else "DEPARTURE"),
            trip_id=event.trip_id,
            stock_before=event.stock_before,
            stock_after=event.stock_after,
            arriving_or_ready_vehicle_count=(1 if event.event_type == "READY" else 0),
            departure_count=(1 if event.event_type == "DEPARTURE" else 0),
        )
        for event in events
    )


def _source_lock_errors(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> list[str]:
    source_by_id = {trip.trip_id: trip for trip in problem.scenario_b.exact_timetable}
    errors: list[str] = []
    for trip in candidate.exact_timetable:
        source = source_by_id.get(trip.source_b_trip_id)
        if source is None:
            continue
        if trip.direction != source.direction:
            errors.append("SOURCE_DIRECTION_LOCK_VIOLATION")
        if trip.departure_terminal != source.departure_terminal:
            errors.append("SOURCE_TERMINAL_LOCK_VIOLATION")
        if trip.b_departure_time != source.departure_time:
            errors.append("SOURCE_B_DEPARTURE_TRACE_MISMATCH")
        if trip.runtime_minutes != source.runtime_minutes:
            errors.append("SOURCE_RUNTIME_LOCK_VIOLATION")
        if trip.arrival_time != trip.c_departure_time + source.runtime_minutes * 60:
            errors.append("CANDIDATE_ARRIVAL_RUNTIME_MISMATCH")
    return errors


def _maximum_simultaneous_vehicle_use(assignments) -> int:
    events: list[tuple[int, int]] = []
    for assignment in assignments:
        events.append((assignment.departure_time, 1))
        events.append((assignment.ready_time, -1))
    active = 0
    maximum = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def validate_and_build_solution_v1(
    context: ScheduleGenerationContextV1,
    candidate: RawScheduleCandidateV1,
) -> CandidateValidationResultV1:
    rejection_codes: list[str] = []
    problem = context.problem
    context_validation = validate_schedule_generation_context_v1(context)
    rejection_codes.extend(issue.code for issue in context_validation.issues)
    coverage = assess_demand_coverage_v1(
        context.normalized_inputs,
        minimum_confidence=(context.evaluation_policy.minimum_authoritative_demand_confidence),
    )
    if not coverage.directional_c_generation_supported:
        rejection_codes.append(DEMAND_COVERAGE_INCOMPLETE_FOR_AUTHORITATIVE_C)
    b = problem.scenario_b
    if candidate.solver_adapter != problem.solver_adapter:
        rejection_codes.append("PROBLEM_ADAPTER_CONTEXT_MISMATCH")
    source_ids = [trip.source_b_trip_id for trip in candidate.exact_timetable]
    c_ids = [trip.c_trip_id for trip in candidate.exact_timetable]
    expected_source_ids = [trip.trip_id for trip in b.exact_timetable]
    if len(set(c_ids)) != len(c_ids):
        rejection_codes.append("DUPLICATE_C_TRIP_ID")
    if len(set(source_ids)) != len(source_ids):
        rejection_codes.append("DUPLICATE_SOURCE_B_TRIP_ID")
    if set(source_ids) != set(expected_source_ids):
        rejection_codes.append("SOURCE_B_MAPPING_NOT_ONE_TO_ONE")
    expected_candidate_fingerprint = candidate_fingerprint(
        problem_fingerprint=problem.problem_fingerprint,
        solver_adapter=candidate.solver_adapter,
        exact_timetable=candidate.exact_timetable,
        headway_regimes=candidate.headway_regimes,
    )
    if candidate.candidate_fingerprint != expected_candidate_fingerprint:
        rejection_codes.append("CANDIDATE_FINGERPRINT_MISMATCH")
    rejection_codes.extend(_source_lock_errors(problem, candidate))
    derived_trip_facts, trip_fact_errors = _derive_trip_facts(problem, candidate)
    rejection_codes.extend(trip_fact_errors)
    reconciled_regimes, regime_errors = _reconcile_regimes(candidate)
    rejection_codes.extend(regime_errors)
    if candidate.solver_status not in {
        NativeSolverStatus.OPTIMAL,
        NativeSolverStatus.FEASIBLE,
    }:
        rejection_codes.append("UNACCEPTABLE_SOLVER_STATUS")

    candidate_scenario = _candidate_scenario(problem, candidate)
    validation = validate_scenario_input(candidate_scenario)
    rejection_codes.extend(validation.error_codes)
    fleet = assess_scenario_b_fleet_v1(candidate_scenario)
    if not fleet.feasible:
        rejection_codes.append("AVAILABLE_FLEET_LIMIT_EXCEEDED")

    assignments: ContractFleetAssignmentResultV1 | None = None
    try:
        assignments = assign_contract_v1_fleet(
            candidate.exact_timetable,
            b.exact_timetable,
            b.turnaround_minutes,
            b.available_fleet_limit,
        )
    except ContractFleetAssignmentError:
        rejection_codes.append("FLEET_ASSIGNMENT_RECONCILIATION_MISMATCH")
    if assignments is not None:
        if not assignments.feasible:
            rejection_codes.append("AVAILABLE_FLEET_LIMIT_EXCEEDED")
        if assignments.vehicle_count != fleet.minimum_required_fleet:
            rejection_codes.append("FLEET_ASSIGNMENT_RECONCILIATION_MISMATCH")
        if (
            assignments.initial_fleet_terminal_1 != fleet.recommended_initial_fleet_terminal_1
            or assignments.initial_fleet_terminal_2 != fleet.recommended_initial_fleet_terminal_2
        ):
            rejection_codes.append("INITIAL_TERMINAL_STOCK_MISMATCH")
        source_by_id = {trip.trip_id: trip for trip in b.exact_timetable}
        candidate_by_id = {trip.c_trip_id: trip for trip in candidate.exact_timetable}
        for assignment in assignments.assignments:
            candidate_trip = candidate_by_id[assignment.c_trip_id]
            source_trip = source_by_id[candidate_trip.source_b_trip_id]
            expected_arrival = candidate_trip.c_departure_time + source_trip.runtime_minutes * 60
            expected_turnaround = (
                b.turnaround_minutes.terminal_1
                if assignment.arrival_terminal == DepartureTerminal.TERMINAL_1
                else b.turnaround_minutes.terminal_2
            )
            if (
                assignment.arrival_time != expected_arrival
                or assignment.ready_time != expected_arrival + expected_turnaround * 60
            ):
                rejection_codes.append("ARRIVAL_TERMINAL_TURNAROUND_MISMATCH")

    if rejection_codes:
        codes = tuple(sorted(set(rejection_codes)))
        return CandidateValidationResultV1(
            status=CandidateValidationStatus.REJECTED,
            rejection_codes=codes,
            summary="Candidate failed independent Contract V1 validation.",
            fleet_assessment=fleet,
            solution=None,
        )

    if assignments is None:  # pragma: no cover - rejection path above guarantees this
        raise AssertionError("Accepted candidate is missing Contract V1 fleet assignments")
    assignment_by_trip = {item.c_trip_id: item for item in assignments.assignments}
    solution_trips = tuple(
        SolutionTripV1(
            c_trip_id=trip.c_trip_id,
            source_b_trip_id=trip.source_b_trip_id,
            direction=trip.direction,
            departure_terminal=trip.departure_terminal,
            b_departure_time=trip.b_departure_time,
            c_departure_time=trip.c_departure_time,
            shift_minutes=derived_trip_facts[trip.c_trip_id].shift_minutes,
            previous_b_headway=(derived_trip_facts[trip.c_trip_id].previous_b_headway),
            previous_c_headway=(derived_trip_facts[trip.c_trip_id].previous_c_headway),
            headway_regime_id=trip.headway_regime_id,
            change_reason=trip.change_reason,
            vehicle_assignment=assignment_by_trip[trip.c_trip_id].vehicle_id,
        )
        for trip in candidate.exact_timetable
    )
    fleet_assignments = assignments.assignments
    block_supply = _candidate_block_supply(context, candidate)
    block_evaluation = tuple(
        BlockEvaluationV1(
            block_id=item.block_id,
            direction=item.direction,
            load_factor=item.load_factor,
            shortage=item.shortage,
            status=item.status,
            confidence=item.confidence,
        )
        for item in block_supply
    )
    shifted = [trip for trip in solution_trips if trip.shift_minutes != 0]
    provisional = ScheduleSolutionV1(
        solver_status=candidate.solver_status,
        solver_adapter=candidate.solver_adapter,
        solve_duration_seconds=candidate.solve_duration_seconds,
        solution_fingerprint="",
        source_b_fingerprint=problem.source_b_fingerprint,
        operating_parameter_locks=problem.operating_parameter_locks,
        c_block_supply_plan=block_supply,
        c_headway_regimes=_solution_regimes(problem, reconciled_regimes),
        c_exact_timetable=solution_trips,
        fleet_assignment=fleet_assignments,
        available_fleet_limit=b.available_fleet_limit,
        approved_active_fleet=b.approved_active_fleet,
        minimum_required_fleet=fleet.minimum_required_fleet,
        recommended_initial_fleet_terminal_1=(fleet.recommended_initial_fleet_terminal_1),
        recommended_initial_fleet_terminal_2=(fleet.recommended_initial_fleet_terminal_2),
        initial_fleet_positioning_mode=(InitialFleetPositioningMode.SOLVER_DETERMINED),
        fleet_margin=fleet.fleet_margin,
        maximum_simultaneous_vehicle_use=_maximum_simultaneous_vehicle_use(fleet_assignments),
        vehicle_stock_profile_terminal_1=_stock_events(fleet.terminal_1_events),
        vehicle_stock_profile_terminal_2=_stock_events(fleet.terminal_2_events),
        fleet_feasibility_status="FLEET_FEASIBLE",
        block_evaluation=block_evaluation,
        residual_overload=sum(item.shortage for item in block_supply),
        shifted_trip_count=len(shifted),
        total_shift_minutes=sum(abs(item.shift_minutes) for item in shifted),
        maximum_shift_minutes=max(
            (abs(item.shift_minutes) for item in shifted),
            default=0.0,
        ),
        explanations=(
            candidate.explanation,
            "Candidate passed independent timetable, traceability, and exact "
            "arrival-terminal fleet validation.",
            "Accepted arrivals use the locked source B per-trip runtimes and readiness "
            "uses the exact terminal-specific turnaround values.",
        ),
        limitations=candidate.limitations
        + (
            "PR-03 supports available_upper_bound fleet constraints and "
            "solver_determined initial positioning only.",
        ),
    )
    solution = replace(
        provisional,
        solution_fingerprint=canonical_sha256(
            solution_fingerprint_payload(
                provisional,
                problem_fingerprint=problem.problem_fingerprint,
            )
        ),
    )
    return CandidateValidationResultV1(
        status=CandidateValidationStatus.ACCEPTED,
        rejection_codes=(),
        summary="Candidate passed independent Contract V1 validation.",
        fleet_assessment=fleet,
        solution=solution,
    )

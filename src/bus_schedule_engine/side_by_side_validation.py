"""Deterministic legacy-versus-Contract-V1 result validation.

This application-layer adapter intentionally knows about both the legacy MVP
presentation result and the unified Contract V1 optimization result.  It does
not authorize a cutover and it never treats a legacy Scenario C as
authoritative.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum, StrEnum
from typing import TypeAlias

from .c_config import ScenarioCConfig
from .contracts_v1 import (
    ContractDirection,
    DemandConfidence,
    DimensionStatus,
    GenerationResultStatus,
    NormalizationOptions,
    RepeatabilityEvidenceV1,
    ScenarioBEvaluationPolicyV1,
    ServiceAdjustmentDecisionPolicyV1,
    SolverPolicyV1,
)
from .importer import ImportedWorkbook
from .models import (
    AnalysisBundle,
    Direction,
    EvaluationStatus,
    ScenarioResult,
)
from .optimization_service import (
    BusScheduleOptimizationResult,
    SolverChoice,
    analyze_and_optimize_schedule_v1,
)
from .service import run_analysis

LEGACY_PATH_IDENTIFIER = "LEGACY_MVP"
UNIFIED_PATH_IDENTIFIER = "UNIFIED_CONTRACT_V1"
LEGACY_SCENARIO_C_AUTHORITY = "LEGACY_DIAGNOSTIC_ONLY"
UNIFIED_SCENARIO_C_AUTHORITY = "CONTRACT_V1_INDEPENDENTLY_VALIDATED"


class ComparisonRuleV1(StrEnum):
    MUST_MATCH = "MUST_MATCH"
    REVIEW_IF_DIFFERENT = "REVIEW_IF_DIFFERENT"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ComparisonStatusV1(StrEnum):
    MATCH = "MATCH"
    DIFFERENT = "DIFFERENT"
    LEGACY_ONLY = "LEGACY_ONLY"
    UNIFIED_ONLY = "UNIFIED_ONLY"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ComparisonDispositionV1(StrEnum):
    INFORMATIONAL = "INFORMATIONAL"
    EXPECTED_BY_DESIGN = "EXPECTED_BY_DESIGN"
    EXPERT_REVIEW_REQUIRED = "EXPERT_REVIEW_REQUIRED"
    BLOCKS_CUTOVER = "BLOCKS_CUTOVER"


class ComparisonCategoryV1(StrEnum):
    SCENARIO_B_SOURCE = "SCENARIO_B_SOURCE"
    SCENARIO_B_CONCLUSIONS = "SCENARIO_B_CONCLUSIONS"
    DEMAND_AUTHORITY = "DEMAND_AUTHORITY"
    ADJUSTMENT_AND_GENERATION = "ADJUSTMENT_AND_GENERATION"
    SCENARIO_C_AUTHORITY = "SCENARIO_C_AUTHORITY"
    SCENARIO_C_TIMETABLE = "SCENARIO_C_TIMETABLE"
    OBJECTIVE_VECTOR = "OBJECTIVE_VECTOR"
    FLEET_AND_POSITIONING = "FLEET_AND_POSITIONING"


# Friendly aliases retain the terminology used in the milestone document.
ComparisonRule = ComparisonRuleV1
ComparisonStatus = ComparisonStatusV1
ComparisonDisposition = ComparisonDispositionV1

ComparisonScalar: TypeAlias = str | int | bool | None
ComparisonValue: TypeAlias = ComparisonScalar | tuple["ComparisonValue", ...]


@dataclass(frozen=True, slots=True)
class TimetableTripSnapshotV1:
    trip_id: str
    source_b_trip_id: str | None
    direction: str
    departure_terminal: str
    departure_time_seconds: int
    runtime_seconds: int
    arrival_time_seconds: int
    shift_from_b_seconds: int | None


@dataclass(frozen=True, slots=True)
class TimetableSnapshotV1:
    trip_count: int
    directional_counts: tuple[tuple[str, int], ...]
    first_departures_by_terminal: tuple[tuple[str, int | None], ...]
    last_departures_by_terminal: tuple[tuple[str, int | None], ...]
    trips: tuple[TimetableTripSnapshotV1, ...]
    timetable_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class DemandBlockSnapshotV1:
    direction: str
    block_start_seconds: int
    block_end_seconds: int
    average_daily_passenger_demand: str


@dataclass(frozen=True, slots=True)
class DemandAuthoritySnapshotV1:
    direction_mode: str | None
    observation_day_interpretation: str | None
    observation_days: int | None
    confidence: str | None
    coverage_status: str | None
    explicit_temporal_gaps: tuple[tuple[str, str, int, int], ...] | None
    directional_generation_supported: bool | None
    blocks: tuple[DemandBlockSnapshotV1, ...]


@dataclass(frozen=True, slots=True)
class FleetAssignmentSnapshotV1:
    vehicle_id: str
    trip_id: str
    departure_terminal: str
    arrival_terminal: str
    departure_time_seconds: int
    arrival_time_seconds: int
    ready_time_seconds: int


@dataclass(frozen=True, slots=True)
class HeadwayRegimeSnapshotV1:
    direction: str
    start_time_seconds: int
    end_time_seconds: int
    trip_count: int
    actual_headway_seconds: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LegacyPathSnapshotV1:
    path_identifier: str
    route_id: str
    terminal_identities: tuple[str, str]
    vehicle_capacity: int
    minimum_turnaround_seconds: tuple[tuple[str, int], ...]
    terminal_occupancy_limits: tuple[tuple[str, int | None], ...]
    scenario_b: TimetableSnapshotV1
    validation_status: str
    validation_issue_codes: tuple[str, ...]
    minimum_required_fleet: int
    active_fleet_presentation_value: int | None
    fleet_feasibility_status: str
    demand_evaluation_status: str
    headway_concern_codes: tuple[str, ...]
    terminal_occupancy_status: str
    demand_authority: DemandAuthoritySnapshotV1
    generation_feasible: bool
    generation_reason_codes_or_messages: tuple[str, ...]
    scenario_c: TimetableSnapshotV1 | None
    scenario_c_authority: str | None
    c_to_b_trace: tuple[tuple[str, str], ...]
    scenario_c_generation_status: str | None
    scenario_c_minimum_required_fleet: int | None
    scenario_c_shifted_trip_count: int | None
    scenario_c_total_absolute_shift_seconds: int | None
    scenario_c_maximum_absolute_shift_seconds: int | None
    scenario_c_headway_regimes: tuple[HeadwayRegimeSnapshotV1, ...]
    weighted_score: str | None
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnifiedPathSnapshotV1:
    path_identifier: str
    route_id: str
    terminal_identities: tuple[str, str]
    vehicle_capacity: int
    minimum_turnaround_seconds: tuple[tuple[str, int], ...]
    terminal_occupancy_limits: tuple[tuple[str, int | None], ...]
    normalized_scenario_b_fingerprint: str
    scenario_b: TimetableSnapshotV1
    scenario_b_disposition: str
    validation_status: str
    validation_issue_codes: tuple[str, ...]
    technical_feasibility_status: str
    technical_feasibility_issue_codes: tuple[str, ...]
    fleet_feasibility_status: str
    minimum_required_fleet: int
    recommended_initial_fleet_terminal_1: int
    recommended_initial_fleet_terminal_2: int
    demand_suitability_status: str
    demand_confidence: str
    headway_concern_codes: tuple[str, ...]
    terminal_occupancy_status: str
    demand_authority: DemandAuthoritySnapshotV1
    adjustment_decision: str
    selected_action: str
    solver_choice: str
    solver_attempted: bool
    heuristic_outcome_status: str | None
    ortools_outcome_status: str | None
    heuristic_native_solver_status: str | None
    ortools_native_solver_status: str | None
    validator_rejection_codes: tuple[str, ...]
    comparison_objective_names: tuple[str, ...] | None
    comparison_heuristic_vector: tuple[int, ...] | None
    comparison_ortools_vector: tuple[int, ...] | None
    comparison_recommended_solver: str | None
    comparison_reason_code: str | None
    scenario_c: TimetableSnapshotV1 | None
    scenario_c_authority: str | None
    solution_fingerprint: str | None
    b_to_c_trace: tuple[tuple[str, str], ...]
    scenario_c_minimum_required_fleet: int | None
    scenario_c_shifted_trip_count: int | None
    scenario_c_total_absolute_shift_seconds: int | None
    scenario_c_maximum_absolute_shift_seconds: int | None
    fleet_assignments: tuple[FleetAssignmentSnapshotV1, ...]
    scenario_c_headway_regimes: tuple[HeadwayRegimeSnapshotV1, ...]
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FactComparisonRecordV1:
    fact_code: str
    category: ComparisonCategoryV1
    comparison_rule: ComparisonRuleV1
    legacy_value: ComparisonValue
    unified_value: ComparisonValue
    comparison_status: ComparisonStatusV1
    disposition: ComparisonDispositionV1
    reason_code: str
    explanation: str

    def __post_init__(self) -> None:
        _validate_comparison_value(self.legacy_value)
        _validate_comparison_value(self.unified_value)


@dataclass(frozen=True, slots=True)
class SideBySideValidationReportV1:
    legacy_snapshot: LegacyPathSnapshotV1
    unified_snapshot: UnifiedPathSnapshotV1
    comparisons: tuple[FactComparisonRecordV1, ...]
    blocking_discrepancy_codes: tuple[str, ...]
    expert_review_required_codes: tuple[str, ...]
    informational_codes: tuple[str, ...]
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]

    @property
    def has_blocking_discrepancies(self) -> bool:
        return bool(self.blocking_discrepancy_codes)

    @property
    def requires_expert_review(self) -> bool:
        return bool(self.expert_review_required_codes)


_DIRECTION_ORDER = {"outbound": 0, "inbound": 1, "combined": 2}
_CATEGORY_ORDER = {value: index for index, value in enumerate(ComparisonCategoryV1)}


def _validate_comparison_value(value: ComparisonValue) -> None:
    if isinstance(value, tuple):
        for item in value:
            _validate_comparison_value(item)
        return
    if value is None or isinstance(value, str | int | bool):
        return
    raise TypeError(
        "comparison values must contain only strings, integers, booleans, None, or tuples"
    )


def _legacy_direction(direction: Direction) -> str:
    return {
        Direction.TERMINAL_1_TO_2: ContractDirection.OUTBOUND.value,
        Direction.TERMINAL_2_TO_1: ContractDirection.INBOUND.value,
        Direction.COMBINED: ContractDirection.COMBINED.value,
    }[direction]


def _stable_number(value: float | int | None) -> str | None:
    if value is None:
        return None
    return format(value, ".12g")


def _directional_counts(
    trips: tuple[TimetableTripSnapshotV1, ...],
) -> tuple[tuple[str, int], ...]:
    return tuple(
        (direction, sum(trip.direction == direction for trip in trips))
        for direction in (ContractDirection.OUTBOUND.value, ContractDirection.INBOUND.value)
    )


def _terminal_endpoints(
    trips: tuple[TimetableTripSnapshotV1, ...],
    terminals: tuple[str, str],
) -> tuple[
    tuple[tuple[str, int | None], ...],
    tuple[tuple[str, int | None], ...],
]:
    first: list[tuple[str, int | None]] = []
    last: list[tuple[str, int | None]] = []
    for terminal in terminals:
        times = sorted(
            trip.departure_time_seconds for trip in trips if trip.departure_terminal == terminal
        )
        first.append((terminal, times[0] if times else None))
        last.append((terminal, times[-1] if times else None))
    return tuple(first), tuple(last)


def _timetable(
    trips: tuple[TimetableTripSnapshotV1, ...],
    terminals: tuple[str, str],
    fingerprint: str | None,
) -> TimetableSnapshotV1:
    ordered = tuple(
        sorted(
            trips,
            key=lambda trip: (
                _DIRECTION_ORDER.get(trip.direction, 99),
                trip.departure_time_seconds,
                trip.source_b_trip_id or "",
                trip.trip_id,
            ),
        )
    )
    first, last = _terminal_endpoints(ordered, terminals)
    return TimetableSnapshotV1(
        trip_count=len(ordered),
        directional_counts=_directional_counts(ordered),
        first_departures_by_terminal=first,
        last_departures_by_terminal=last,
        trips=ordered,
        timetable_fingerprint=fingerprint or None,
    )


def _legacy_timetable(result: ScenarioResult) -> TimetableSnapshotV1:
    parameters = result.parameters
    terminals = (parameters.terminal_1_name, parameters.terminal_2_name)
    default_runtime = parameters.default_trip_runtime_minutes
    trace_by_c_id = {trace.c_trip_id: trace for trace in result.trip_traces}
    rows: list[TimetableTripSnapshotV1] = []
    for trip in result.trips:
        arrival = trip.resolved_arrival_seconds(default_runtime)
        trace = trace_by_c_id.get(trip.trip_id)
        source_departure = trip.source_b_departure_seconds
        if source_departure is None and trace is not None:
            source_departure = trace.b_departure_seconds
        shift = trip.departure_seconds - source_departure if source_departure is not None else None
        rows.append(
            TimetableTripSnapshotV1(
                trip_id=trip.trip_id,
                source_b_trip_id=trip.source_b_trip_id
                or (trip.trip_id if result.name == "B" else None),
                direction=_legacy_direction(trip.direction),
                departure_terminal=trip.departure_terminal,
                departure_time_seconds=trip.departure_seconds,
                runtime_seconds=arrival - trip.departure_seconds,
                arrival_time_seconds=arrival,
                shift_from_b_seconds=shift,
            )
        )
    return _timetable(tuple(rows), terminals, result.timetable_fingerprint)


def _unified_b_timetable(result: BusScheduleOptimizationResult) -> TimetableSnapshotV1:
    scenario = result.normalized_inputs.scenario_b
    terminals = (scenario.terminal_1_name, scenario.terminal_2_name)
    terminal_names = {
        "terminal_1": scenario.terminal_1_name,
        "terminal_2": scenario.terminal_2_name,
    }
    rows = tuple(
        TimetableTripSnapshotV1(
            trip_id=trip.trip_id,
            source_b_trip_id=trip.trip_id,
            direction=trip.direction.value,
            departure_terminal=terminal_names[trip.departure_terminal.value],
            departure_time_seconds=trip.departure_time,
            runtime_seconds=trip.runtime_minutes * 60,
            arrival_time_seconds=trip.resolved_arrival_time,
            shift_from_b_seconds=None,
        )
        for trip in scenario.exact_timetable
    )
    return _timetable(rows, terminals, _scenario_fingerprint_or_none(result))


def _scenario_fingerprint_or_none(result: BusScheduleOptimizationResult) -> str:
    """Return the supplied normalized fingerprint without recalculating it."""
    return result.normalized_inputs.scenario_b_fingerprint


def _accepted_solution(result: BusScheduleOptimizationResult):
    outcome = result.recommended_outcome
    if (
        outcome is None
        or outcome.result_status != GenerationResultStatus.SOLUTION_ACCEPTED
        or outcome.solution is None
    ):
        return None
    return outcome.solution


def _unified_c_timetable(result: BusScheduleOptimizationResult) -> TimetableSnapshotV1 | None:
    solution = _accepted_solution(result)
    if solution is None:
        return None
    scenario = result.normalized_inputs.scenario_b
    terminals = (scenario.terminal_1_name, scenario.terminal_2_name)
    terminal_names = {
        "terminal_1": scenario.terminal_1_name,
        "terminal_2": scenario.terminal_2_name,
    }
    runtime_by_source = {
        trip.trip_id: trip.runtime_minutes * 60 for trip in scenario.exact_timetable
    }
    rows: list[TimetableTripSnapshotV1] = []
    for trip in solution.c_exact_timetable:
        runtime = runtime_by_source[trip.source_b_trip_id]
        rows.append(
            TimetableTripSnapshotV1(
                trip_id=trip.c_trip_id,
                source_b_trip_id=trip.source_b_trip_id,
                direction=trip.direction.value,
                departure_terminal=terminal_names[trip.departure_terminal.value],
                departure_time_seconds=trip.c_departure_time,
                runtime_seconds=runtime,
                arrival_time_seconds=trip.c_departure_time + runtime,
                shift_from_b_seconds=trip.c_departure_time - trip.b_departure_time,
            )
        )
    return _timetable(tuple(rows), terminals, solution.solution_fingerprint)


def _legacy_demand_authority(result_b: ScenarioResult) -> DemandAuthoritySnapshotV1:
    blocks = tuple(
        sorted(
            (
                DemandBlockSnapshotV1(
                    direction=_legacy_direction(block.direction),
                    block_start_seconds=block.block_start_seconds,
                    block_end_seconds=block.block_end_seconds,
                    average_daily_passenger_demand=_stable_number(block.demand) or "0",
                )
                for block in result_b.evaluation.blocks
            ),
            key=lambda block: (
                _DIRECTION_ORDER.get(block.direction, 99),
                block.block_start_seconds,
                block.block_end_seconds,
                block.average_daily_passenger_demand,
            ),
        )
    )
    directions = {block.direction for block in blocks}
    if not directions:
        direction_mode = "no_intraday_evidence"
    elif directions == {ContractDirection.COMBINED.value}:
        direction_mode = "combined_only"
    elif ContractDirection.COMBINED.value in directions:
        direction_mode = "mixed_direction_grain"
    else:
        direction_mode = "directional_only"
    return DemandAuthoritySnapshotV1(
        direction_mode=direction_mode,
        observation_day_interpretation=None,
        observation_days=None,
        confidence=None,
        coverage_status=None,
        explicit_temporal_gaps=None,
        directional_generation_supported=None,
        blocks=blocks,
    )


def _unified_demand_authority(
    result: BusScheduleOptimizationResult,
) -> DemandAuthoritySnapshotV1:
    demand = result.normalized_inputs.observed_demand
    resolution = result.b_evaluation.demand_resolution
    coverage = resolution.coverage_assessment if resolution is not None else None
    volume_classifications = (
        sorted({item.volume_classification.value for item in demand.observations})
        if demand is not None
        else []
    )
    interpretation = (
        volume_classifications[0]
        if len(volume_classifications) == 1
        else ("mixed:" + ",".join(volume_classifications) if volume_classifications else None)
    )
    blocks = (
        tuple(
            sorted(
                (
                    DemandBlockSnapshotV1(
                        direction=block.direction.value,
                        block_start_seconds=block.start_time,
                        block_end_seconds=block.end_time,
                        average_daily_passenger_demand=(
                            _stable_number(block.observed_passengers) or "0"
                        ),
                    )
                    for block in resolution.blocks
                ),
                key=lambda block: (
                    _DIRECTION_ORDER.get(block.direction, 99),
                    block.block_start_seconds,
                    block.block_end_seconds,
                    block.average_daily_passenger_demand,
                ),
            )
        )
        if resolution is not None
        else ()
    )
    gaps = (
        tuple(
            sorted(
                (
                    gap.code,
                    gap.stream.value,
                    gap.start_time,
                    gap.end_time,
                )
                for gap in coverage.uncovered_segments
            )
        )
        if coverage is not None
        else None
    )
    return DemandAuthoritySnapshotV1(
        direction_mode=coverage.mode.value if coverage is not None else None,
        observation_day_interpretation=interpretation,
        observation_days=demand.observation_days if demand is not None else None,
        confidence=(
            resolution.contract.confidence_level.value
            if resolution is not None
            else DemandConfidence.UNKNOWN.value
        ),
        coverage_status=(
            "SUPPORTED"
            if coverage is not None and coverage.whole_b_suitability_supported
            else ("INCOMPLETE" if coverage is not None else "NOT_AVAILABLE")
        ),
        explicit_temporal_gaps=gaps,
        directional_generation_supported=(
            coverage.directional_c_generation_supported if coverage is not None else None
        ),
        blocks=blocks,
    )


def _legacy_headway_regimes(
    result_c: ScenarioResult | None,
) -> tuple[HeadwayRegimeSnapshotV1, ...]:
    if result_c is None:
        return ()
    return tuple(
        sorted(
            (
                HeadwayRegimeSnapshotV1(
                    direction=_legacy_direction(regime.direction),
                    start_time_seconds=regime.start_seconds,
                    end_time_seconds=regime.end_seconds,
                    trip_count=regime.trip_count,
                    actual_headway_seconds=tuple(
                        int(round(value * 60)) for value in regime.actual_headway_sequence
                    ),
                )
                for regime in result_c.headway_regimes
            ),
            key=lambda item: (
                _DIRECTION_ORDER.get(item.direction, 99),
                item.start_time_seconds,
                item.end_time_seconds,
                item.trip_count,
                item.actual_headway_seconds,
            ),
        )
    )


def _unified_headway_regimes(
    result: BusScheduleOptimizationResult,
) -> tuple[HeadwayRegimeSnapshotV1, ...]:
    solution = _accepted_solution(result)
    if solution is None:
        return ()
    return tuple(
        sorted(
            (
                HeadwayRegimeSnapshotV1(
                    direction=regime.direction.value,
                    start_time_seconds=regime.start_time,
                    end_time_seconds=regime.end_time,
                    trip_count=regime.trip_count,
                    actual_headway_seconds=tuple(
                        int(round(value * 60)) for value in regime.actual_headway_sequence
                    ),
                )
                for regime in solution.c_headway_regimes
            ),
            key=lambda item: (
                _DIRECTION_ORDER.get(item.direction, 99),
                item.start_time_seconds,
                item.end_time_seconds,
                item.trip_count,
                item.actual_headway_seconds,
            ),
        )
    )


def _shift_metrics(
    timetable: TimetableSnapshotV1 | None,
) -> tuple[int | None, int | None, int | None]:
    if timetable is None:
        return None, None, None
    shifts = [
        abs(trip.shift_from_b_seconds)
        for trip in timetable.trips
        if trip.shift_from_b_seconds is not None
    ]
    return (
        sum(value > 0 for value in shifts),
        sum(shifts),
        max(shifts, default=0),
    )


def _build_legacy_snapshot(bundle: AnalysisBundle) -> LegacyPathSnapshotV1:
    result_b = bundle.get("B")
    if result_b is None:
        raise ValueError("legacy analysis did not return Scenario B")
    result_c = bundle.get("C")
    parameters = result_b.parameters
    timetable_b = _legacy_timetable(result_b)
    timetable_c = _legacy_timetable(result_c) if result_c is not None else None
    shifted, total_shift, maximum_shift = _shift_metrics(timetable_c)
    headway_codes = tuple(
        sorted(
            {issue.code for issue in result_b.validation.issues if "HEADWAY" in issue.code.upper()}
            | (set(result_b.regularity.gate_failures) if result_b.regularity is not None else set())
        )
    )
    return LegacyPathSnapshotV1(
        path_identifier=LEGACY_PATH_IDENTIFIER,
        route_id=parameters.route_id,
        terminal_identities=(parameters.terminal_1_name, parameters.terminal_2_name),
        vehicle_capacity=parameters.capacity,
        minimum_turnaround_seconds=(
            ("terminal_1", parameters.effective_layover_minutes * 60),
            ("terminal_2", parameters.effective_layover_minutes * 60),
        ),
        terminal_occupancy_limits=(
            ("terminal_1", parameters.terminal_1_max_occupancy_vehicles),
            ("terminal_2", parameters.terminal_2_max_occupancy_vehicles),
        ),
        scenario_b=timetable_b,
        validation_status=result_b.validation.status,
        validation_issue_codes=tuple(sorted({issue.code for issue in result_b.validation.issues})),
        minimum_required_fleet=result_b.fleet.minimum_vehicles,
        active_fleet_presentation_value=result_b.active_vehicle_count,
        fleet_feasibility_status=("FAIL" if result_b.fleet.conflicts else "PASS"),
        demand_evaluation_status=result_b.evaluation.demand_status.value,
        headway_concern_codes=headway_codes,
        terminal_occupancy_status="NOT_EVALUATED",
        demand_authority=_legacy_demand_authority(result_b),
        generation_feasible=bundle.generation.feasible,
        generation_reason_codes_or_messages=tuple(
            sorted(
                {
                    *bundle.generation.reasons,
                    *(
                        (result_c.recommendation_reason,)
                        if result_c is not None and result_c.recommendation_reason
                        else ()
                    ),
                }
            )
        ),
        scenario_c=timetable_c,
        scenario_c_authority=LEGACY_SCENARIO_C_AUTHORITY if result_c is not None else None,
        c_to_b_trace=(
            tuple(
                sorted(
                    (trip.source_b_trip_id, trip.trip_id)
                    for trip in timetable_c.trips
                    if trip.source_b_trip_id is not None
                )
            )
            if timetable_c is not None
            else ()
        ),
        scenario_c_generation_status=(
            result_c.generation_status.value
            if result_c is not None and result_c.generation_status is not None
            else None
        ),
        scenario_c_minimum_required_fleet=(
            result_c.fleet.minimum_vehicles if result_c is not None else None
        ),
        scenario_c_shifted_trip_count=shifted,
        scenario_c_total_absolute_shift_seconds=total_shift,
        scenario_c_maximum_absolute_shift_seconds=maximum_shift,
        scenario_c_headway_regimes=_legacy_headway_regimes(result_c),
        weighted_score=_stable_number(result_c.score if result_c is not None else result_b.score),
        limitations=tuple(sorted(set(bundle.limitations))),
    )


def _dimension_issue_codes(*dimensions) -> tuple[str, ...]:
    return tuple(sorted({issue.code for dimension in dimensions for issue in dimension.issues}))


def _outcome_status(outcome) -> str | None:
    return outcome.result_status.value if outcome is not None else None


def _native_status(outcome) -> str | None:
    return (
        outcome.solver_status.value
        if outcome is not None and outcome.solver_status is not None
        else None
    )


def _validator_rejections(result: BusScheduleOptimizationResult) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                code
                for outcome in (result.heuristic_outcome, result.ortools_outcome)
                if outcome is not None and outcome.diagnostic_candidate is not None
                for code in outcome.diagnostic_candidate.rejection_codes
            }
        )
    )


def _build_unified_snapshot(
    result: BusScheduleOptimizationResult,
) -> UnifiedPathSnapshotV1:
    scenario = result.normalized_inputs.scenario_b
    evaluation = result.b_evaluation.evaluation
    fleet = result.b_evaluation.fleet_assessment
    timetable_b = _unified_b_timetable(result)
    timetable_c = _unified_c_timetable(result)
    solution = _accepted_solution(result)
    shifted, total_shift, maximum_shift = _shift_metrics(timetable_c)
    validation_dimensions = (
        evaluation.input_validity,
        evaluation.parameter_consistency,
        evaluation.technical_feasibility,
    )
    validation_status = (
        "PASS"
        if all(dimension.status == DimensionStatus.PASS for dimension in validation_dimensions)
        else "FAIL"
    )
    terminal_limits = scenario.terminal_occupancy_limits
    occupancy_issue_codes = {
        issue.code
        for issue in evaluation.technical_feasibility.issues
        if "OCCUPANCY_CAPACITY_EXCEEDED" in issue.code
    }
    terminal_occupancy_status = (
        "NOT_EVALUATED"
        if terminal_limits is None
        else ("FAIL" if occupancy_issue_codes else "PASS")
    )
    comparison = result.comparison
    return UnifiedPathSnapshotV1(
        path_identifier=UNIFIED_PATH_IDENTIFIER,
        route_id=scenario.route_id,
        terminal_identities=(scenario.terminal_1_name, scenario.terminal_2_name),
        vehicle_capacity=scenario.vehicle_capacity,
        minimum_turnaround_seconds=(
            ("terminal_1", scenario.turnaround_minutes.terminal_1 * 60),
            ("terminal_2", scenario.turnaround_minutes.terminal_2 * 60),
        ),
        terminal_occupancy_limits=(
            (
                "terminal_1",
                terminal_limits.terminal_1 if terminal_limits is not None else None,
            ),
            (
                "terminal_2",
                terminal_limits.terminal_2 if terminal_limits is not None else None,
            ),
        ),
        normalized_scenario_b_fingerprint=result.normalized_inputs.scenario_b_fingerprint,
        scenario_b=timetable_b,
        scenario_b_disposition=evaluation.disposition.value,
        validation_status=validation_status,
        validation_issue_codes=_dimension_issue_codes(*validation_dimensions),
        technical_feasibility_status=evaluation.technical_feasibility.status.value,
        technical_feasibility_issue_codes=tuple(
            sorted(
                {
                    *(issue.code for issue in evaluation.technical_feasibility.issues),
                    *result.adjustment_assessment.technical_evidence.issue_codes,
                }
            )
        ),
        fleet_feasibility_status=evaluation.fleet_feasibility.status.value,
        minimum_required_fleet=fleet.minimum_required_fleet,
        recommended_initial_fleet_terminal_1=(fleet.recommended_initial_fleet_terminal_1),
        recommended_initial_fleet_terminal_2=(fleet.recommended_initial_fleet_terminal_2),
        demand_suitability_status=evaluation.demand_suitability.status.value,
        demand_confidence=evaluation.confidence.value,
        headway_concern_codes=tuple(
            sorted({issue.code for issue in evaluation.headway_quality.issues})
        ),
        terminal_occupancy_status=terminal_occupancy_status,
        demand_authority=_unified_demand_authority(result),
        adjustment_decision=result.adjustment_assessment.primary_decision.value,
        selected_action=result.selected_action.value,
        solver_choice=result.solver_choice.value,
        solver_attempted=result.solver_attempted,
        heuristic_outcome_status=_outcome_status(result.heuristic_outcome),
        ortools_outcome_status=_outcome_status(result.ortools_outcome),
        heuristic_native_solver_status=_native_status(result.heuristic_outcome),
        ortools_native_solver_status=_native_status(result.ortools_outcome),
        validator_rejection_codes=_validator_rejections(result),
        comparison_objective_names=(comparison.objective_names if comparison is not None else None),
        comparison_heuristic_vector=(
            comparison.heuristic_vector if comparison is not None else None
        ),
        comparison_ortools_vector=(comparison.ortools_vector if comparison is not None else None),
        comparison_recommended_solver=(
            comparison.recommended_solver.value
            if comparison is not None and comparison.recommended_solver is not None
            else None
        ),
        comparison_reason_code=(comparison.reason_code if comparison is not None else None),
        scenario_c=timetable_c,
        scenario_c_authority=(UNIFIED_SCENARIO_C_AUTHORITY if solution is not None else None),
        solution_fingerprint=(solution.solution_fingerprint if solution is not None else None),
        b_to_c_trace=(
            tuple(
                sorted(
                    (trip.source_b_trip_id, trip.trip_id)
                    for trip in timetable_c.trips
                    if trip.source_b_trip_id is not None
                )
            )
            if timetable_c is not None
            else ()
        ),
        scenario_c_minimum_required_fleet=(
            solution.minimum_required_fleet if solution is not None else None
        ),
        scenario_c_shifted_trip_count=shifted,
        scenario_c_total_absolute_shift_seconds=total_shift,
        scenario_c_maximum_absolute_shift_seconds=maximum_shift,
        fleet_assignments=(
            tuple(
                sorted(
                    (
                        FleetAssignmentSnapshotV1(
                            vehicle_id=assignment.vehicle_id,
                            trip_id=assignment.c_trip_id,
                            departure_terminal=assignment.departure_terminal.value,
                            arrival_terminal=assignment.arrival_terminal.value,
                            departure_time_seconds=assignment.departure_time,
                            arrival_time_seconds=assignment.arrival_time,
                            ready_time_seconds=assignment.ready_time,
                        )
                        for assignment in solution.fleet_assignment
                    ),
                    key=lambda item: (
                        item.departure_time_seconds,
                        item.vehicle_id,
                        item.trip_id,
                    ),
                )
            )
            if solution is not None
            else ()
        ),
        scenario_c_headway_regimes=_unified_headway_regimes(result),
        explanations=tuple(result.explanations),
        limitations=tuple(result.limitations),
    )


def _comparison_status(
    rule: ComparisonRuleV1,
    legacy_value: ComparisonValue,
    unified_value: ComparisonValue,
) -> ComparisonStatusV1:
    if legacy_value is None and unified_value is None:
        return ComparisonStatusV1.NOT_AVAILABLE
    if legacy_value is None:
        return ComparisonStatusV1.UNIFIED_ONLY
    if unified_value is None:
        return ComparisonStatusV1.LEGACY_ONLY
    if rule == ComparisonRuleV1.NOT_COMPARABLE:
        return ComparisonStatusV1.NOT_APPLICABLE
    return (
        ComparisonStatusV1.MATCH if legacy_value == unified_value else ComparisonStatusV1.DIFFERENT
    )


def _comparison_disposition(
    rule: ComparisonRuleV1,
    status: ComparisonStatusV1,
) -> ComparisonDispositionV1:
    if rule == ComparisonRuleV1.NOT_COMPARABLE:
        return ComparisonDispositionV1.EXPECTED_BY_DESIGN
    if status in {
        ComparisonStatusV1.DIFFERENT,
        ComparisonStatusV1.LEGACY_ONLY,
        ComparisonStatusV1.UNIFIED_ONLY,
    }:
        return (
            ComparisonDispositionV1.BLOCKS_CUTOVER
            if rule == ComparisonRuleV1.MUST_MATCH
            else ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED
        )
    return ComparisonDispositionV1.INFORMATIONAL


def _fact_record(
    *,
    fact_code: str,
    category: ComparisonCategoryV1,
    rule: ComparisonRuleV1,
    legacy_value: ComparisonValue,
    unified_value: ComparisonValue,
    reason_code: str | None = None,
    explanation: str | None = None,
    status: ComparisonStatusV1 | None = None,
    disposition: ComparisonDispositionV1 | None = None,
) -> FactComparisonRecordV1:
    effective_status = status or _comparison_status(rule, legacy_value, unified_value)
    effective_disposition = disposition or _comparison_disposition(rule, effective_status)
    effective_reason = reason_code or (
        f"{fact_code}_MATCH"
        if effective_status == ComparisonStatusV1.MATCH
        else f"{fact_code}_MISMATCH"
    )
    effective_explanation = explanation or (
        f"{fact_code} has the same semantic value on both paths."
        if effective_status == ComparisonStatusV1.MATCH
        else f"{fact_code} differs or is unavailable on one execution path."
    )
    return FactComparisonRecordV1(
        fact_code=fact_code,
        category=category,
        comparison_rule=rule,
        legacy_value=legacy_value,
        unified_value=unified_value,
        comparison_status=effective_status,
        disposition=effective_disposition,
        reason_code=effective_reason,
        explanation=effective_explanation,
    )


def _trip_value(
    timetable: TimetableSnapshotV1,
    attribute: str,
) -> ComparisonValue:
    return tuple(
        (
            trip.source_b_trip_id or trip.trip_id,
            getattr(trip, attribute),
        )
        for trip in sorted(
            timetable.trips,
            key=lambda item: (item.source_b_trip_id or item.trip_id, item.trip_id),
        )
    )


def _source_trip_ids(timetable: TimetableSnapshotV1) -> tuple[str, ...]:
    return tuple(sorted(trip.source_b_trip_id or trip.trip_id for trip in timetable.trips))


def _legacy_demand_semantic(status: str) -> str:
    mapping = {
        EvaluationStatus.SUITABLE.value: "SUITABLE",
        EvaluationStatus.MONITOR.value: "MONITOR",
        EvaluationStatus.UNSUITABLE.value: "UNSUITABLE",
        EvaluationStatus.NO_SERVICE_WITH_DEMAND.value: "UNSUITABLE",
        EvaluationStatus.INSUFFICIENT_DATA.value: "INSUFFICIENT_DATA",
    }
    return mapping.get(status, status)


def _unified_demand_semantic(status: str) -> str:
    return {
        DimensionStatus.PASS.value: "SUITABLE",
        DimensionStatus.WARNING.value: "MONITOR",
        DimensionStatus.FAIL.value: "UNSUITABLE",
        DimensionStatus.INSUFFICIENT_DATA.value: "INSUFFICIENT_DATA",
        DimensionStatus.NOT_EVALUATED.value: "NOT_EVALUATED",
    }[status]


def _block_keys(authority: DemandAuthoritySnapshotV1) -> ComparisonValue:
    return tuple(
        (
            block.direction,
            block.block_start_seconds,
            block.block_end_seconds,
        )
        for block in authority.blocks
    )


def _block_values(authority: DemandAuthoritySnapshotV1) -> ComparisonValue:
    return tuple(
        (
            block.direction,
            block.block_start_seconds,
            block.block_end_seconds,
            block.average_daily_passenger_demand,
        )
        for block in authority.blocks
    )


def _headway_value(
    regimes: tuple[HeadwayRegimeSnapshotV1, ...],
) -> ComparisonValue:
    return tuple(
        (
            regime.direction,
            regime.start_time_seconds,
            regime.end_time_seconds,
            regime.trip_count,
            regime.actual_headway_seconds,
        )
        for regime in regimes
    )


def _build_comparisons(
    legacy: LegacyPathSnapshotV1,
    unified: UnifiedPathSnapshotV1,
) -> tuple[FactComparisonRecordV1, ...]:
    records: list[FactComparisonRecordV1] = []

    source_facts: tuple[tuple[str, ComparisonValue, ComparisonValue], ...] = (
        ("SCENARIO_B_ROUTE_ID", legacy.route_id, unified.route_id),
        (
            "SCENARIO_B_TERMINAL_IDENTITIES",
            legacy.terminal_identities,
            unified.terminal_identities,
        ),
        (
            "SCENARIO_B_TOTAL_TRIP_COUNT",
            legacy.scenario_b.trip_count,
            unified.scenario_b.trip_count,
        ),
        (
            "SCENARIO_B_DIRECTIONAL_TRIP_COUNTS",
            legacy.scenario_b.directional_counts,
            unified.scenario_b.directional_counts,
        ),
        (
            "SCENARIO_B_FIRST_DEPARTURES",
            legacy.scenario_b.first_departures_by_terminal,
            unified.scenario_b.first_departures_by_terminal,
        ),
        (
            "SCENARIO_B_LAST_DEPARTURES",
            legacy.scenario_b.last_departures_by_terminal,
            unified.scenario_b.last_departures_by_terminal,
        ),
        (
            "SCENARIO_B_SOURCE_TRIP_IDS",
            _source_trip_ids(legacy.scenario_b),
            _source_trip_ids(unified.scenario_b),
        ),
        (
            "SCENARIO_B_TRIP_DIRECTIONS",
            _trip_value(legacy.scenario_b, "direction"),
            _trip_value(unified.scenario_b, "direction"),
        ),
        (
            "SCENARIO_B_TRIP_DEPARTURE_TERMINALS",
            _trip_value(legacy.scenario_b, "departure_terminal"),
            _trip_value(unified.scenario_b, "departure_terminal"),
        ),
        (
            "SCENARIO_B_TRIP_DEPARTURE_TIMES",
            _trip_value(legacy.scenario_b, "departure_time_seconds"),
            _trip_value(unified.scenario_b, "departure_time_seconds"),
        ),
        (
            "SCENARIO_B_TRIP_RUNTIMES",
            _trip_value(legacy.scenario_b, "runtime_seconds"),
            _trip_value(unified.scenario_b, "runtime_seconds"),
        ),
        ("SCENARIO_B_VEHICLE_CAPACITY", legacy.vehicle_capacity, unified.vehicle_capacity),
        (
            "SCENARIO_B_MINIMUM_TURNAROUND_VALUES",
            legacy.minimum_turnaround_seconds,
            unified.minimum_turnaround_seconds,
        ),
        (
            "SCENARIO_B_TERMINAL_OCCUPANCY_LIMITS",
            legacy.terminal_occupancy_limits,
            unified.terminal_occupancy_limits,
        ),
    )
    records.extend(
        _fact_record(
            fact_code=code,
            category=ComparisonCategoryV1.SCENARIO_B_SOURCE,
            rule=ComparisonRuleV1.MUST_MATCH,
            legacy_value=legacy_value,
            unified_value=unified_value,
        )
        for code, legacy_value, unified_value in source_facts
    )

    conclusion_facts: tuple[tuple[str, ComparisonValue, ComparisonValue], ...] = (
        (
            "SCENARIO_B_OVERALL_VALIDITY",
            legacy.validation_status,
            unified.validation_status,
        ),
        (
            "SCENARIO_B_VALIDATION_ISSUE_CODES",
            legacy.validation_issue_codes,
            unified.validation_issue_codes,
        ),
        (
            "SCENARIO_B_MINIMUM_REQUIRED_FLEET",
            legacy.minimum_required_fleet,
            unified.minimum_required_fleet,
        ),
        (
            "SCENARIO_B_FLEET_FEASIBILITY",
            legacy.fleet_feasibility_status,
            unified.fleet_feasibility_status,
        ),
        (
            "SCENARIO_B_DEMAND_SUITABILITY",
            _legacy_demand_semantic(legacy.demand_evaluation_status),
            _unified_demand_semantic(unified.demand_suitability_status),
        ),
        (
            "SCENARIO_B_HEADWAY_CONCERNS",
            legacy.headway_concern_codes,
            unified.headway_concern_codes,
        ),
        (
            "SCENARIO_B_TERMINAL_OCCUPANCY_STATUS",
            legacy.terminal_occupancy_status,
            unified.terminal_occupancy_status,
        ),
    )
    records.extend(
        _fact_record(
            fact_code=code,
            category=ComparisonCategoryV1.SCENARIO_B_CONCLUSIONS,
            rule=ComparisonRuleV1.REVIEW_IF_DIFFERENT,
            legacy_value=legacy_value,
            unified_value=unified_value,
        )
        for code, legacy_value, unified_value in conclusion_facts
    )

    legacy_demand = legacy.demand_authority
    unified_demand = unified.demand_authority
    demand_facts: tuple[tuple[str, ComparisonValue, ComparisonValue], ...] = (
        (
            "DEMAND_DIRECTION_MODE",
            legacy_demand.direction_mode,
            unified_demand.direction_mode,
        ),
        (
            "DEMAND_OBSERVATION_DAY_INTERPRETATION",
            legacy_demand.observation_day_interpretation,
            unified_demand.observation_day_interpretation,
        ),
        (
            "DEMAND_OBSERVATION_DAYS",
            legacy_demand.observation_days,
            unified_demand.observation_days,
        ),
        ("DEMAND_CONFIDENCE", legacy_demand.confidence, unified_demand.confidence),
        (
            "DEMAND_COVERAGE_STATUS",
            legacy_demand.coverage_status,
            unified_demand.coverage_status,
        ),
        (
            "DEMAND_EXPLICIT_TEMPORAL_GAPS",
            legacy_demand.explicit_temporal_gaps,
            unified_demand.explicit_temporal_gaps,
        ),
        (
            "DEMAND_DIRECTIONAL_GENERATION_SUPPORTED",
            legacy_demand.directional_generation_supported,
            unified_demand.directional_generation_supported,
        ),
    )
    records.extend(
        _fact_record(
            fact_code=code,
            category=ComparisonCategoryV1.DEMAND_AUTHORITY,
            rule=ComparisonRuleV1.REVIEW_IF_DIFFERENT,
            legacy_value=legacy_value,
            unified_value=unified_value,
        )
        for code, legacy_value, unified_value in demand_facts
    )
    legacy_grain = _block_keys(legacy_demand)
    unified_grain = _block_keys(unified_demand)
    grain_matches = legacy_grain == unified_grain
    records.append(
        _fact_record(
            fact_code="DEMAND_BLOCK_GRAIN",
            category=ComparisonCategoryV1.DEMAND_AUTHORITY,
            rule=ComparisonRuleV1.REVIEW_IF_DIFFERENT,
            legacy_value=legacy_grain,
            unified_value=unified_grain,
            reason_code=(
                "DEMAND_BLOCK_GRAIN_MATCH" if grain_matches else "DEMAND_BLOCK_GRAIN_DIFFERS"
            ),
            explanation=(
                "Demand blocks use identical direction and exact interval boundaries."
                if grain_matches
                else "Demand block grains differ; the adapter does not aggregate or split them."
            ),
        )
    )
    records.append(
        _fact_record(
            fact_code="DEMAND_BLOCK_VALUES",
            category=ComparisonCategoryV1.DEMAND_AUTHORITY,
            rule=(
                ComparisonRuleV1.REVIEW_IF_DIFFERENT
                if grain_matches
                else ComparisonRuleV1.NOT_COMPARABLE
            ),
            legacy_value=_block_values(legacy_demand),
            unified_value=_block_values(unified_demand),
            reason_code=(
                None if grain_matches else "DEMAND_BLOCK_VALUES_NOT_COMPARED_DIFFERENT_GRAIN"
            ),
            explanation=(
                None
                if grain_matches
                else "Passenger demand is not forced onto different block boundaries."
            ),
        )
    )

    records.extend(
        (
            _fact_record(
                fact_code="LEGACY_GENERATION_BEHAVIOR",
                category=ComparisonCategoryV1.ADJUSTMENT_AND_GENERATION,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=(
                    legacy.generation_feasible,
                    legacy.scenario_c_generation_status,
                    legacy.generation_reason_codes_or_messages,
                ),
                unified_value=None,
                reason_code="LEGACY_GENERATOR_DECISION_CONTRACT_NOT_COMPARABLE",
                explanation="The legacy generator does not implement the unified adjustment contract.",
            ),
            _fact_record(
                fact_code="UNIFIED_ADJUSTMENT_DECISION",
                category=ComparisonCategoryV1.ADJUSTMENT_AND_GENERATION,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=None,
                unified_value=unified.adjustment_decision,
                reason_code="UNIFIED_ADJUSTMENT_DECISION_ONLY",
                explanation="The canonical adjustment decision exists only on the unified path.",
                disposition=ComparisonDispositionV1.INFORMATIONAL,
            ),
            _fact_record(
                fact_code="UNIFIED_SELECTED_ACTION",
                category=ComparisonCategoryV1.ADJUSTMENT_AND_GENERATION,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=None,
                unified_value=unified.selected_action,
                reason_code="UNIFIED_SELECTED_ACTION_ONLY",
                explanation="The selected optimization action is unified-path authority.",
                disposition=ComparisonDispositionV1.INFORMATIONAL,
            ),
            _fact_record(
                fact_code="UNIFIED_SOLVER_ATTEMPTED",
                category=ComparisonCategoryV1.ADJUSTMENT_AND_GENERATION,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=None,
                unified_value=unified.solver_attempted,
                reason_code="UNIFIED_SOLVER_ATTEMPT_STATUS_ONLY",
                explanation="Solver-attempt status is preserved without inferring legacy equivalence.",
                disposition=ComparisonDispositionV1.INFORMATIONAL,
            ),
            _fact_record(
                fact_code="UNIFIED_SOLVER_OUTCOMES",
                category=ComparisonCategoryV1.ADJUSTMENT_AND_GENERATION,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=None,
                unified_value=(
                    unified.heuristic_outcome_status,
                    unified.ortools_outcome_status,
                    unified.heuristic_native_solver_status,
                    unified.ortools_native_solver_status,
                    unified.validator_rejection_codes,
                ),
                reason_code="UNIFIED_SOLVER_OUTCOMES_ONLY",
                explanation="Native and validation outcomes are preserved only from returned results.",
                disposition=ComparisonDispositionV1.INFORMATIONAL,
            ),
        )
    )

    legacy_has_c = legacy.scenario_c is not None
    unified_has_c = unified.scenario_c is not None
    if legacy_has_c and not unified_has_c:
        c_reason = "LEGACY_C_WITHOUT_UNIFIED_AUTHORITY"
        c_status = ComparisonStatusV1.DIFFERENT
        c_disposition = ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED
        c_explanation = (
            "Legacy generated diagnostic Scenario C, but the unified path has no "
            "independently accepted Scenario C."
        )
    elif unified_has_c and not legacy_has_c:
        c_reason = "UNIFIED_ACCEPTED_C_WITHOUT_LEGACY_C"
        c_status = ComparisonStatusV1.DIFFERENT
        c_disposition = ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED
        c_explanation = (
            "The unified path has an independently accepted Scenario C while legacy has none."
        )
    elif legacy_has_c and unified_has_c:
        c_reason = "BOTH_PATHS_HAVE_SCENARIO_C"
        c_status = ComparisonStatusV1.MATCH
        c_disposition = ComparisonDispositionV1.INFORMATIONAL
        c_explanation = (
            "Both paths returned Scenario C; semantic timetable facts are compared below."
        )
    else:
        c_reason = "NO_SCENARIO_C_ON_EITHER_PATH"
        c_status = ComparisonStatusV1.NOT_APPLICABLE
        c_disposition = ComparisonDispositionV1.INFORMATIONAL
        c_explanation = "Neither path returned Scenario C."
    records.append(
        _fact_record(
            fact_code="SCENARIO_C_EXISTENCE",
            category=ComparisonCategoryV1.SCENARIO_C_AUTHORITY,
            rule=ComparisonRuleV1.REVIEW_IF_DIFFERENT,
            legacy_value=legacy_has_c,
            unified_value=unified_has_c,
            reason_code=c_reason,
            explanation=c_explanation,
            status=c_status,
            disposition=c_disposition,
        )
    )
    records.append(
        _fact_record(
            fact_code="SCENARIO_C_AUTHORITY",
            category=ComparisonCategoryV1.SCENARIO_C_AUTHORITY,
            rule=ComparisonRuleV1.NOT_COMPARABLE,
            legacy_value=legacy.scenario_c_authority,
            unified_value=unified.scenario_c_authority,
            reason_code="SCENARIO_C_AUTHORITIES_DIFFER_BY_DESIGN",
            explanation=(
                "Legacy C is diagnostic-only; unified C is authoritative only after "
                "independent validation."
            ),
        )
    )

    if legacy.scenario_c is not None and unified.scenario_c is not None:
        legacy_c = legacy.scenario_c
        unified_c = unified.scenario_c
        c_facts: tuple[tuple[str, ComparisonValue, ComparisonValue], ...] = (
            ("SCENARIO_C_TOTAL_TRIP_COUNT", legacy_c.trip_count, unified_c.trip_count),
            (
                "SCENARIO_C_DIRECTIONAL_TRIP_COUNTS",
                legacy_c.directional_counts,
                unified_c.directional_counts,
            ),
            (
                "SCENARIO_C_FIRST_DEPARTURES",
                legacy_c.first_departures_by_terminal,
                unified_c.first_departures_by_terminal,
            ),
            (
                "SCENARIO_C_LAST_DEPARTURES",
                legacy_c.last_departures_by_terminal,
                unified_c.last_departures_by_terminal,
            ),
            (
                "SCENARIO_C_SOURCE_MAPPING",
                _source_trip_ids(legacy_c),
                _source_trip_ids(unified_c),
            ),
            (
                "SCENARIO_C_PER_SOURCE_DEPARTURE_TIMES",
                _trip_value(legacy_c, "departure_time_seconds"),
                _trip_value(unified_c, "departure_time_seconds"),
            ),
            (
                "SCENARIO_C_PER_SOURCE_RUNTIMES",
                _trip_value(legacy_c, "runtime_seconds"),
                _trip_value(unified_c, "runtime_seconds"),
            ),
            (
                "SCENARIO_C_SHIFTED_TRIP_COUNT",
                legacy.scenario_c_shifted_trip_count,
                unified.scenario_c_shifted_trip_count,
            ),
            (
                "SCENARIO_C_TOTAL_ABSOLUTE_SHIFT",
                legacy.scenario_c_total_absolute_shift_seconds,
                unified.scenario_c_total_absolute_shift_seconds,
            ),
            (
                "SCENARIO_C_MAXIMUM_ABSOLUTE_SHIFT",
                legacy.scenario_c_maximum_absolute_shift_seconds,
                unified.scenario_c_maximum_absolute_shift_seconds,
            ),
            (
                "SCENARIO_C_MINIMUM_REQUIRED_FLEET",
                legacy.scenario_c_minimum_required_fleet,
                unified.scenario_c_minimum_required_fleet,
            ),
            (
                "SCENARIO_C_HEADWAY_REGIMES",
                _headway_value(legacy.scenario_c_headway_regimes),
                _headway_value(unified.scenario_c_headway_regimes),
            ),
        )
        records.extend(
            _fact_record(
                fact_code=code,
                category=ComparisonCategoryV1.SCENARIO_C_TIMETABLE,
                rule=ComparisonRuleV1.REVIEW_IF_DIFFERENT,
                legacy_value=legacy_value,
                unified_value=unified_value,
            )
            for code, legacy_value, unified_value in c_facts
        )

    records.extend(
        (
            _fact_record(
                fact_code="LEGACY_WEIGHTED_SCORE",
                category=ComparisonCategoryV1.OBJECTIVE_VECTOR,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=legacy.weighted_score,
                unified_value=None,
                reason_code="LEGACY_WEIGHTED_SCORE_NOT_COMPARABLE",
                explanation="The legacy weighted score is not a cross-path quality authority.",
            ),
            _fact_record(
                fact_code="UNIFIED_OBJECTIVE_VECTOR",
                category=ComparisonCategoryV1.OBJECTIVE_VECTOR,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=None,
                unified_value=(
                    (
                        unified.comparison_objective_names,
                        unified.comparison_heuristic_vector,
                        unified.comparison_ortools_vector,
                        unified.comparison_recommended_solver,
                        unified.comparison_reason_code,
                    )
                    if unified.comparison_objective_names is not None
                    else None
                ),
                reason_code="UNIFIED_OBJECTIVE_VECTOR_ONLY",
                explanation=(
                    "The existing unified comparison vector is preserved; no solver problem "
                    "is rebuilt and absent vectors remain None."
                ),
                disposition=ComparisonDispositionV1.INFORMATIONAL,
            ),
            _fact_record(
                fact_code="UNIFIED_INITIAL_FLEET_TERMINAL_1",
                category=ComparisonCategoryV1.FLEET_AND_POSITIONING,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=None,
                unified_value=unified.recommended_initial_fleet_terminal_1,
                reason_code="UNIFIED_INITIAL_POSITIONING_ONLY",
                explanation="Initial Terminal 1 positioning is unified-only authority.",
                disposition=ComparisonDispositionV1.INFORMATIONAL,
            ),
            _fact_record(
                fact_code="UNIFIED_INITIAL_FLEET_TERMINAL_2",
                category=ComparisonCategoryV1.FLEET_AND_POSITIONING,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=None,
                unified_value=unified.recommended_initial_fleet_terminal_2,
                reason_code="UNIFIED_INITIAL_POSITIONING_ONLY",
                explanation="Initial Terminal 2 positioning is unified-only authority.",
                disposition=ComparisonDispositionV1.INFORMATIONAL,
            ),
            _fact_record(
                fact_code="UNIFIED_ACCEPTED_SOLUTION_FINGERPRINT",
                category=ComparisonCategoryV1.SCENARIO_C_AUTHORITY,
                rule=ComparisonRuleV1.NOT_COMPARABLE,
                legacy_value=None,
                unified_value=unified.solution_fingerprint,
                reason_code="UNIFIED_ACCEPTED_SOLUTION_FINGERPRINT_ONLY",
                explanation="An accepted solution fingerprint is preserved only when one exists.",
                disposition=ComparisonDispositionV1.INFORMATIONAL,
            ),
        )
    )

    return tuple(
        sorted(
            records,
            key=lambda record: (
                _CATEGORY_ORDER[record.category],
                record.fact_code,
                record.reason_code,
            ),
        )
    )


def _report(
    legacy: LegacyPathSnapshotV1,
    unified: UnifiedPathSnapshotV1,
) -> SideBySideValidationReportV1:
    comparisons = _build_comparisons(legacy, unified)
    blocking = tuple(
        sorted(
            {
                record.reason_code
                for record in comparisons
                if record.disposition == ComparisonDispositionV1.BLOCKS_CUTOVER
            }
        )
    )
    review = tuple(
        sorted(
            {
                record.reason_code
                for record in comparisons
                if record.disposition == ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED
            }
        )
    )
    informational = tuple(
        sorted(
            {
                record.reason_code
                for record in comparisons
                if record.disposition
                in {
                    ComparisonDispositionV1.INFORMATIONAL,
                    ComparisonDispositionV1.EXPECTED_BY_DESIGN,
                }
            }
        )
    )
    return SideBySideValidationReportV1(
        legacy_snapshot=legacy,
        unified_snapshot=unified,
        comparisons=comparisons,
        blocking_discrepancy_codes=blocking,
        expert_review_required_codes=review,
        informational_codes=informational,
        explanations=(
            "Scenario B source and lock mismatches block any later presentation cutover.",
            "Conclusion and Scenario C differences remain visible for expert review.",
            "This report is evidence only and never authorizes cutover.",
        ),
        limitations=(
            "Legacy and Contract V1 timetable fingerprints use different profiles and are not compared.",
            "Legacy Scenario C is diagnostic-only even when its facts match an accepted unified solution.",
            "The legacy weighted score is not comparable to the unified 15-stage objective vector.",
            "No chart, XLSX, UI, solver, validation, demand, fleet, or headway logic is rerun by snapshots.",
        ),
    )


def run_side_by_side_validation_v1(
    imported: ImportedWorkbook,
    normalization_options: NormalizationOptions,
    *,
    solver_choice: SolverChoice = SolverChoice.HEURISTIC,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    decision_policy: ServiceAdjustmentDecisionPolicyV1 | None = None,
    repeatability_evidence: RepeatabilityEvidenceV1 | None = None,
    heuristic_config: ScenarioCConfig | None = None,
    solver_policy: SolverPolicyV1 | None = None,
) -> SideBySideValidationReportV1:
    """Run isolated legacy and unified paths and compare returned-result facts."""
    legacy_input = deepcopy(imported)
    unified_input = deepcopy(imported)
    legacy_result = run_analysis(legacy_input)
    unified_result = analyze_and_optimize_schedule_v1(
        unified_input,
        normalization_options,
        solver_choice=solver_choice,
        evaluation_policy=evaluation_policy,
        decision_policy=decision_policy,
        repeatability_evidence=repeatability_evidence,
        heuristic_config=heuristic_config,
        solver_policy=solver_policy,
    )
    legacy_snapshot = _build_legacy_snapshot(legacy_result)
    unified_snapshot = _build_unified_snapshot(unified_result)
    return _report(legacy_snapshot, unified_snapshot)


def _serialize(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def side_by_side_report_to_dict(
    report: SideBySideValidationReportV1,
) -> dict[str, object]:
    """Serialize a report deterministically with enum values and ordered arrays."""
    if not isinstance(report, SideBySideValidationReportV1):
        raise TypeError("report must be a SideBySideValidationReportV1")
    serialized = _serialize(report)
    if not isinstance(serialized, dict):
        raise AssertionError("report serialization must produce a dictionary")
    return serialized


__all__ = [
    "ComparisonCategoryV1",
    "ComparisonDisposition",
    "ComparisonDispositionV1",
    "ComparisonRule",
    "ComparisonRuleV1",
    "ComparisonStatus",
    "ComparisonStatusV1",
    "DemandAuthoritySnapshotV1",
    "DemandBlockSnapshotV1",
    "FactComparisonRecordV1",
    "FleetAssignmentSnapshotV1",
    "HeadwayRegimeSnapshotV1",
    "LegacyPathSnapshotV1",
    "SideBySideValidationReportV1",
    "TimetableSnapshotV1",
    "TimetableTripSnapshotV1",
    "UnifiedPathSnapshotV1",
    "run_side_by_side_validation_v1",
    "side_by_side_report_to_dict",
]

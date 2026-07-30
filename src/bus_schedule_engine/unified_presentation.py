"""Validation-only presentation projection for unified Contract V1 results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias

from .contracts_v1 import (
    DepartureTerminal,
    GenerationResultStatus,
    ScenarioId,
)
from .contracts_v1.evaluation import BlockSupplyPlanV1, EvaluationDimensionV1
from .contracts_v1.models import ScenarioInputV1
from .contracts_v1.solver_models import ScheduleSolutionV1
from .contracts_v1.terminal_occupancy import (
    TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED,
    TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED,
    TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,
)
from .optimization_service import BusScheduleOptimizationResult

if TYPE_CHECKING:
    from .side_by_side_validation import SideBySideValidationReportV1

PRESENTATION_MODE_VALIDATION_ONLY = "VALIDATION_ONLY"
SCENARIO_C_AUTHORITY_ACCEPTED = "CONTRACT_V1_INDEPENDENTLY_VALIDATED"
DISPLAY_DERIVED = "DISPLAY_DERIVED"
UNIFIED_LIMITATIONS_REQUIRE_EXPERT_REVIEW = "UNIFIED_LIMITATIONS_REQUIRE_EXPERT_REVIEW"

_DIRECTION_ORDER = {"outbound": 0, "inbound": 1, "combined": 2}
_SCENARIO_ORDER = {"A": 0, "B": 1, "C": 2}
_DIMENSION_ORDER = (
    "input_validity",
    "parameter_consistency",
    "technical_feasibility",
    "demand_suitability",
    "fleet_feasibility",
    "headway_quality",
)

ComparisonScalar: TypeAlias = str | int | bool | None
ComparisonValue: TypeAlias = ComparisonScalar | tuple["ComparisonValue", ...]


class UnifiedPresentationConsistencyError(ValueError):
    """Raised when supplied unified and validation facts cannot be reconciled."""


@dataclass(frozen=True, slots=True)
class PresentationTripV1:
    scenario_id: str
    trip_id: str
    source_b_trip_id: str | None
    direction: str
    departure_terminal: str
    arrival_terminal: str
    departure_time_seconds: int
    arrival_time_seconds: int
    runtime_seconds: int
    b_departure_time_seconds: int | None
    shift_minutes: float | None
    vehicle_assignment: str | None
    headway_regime_id: str | None
    change_reason: str | None


@dataclass(frozen=True, slots=True)
class PresentationScenarioV1:
    scenario_id: str
    source_fingerprint: str | None
    trips: tuple[PresentationTripV1, ...]


@dataclass(frozen=True, slots=True)
class PresentationBlockV1:
    block_id: str
    direction: str
    block_start_seconds: int
    block_end_seconds: int
    passenger_demand: float
    confidence: str
    vehicle_capacity: int
    a_trip_count: int | None
    b_trip_count: int | None
    c_actual_trip_count: int | None
    required_trips_85: int
    required_trips_90: int
    b_nominal_capacity: float
    c_nominal_capacity: float | None
    b_load_factor: float | None
    c_load_factor: float | None
    b_shortage: float
    c_shortage: float | None
    b_status: str
    c_status: str | None
    allocation_reason: str
    c_allocation_reason: str | None


@dataclass(frozen=True, slots=True)
class PresentationDimensionV1:
    dimension_name: str
    status: str
    confidence: str
    explanation: str
    issue_codes: tuple[str, ...]
    issue_severities: tuple[str, ...]
    issue_messages: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PresentationOutcomeV1:
    b_disposition: str
    adjustment_decision: str
    selected_action: str
    solver_choice: str
    solver_attempted: bool
    heuristic_result_status: str | None
    ortools_result_status: str | None
    heuristic_native_solver_status: str | None
    ortools_native_solver_status: str | None
    validator_rejection_codes: tuple[str, ...]
    comparison_objective_names: tuple[str, ...] | None
    heuristic_objective_vector: tuple[int, ...] | None
    ortools_objective_vector: tuple[int, ...] | None
    recommended_solver: str | None
    comparison_reason: str | None
    accepted_c_exists: bool
    accepted_c_authority: str | None
    accepted_solution_fingerprint: str | None
    accepted_outcome_fingerprint: str | None
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PresentationFleetAssignmentV1:
    vehicle_id: str
    trip_id: str
    departure_terminal: str
    arrival_terminal: str
    departure_time_seconds: int
    arrival_time_seconds: int
    ready_time_seconds: int


@dataclass(frozen=True, slots=True)
class PresentationInitialFleetV1:
    terminal_1_vehicle_count: int
    terminal_2_vehicle_count: int
    positioning_mode: str
    available_fleet_limit: int
    approved_active_fleet: int | None
    minimum_required_fleet: int
    fleet_margin: int
    maximum_simultaneous_vehicle_use: int
    fleet_feasibility_status: str


@dataclass(frozen=True, slots=True)
class PresentationHeadwayRegimeV1:
    regime_id: str
    direction: str
    start_time_seconds: int
    end_time_seconds: int
    covered_analysis_blocks: tuple[str, ...]
    trip_count: int
    target_service_rate: float
    target_headway: float
    actual_headway_sequence: tuple[int, ...]
    transition_headways: tuple[int, ...]
    exceptional_headways: tuple[int, ...]
    boundary_reason: str
    regularity_status: str


@dataclass(frozen=True, slots=True)
class PresentationDemandGapV1:
    code: str
    direction: str
    start_time_seconds: int
    end_time_seconds: int


@dataclass(frozen=True, slots=True)
class PresentationDiscrepancyV1:
    fact_code: str
    category: str
    comparison_rule: str
    legacy_value: ComparisonValue
    unified_value: ComparisonValue
    comparison_status: str
    disposition: str
    reason_code: str
    explanation: str


@dataclass(frozen=True, slots=True)
class UnifiedPresentationBundleV1:
    presentation_mode: str
    presentation_fingerprint: str
    route_id: str
    route_name: str
    route_type: str
    terminal_1_name: str
    terminal_2_name: str
    source_id: str
    imported_at: str
    source_a_fingerprint: str | None
    source_b_fingerprint: str
    accepted_solution_fingerprint: str | None
    accepted_outcome_fingerprint: str | None
    cutover_blocked: bool
    requires_expert_review: bool
    blocking_discrepancy_codes: tuple[str, ...]
    expert_review_required_codes: tuple[str, ...]
    informational_codes: tuple[str, ...]
    scenarios: tuple[PresentationScenarioV1, ...]
    blocks: tuple[PresentationBlockV1, ...]
    dimensions: tuple[PresentationDimensionV1, ...]
    outcome: PresentationOutcomeV1
    fleet_assignments: tuple[PresentationFleetAssignmentV1, ...]
    initial_fleet: PresentationInitialFleetV1 | None
    headway_regimes: tuple[PresentationHeadwayRegimeV1, ...]
    demand_gaps: tuple[PresentationDemandGapV1, ...]
    terminal_occupancy_status: str
    terminal_occupancy_terminal_statuses: tuple[tuple[str, str], ...]
    terminal_occupancy_limits: tuple[tuple[str, int | None], ...]
    terminal_occupancy_issue_codes: tuple[str, ...]
    discrepancies: tuple[PresentationDiscrepancyV1, ...]
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]
    validation_explanations: tuple[str, ...]
    validation_limitations: tuple[str, ...]

    def scenario(self, scenario_id: str) -> PresentationScenarioV1 | None:
        """Return one projected scenario without inventing a missing Scenario C."""
        return next(
            (item for item in self.scenarios if item.scenario_id == scenario_id),
            None,
        )


def _enum_value(value: Enum | None) -> str | None:
    return value.value if value is not None else None


def _outcome_status(outcome: object | None) -> str | None:
    return _enum_value(getattr(outcome, "result_status", None))


def _native_solver_status(outcome: object | None) -> str | None:
    return _enum_value(getattr(outcome, "solver_status", None))


def _accepted_solution(result: BusScheduleOptimizationResult) -> ScheduleSolutionV1 | None:
    outcome = result.recommended_outcome
    if (
        outcome is not None
        and outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
        and outcome.solution is not None
    ):
        return outcome.solution
    return None


def _terminal_name(
    terminal: DepartureTerminal,
    scenario: ScenarioInputV1,
) -> str:
    return {
        DepartureTerminal.TERMINAL_1: scenario.terminal_1_name,
        DepartureTerminal.TERMINAL_2: scenario.terminal_2_name,
    }[terminal]


def _arrival_terminal_name(
    terminal: DepartureTerminal,
    scenario: ScenarioInputV1,
) -> str:
    return {
        DepartureTerminal.TERMINAL_1: scenario.terminal_2_name,
        DepartureTerminal.TERMINAL_2: scenario.terminal_1_name,
    }[terminal]


def _trip_sort_key(trip: PresentationTripV1) -> tuple[object, ...]:
    return (
        _DIRECTION_ORDER.get(trip.direction, 99),
        trip.departure_time_seconds,
        trip.source_b_trip_id or "",
        trip.trip_id,
    )


def _scenario_trips(
    scenario: ScenarioInputV1,
    *,
    scenario_id: str,
) -> tuple[PresentationTripV1, ...]:
    return tuple(
        sorted(
            (
                PresentationTripV1(
                    scenario_id=scenario_id,
                    trip_id=trip.trip_id,
                    source_b_trip_id=None,
                    direction=trip.direction.value,
                    departure_terminal=_terminal_name(trip.departure_terminal, scenario),
                    arrival_terminal=_arrival_terminal_name(trip.departure_terminal, scenario),
                    departure_time_seconds=trip.departure_time,
                    arrival_time_seconds=trip.resolved_arrival_time,
                    runtime_seconds=trip.runtime_minutes * 60,
                    b_departure_time_seconds=None,
                    shift_minutes=None,
                    vehicle_assignment=trip.vehicle_assignment,
                    headway_regime_id=None,
                    change_reason=None,
                )
                for trip in scenario.exact_timetable
            ),
            key=_trip_sort_key,
        )
    )


def _consistency_error(code: str, message: str) -> UnifiedPresentationConsistencyError:
    return UnifiedPresentationConsistencyError(f"{code}: {message}")


def _verify_result_report_consistency(
    result: BusScheduleOptimizationResult,
    report: SideBySideValidationReportV1,
    solution: ScheduleSolutionV1 | None,
) -> None:
    scenario_b = result.normalized_inputs.scenario_b
    snapshot = report.unified_snapshot
    source_b_fingerprint = result.normalized_inputs.scenario_b_fingerprint
    accepted_c_exists = solution is not None
    report_c_exists = snapshot.scenario_c is not None

    if scenario_b.route_id != snapshot.route_id:
        raise _consistency_error(
            "ROUTE_ID_MISMATCH",
            "unified result and validation report use different route IDs",
        )
    if (scenario_b.terminal_1_name, scenario_b.terminal_2_name) != snapshot.terminal_identities:
        raise _consistency_error(
            "TERMINAL_IDENTITY_MISMATCH",
            "unified result and validation report use different terminal identities",
        )
    if source_b_fingerprint != snapshot.normalized_scenario_b_fingerprint:
        raise _consistency_error(
            "SOURCE_B_FINGERPRINT_MISMATCH",
            "normalized Scenario B fingerprint differs from the validation report",
        )
    if snapshot.scenario_b.timetable_fingerprint != source_b_fingerprint:
        raise _consistency_error(
            "REPORT_B_TIMETABLE_FINGERPRINT_MISMATCH",
            "validation report Scenario B does not bind its normalized fingerprint",
        )
    expected_b_trips = tuple(
        sorted(
            (
                trip.trip_id,
                trip.trip_id,
                trip.direction.value,
                _terminal_name(trip.departure_terminal, scenario_b),
                trip.departure_time,
                trip.resolved_arrival_time,
                trip.runtime_minutes * 60,
            )
            for trip in scenario_b.exact_timetable
        )
    )
    reported_b_trips = tuple(
        sorted(
            (
                trip.trip_id,
                trip.source_b_trip_id,
                trip.direction,
                trip.departure_terminal,
                trip.departure_time_seconds,
                trip.arrival_time_seconds,
                trip.runtime_seconds,
            )
            for trip in snapshot.scenario_b.trips
        )
    )
    if expected_b_trips != reported_b_trips:
        raise _consistency_error(
            "REPORT_B_TIMETABLE_FACT_MISMATCH",
            "validation report Scenario B facts differ from the supplied unified result",
        )
    if accepted_c_exists != report_c_exists:
        raise _consistency_error(
            "ACCEPTED_C_EXISTENCE_MISMATCH",
            "accepted Scenario C existence differs between result and report",
        )
    if accepted_c_exists:
        assert solution is not None
        if solution.solution_fingerprint != snapshot.solution_fingerprint:
            raise _consistency_error(
                "ACCEPTED_SOLUTION_FINGERPRINT_MISMATCH",
                "accepted solution fingerprint differs from the validation report",
            )
        if solution.source_b_fingerprint != source_b_fingerprint:
            raise _consistency_error(
                "ACCEPTED_SOLUTION_SOURCE_B_MISMATCH",
                "accepted solution does not bind normalized Scenario B",
            )
        if snapshot.scenario_c_authority != SCENARIO_C_AUTHORITY_ACCEPTED:
            raise _consistency_error(
                "ACCEPTED_C_AUTHORITY_MISMATCH",
                "validation report does not mark accepted Scenario C authority",
            )
        if (
            snapshot.scenario_c is None
            or snapshot.scenario_c.timetable_fingerprint != solution.solution_fingerprint
        ):
            raise _consistency_error(
                "REPORT_C_TIMETABLE_FINGERPRINT_MISMATCH",
                "validation report Scenario C does not bind the accepted solution",
            )
        fleet_by_trip = {item.c_trip_id: item for item in solution.fleet_assignment}
        if len(fleet_by_trip) != len(solution.fleet_assignment):
            raise _consistency_error(
                "DUPLICATE_C_FLEET_ASSIGNMENT",
                "accepted solution repeats a C fleet-assignment trip ID",
            )
        solution_c_ids = {trip.c_trip_id for trip in solution.c_exact_timetable}
        if set(fleet_by_trip) != solution_c_ids:
            raise _consistency_error(
                "C_FLEET_ASSIGNMENT_SET_MISMATCH",
                "accepted solution fleet assignments do not cover exact C trips",
            )
        expected_c_trips = tuple(
            sorted(
                (
                    trip.c_trip_id,
                    trip.source_b_trip_id,
                    trip.direction.value,
                    _terminal_name(trip.departure_terminal, scenario_b),
                    trip.c_departure_time,
                    fleet_by_trip[trip.c_trip_id].arrival_time,
                    fleet_by_trip[trip.c_trip_id].arrival_time
                    - fleet_by_trip[trip.c_trip_id].departure_time,
                    trip.c_departure_time - trip.b_departure_time,
                )
                for trip in solution.c_exact_timetable
            )
        )
        reported_c_trips = tuple(
            sorted(
                (
                    trip.trip_id,
                    trip.source_b_trip_id,
                    trip.direction,
                    trip.departure_terminal,
                    trip.departure_time_seconds,
                    trip.arrival_time_seconds,
                    trip.runtime_seconds,
                    trip.shift_from_b_seconds,
                )
                for trip in snapshot.scenario_c.trips
            )
        )
        if expected_c_trips != reported_c_trips:
            raise _consistency_error(
                "REPORT_C_TIMETABLE_FACT_MISMATCH",
                "validation report Scenario C facts differ from the accepted solution",
            )
    elif snapshot.scenario_c_authority is not None or snapshot.solution_fingerprint is not None:
        raise _consistency_error(
            "REPORT_C_AUTHORITY_WITHOUT_ACCEPTED_SOLUTION",
            "validation report exposes Scenario C authority without an accepted solution",
        )


def _build_c_scenario(
    result: BusScheduleOptimizationResult,
    solution: ScheduleSolutionV1,
) -> PresentationScenarioV1:
    scenario_b = result.normalized_inputs.scenario_b
    b_by_id = {trip.trip_id: trip for trip in scenario_b.exact_timetable}
    if len(b_by_id) != len(scenario_b.exact_timetable):
        raise _consistency_error("DUPLICATE_B_TRIP_ID", "normalized Scenario B trip IDs repeat")

    c_ids = [trip.c_trip_id for trip in solution.c_exact_timetable]
    source_ids = [trip.source_b_trip_id for trip in solution.c_exact_timetable]
    if len(set(c_ids)) != len(c_ids) or len(set(source_ids)) != len(source_ids):
        raise _consistency_error(
            "C_TRACE_NOT_ONE_TO_ONE",
            "accepted Scenario C must map one-to-one to source B trips",
        )
    if set(source_ids) != set(b_by_id):
        raise _consistency_error(
            "C_TRACE_SOURCE_SET_MISMATCH",
            "accepted Scenario C source mapping does not exactly cover Scenario B",
        )

    fleet_by_trip = {item.c_trip_id: item for item in solution.fleet_assignment}
    if len(fleet_by_trip) != len(solution.fleet_assignment) or set(fleet_by_trip) != set(c_ids):
        raise _consistency_error(
            "C_FLEET_ASSIGNMENT_MISMATCH",
            "accepted Scenario C fleet assignments do not map one-to-one to C trips",
        )
    regime_ids = {item.regime_id for item in solution.c_headway_regimes}

    rows: list[PresentationTripV1] = []
    for trip in solution.c_exact_timetable:
        source = b_by_id[trip.source_b_trip_id]
        fleet = fleet_by_trip[trip.c_trip_id]
        if (
            source.departure_time != trip.b_departure_time
            or source.direction != trip.direction
            or source.departure_terminal != trip.departure_terminal
        ):
            raise _consistency_error(
                "C_TRACE_FACT_MISMATCH",
                f"accepted C trip {trip.c_trip_id} does not preserve its returned B source facts",
            )
        if (
            fleet.departure_time != trip.c_departure_time
            or fleet.departure_terminal != trip.departure_terminal
            or fleet.vehicle_id != trip.vehicle_assignment
        ):
            raise _consistency_error(
                "C_FLEET_FACT_MISMATCH",
                f"accepted C trip {trip.c_trip_id} conflicts with its returned fleet assignment",
            )
        if trip.headway_regime_id not in regime_ids:
            raise _consistency_error(
                "C_HEADWAY_REGIME_MISMATCH",
                f"accepted C trip {trip.c_trip_id} references an unknown headway regime",
            )
        rows.append(
            PresentationTripV1(
                scenario_id=ScenarioId.C.value,
                trip_id=trip.c_trip_id,
                source_b_trip_id=trip.source_b_trip_id,
                direction=trip.direction.value,
                departure_terminal=_terminal_name(fleet.departure_terminal, scenario_b),
                arrival_terminal=_terminal_name(fleet.arrival_terminal, scenario_b),
                departure_time_seconds=fleet.departure_time,
                arrival_time_seconds=fleet.arrival_time,
                runtime_seconds=fleet.arrival_time - fleet.departure_time,
                b_departure_time_seconds=trip.b_departure_time,
                shift_minutes=trip.shift_minutes,
                vehicle_assignment=fleet.vehicle_id,
                headway_regime_id=trip.headway_regime_id,
                change_reason=trip.change_reason,
            )
        )
    return PresentationScenarioV1(
        scenario_id=ScenarioId.C.value,
        source_fingerprint=solution.solution_fingerprint,
        trips=tuple(sorted(rows, key=_trip_sort_key)),
    )


def _block_key(plan: BlockSupplyPlanV1) -> tuple[str, str, int, int]:
    return (
        plan.block_id,
        plan.direction.value,
        plan.block_start,
        plan.block_end,
    )


def _plan_by_key(
    plans: tuple[BlockSupplyPlanV1, ...],
    *,
    label: str,
) -> dict[tuple[str, str, int, int], BlockSupplyPlanV1]:
    mapped = {_block_key(plan): plan for plan in plans}
    if len(mapped) != len(plans):
        raise _consistency_error(
            "DUPLICATE_BLOCK_KEY",
            f"{label} supply plan repeats an exact semantic block key",
        )
    return mapped


def _verify_corresponding_plan(
    baseline: BlockSupplyPlanV1,
    other: BlockSupplyPlanV1,
    *,
    label: str,
) -> None:
    facts = (
        "passenger_demand",
        "vehicle_capacity",
        "required_trips_85",
        "required_trips_90",
        "confidence",
    )
    if any(getattr(baseline, name) != getattr(other, name) for name in facts):
        raise _consistency_error(
            "BLOCK_PLAN_FACT_MISMATCH",
            f"{label} supply plan conflicts at exact block {_block_key(baseline)}",
        )


def _build_blocks(
    result: BusScheduleOptimizationResult,
    solution: ScheduleSolutionV1 | None,
) -> tuple[PresentationBlockV1, ...]:
    a_by_key = _plan_by_key(result.b_evaluation.a_block_supply, label="Scenario A")
    b_by_key = _plan_by_key(result.b_evaluation.b_block_supply, label="Scenario B")
    c_by_key = _plan_by_key(
        solution.c_block_supply_plan if solution is not None else (),
        label="Scenario C",
    )
    resolution = result.b_evaluation.demand_resolution
    resolution_keys = (
        {
            (block.block_id, block.direction.value, block.start_time, block.end_time)
            for block in resolution.blocks
        }
        if resolution is not None
        else set()
    )
    if resolution_keys != set(b_by_key):
        raise _consistency_error(
            "B_BLOCK_GRAIN_MISMATCH",
            "Scenario B supply plan does not match exact demand-analysis block grain",
        )
    scenario_a_exists = result.normalized_inputs.scenario_a is not None
    if scenario_a_exists and set(a_by_key) != set(b_by_key):
        raise _consistency_error(
            "A_BLOCK_GRAIN_MISMATCH",
            "Scenario A and B supply plans cannot be reconciled on exact block keys",
        )
    if not scenario_a_exists and a_by_key:
        raise _consistency_error(
            "A_BLOCKS_WITHOUT_SCENARIO_A",
            "Scenario A supply rows exist without normalized Scenario A",
        )
    if solution is not None and set(c_by_key) != set(b_by_key):
        raise _consistency_error(
            "C_BLOCK_GRAIN_MISMATCH",
            "accepted Scenario C and B supply plans cannot be reconciled on exact block keys",
        )

    rows: list[PresentationBlockV1] = []
    for key in sorted(
        b_by_key,
        key=lambda item: (
            _DIRECTION_ORDER.get(item[1], 99),
            item[2],
            item[3],
            item[0],
        ),
    ):
        b_plan = b_by_key[key]
        a_plan = a_by_key.get(key)
        c_plan = c_by_key.get(key)
        if a_plan is not None:
            _verify_corresponding_plan(b_plan, a_plan, label="Scenario A")
            if a_plan.a_trip_count != b_plan.a_trip_count:
                raise _consistency_error(
                    "A_BLOCK_COUNT_MISMATCH",
                    f"Scenario A trip count conflicts at exact block {key}",
                )
        if c_plan is not None:
            _verify_corresponding_plan(b_plan, c_plan, label="Scenario C")
        rows.append(
            PresentationBlockV1(
                block_id=b_plan.block_id,
                direction=b_plan.direction.value,
                block_start_seconds=b_plan.block_start,
                block_end_seconds=b_plan.block_end,
                passenger_demand=b_plan.passenger_demand,
                confidence=b_plan.confidence.value,
                vehicle_capacity=b_plan.vehicle_capacity,
                a_trip_count=(a_plan.a_trip_count if a_plan is not None else None),
                b_trip_count=b_plan.b_trip_count,
                c_actual_trip_count=(c_plan.c_actual_trip_count if c_plan is not None else None),
                required_trips_85=b_plan.required_trips_85,
                required_trips_90=b_plan.required_trips_90,
                b_nominal_capacity=b_plan.nominal_capacity,
                c_nominal_capacity=(c_plan.nominal_capacity if c_plan is not None else None),
                b_load_factor=b_plan.load_factor,
                c_load_factor=(c_plan.load_factor if c_plan is not None else None),
                b_shortage=b_plan.shortage,
                c_shortage=(c_plan.shortage if c_plan is not None else None),
                b_status=b_plan.status.value,
                c_status=(c_plan.status.value if c_plan is not None else None),
                allocation_reason=b_plan.allocation_reason,
                c_allocation_reason=(c_plan.allocation_reason if c_plan is not None else None),
            )
        )
    return tuple(rows)


def _presentation_dimension(
    name: str,
    dimension: EvaluationDimensionV1,
) -> PresentationDimensionV1:
    issues = tuple(
        sorted(
            dimension.issues,
            key=lambda issue: (
                issue.code,
                issue.severity.value,
                issue.message,
            ),
        )
    )
    return PresentationDimensionV1(
        dimension_name=name,
        status=dimension.status.value,
        confidence=dimension.confidence.value,
        explanation=dimension.explanation,
        issue_codes=tuple(issue.code for issue in issues),
        issue_severities=tuple(issue.severity.value for issue in issues),
        issue_messages=tuple(issue.message for issue in issues),
        evidence=tuple(sorted(dimension.evidence)),
    )


def _validator_rejection_codes(result: BusScheduleOptimizationResult) -> tuple[str, ...]:
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


def _build_outcome(
    result: BusScheduleOptimizationResult,
    solution: ScheduleSolutionV1 | None,
) -> PresentationOutcomeV1:
    comparison = result.comparison
    accepted = solution is not None
    recommended = result.recommended_outcome
    return PresentationOutcomeV1(
        b_disposition=result.b_evaluation.evaluation.disposition.value,
        adjustment_decision=result.adjustment_assessment.primary_decision.value,
        selected_action=result.selected_action.value,
        solver_choice=result.solver_choice.value,
        solver_attempted=result.solver_attempted,
        heuristic_result_status=_outcome_status(result.heuristic_outcome),
        ortools_result_status=_outcome_status(result.ortools_outcome),
        heuristic_native_solver_status=_native_solver_status(result.heuristic_outcome),
        ortools_native_solver_status=_native_solver_status(result.ortools_outcome),
        validator_rejection_codes=_validator_rejection_codes(result),
        comparison_objective_names=(comparison.objective_names if comparison is not None else None),
        heuristic_objective_vector=(
            comparison.heuristic_vector if comparison is not None else None
        ),
        ortools_objective_vector=(comparison.ortools_vector if comparison is not None else None),
        recommended_solver=(
            comparison.recommended_solver.value
            if comparison is not None and comparison.recommended_solver is not None
            else None
        ),
        comparison_reason=(comparison.reason_code if comparison is not None else None),
        accepted_c_exists=accepted,
        accepted_c_authority=(SCENARIO_C_AUTHORITY_ACCEPTED if accepted else None),
        accepted_solution_fingerprint=(
            solution.solution_fingerprint if solution is not None else None
        ),
        accepted_outcome_fingerprint=(
            recommended.outcome_fingerprint if accepted and recommended is not None else None
        ),
        explanations=tuple(result.explanations),
        limitations=tuple(result.limitations),
    )


def _build_fleet_assignments(
    result: BusScheduleOptimizationResult,
    solution: ScheduleSolutionV1 | None,
) -> tuple[PresentationFleetAssignmentV1, ...]:
    if solution is None:
        return ()
    scenario_b = result.normalized_inputs.scenario_b
    return tuple(
        PresentationFleetAssignmentV1(
            vehicle_id=item.vehicle_id,
            trip_id=item.c_trip_id,
            departure_terminal=_terminal_name(item.departure_terminal, scenario_b),
            arrival_terminal=_terminal_name(item.arrival_terminal, scenario_b),
            departure_time_seconds=item.departure_time,
            arrival_time_seconds=item.arrival_time,
            ready_time_seconds=item.ready_time,
        )
        for item in sorted(
            solution.fleet_assignment,
            key=lambda item: (item.departure_time, item.vehicle_id, item.c_trip_id),
        )
    )


def _build_initial_fleet(
    solution: ScheduleSolutionV1 | None,
) -> PresentationInitialFleetV1 | None:
    if solution is None:
        return None
    return PresentationInitialFleetV1(
        terminal_1_vehicle_count=solution.recommended_initial_fleet_terminal_1,
        terminal_2_vehicle_count=solution.recommended_initial_fleet_terminal_2,
        positioning_mode=solution.initial_fleet_positioning_mode.value,
        available_fleet_limit=solution.available_fleet_limit,
        approved_active_fleet=solution.approved_active_fleet,
        minimum_required_fleet=solution.minimum_required_fleet,
        fleet_margin=solution.fleet_margin,
        maximum_simultaneous_vehicle_use=solution.maximum_simultaneous_vehicle_use,
        fleet_feasibility_status=solution.fleet_feasibility_status,
    )


def _build_headway_regimes(
    solution: ScheduleSolutionV1 | None,
) -> tuple[PresentationHeadwayRegimeV1, ...]:
    if solution is None:
        return ()
    return tuple(
        PresentationHeadwayRegimeV1(
            regime_id=item.regime_id,
            direction=item.direction.value,
            start_time_seconds=item.start_time,
            end_time_seconds=item.end_time,
            covered_analysis_blocks=tuple(item.covered_analysis_blocks),
            trip_count=item.trip_count,
            target_service_rate=item.target_service_rate,
            target_headway=item.target_headway,
            actual_headway_sequence=tuple(item.actual_headway_sequence),
            transition_headways=tuple(item.transition_headways),
            exceptional_headways=tuple(item.exceptional_headways),
            boundary_reason=item.boundary_reason,
            regularity_status=item.regularity_status,
        )
        for item in sorted(
            solution.c_headway_regimes,
            key=lambda item: (
                _DIRECTION_ORDER.get(item.direction.value, 99),
                item.start_time,
                item.end_time,
                item.regime_id,
            ),
        )
    )


def _build_demand_gaps(
    result: BusScheduleOptimizationResult,
) -> tuple[PresentationDemandGapV1, ...]:
    resolution = result.b_evaluation.demand_resolution
    coverage = resolution.coverage_assessment if resolution is not None else None
    if coverage is None:
        return ()
    return tuple(
        PresentationDemandGapV1(
            code=item.code,
            direction=item.stream.value,
            start_time_seconds=item.start_time,
            end_time_seconds=item.end_time,
        )
        for item in sorted(
            coverage.uncovered_segments,
            key=lambda item: (
                _DIRECTION_ORDER.get(item.stream.value, 99),
                item.start_time,
                item.end_time,
                item.code,
            ),
        )
    )


def _build_discrepancies(
    report: SideBySideValidationReportV1,
) -> tuple[PresentationDiscrepancyV1, ...]:
    return tuple(
        PresentationDiscrepancyV1(
            fact_code=item.fact_code,
            category=item.category.value,
            comparison_rule=item.comparison_rule.value,
            legacy_value=item.legacy_value,
            unified_value=item.unified_value,
            comparison_status=item.comparison_status.value,
            disposition=item.disposition.value,
            reason_code=item.reason_code,
            explanation=item.explanation,
        )
        for item in report.comparisons
    )


def _terminal_occupancy_evidence(
    result: BusScheduleOptimizationResult,
) -> tuple[
    str,
    tuple[tuple[str, str], ...],
    tuple[tuple[str, int | None], ...],
    tuple[str, ...],
]:
    scenario = result.normalized_inputs.scenario_b
    limits = scenario.terminal_occupancy_limits
    returned_codes = {
        *(issue.code for issue in result.b_evaluation.evaluation.technical_feasibility.issues),
        *result.b_evaluation.evaluation.limitations,
        *result.limitations,
    }
    occupancy_codes = tuple(
        sorted(
            returned_codes
            & {
                TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED,
                TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED,
                TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED,
                TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,
                TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,
            }
        )
    )
    terminal_1_limit = limits.terminal_1 if limits is not None else None
    terminal_2_limit = limits.terminal_2 if limits is not None else None
    terminal_1_status = (
        "NOT_EVALUATED"
        if terminal_1_limit is None
        else ("FAIL" if TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED in occupancy_codes else "PASS")
    )
    terminal_2_status = (
        "NOT_EVALUATED"
        if terminal_2_limit is None
        else ("FAIL" if TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED in occupancy_codes else "PASS")
    )
    terminal_statuses = (
        ("terminal_1", terminal_1_status),
        ("terminal_2", terminal_2_status),
    )
    status_values = {terminal_1_status, terminal_2_status}
    if "FAIL" in status_values:
        aggregate_status = "FAIL"
    elif status_values == {"NOT_EVALUATED"}:
        aggregate_status = "NOT_EVALUATED"
    elif status_values == {"PASS"}:
        aggregate_status = "PASS"
    else:
        aggregate_status = "PARTIALLY_EVALUATED"
    return (
        aggregate_status,
        terminal_statuses,
        (
            ("terminal_1", terminal_1_limit),
            ("terminal_2", terminal_2_limit),
        ),
        occupancy_codes,
    )


def _runtime_review_codes(
    dimensions: tuple[PresentationDimensionV1, ...],
    result: BusScheduleOptimizationResult,
    terminal_occupancy_issue_codes: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    expert_codes = {
        code
        for dimension in dimensions
        for code, severity in zip(
            dimension.issue_codes,
            dimension.issue_severities,
            strict=True,
        )
        if severity != "INFO"
    }
    informational_codes = {
        code
        for dimension in dimensions
        for code, severity in zip(
            dimension.issue_codes,
            dimension.issue_severities,
            strict=True,
        )
        if severity == "INFO"
    }
    expert_codes.update(_validator_rejection_codes(result))
    expert_codes.update(terminal_occupancy_issue_codes)
    if result.limitations and not expert_codes:
        expert_codes.add(UNIFIED_LIMITATIONS_REQUIRE_EXPERT_REVIEW)
    return tuple(sorted(expert_codes)), tuple(sorted(informational_codes))


def _serialize(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple | list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in sorted(value.items())}
    return value


def unified_presentation_to_dict(
    presentation: UnifiedPresentationBundleV1,
) -> dict[str, object]:
    """Serialize a presentation deterministically into JSON-compatible values."""
    if not isinstance(presentation, UnifiedPresentationBundleV1):
        raise TypeError("presentation must be a UnifiedPresentationBundleV1")
    serialized = _serialize(presentation)
    if not isinstance(serialized, dict):
        raise AssertionError("presentation serialization must produce a dictionary")
    return serialized


def _presentation_fingerprint(presentation: UnifiedPresentationBundleV1) -> str:
    payload = unified_presentation_to_dict(presentation)
    payload.pop("presentation_fingerprint", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def verify_unified_presentation_integrity_v1(
    presentation: UnifiedPresentationBundleV1,
) -> None:
    """Reject presentation copies whose mode or semantic fingerprint is stale."""
    if not isinstance(presentation, UnifiedPresentationBundleV1):
        raise TypeError("presentation must be a UnifiedPresentationBundleV1")
    if presentation.presentation_mode != PRESENTATION_MODE_VALIDATION_ONLY:
        raise _consistency_error(
            "PRESENTATION_MODE_MISMATCH",
            "unified presentation artifacts must remain VALIDATION_ONLY",
        )
    expected_fingerprint = _presentation_fingerprint(presentation)
    if presentation.presentation_fingerprint != expected_fingerprint:
        raise _consistency_error(
            "PRESENTATION_FINGERPRINT_MISMATCH",
            "stored presentation fingerprint does not match its semantic contents",
        )


def _build_unified_presentation(
    result: BusScheduleOptimizationResult,
    validation_report: SideBySideValidationReportV1 | None,
) -> UnifiedPresentationBundleV1:
    if not isinstance(result, BusScheduleOptimizationResult):
        raise TypeError("result must be a BusScheduleOptimizationResult")

    solution = _accepted_solution(result)
    if solution is not None and (
        solution.source_b_fingerprint != result.normalized_inputs.scenario_b_fingerprint
    ):
        raise _consistency_error(
            "ACCEPTED_SOLUTION_SOURCE_B_MISMATCH",
            "accepted solution does not bind normalized Scenario B",
        )
    if validation_report is not None:
        _verify_result_report_consistency(result, validation_report, solution)
    normalized = result.normalized_inputs
    scenario_b = normalized.scenario_b

    scenarios: list[PresentationScenarioV1] = []
    if normalized.scenario_a is not None:
        scenarios.append(
            PresentationScenarioV1(
                scenario_id=ScenarioId.A.value,
                source_fingerprint=normalized.scenario_a_fingerprint,
                trips=_scenario_trips(normalized.scenario_a, scenario_id=ScenarioId.A.value),
            )
        )
    scenarios.append(
        PresentationScenarioV1(
            scenario_id=ScenarioId.B.value,
            source_fingerprint=normalized.scenario_b_fingerprint,
            trips=_scenario_trips(scenario_b, scenario_id=ScenarioId.B.value),
        )
    )
    if solution is not None:
        scenarios.append(_build_c_scenario(result, solution))
    scenarios.sort(key=lambda item: _SCENARIO_ORDER[item.scenario_id])

    evaluation = result.b_evaluation.evaluation
    dimensions = tuple(
        _presentation_dimension(name, getattr(evaluation, name)) for name in _DIMENSION_ORDER
    )
    outcome = _build_outcome(result, solution)
    (
        terminal_occupancy_status,
        terminal_occupancy_terminal_statuses,
        terminal_occupancy_limits,
        terminal_occupancy_issue_codes,
    ) = _terminal_occupancy_evidence(result)
    if validation_report is None:
        expert_review_required_codes, informational_codes = _runtime_review_codes(
            dimensions,
            result,
            terminal_occupancy_issue_codes,
        )
        blocking_discrepancy_codes: tuple[str, ...] = ()
        discrepancies: tuple[PresentationDiscrepancyV1, ...] = ()
        validation_explanations: tuple[str, ...] = ()
        validation_limitations: tuple[str, ...] = ()
    else:
        snapshot = validation_report.unified_snapshot
        if (
            terminal_occupancy_status != snapshot.terminal_occupancy_status
            or terminal_occupancy_terminal_statuses
            != tuple(snapshot.terminal_occupancy_terminal_statuses)
            or terminal_occupancy_limits != tuple(snapshot.terminal_occupancy_limits)
            or terminal_occupancy_issue_codes != tuple(snapshot.terminal_occupancy_issue_codes)
        ):
            raise _consistency_error(
                "TERMINAL_OCCUPANCY_REPORT_MISMATCH",
                "unified terminal occupancy facts differ from the validation report",
            )
        blocking_discrepancy_codes = tuple(validation_report.blocking_discrepancy_codes)
        expert_review_required_codes = tuple(validation_report.expert_review_required_codes)
        informational_codes = tuple(validation_report.informational_codes)
        discrepancies = _build_discrepancies(validation_report)
        validation_explanations = tuple(validation_report.explanations)
        validation_limitations = tuple(validation_report.limitations)

    provisional = UnifiedPresentationBundleV1(
        presentation_mode=PRESENTATION_MODE_VALIDATION_ONLY,
        presentation_fingerprint="",
        route_id=scenario_b.route_id,
        route_name=scenario_b.route_name,
        route_type=scenario_b.route_type.value,
        terminal_1_name=scenario_b.terminal_1_name,
        terminal_2_name=scenario_b.terminal_2_name,
        source_id=scenario_b.source_metadata.source_id,
        imported_at=scenario_b.source_metadata.imported_at.isoformat(),
        source_a_fingerprint=normalized.scenario_a_fingerprint,
        source_b_fingerprint=normalized.scenario_b_fingerprint,
        accepted_solution_fingerprint=outcome.accepted_solution_fingerprint,
        accepted_outcome_fingerprint=outcome.accepted_outcome_fingerprint,
        cutover_blocked=bool(blocking_discrepancy_codes),
        requires_expert_review=bool(blocking_discrepancy_codes or expert_review_required_codes),
        blocking_discrepancy_codes=blocking_discrepancy_codes,
        expert_review_required_codes=expert_review_required_codes,
        informational_codes=informational_codes,
        scenarios=tuple(scenarios),
        blocks=_build_blocks(result, solution),
        dimensions=dimensions,
        outcome=outcome,
        fleet_assignments=_build_fleet_assignments(result, solution),
        initial_fleet=_build_initial_fleet(solution),
        headway_regimes=_build_headway_regimes(solution),
        demand_gaps=_build_demand_gaps(result),
        terminal_occupancy_status=terminal_occupancy_status,
        terminal_occupancy_terminal_statuses=terminal_occupancy_terminal_statuses,
        terminal_occupancy_limits=terminal_occupancy_limits,
        terminal_occupancy_issue_codes=terminal_occupancy_issue_codes,
        discrepancies=discrepancies,
        explanations=tuple(result.explanations),
        limitations=tuple(result.limitations),
        validation_explanations=validation_explanations,
        validation_limitations=validation_limitations,
    )
    return replace(
        provisional,
        presentation_fingerprint=_presentation_fingerprint(provisional),
    )


def build_unified_application_presentation_v1(
    result: BusScheduleOptimizationResult,
) -> UnifiedPresentationBundleV1:
    """Project a Contract-only application presentation without legacy comparison facts."""
    return _build_unified_presentation(result, None)


def build_unified_presentation_v1(
    result: BusScheduleOptimizationResult,
    validation_report: SideBySideValidationReportV1,
) -> UnifiedPresentationBundleV1:
    """Project returned unified and offline 5A1 facts into a presentation."""
    from .side_by_side_validation import SideBySideValidationReportV1

    if not isinstance(validation_report, SideBySideValidationReportV1):
        raise TypeError("validation_report must be a SideBySideValidationReportV1")
    return _build_unified_presentation(result, validation_report)


__all__ = [
    "DISPLAY_DERIVED",
    "PRESENTATION_MODE_VALIDATION_ONLY",
    "UNIFIED_LIMITATIONS_REQUIRE_EXPERT_REVIEW",
    "PresentationBlockV1",
    "PresentationDemandGapV1",
    "PresentationDimensionV1",
    "PresentationDiscrepancyV1",
    "PresentationFleetAssignmentV1",
    "PresentationHeadwayRegimeV1",
    "PresentationInitialFleetV1",
    "PresentationOutcomeV1",
    "PresentationScenarioV1",
    "PresentationTripV1",
    "UnifiedPresentationBundleV1",
    "UnifiedPresentationConsistencyError",
    "build_unified_application_presentation_v1",
    "build_unified_presentation_v1",
    "unified_presentation_to_dict",
    "verify_unified_presentation_integrity_v1",
]

"""Versioned contracts for B-anchored two-stage Scenario C optimization."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from enum import StrEnum

from .models import (
    B_ANCHORED_TWO_STAGE_REBALANCE_V1,
    COMBINED_DEMAND_FIXED_DIRECTION_COUNTS,
    DIRECTIONAL_DEMAND_FIXED_DIRECTION_COUNTS,
    ContractDirection,
    DemandAllocationAuthorityModeV1,
    ScenarioCOptimizationModeV1,
)
from .serialization import canonical_sha256
from .solver_models import (
    NativeSolverStatus,
    RawScheduleCandidateV1,
    ScheduleGenerationOutcomeV1,
    SolverRunResultV1,
)
from .solver_problem import jsonable

SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE = "scenario_c_uniform_integer_regime_policy_v3"
TRIP_ALLOCATION_PLAN_PROFILE_V1 = "scenario_c_trip_allocation_plan_v1"
TWO_STAGE_ACCEPTANCE_PROFILE_V1 = "scenario_c_two_stage_final_acceptance_v1"
TWO_STAGE_RESULT_FINGERPRINT_PROFILE_V1 = "scenario_c_two_stage_result_v1"
FINAL_SERVICE_SENTINEL = "FINAL_SERVICE_SENTINEL"
STAGE_1_NECESSARY_FEASIBILITY_PROFILE_V1 = "scenario_c_stage_1_necessary_feasibility_v1"
STAGE_2_INFEASIBILITY_DIAGNOSTIC_PROFILE_V1 = "scenario_c_stage_2_infeasibility_diagnostic_v1"


class TripAllocationSolveStatusV1(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    UNREPRESENTABLE = "UNREPRESENTABLE"
    NOT_FOUND_WITHIN_SOLVE_LIMIT = "NOT_FOUND_WITHIN_SOLVE_LIMIT"
    INFEASIBLE = "INFEASIBLE"


class FinalAcceptanceStateV1(StrEnum):
    FINAL_RECOMMENDED = "FINAL_RECOMMENDED"
    VALID_CANDIDATE_NOT_FINAL = "VALID_CANDIDATE_NOT_FINAL"
    KEEP_SCENARIO_B = "KEEP_SCENARIO_B"
    NO_FINAL_C_WITHIN_SOLVE_BUDGET = "NO_FINAL_C_WITHIN_SOLVE_BUDGET"


class ServiceBoundarySemanticsV1(StrEnum):
    HALF_OPEN_DEMAND_MEMBERSHIP = "HALF_OPEN_DEMAND_MEMBERSHIP"
    FINAL_SERVICE_SENTINEL = FINAL_SERVICE_SENTINEL


class Stage2ConstraintFamilyV1(StrEnum):
    ALLOCATION_MEMBERSHIP = "ALLOCATION_MEMBERSHIP"
    UNIFORM_HEADWAY = "UNIFORM_HEADWAY"
    REGIME_BOUNDARIES = "REGIME_BOUNDARIES"
    MINIMUM_OPERATIONAL_HEADWAY = "MINIMUM_OPERATIONAL_HEADWAY"
    B_SHIFT_BOUND = "B_SHIFT_BOUND"
    FIRST_LAST_LOCK = "FIRST_LAST_LOCK"
    FINAL_SERVICE_TAIL = "FINAL_SERVICE_TAIL"
    REGIME_TRANSITION_JUMP = "REGIME_TRANSITION_JUMP"
    SOURCE_RUNTIME = "SOURCE_RUNTIME"
    TURNAROUND = "TURNAROUND"
    FLEET = "FLEET"
    TERMINAL_OCCUPANCY = "TERMINAL_OCCUPANCY"
    PROTECTED_SERVICE_FLOOR = "PROTECTED_SERVICE_FLOOR"


def is_strict_uniform_integer_headway_sequence_v3(
    sequence: tuple[int | float, ...],
) -> bool:
    """Return whether a measurable V3 sequence is one positive integer headway."""
    return bool(sequence) and all(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value).is_integer()
        and value > 0
        and value == sequence[0]
        for value in sequence
    )


def _positive_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _non_negative_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class FinalServiceTailPolicyV1:
    profile: str = "scenario_c_final_service_tail_policy_v1"
    final_service_tail_window_minutes: int = 60
    final_service_tail_minimum_trip_count: int = 2
    final_service_tail_maximum_headway_minutes: int = 60
    prefer_final_tail_headway_not_shorter_than_previous_regime: bool = True

    def __post_init__(self) -> None:
        if not self.profile.strip():
            raise ValueError("final-service-tail profile must be non-empty")
        _positive_integer(
            "final_service_tail_window_minutes",
            self.final_service_tail_window_minutes,
        )
        _positive_integer(
            "final_service_tail_minimum_trip_count",
            self.final_service_tail_minimum_trip_count,
        )
        _positive_integer(
            "final_service_tail_maximum_headway_minutes",
            self.final_service_tail_maximum_headway_minutes,
        )


@dataclass(frozen=True, slots=True)
class UniformIntegerRegimePolicyV3:
    profile: str = SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE
    allocation_plan_profile: str = TRIP_ALLOCATION_PLAN_PROFILE_V1
    preferred_max_shift_per_trip_minutes: int = 15
    absolute_max_shift_per_trip_minutes: int = 30
    minimum_operational_headway_minutes: int = 2
    maximum_regime_boundary_adjustment_minutes: int = 5
    maximum_headway_regimes_per_direction: int = 16
    maximum_stage_1_alternative_plans: int = 4
    maximum_transition_jump_minutes: int = 15
    minimum_material_service_rate_change_ratio: float = 0.15
    final_service_tail: FinalServiceTailPolicyV1 = FinalServiceTailPolicyV1()

    def __post_init__(self) -> None:
        if self.profile != SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE:
            raise ValueError("V3 policy profile must use the authoritative V3 identifier")
        if not self.allocation_plan_profile.strip():
            raise ValueError("allocation_plan_profile must be non-empty")
        _non_negative_integer(
            "preferred_max_shift_per_trip_minutes",
            self.preferred_max_shift_per_trip_minutes,
        )
        _positive_integer(
            "absolute_max_shift_per_trip_minutes",
            self.absolute_max_shift_per_trip_minutes,
        )
        if self.preferred_max_shift_per_trip_minutes > self.absolute_max_shift_per_trip_minutes:
            raise ValueError("preferred shift cannot exceed the absolute hard shift bound")
        _positive_integer(
            "minimum_operational_headway_minutes",
            self.minimum_operational_headway_minutes,
        )
        _non_negative_integer(
            "maximum_regime_boundary_adjustment_minutes",
            self.maximum_regime_boundary_adjustment_minutes,
        )
        _positive_integer(
            "maximum_headway_regimes_per_direction",
            self.maximum_headway_regimes_per_direction,
        )
        _positive_integer(
            "maximum_stage_1_alternative_plans",
            self.maximum_stage_1_alternative_plans,
        )
        _non_negative_integer(
            "maximum_transition_jump_minutes",
            self.maximum_transition_jump_minutes,
        )
        if (
            isinstance(self.minimum_material_service_rate_change_ratio, bool)
            or not isinstance(self.minimum_material_service_rate_change_ratio, (int, float))
            or not math.isfinite(float(self.minimum_material_service_rate_change_ratio))
            or self.minimum_material_service_rate_change_ratio < 0
        ):
            raise ValueError("minimum material service-rate change must be finite and non-negative")
        if (
            self.final_service_tail.final_service_tail_maximum_headway_minutes
            < self.minimum_operational_headway_minutes
        ):
            raise ValueError("final-tail maximum headway cannot be below the operational minimum")

    @property
    def policy_fingerprint(self) -> str:
        return canonical_sha256(
            {
                "optimization_mode": B_ANCHORED_TWO_STAGE_REBALANCE_V1,
                "regime_policy": jsonable(asdict(self)),
            }
        )


@dataclass(frozen=True, slots=True)
class TripAllocationBlockV1:
    block_id: str
    direction: ContractDirection
    start_minute: int
    end_minute: int
    trip_count: int
    observed_passengers: float
    required_trips_90: int
    required_trips_85: int
    source_b_trip_count: int
    protected_minimum_trip_count: int = 0
    directional_trip_counts: tuple[tuple[ContractDirection, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.block_id.strip():
            raise ValueError("allocation block_id must be non-empty")
        if self.direction not in {
            ContractDirection.OUTBOUND,
            ContractDirection.INBOUND,
            ContractDirection.COMBINED,
        }:
            raise ValueError("allocation block direction is invalid")
        if self.end_minute <= self.start_minute:
            raise ValueError("allocation block must have a positive span")
        for name in (
            "trip_count",
            "required_trips_90",
            "required_trips_85",
            "source_b_trip_count",
            "protected_minimum_trip_count",
        ):
            _non_negative_integer(name, getattr(self, name))
        if (
            isinstance(self.observed_passengers, bool)
            or not isinstance(self.observed_passengers, (int, float))
            or not math.isfinite(float(self.observed_passengers))
            or self.observed_passengers < 0
        ):
            raise ValueError("observed_passengers must be finite and non-negative")
        if self.trip_count < self.protected_minimum_trip_count:
            raise ValueError("allocation cannot fall below its protected trip floor")
        directional_counts = dict(self.directional_trip_counts)
        if len(directional_counts) != len(self.directional_trip_counts) or any(
            direction not in {ContractDirection.OUTBOUND, ContractDirection.INBOUND}
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for direction, count in self.directional_trip_counts
        ):
            raise ValueError("directional allocation details must be unique non-negative counts")
        if self.direction == ContractDirection.COMBINED:
            if (
                set(directional_counts)
                != {
                    ContractDirection.OUTBOUND,
                    ContractDirection.INBOUND,
                }
                or sum(directional_counts.values()) != self.trip_count
            ):
                raise ValueError(
                    "combined allocation blocks must expose both fixed-direction contributions"
                )
        elif directional_counts:
            expected = directional_counts.get(self.direction)
            if len(directional_counts) != 1 or expected != self.trip_count:
                raise ValueError("directional allocation details do not match the block total")


@dataclass(frozen=True, slots=True)
class FinalServiceSentinelV1:
    direction: ContractDirection
    source_b_trip_id: str
    departure_minute: int
    boundary_semantics: ServiceBoundarySemanticsV1 = (
        ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL
    )

    def __post_init__(self) -> None:
        if self.direction not in {ContractDirection.OUTBOUND, ContractDirection.INBOUND}:
            raise ValueError("final-service sentinel must have a timetable direction")
        if not self.source_b_trip_id.strip():
            raise ValueError("final-service sentinel source identity must be non-empty")
        _non_negative_integer("departure_minute", self.departure_minute)
        if self.boundary_semantics != ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL:
            raise ValueError("final-service sentinel must use explicit sentinel semantics")


@dataclass(frozen=True, slots=True)
class ProposedServiceRegimeV1:
    regime_id: str
    direction: ContractDirection
    covered_demand_block_ids: tuple[str, ...]
    trip_count: int
    permitted_start_window: tuple[int, int]
    permitted_end_window: tuple[int, int]
    planned_start_minute: int
    planned_end_minute: int
    minimum_headway_minutes: int
    maximum_headway_minutes: int
    uniform_headway_minutes: int | None
    boundary_reason: str
    is_final_service_tail: bool = False
    boundary_semantics: ServiceBoundarySemanticsV1 = (
        ServiceBoundarySemanticsV1.HALF_OPEN_DEMAND_MEMBERSHIP
    )

    def __post_init__(self) -> None:
        if not self.regime_id.strip() or not self.boundary_reason.strip():
            raise ValueError("regime identity and boundary reason must be non-empty")
        if self.direction not in {ContractDirection.OUTBOUND, ContractDirection.INBOUND}:
            raise ValueError("service regime must have a timetable direction")
        if (
            self.boundary_semantics == ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL
            and not self.is_final_service_tail
        ):
            raise ValueError("only a final-service-tail regime may contain a sentinel boundary")
        if not self.covered_demand_block_ids:
            raise ValueError("service regime must cover at least one demand block")
        _positive_integer("trip_count", self.trip_count)
        _positive_integer("minimum_headway_minutes", self.minimum_headway_minutes)
        _positive_integer("maximum_headway_minutes", self.maximum_headway_minutes)
        if self.minimum_headway_minutes > self.maximum_headway_minutes:
            raise ValueError("regime minimum headway cannot exceed its maximum")
        for name, window in (
            ("permitted_start_window", self.permitted_start_window),
            ("permitted_end_window", self.permitted_end_window),
        ):
            if len(window) != 2 or window[0] > window[1]:
                raise ValueError(f"{name} must be an inclusive ordered minute window")
        if (
            not self.permitted_start_window[0]
            <= self.planned_start_minute
            <= (self.permitted_start_window[1])
        ):
            raise ValueError("planned start falls outside its permitted window")
        if (
            not self.permitted_end_window[0]
            <= self.planned_end_minute
            <= (self.permitted_end_window[1])
        ):
            raise ValueError("planned end falls outside its permitted window")
        if self.planned_end_minute < self.planned_start_minute:
            raise ValueError("planned regime boundary order is invalid")
        if self.trip_count == 1:
            if self.uniform_headway_minutes is not None:
                raise ValueError("a singleton regime has no measurable uniform headway")
            if self.planned_start_minute != self.planned_end_minute:
                raise ValueError("a singleton regime must use one planned minute")
            return
        if self.uniform_headway_minutes is None:
            raise ValueError("a measurable V3 regime requires one exact integer headway")
        _positive_integer("uniform_headway_minutes", self.uniform_headway_minutes)
        if (
            not self.minimum_headway_minutes
            <= self.uniform_headway_minutes
            <= (self.maximum_headway_minutes)
        ):
            raise ValueError("uniform headway falls outside policy bounds")
        expected_span = (self.trip_count - 1) * self.uniform_headway_minutes
        if self.planned_end_minute - self.planned_start_minute != expected_span:
            raise ValueError("regime span is not exactly representable by its trip count")

    @property
    def measurable(self) -> bool:
        return self.trip_count >= 2


@dataclass(frozen=True, slots=True)
class Stage1NecessaryFeasibilityResultV1:
    allocation_candidate_fingerprint: str
    passed: bool
    constraint_families: tuple[Stage2ConstraintFamilyV1, ...]
    fleet_lower_bound: int | None
    explanation: str
    diagnostic_profile: str = STAGE_1_NECESSARY_FEASIBILITY_PROFILE_V1
    diagnostic_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.allocation_candidate_fingerprint.strip() or not self.explanation.strip():
            raise ValueError("Stage 1 necessary-feasibility identity and explanation are required")
        if self.diagnostic_profile != STAGE_1_NECESSARY_FEASIBILITY_PROFILE_V1:
            raise ValueError("Stage 1 necessary-feasibility profile is invalid")
        if self.fleet_lower_bound is not None:
            _positive_integer("fleet_lower_bound", self.fleet_lower_bound)
        if len(set(self.constraint_families)) != len(self.constraint_families):
            raise ValueError("necessary-feasibility constraint families must be unique")
        if self.passed and self.constraint_families:
            raise ValueError("a passed necessary-feasibility result cannot list failed families")
        if self.diagnostic_fingerprint and self.diagnostic_fingerprint != (
            calculate_stage_1_necessary_feasibility_fingerprint(self)
        ):
            raise ValueError("Stage 1 necessary-feasibility fingerprint is invalid")


def calculate_stage_1_necessary_feasibility_fingerprint(
    result: Stage1NecessaryFeasibilityResultV1,
) -> str:
    payload = jsonable(asdict(result))
    payload.pop("diagnostic_fingerprint", None)
    return canonical_sha256(payload)


def finalize_stage_1_necessary_feasibility(
    result: Stage1NecessaryFeasibilityResultV1,
) -> Stage1NecessaryFeasibilityResultV1:
    return replace(
        result,
        diagnostic_fingerprint=calculate_stage_1_necessary_feasibility_fingerprint(result),
    )


@dataclass(frozen=True, slots=True)
class TripAllocationPlanV1:
    source_b_fingerprint: str
    demand_authority_fingerprint: str
    optimization_mode: ScenarioCOptimizationModeV1
    demand_authority_mode: DemandAllocationAuthorityModeV1
    allocation_plan_profile: str
    uniform_regime_profile: str
    final_tail_policy_fingerprint: str
    total_trips: int
    trips_by_direction: tuple[tuple[ContractDirection, int], ...]
    allocation_blocks: tuple[TripAllocationBlockV1, ...]
    proposed_regimes: tuple[ProposedServiceRegimeV1, ...]
    final_service_sentinels: tuple[FinalServiceSentinelV1, ...]
    necessary_feasibility: Stage1NecessaryFeasibilityResultV1
    objective_vector: tuple[int, ...]
    solve_status: TripAllocationSolveStatusV1
    solve_duration_seconds: float
    allocation_fingerprint: str
    rank: int = 1

    def __post_init__(self) -> None:
        if self.optimization_mode != ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE:
            raise ValueError("TripAllocationPlanV1 is valid only for B-anchored two-stage mode")
        if self.uniform_regime_profile != SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE:
            raise ValueError("allocation plan must bind the V3 uniform-regime profile")
        if not all(
            value.strip()
            for value in (
                self.source_b_fingerprint,
                self.demand_authority_fingerprint,
                self.allocation_plan_profile,
                self.final_tail_policy_fingerprint,
            )
        ):
            raise ValueError("allocation authority fingerprints and profiles must be non-empty")
        _positive_integer("total_trips", self.total_trips)
        _positive_integer("rank", self.rank)
        if (
            isinstance(self.solve_duration_seconds, bool)
            or not isinstance(self.solve_duration_seconds, (int, float))
            or not math.isfinite(float(self.solve_duration_seconds))
            or self.solve_duration_seconds < 0
        ):
            raise ValueError("allocation solve duration must be finite and non-negative")
        direction_counts = dict(self.trips_by_direction)
        if len(self.trips_by_direction) != 2 or set(direction_counts) != {
            ContractDirection.OUTBOUND,
            ContractDirection.INBOUND,
        }:
            raise ValueError("allocation plan must bind both directional totals")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in direction_counts.values()
        ):
            raise ValueError("directional trip totals must be positive integers")
        if sum(direction_counts.values()) != self.total_trips:
            raise ValueError("allocation directional totals do not equal the daily total")
        sentinel_counts = {
            direction: sum(item.direction == direction for item in self.final_service_sentinels)
            for direction in direction_counts
        }
        if len({item.direction for item in self.final_service_sentinels}) != len(
            self.final_service_sentinels
        ) or any(
            item.boundary_semantics != ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL
            for item in self.final_service_sentinels
        ):
            raise ValueError("final-service sentinels must be unique by direction")
        allocated = {
            direction: sum(
                dict(block.directional_trip_counts).get(direction, 0)
                for block in self.allocation_blocks
            )
            + sentinel_counts[direction]
            for direction in direction_counts
        }
        if allocated != direction_counts:
            raise ValueError("block allocation does not reproduce fixed directional counts")
        regime_counts = {
            direction: sum(
                regime.trip_count
                for regime in self.proposed_regimes
                if regime.direction == direction
            )
            for direction in direction_counts
        }
        if regime_counts != direction_counts:
            raise ValueError("regime allocation does not reproduce fixed directional counts")
        if self.allocation_fingerprint and (
            self.allocation_fingerprint != calculate_allocation_fingerprint(self)
        ):
            raise ValueError("allocation fingerprint does not match immutable plan facts")
        if (
            not self.necessary_feasibility.passed
            or self.necessary_feasibility.diagnostic_fingerprint
            != calculate_stage_1_necessary_feasibility_fingerprint(self.necessary_feasibility)
        ):
            raise ValueError("an admitted allocation plan requires a passed feasibility probe")


def allocation_fingerprint_payload(plan: TripAllocationPlanV1) -> dict[str, object]:
    payload = jsonable(asdict(plan))
    payload.pop("allocation_fingerprint", None)
    payload.pop("solve_duration_seconds", None)
    return {
        "fingerprint_profile": plan.allocation_plan_profile,
        "allocation_plan": payload,
    }


def calculate_allocation_fingerprint(plan: TripAllocationPlanV1) -> str:
    return canonical_sha256(allocation_fingerprint_payload(plan))


def finalize_allocation_plan(plan: TripAllocationPlanV1) -> TripAllocationPlanV1:
    return replace(plan, allocation_fingerprint=calculate_allocation_fingerprint(plan))


@dataclass(frozen=True, slots=True)
class Stage1AllocationResultV1:
    solve_status: TripAllocationSolveStatusV1
    plans: tuple[TripAllocationPlanV1, ...]
    candidate_count: int
    admissible_allocation_count: int
    necessary_feasibility_pruned_count: int
    pruned_necessary_feasibility: tuple[Stage1NecessaryFeasibilityResultV1, ...]
    solve_duration_seconds: float
    budget_exhausted: bool
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Stage2InfeasibilityDiagnosticV1:
    allocation_plan_fingerprint: str
    native_solver_status: NativeSolverStatus
    constraint_families: tuple[Stage2ConstraintFamilyV1, ...]
    explanation: str
    diagnostic_profile: str = STAGE_2_INFEASIBILITY_DIAGNOSTIC_PROFILE_V1
    diagnostic_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.allocation_plan_fingerprint.strip() or not self.explanation.strip():
            raise ValueError(
                "Stage 2 infeasibility diagnostic identity and explanation are required"
            )
        if self.native_solver_status != NativeSolverStatus.INFEASIBLE:
            raise ValueError("Stage 2 infeasibility diagnostic requires native INFEASIBLE status")
        if not self.constraint_families or len(set(self.constraint_families)) != len(
            self.constraint_families
        ):
            raise ValueError("Stage 2 diagnostic families must be non-empty and unique")
        if self.diagnostic_profile != STAGE_2_INFEASIBILITY_DIAGNOSTIC_PROFILE_V1:
            raise ValueError("Stage 2 infeasibility diagnostic profile is invalid")
        if self.diagnostic_fingerprint and self.diagnostic_fingerprint != (
            calculate_stage_2_infeasibility_diagnostic_fingerprint(self)
        ):
            raise ValueError("Stage 2 infeasibility diagnostic fingerprint is invalid")


def calculate_stage_2_infeasibility_diagnostic_fingerprint(
    diagnostic: Stage2InfeasibilityDiagnosticV1,
) -> str:
    payload = jsonable(asdict(diagnostic))
    payload.pop("diagnostic_fingerprint", None)
    return canonical_sha256(payload)


def finalize_stage_2_infeasibility_diagnostic(
    diagnostic: Stage2InfeasibilityDiagnosticV1,
) -> Stage2InfeasibilityDiagnosticV1:
    return replace(
        diagnostic,
        diagnostic_fingerprint=(calculate_stage_2_infeasibility_diagnostic_fingerprint(diagnostic)),
    )


@dataclass(frozen=True, slots=True)
class Stage2TimetableResultV1:
    solver_status: NativeSolverStatus
    candidate: RawScheduleCandidateV1 | None
    allocation_plan: TripAllocationPlanV1
    solve_duration_seconds: float
    variable_count: int
    constraint_count: int
    maximum_departure_domain_width_minutes: int
    full_service_window_domain_count: int
    infeasibility_diagnostic: Stage2InfeasibilityDiagnosticV1 | None
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TwoStageNativeRunV1:
    solver_run: SolverRunResultV1
    stage_1_result: Stage1AllocationResultV1
    selected_allocation_plan: TripAllocationPlanV1 | None
    final_tail_metrics: tuple[FinalServiceTailMetricsV1, ...]
    diagnostics: TwoStageSolveDiagnosticsV1


@dataclass(frozen=True, slots=True)
class FinalServiceTailMetricsV1:
    direction: ContractDirection
    final_tail_start: int
    final_tail_end: int
    final_tail_span_minutes: int
    final_tail_trip_count: int
    final_tail_uniform_headway_minutes: int | None
    minutes_from_penultimate_trip_to_last_departure: int | None


@dataclass(frozen=True, slots=True)
class TwoStageSolveDiagnosticsV1:
    stage_1_candidate_count: int
    stage_1_admissible_allocation_count: int
    stage_1_necessary_feasibility_pruned_count: int
    stage_2_allocation_attempt_count: int
    stage_2_variable_count: int
    stage_2_constraint_count: int
    maximum_stage_2_departure_domain_width_minutes: int
    full_service_window_domain_count: int
    regime_count_by_direction: tuple[tuple[ContractDirection, int], ...]
    solve_duration_stage_1: float
    solve_duration_stage_2: float
    total_solve_duration: float
    total_budget_seconds: float
    budget_exhausted: bool
    stage_2_infeasibility_diagnostics: tuple[Stage2InfeasibilityDiagnosticV1, ...]


@dataclass(frozen=True, slots=True)
class TwoStageScenarioCResultV1:
    final_acceptance_state: FinalAcceptanceStateV1
    native_solver_status: NativeSolverStatus | None
    allocation_plan: TripAllocationPlanV1 | None
    candidate_outcome: ScheduleGenerationOutcomeV1 | None
    final_tail_metrics: tuple[FinalServiceTailMetricsV1, ...]
    diagnostics: TwoStageSolveDiagnosticsV1
    b_quality_vector: tuple[int, ...]
    c_quality_vector: tuple[int, ...] | None
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]
    result_fingerprint: str


def two_stage_result_fingerprint_payload(result: TwoStageScenarioCResultV1) -> dict[str, object]:
    payload = jsonable(asdict(result))
    payload.pop("result_fingerprint", None)
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, dict):
        diagnostics.pop("solve_duration_stage_1", None)
        diagnostics.pop("solve_duration_stage_2", None)
        diagnostics.pop("total_solve_duration", None)
    outcome = payload.get("candidate_outcome")
    if isinstance(outcome, dict):
        outcome.pop("solve_duration_seconds", None)
        solution = outcome.get("solution")
        if isinstance(solution, dict):
            solution.pop("solve_duration_seconds", None)
    allocation = payload.get("allocation_plan")
    if isinstance(allocation, dict):
        allocation.pop("solve_duration_seconds", None)
    return {
        "fingerprint_profile": TWO_STAGE_RESULT_FINGERPRINT_PROFILE_V1,
        "acceptance_profile": TWO_STAGE_ACCEPTANCE_PROFILE_V1,
        "result": payload,
    }


def finalize_two_stage_result(result: TwoStageScenarioCResultV1) -> TwoStageScenarioCResultV1:
    return replace(
        result,
        result_fingerprint=canonical_sha256(two_stage_result_fingerprint_payload(result)),
    )


__all__ = [
    "B_ANCHORED_TWO_STAGE_REBALANCE_V1",
    "COMBINED_DEMAND_FIXED_DIRECTION_COUNTS",
    "DIRECTIONAL_DEMAND_FIXED_DIRECTION_COUNTS",
    "FINAL_SERVICE_SENTINEL",
    "SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE",
    "STAGE_1_NECESSARY_FEASIBILITY_PROFILE_V1",
    "STAGE_2_INFEASIBILITY_DIAGNOSTIC_PROFILE_V1",
    "TRIP_ALLOCATION_PLAN_PROFILE_V1",
    "DemandAllocationAuthorityModeV1",
    "FinalAcceptanceStateV1",
    "FinalServiceSentinelV1",
    "FinalServiceTailMetricsV1",
    "FinalServiceTailPolicyV1",
    "ProposedServiceRegimeV1",
    "ScenarioCOptimizationModeV1",
    "ServiceBoundarySemanticsV1",
    "Stage1AllocationResultV1",
    "Stage1NecessaryFeasibilityResultV1",
    "Stage2ConstraintFamilyV1",
    "Stage2InfeasibilityDiagnosticV1",
    "Stage2TimetableResultV1",
    "TripAllocationBlockV1",
    "TripAllocationPlanV1",
    "TripAllocationSolveStatusV1",
    "TwoStageScenarioCResultV1",
    "TwoStageNativeRunV1",
    "TwoStageSolveDiagnosticsV1",
    "UniformIntegerRegimePolicyV3",
    "allocation_fingerprint_payload",
    "calculate_allocation_fingerprint",
    "calculate_stage_1_necessary_feasibility_fingerprint",
    "calculate_stage_2_infeasibility_diagnostic_fingerprint",
    "finalize_allocation_plan",
    "finalize_stage_1_necessary_feasibility",
    "finalize_stage_2_infeasibility_diagnostic",
    "finalize_two_stage_result",
    "is_strict_uniform_integer_headway_sequence_v3",
    "two_stage_result_fingerprint_payload",
]

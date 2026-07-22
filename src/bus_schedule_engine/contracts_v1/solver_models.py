from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.models import DemandRecord, ScenarioParameters, Trip

from .evaluation import (
    BlockEvaluationV1,
    BlockSupplyPlanV1,
    FleetAssessmentV1,
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
)
from .models import (
    CONTRACT_VERSION,
    ContractDirection,
    DepartureTerminal,
    NormalizedInputBundleV1,
)


class SolverExecutionStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    COMPLETED = "COMPLETED"


class NativeSolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    MODEL_INVALID = "MODEL_INVALID"
    UNKNOWN = "UNKNOWN"


class GenerationResultStatus(StrEnum):
    SOLUTION_ACCEPTED = "SOLUTION_ACCEPTED"
    NO_FEASIBLE_C_WITH_B_PARAMETERS = "NO_FEASIBLE_C_WITH_B_PARAMETERS"
    C_NOT_FOUND_WITHIN_SOLVE_LIMIT = "C_NOT_FOUND_WITHIN_SOLVE_LIMIT"
    C_NOT_GENERATED_MODEL_INVALID = "C_NOT_GENERATED_MODEL_INVALID"
    C_NOT_GENERATED_INSUFFICIENT_DATA = "C_NOT_GENERATED_INSUFFICIENT_DATA"
    C_NOT_REQUIRED_B_SUITABLE = "C_NOT_REQUIRED_B_SUITABLE"
    CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR = "CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR"


class CandidateValidationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class InitialFleetPositioningMode(StrEnum):
    SOLVER_DETERMINED = "solver_determined"
    FIXED = "fixed"
    BOUNDED = "bounded"


@dataclass(frozen=True, slots=True)
class OperatingParameterLockV1:
    field: str
    value: object
    source_fingerprint: str
    locked: bool = True
    authorized_exception: str | None = None


@dataclass(frozen=True, slots=True)
class RawCandidateTripV1:
    c_trip_id: str
    source_b_trip_id: str
    direction: ContractDirection
    departure_terminal: DepartureTerminal
    b_departure_time: int
    c_departure_time: int
    arrival_time: int
    runtime_minutes: int
    shift_minutes: float
    previous_b_headway: float | None
    previous_c_headway: float | None
    headway_regime_id: str
    change_reason: str


@dataclass(frozen=True, slots=True)
class RawHeadwayRegimeV1:
    regime_id: str
    direction: ContractDirection
    start_time: int
    end_time: int
    trip_count: int
    target_headway: float
    actual_headway_sequence: tuple[float, ...]
    boundary_reason: str
    legacy_regularity_status: str


@dataclass(frozen=True, slots=True)
class RawScheduleCandidateV1:
    solver_status: NativeSolverStatus
    solver_adapter: str
    solve_duration_seconds: float
    candidate_fingerprint: str
    exact_timetable: tuple[RawCandidateTripV1, ...]
    headway_regimes: tuple[RawHeadwayRegimeV1, ...]
    explanation: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SolverRunResultV1:
    execution_status: SolverExecutionStatus
    solver_status: NativeSolverStatus
    solver_adapter: str
    solve_duration_seconds: float
    candidate: RawScheduleCandidateV1 | None
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SolutionTripV1:
    c_trip_id: str
    source_b_trip_id: str
    direction: ContractDirection
    departure_terminal: DepartureTerminal
    b_departure_time: int
    c_departure_time: int
    shift_minutes: float
    previous_b_headway: float | None
    previous_c_headway: float | None
    headway_regime_id: str
    change_reason: str
    vehicle_assignment: str


@dataclass(frozen=True, slots=True)
class SolutionHeadwayRegimeV1:
    regime_id: str
    direction: ContractDirection
    start_time: int
    end_time: int
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
class FleetAssignmentV1:
    vehicle_id: str
    c_trip_id: str
    departure_terminal: DepartureTerminal
    arrival_terminal: DepartureTerminal
    departure_time: int
    arrival_time: int
    ready_time: int


@dataclass(frozen=True, slots=True)
class StockProfileEventV1:
    event_time: int
    event_type: str
    trip_id: str | None
    stock_before: int
    stock_after: int
    arriving_or_ready_vehicle_count: int
    departure_count: int


@dataclass(frozen=True, slots=True)
class ScheduleSolutionV1:
    solver_status: NativeSolverStatus
    solver_adapter: str
    solve_duration_seconds: float
    solution_fingerprint: str
    source_b_fingerprint: str
    operating_parameter_locks: tuple[OperatingParameterLockV1, ...]
    c_block_supply_plan: tuple[BlockSupplyPlanV1, ...]
    c_headway_regimes: tuple[SolutionHeadwayRegimeV1, ...]
    c_exact_timetable: tuple[SolutionTripV1, ...]
    fleet_assignment: tuple[FleetAssignmentV1, ...]
    available_fleet_limit: int
    approved_active_fleet: int | None
    minimum_required_fleet: int
    recommended_initial_fleet_terminal_1: int
    recommended_initial_fleet_terminal_2: int
    initial_fleet_positioning_mode: InitialFleetPositioningMode
    fleet_margin: int
    maximum_simultaneous_vehicle_use: int
    vehicle_stock_profile_terminal_1: tuple[StockProfileEventV1, ...]
    vehicle_stock_profile_terminal_2: tuple[StockProfileEventV1, ...]
    fleet_feasibility_status: str
    block_evaluation: tuple[BlockEvaluationV1, ...]
    residual_overload: float
    shifted_trip_count: int
    total_shift_minutes: float
    maximum_shift_minutes: float
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    @property
    def status(self) -> GenerationResultStatus:
        return GenerationResultStatus.SOLUTION_ACCEPTED


@dataclass(frozen=True, slots=True)
class RejectedCandidateDiagnosticV1:
    candidate_fingerprint: str
    rejection_codes: tuple[str, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class CandidateValidationResultV1:
    status: CandidateValidationStatus
    rejection_codes: tuple[str, ...]
    summary: str
    fleet_assessment: FleetAssessmentV1 | None
    solution: ScheduleSolutionV1 | None

    @property
    def passed(self) -> bool:
        return self.status == CandidateValidationStatus.ACCEPTED


@dataclass(frozen=True, slots=True)
class ScheduleGenerationOutcomeV1:
    result_status: GenerationResultStatus
    execution_status: SolverExecutionStatus
    solver_status: NativeSolverStatus | None
    solver_adapter: str | None
    solve_duration_seconds: float
    outcome_fingerprint: str
    source_b_fingerprint: str
    solution: ScheduleSolutionV1 | None
    diagnostic_candidate: RejectedCandidateDiagnosticV1 | None
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ScheduleProblemV1:
    normalized_inputs: NormalizedInputBundleV1
    b_evaluation: ScenarioBEvaluationBundleV1
    evaluation_policy: ScenarioBEvaluationPolicyV1
    legacy_parameters: ScenarioParameters
    legacy_trips_b: tuple[Trip, ...]
    legacy_demand: tuple[DemandRecord, ...]
    heuristic_config: ScenarioCConfig
    problem_fingerprint: str

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


class ScheduleSolver(Protocol):
    adapter_id: str

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1: ...

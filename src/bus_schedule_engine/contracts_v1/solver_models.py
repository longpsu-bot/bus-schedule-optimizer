from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from bus_schedule_engine.models import (
    ProtectedServiceFloorCandidateValidationV1,
    ProtectedServiceFloorEnforcementAuthorityV1,
)

from .demand_resolution import DemandAnalysisBlockV1, DemandResolutionContractV1
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
    DemandConfidence,
    DemandResponseMode,
    DepartureTerminal,
    NormalizedInputBundleV1,
    ScenarioAInput,
    ScenarioBInput,
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


class DirectionTripLockMode(StrEnum):
    FIXED_BY_DIRECTION = "fixed_by_direction"
    TOTAL_ONLY = "total_only"


class FleetConstraintMode(StrEnum):
    AVAILABLE_UPPER_BOUND = "available_upper_bound"
    EXACT_SCHEDULED_FLEET = "exact_scheduled_fleet"


class BoundaryConvention(StrEnum):
    HALF_OPEN = "half_open"
    HALF_OPEN_WITH_FINAL_SENTINEL = "half_open_with_final_sentinel"
    HALF_OPEN_WITH_DOCUMENTED_FINAL_INCLUSIVE = "half_open_with_documented_final_inclusive"


@dataclass(frozen=True, slots=True)
class DirectionRedistributionAuthorizationV1:
    enabled: bool
    authorized_by: str
    directional_demand_confidence: DemandConfidence


@dataclass(frozen=True, slots=True)
class InitialFleetValuesV1:
    terminal_1: int
    terminal_2: int


@dataclass(frozen=True, slots=True)
class InitialFleetBoundsV1:
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class BoundedInitialFleetV1:
    terminal_1: InitialFleetBoundsV1
    terminal_2: InitialFleetBoundsV1


@dataclass(frozen=True, slots=True)
class SolverPolicyV1:
    time_limit_seconds: float | None = None
    worker_count: int | None = None
    random_seed: int | None = None
    require_independent_validation: bool = True


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
    protected_service_floor_enforcement_fingerprint: str | None = None
    protected_service_floor_validation_fingerprint: str | None = None

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
    protected_service_floor_enforcement_fingerprint: str | None = None
    protected_service_floor_validation_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateValidationResultV1:
    status: CandidateValidationStatus
    rejection_codes: tuple[str, ...]
    summary: str
    fleet_assessment: FleetAssessmentV1 | None
    solution: ScheduleSolutionV1 | None
    protected_service_floor_validation: ProtectedServiceFloorCandidateValidationV1 | None = None

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
    protected_service_floor_enforcement_fingerprint: str | None = None
    protected_service_floor_validation_fingerprint: str | None = None

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ScheduleProblemV1:
    problem_id: str
    problem_fingerprint: str
    evaluation_fingerprint: str
    source_a_fingerprint: str | None
    source_b_fingerprint: str
    observed_demand_fingerprint: str | None
    solver_adapter: str
    adapter_context_fingerprint: str
    scenario_a: ScenarioAInput | None
    scenario_b: ScenarioBInput
    demand_response_mode: DemandResponseMode | None
    demand_resolution: DemandResolutionContractV1 | None
    analysis_blocks: tuple[DemandAnalysisBlockV1, ...]
    operating_parameter_locks: tuple[OperatingParameterLockV1, ...]
    direction_trip_lock_mode: DirectionTripLockMode
    direction_redistribution_authorization: DirectionRedistributionAuthorizationV1 | None
    fleet_constraint_mode: FleetConstraintMode
    initial_fleet_positioning_mode: InitialFleetPositioningMode
    fixed_initial_fleet: InitialFleetValuesV1 | None
    bounded_initial_fleet: BoundedInitialFleetV1 | None
    planning_load_factor_ceiling: float
    critical_load_factor_ceiling: float
    block_requirements: tuple[BlockSupplyPlanV1, ...]
    boundary_convention: BoundaryConvention
    solver_policy: SolverPolicyV1

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ScheduleGenerationContextV1:
    problem: ScheduleProblemV1
    normalized_inputs: NormalizedInputBundleV1
    b_evaluation: ScenarioBEvaluationBundleV1
    evaluation_policy: ScenarioBEvaluationPolicyV1
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None

    @property
    def problem_fingerprint(self) -> str:
        return self.problem.problem_fingerprint

    @property
    def contract_version(self) -> str:
        return self.problem.contract_version


class ScheduleSolver(Protocol):
    adapter_id: str

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1: ...

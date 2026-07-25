from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from enum import Enum, StrEnum
from itertools import combinations
from typing import Any

from .demand_coverage import (
    COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE,
    DEMAND_DEPARTURE_NOT_COVERED,
    DEMAND_DIRECTION_STREAM_MISSING,
    DEMAND_SERVICE_WINDOW_NOT_COVERED,
    DEMAND_TEMPORAL_COVERAGE_GAP,
    MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT,
    DemandCoverageAssessmentV1,
    DemandCoverageModeV1,
    assess_demand_coverage_v1,
)
from .evaluation import (
    BDisposition,
    BlockSupplyStatus,
    FleetAssessmentV1,
    ScenarioBEvaluationPolicyV1,
    assess_scenario_b_fleet_v1,
)
from .fleet_assignment import ContractFleetAssignmentError, assign_contract_v1_fleet
from .headway_regimes import (
    ContinuousHeadwayRegimeV1,
    segment_continuous_headway_regimes_v1,
)
from .models import (
    CONTRACT_VERSION,
    ContractDirection,
    DemandConfidence,
    DepartureTerminal,
    ExactTimetableTrip,
    ScenarioBInput,
    TripsByDirection,
)
from .serialization import canonical_sha256, scenario_fingerprint
from .solver_models import (
    BoundaryConvention,
    DirectionTripLockMode,
    FleetConstraintMode,
    InitialFleetPositioningMode,
    RawCandidateTripV1,
    ScheduleGenerationContextV1,
)
from .validation import validate_scenario_input

EVALUATOR_FINGERPRINT_PROFILE = "contract_v1_d1_service_adjustment"
HEURISTIC_ADAPTER_ID = "legacy_heuristic_v1"

ADJUSTMENT_DECISION_DATA_INSUFFICIENT = "ADJUSTMENT_DECISION_DATA_INSUFFICIENT"
DIRECTIONAL_ACTION_NOT_SUPPORTED_BY_COMBINED_DEMAND = (
    "DIRECTIONAL_ACTION_NOT_SUPPORTED_BY_COMBINED_DEMAND"
)
INSUFFICIENT_DAYS_FOR_REDUCTION_DECISION = "INSUFFICIENT_DAYS_FOR_REDUCTION_DECISION"
TOTAL_TRIP_SUPPLY_SHORTAGE = "TOTAL_TRIP_SUPPLY_SHORTAGE"
BLOCK_TRIP_SHORTAGE = "BLOCK_TRIP_SHORTAGE"
ELIGIBLE_DONOR_SUPPLY_AVAILABLE = "ELIGIBLE_DONOR_SUPPLY_AVAILABLE"
TEMPORAL_TRIP_ALLOCATION_MISMATCH = "TEMPORAL_TRIP_ALLOCATION_MISMATCH"
STABLE_RESIDUAL_TRIP_SURPLUS = "STABLE_RESIDUAL_TRIP_SURPLUS"
LOW_LOAD_REVIEW_ONLY = "LOW_LOAD_REVIEW_ONLY"
HEADWAY_RANGE_ABOVE_BALANCED_TOLERANCE = "HEADWAY_RANGE_ABOVE_BALANCED_TOLERANCE"
REGULAR_HEADWAY_RATE_BELOW_REQUIRED = "REGULAR_HEADWAY_RATE_BELOW_REQUIRED"
ZERO_HEADWAY_EXCEPTION_PRESENT = "ZERO_HEADWAY_EXCEPTION_PRESENT"
FLEET_RATIO_ABOVE_ONE = "FLEET_RATIO_ABOVE_ONE"
NEGATIVE_TERMINAL_STOCK = "NEGATIVE_TERMINAL_STOCK"
TURNAROUND_MARGIN_NEGATIVE = "TURNAROUND_MARGIN_NEGATIVE"
CURRENT_SOLVER_CAN_IMPLEMENT = "CURRENT_SOLVER_CAN_IMPLEMENT"
CURRENT_SOLVER_CAPABILITY_INSUFFICIENT = "CURRENT_SOLVER_CAPABILITY_INSUFFICIENT"
JOINT_DONOR_CAPACITY_NOT_PROVEN = "JOINT_DONOR_CAPACITY_NOT_PROVEN"
JOINT_DONOR_SEARCH_LIMIT_REACHED = "JOINT_DONOR_SEARCH_LIMIT_REACHED"
JOINT_REDUCTION_SEARCH_LIMIT_REACHED = "JOINT_REDUCTION_SEARCH_LIMIT_REACHED"
JOINT_REDUCTION_MAXIMUM_NOT_PROVEN = "JOINT_REDUCTION_MAXIMUM_NOT_PROVEN"
RESPACE_DIAGNOSTIC_VALIDATION_FAILED = "RESPACE_DIAGNOSTIC_VALIDATION_FAILED"

_DIRECTION_ORDER = {
    ContractDirection.OUTBOUND: 0,
    ContractDirection.INBOUND: 1,
    ContractDirection.COMBINED: 2,
}

_HeadwayClassificationResult = tuple[
    float,
    float | None,
    float | None,
    float | None,
    int,
    "HeadwayRegularityClassificationV1",
]


class ServiceAdjustmentDecisionV1(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    TECHNICAL_ADJUSTMENT_REQUIRED = "TECHNICAL_ADJUSTMENT_REQUIRED"
    INCREASE_TOTAL_TRIPS = "INCREASE_TOTAL_TRIPS"
    REDISTRIBUTE_TRIPS = "REDISTRIBUTE_TRIPS"
    REDUCE_TOTAL_TRIPS = "REDUCE_TOTAL_TRIPS"
    REDISTRIBUTE_DEPARTURE_TIMES = "REDISTRIBUTE_DEPARTURE_TIMES"
    KEEP_CURRENT_TIMETABLE = "KEEP_CURRENT_TIMETABLE"


class HeadwayRegularityClassificationV1(StrEnum):
    REGULAR = "REGULAR"
    BALANCED_ROUNDING = "BALANCED_ROUNDING"
    IRREGULAR = "IRREGULAR"
    EXCEPTIONAL = "EXCEPTIONAL"


@dataclass(frozen=True, slots=True)
class ServiceAdjustmentPolicyV1:
    planning_load_factor_ceiling: float = 0.85
    critical_load_factor_ceiling: float = 0.90
    low_load_review_threshold: float = 0.30
    minimum_authoritative_demand_confidence: DemandConfidence = DemandConfidence.MEDIUM
    headway_rounding_tolerance_minutes: int = 1
    required_regular_headway_rate: float = 1.0
    minimum_sustained_change_intervals: int = 2
    minimum_material_headway_change_minutes: int = 5
    minimum_material_service_rate_change_ratio: float = 0.15
    maximum_headway_regimes_per_direction: int = 6
    minimum_valid_observed_days_for_reduction: int = 3
    minimum_surplus_consistency_rate: float = 0.80
    minimum_residual_surplus_trips_for_reduction: int = 1
    minimum_service_trips_per_direction: int = 1
    maximum_joint_donor_search_states: int = 10_000
    maximum_joint_reduction_search_states: int = 10_000
    fixed_resource_solver_adapter: str = HEURISTIC_ADAPTER_ID
    fixed_resource_authorized_decisions: tuple[ServiceAdjustmentDecisionV1, ...] = (
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.fixed_resource_authorized_decisions, tuple):
            raise ValueError("fixed_resource_authorized_decisions must be an immutable tuple")
        for name, value in (
            ("planning_load_factor_ceiling", self.planning_load_factor_ceiling),
            ("critical_load_factor_ceiling", self.critical_load_factor_ceiling),
            ("low_load_review_threshold", self.low_load_review_threshold),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0 < float(value) <= 1
            ):
                raise ValueError(f"{name} must be finite and in (0, 1]")
        if self.planning_load_factor_ceiling > self.critical_load_factor_ceiling:
            raise ValueError("planning load-factor ceiling may not exceed the critical ceiling")
        if self.headway_rounding_tolerance_minutes < 0:
            raise ValueError("headway_rounding_tolerance_minutes must be non-negative")
        if not 0 <= self.required_regular_headway_rate <= 1:
            raise ValueError("required_regular_headway_rate must be in [0, 1]")
        if self.minimum_sustained_change_intervals < 1:
            raise ValueError("minimum_sustained_change_intervals must be positive")
        if self.minimum_material_headway_change_minutes < 0:
            raise ValueError("minimum_material_headway_change_minutes must be non-negative")
        if not 0 <= self.minimum_material_service_rate_change_ratio <= 1:
            raise ValueError("minimum material service-rate change must be in [0, 1]")
        if self.maximum_headway_regimes_per_direction < 1:
            raise ValueError("maximum_headway_regimes_per_direction must be positive")
        if self.minimum_valid_observed_days_for_reduction < 1:
            raise ValueError("minimum_valid_observed_days_for_reduction must be positive")
        if not 0 < self.minimum_surplus_consistency_rate <= 1:
            raise ValueError("minimum_surplus_consistency_rate must be in (0, 1]")
        if self.minimum_residual_surplus_trips_for_reduction < 1:
            raise ValueError("minimum_residual_surplus_trips_for_reduction must be positive")
        if self.minimum_service_trips_per_direction < 1:
            raise ValueError("minimum_service_trips_per_direction must be positive")
        if self.maximum_joint_donor_search_states < 1:
            raise ValueError("maximum_joint_donor_search_states must be positive")
        if self.maximum_joint_reduction_search_states < 1:
            raise ValueError("maximum_joint_reduction_search_states must be positive")
        if not self.fixed_resource_solver_adapter.strip():
            raise ValueError("fixed_resource_solver_adapter is required")
        if len(set(self.fixed_resource_authorized_decisions)) != len(
            self.fixed_resource_authorized_decisions
        ):
            raise ValueError("fixed_resource_authorized_decisions may not contain duplicates")


@dataclass(frozen=True, slots=True)
class RepeatabilityDayEvidenceV1:
    day_reference: str
    fully_supported: bool
    current_daily_trips: int
    required_daily_trips: int | None
    shortage_block_count: int
    no_service_with_demand_block_count: int
    critical_block_count: int
    authoritative_evidence_fingerprint: str
    warning_block_count: int = 0

    def __post_init__(self) -> None:
        if not self.day_reference.strip():
            raise ValueError("day_reference is required")
        if self.current_daily_trips < 0:
            raise ValueError("current_daily_trips must be non-negative")
        if self.required_daily_trips is not None and self.required_daily_trips < 0:
            raise ValueError("required_daily_trips must be non-negative when present")
        for name, value in (
            ("shortage_block_count", self.shortage_block_count),
            ("no_service_with_demand_block_count", self.no_service_with_demand_block_count),
            ("critical_block_count", self.critical_block_count),
            ("warning_block_count", self.warning_block_count),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.fully_supported and self.required_daily_trips is None:
            raise ValueError("fully supported days require required_daily_trips")
        if not self.authoritative_evidence_fingerprint.strip():
            raise ValueError("authoritative_evidence_fingerprint is required")

    @property
    def daily_surplus_trips(self) -> int:
        if self.required_daily_trips is None:
            return 0
        return max(0, self.current_daily_trips - self.required_daily_trips)

    @property
    def qualifies_as_surplus_day(self) -> bool:
        return bool(
            self.fully_supported
            and self.required_daily_trips is not None
            and self.required_daily_trips < self.current_daily_trips
            and self.shortage_block_count == 0
            and self.no_service_with_demand_block_count == 0
            and self.critical_block_count == 0
        )


@dataclass(frozen=True, slots=True)
class RepeatabilityEvidenceV1:
    days: tuple[RepeatabilityDayEvidenceV1, ...]
    configured_minimum_valid_day_count: int
    configured_minimum_surplus_consistency_rate: float
    representative_day_type_or_provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.days, tuple):
            raise ValueError("repeatability days must be an immutable tuple")
        if self.configured_minimum_valid_day_count < 1:
            raise ValueError("configured_minimum_valid_day_count must be positive")
        if not 0 < self.configured_minimum_surplus_consistency_rate <= 1:
            raise ValueError("configured minimum surplus consistency must be in (0, 1]")
        if not self.representative_day_type_or_provenance.strip():
            raise ValueError("representative day type or provenance is required")
        day_references = tuple(day.day_reference for day in self.days)
        if len(set(day_references)) != len(day_references):
            raise ValueError("repeatability days may not contain duplicate day references")
        if day_references != tuple(sorted(day_references)):
            raise ValueError("repeatability days must use deterministic day-reference order")

    @property
    def valid_days(self) -> tuple[RepeatabilityDayEvidenceV1, ...]:
        return tuple(
            day for day in self.days if day.fully_supported and day.required_daily_trips is not None
        )

    @property
    def valid_observed_day_count(self) -> int:
        return len(self.valid_days)

    @property
    def surplus_day_count(self) -> int:
        return sum(day.qualifies_as_surplus_day for day in self.valid_days)

    @property
    def surplus_consistency_rate(self) -> float:
        if not self.valid_observed_day_count:
            return 0.0
        return self.surplus_day_count / self.valid_observed_day_count

    @property
    def daily_required_trip_sequence(self) -> tuple[int, ...]:
        return tuple(
            day.required_daily_trips
            for day in self.valid_days
            if day.required_daily_trips is not None
        )

    @property
    def daily_surplus_sequence(self) -> tuple[int, ...]:
        return tuple(
            day.daily_surplus_trips if day.qualifies_as_surplus_day else 0
            for day in self.valid_days
        )


@dataclass(frozen=True, slots=True)
class BlockAdjustmentEvidenceV1:
    direction: ContractDirection
    block_id: str
    block_start: int
    block_end: int
    current_trip_count: int
    passenger_demand: float
    nominal_capacity: float
    load_factor: float | None
    required_trips_at_planning_ceiling: int
    required_trips_at_critical_ceiling: int
    shortage_trips: int
    potential_surplus_trips: int
    block_status: BlockSupplyStatus
    demand_confidence: DemandConfidence
    source_block_ids: tuple[str, ...]
    donor_eligible: bool
    eligible_donor_trip_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JointDonorValidationEvidenceV1:
    direction: ContractDirection
    shortage_quantity: int
    candidate_trip_ids: tuple[str, ...]
    selected_jointly_feasible_trip_ids: tuple[str, ...]
    proven_joint_capacity: int
    search_complete: bool
    search_state_count: int
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JointReductionValidationEvidenceV1:
    candidate_trip_ids: tuple[str, ...]
    selected_jointly_feasible_trip_ids: tuple[str, ...]
    requested_upper_bound: int
    proven_supported_quantity: int
    maximum_proven: bool
    search_complete: bool
    search_state_count: int
    search_state_limit: int
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DailyAdjustmentEvidenceV1:
    fully_supported: bool
    current_daily_trips: int
    required_daily_trips: int | None
    required_daily_trips_at_critical_ceiling: int | None
    daily_trip_gap: int | None
    total_shortage_trips: int | None
    total_potential_surplus_trips: int | None
    maximum_supported_load_factor: float | None
    no_service_with_demand_block_count: int
    critical_block_count: int
    warning_block_count: int


@dataclass(frozen=True, slots=True)
class BlockAllocationShareV1:
    block_id: str
    demand_share: float
    trip_share: float


@dataclass(frozen=True, slots=True)
class DirectionalAllocationEvidenceV1:
    direction: ContractDirection
    total_directional_demand: float
    total_directional_trips: int
    block_shares: tuple[BlockAllocationShareV1, ...]
    allocation_mismatch_index: float


@dataclass(frozen=True, slots=True)
class RespaceDiagnosticEvidenceV1:
    diagnostic_scenario_fingerprint: str
    changed_trip_ids: tuple[str, ...]
    scenario_validation_issue_codes: tuple[str, ...]
    operating_lock_issue_codes: tuple[str, ...]
    runtime_issue_trip_ids: tuple[str, ...]
    turnaround_or_location_issue_codes: tuple[str, ...]
    minimum_required_fleet: int
    available_fleet_limit: int
    minimum_terminal_stock_terminal_1: int
    minimum_terminal_stock_terminal_2: int
    fleet_assignment_vehicle_count: int
    issue_codes: tuple[str, ...]
    passed: bool


@dataclass(frozen=True, slots=True)
class HeadwayRegimeEvidenceV1:
    regime_id: str
    direction: ContractDirection
    ordered_trip_ids: tuple[str, ...]
    first_departure: int
    last_departure: int
    actual_headway_sequence: tuple[float, ...]
    balanced_target_sequence: tuple[float, ...]
    minimum_headway: float | None
    maximum_headway: float | None
    headway_range: float | None
    regular_headway_rate: float
    zero_headway_count: int
    regularity_classification: HeadwayRegularityClassificationV1
    respace_technically_possible: bool
    respace_diagnostic: RespaceDiagnosticEvidenceV1 | None


@dataclass(frozen=True, slots=True)
class TechnicalEventEvidenceV1:
    terminal: DepartureTerminal
    event_time: int
    event_type: str
    trip_id: str
    stock_after: int


@dataclass(frozen=True, slots=True)
class TechnicalAdjustmentEvidenceV1:
    minimum_required_fleet: int
    available_fleet_limit: int
    fleet_ratio: float
    fleet_margin: int
    independently_derived_initial_fleet_terminal_1: int
    independently_derived_initial_fleet_terminal_2: int
    minimum_terminal_stock_terminal_1: int
    minimum_terminal_stock_terminal_2: int
    first_negative_stock_event: TechnicalEventEvidenceV1 | None
    minimum_turnaround_margin_minutes: float | None
    turnaround_violation_count: int
    affected_trip_or_vehicle_references: tuple[str, ...]
    runtime_inconsistencies: tuple[str, ...]
    first_last_departure_lock_failures: tuple[str, ...]
    trip_count_and_directional_count_inconsistencies: tuple[str, ...]
    context_validation_issue_codes: tuple[str, ...]
    issue_codes: tuple[str, ...]
    technically_feasible: bool


@dataclass(frozen=True, slots=True)
class ServiceAdjustmentAssessmentV1:
    assessment_id: str
    evaluator_fingerprint: str
    evaluator_fingerprint_profile: str
    source_problem_fingerprint: str
    source_b_fingerprint: str
    observed_demand_fingerprint: str | None
    authoritative_b_evaluation_fingerprint: str
    adjustment_policy_fingerprint: str
    primary_decision: ServiceAdjustmentDecisionV1
    reason_codes: tuple[str, ...]
    explanation: str
    evidence: tuple[str, ...]
    block_evidence: tuple[BlockAdjustmentEvidenceV1, ...]
    joint_donor_evidence: tuple[JointDonorValidationEvidenceV1, ...]
    daily_evidence: DailyAdjustmentEvidenceV1
    allocation_evidence: tuple[DirectionalAllocationEvidenceV1, ...]
    headway_evidence: tuple[HeadwayRegimeEvidenceV1, ...]
    technical_evidence: TechnicalAdjustmentEvidenceV1
    repeatability_evidence: RepeatabilityEvidenceV1 | None
    joint_reduction_evidence: JointReductionValidationEvidenceV1 | None
    maximum_supported_reduction_quantity: int
    limitations: tuple[str, ...]
    heuristic_authorized: bool
    authorized_generation_action: str | None

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _deduplicate(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _effective_policy(
    requested: ServiceAdjustmentPolicyV1 | None,
    evaluation_policy: ScenarioBEvaluationPolicyV1,
) -> ServiceAdjustmentPolicyV1:
    if requested is not None:
        return requested
    return ServiceAdjustmentPolicyV1(
        planning_load_factor_ceiling=evaluation_policy.planning_load_factor_ceiling,
        critical_load_factor_ceiling=evaluation_policy.critical_load_factor_ceiling,
        low_load_review_threshold=evaluation_policy.low_load_review_threshold,
        minimum_authoritative_demand_confidence=(
            evaluation_policy.minimum_authoritative_demand_confidence
        ),
    )


def _policy_payload(policy: ServiceAdjustmentPolicyV1) -> dict[str, object]:
    return {
        "planning_load_factor_ceiling": policy.planning_load_factor_ceiling,
        "critical_load_factor_ceiling": policy.critical_load_factor_ceiling,
        "low_load_review_threshold": policy.low_load_review_threshold,
        "minimum_authoritative_demand_confidence": (
            policy.minimum_authoritative_demand_confidence.value
        ),
        "headway_rounding_tolerance_minutes": policy.headway_rounding_tolerance_minutes,
        "required_regular_headway_rate": policy.required_regular_headway_rate,
        "minimum_sustained_change_intervals": policy.minimum_sustained_change_intervals,
        "minimum_material_headway_change_minutes": (policy.minimum_material_headway_change_minutes),
        "minimum_material_service_rate_change_ratio": (
            policy.minimum_material_service_rate_change_ratio
        ),
        "maximum_headway_regimes_per_direction": (policy.maximum_headway_regimes_per_direction),
        "minimum_valid_observed_days_for_reduction": (
            policy.minimum_valid_observed_days_for_reduction
        ),
        "minimum_surplus_consistency_rate": policy.minimum_surplus_consistency_rate,
        "minimum_residual_surplus_trips_for_reduction": (
            policy.minimum_residual_surplus_trips_for_reduction
        ),
        "minimum_service_trips_per_direction": policy.minimum_service_trips_per_direction,
        "maximum_joint_donor_search_states": policy.maximum_joint_donor_search_states,
        "maximum_joint_reduction_search_states": (policy.maximum_joint_reduction_search_states),
        "fixed_resource_solver_adapter": policy.fixed_resource_solver_adapter,
        "fixed_resource_authorized_decisions": [
            item.value for item in policy.fixed_resource_authorized_decisions
        ],
    }


def _coverage(context: ScheduleGenerationContextV1) -> DemandCoverageAssessmentV1:
    resolution = context.b_evaluation.demand_resolution
    if resolution is not None and resolution.coverage_assessment is not None:
        return resolution.coverage_assessment
    minimum = context.evaluation_policy.minimum_authoritative_demand_confidence
    return assess_demand_coverage_v1(
        context.normalized_inputs,
        minimum_confidence=minimum,
    )


def _block_evidence(
    context: ScheduleGenerationContextV1,
) -> tuple[BlockAdjustmentEvidenceV1, ...]:
    resolution = context.b_evaluation.demand_resolution
    source_ids = (
        {block.block_id: block.source_interval_ids for block in resolution.blocks}
        if resolution is not None
        else {}
    )
    evidence = [
        BlockAdjustmentEvidenceV1(
            direction=plan.direction,
            block_id=plan.block_id,
            block_start=plan.block_start,
            block_end=plan.block_end,
            current_trip_count=plan.b_trip_count or 0,
            passenger_demand=plan.passenger_demand,
            nominal_capacity=plan.nominal_capacity,
            load_factor=plan.load_factor,
            required_trips_at_planning_ceiling=plan.required_trips_85,
            required_trips_at_critical_ceiling=plan.required_trips_90,
            shortage_trips=max(0, plan.required_trips_85 - (plan.b_trip_count or 0)),
            potential_surplus_trips=max(0, (plan.b_trip_count or 0) - plan.required_trips_85),
            block_status=plan.status,
            demand_confidence=plan.confidence,
            source_block_ids=tuple(source_ids.get(plan.block_id, ())),
            donor_eligible=False,
            eligible_donor_trip_ids=(),
        )
        for plan in context.b_evaluation.b_block_supply
    ]
    return tuple(
        sorted(
            evidence,
            key=lambda item: (
                _DIRECTION_ORDER[item.direction],
                item.block_start,
                item.block_end,
                item.block_id,
            ),
        )
    )


def _daily_evidence(
    scenario: ScenarioBInput,
    blocks: tuple[BlockAdjustmentEvidenceV1, ...],
    coverage: DemandCoverageAssessmentV1,
) -> DailyAdjustmentEvidenceV1:
    fully_supported = coverage.whole_b_suitability_supported and bool(blocks)
    required = (
        sum(item.required_trips_at_planning_ceiling for item in blocks) if fully_supported else None
    )
    required_critical = (
        sum(item.required_trips_at_critical_ceiling for item in blocks) if fully_supported else None
    )
    supported_loads = [item.load_factor for item in blocks if item.load_factor is not None]
    return DailyAdjustmentEvidenceV1(
        fully_supported=fully_supported,
        current_daily_trips=scenario.total_daily_trips,
        required_daily_trips=required,
        required_daily_trips_at_critical_ceiling=required_critical,
        daily_trip_gap=(required - scenario.total_daily_trips if required is not None else None),
        total_shortage_trips=(
            sum(item.shortage_trips for item in blocks) if fully_supported else None
        ),
        total_potential_surplus_trips=(
            sum(item.potential_surplus_trips for item in blocks) if fully_supported else None
        ),
        maximum_supported_load_factor=max(supported_loads, default=None),
        no_service_with_demand_block_count=sum(
            item.block_status == BlockSupplyStatus.NO_SERVICE_WITH_DEMAND for item in blocks
        ),
        critical_block_count=sum(
            item.block_status == BlockSupplyStatus.CRITICAL_ABOVE_90 for item in blocks
        ),
        warning_block_count=sum(
            item.block_status == BlockSupplyStatus.WARNING_ABOVE_85 for item in blocks
        ),
    )


def _allocation_evidence(
    scenario: ScenarioBInput,
    blocks: tuple[BlockAdjustmentEvidenceV1, ...],
    coverage: DemandCoverageAssessmentV1,
) -> tuple[DirectionalAllocationEvidenceV1, ...]:
    if not coverage.directional_c_generation_supported:
        return ()
    output: list[DirectionalAllocationEvidenceV1] = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        directional = tuple(item for item in blocks if item.direction == direction)
        total_demand = sum(item.passenger_demand for item in directional)
        total_trips = (
            scenario.trips_by_direction.outbound
            if direction == ContractDirection.OUTBOUND
            else scenario.trips_by_direction.inbound
        )
        shares = tuple(
            BlockAllocationShareV1(
                block_id=item.block_id,
                demand_share=(item.passenger_demand / total_demand if total_demand > 0 else 0.0),
                trip_share=(item.current_trip_count / total_trips if total_trips > 0 else 0.0),
            )
            for item in directional
        )
        mismatch = 0.5 * sum(abs(item.demand_share - item.trip_share) for item in shares)
        output.append(
            DirectionalAllocationEvidenceV1(
                direction=direction,
                total_directional_demand=total_demand,
                total_directional_trips=total_trips,
                block_shares=shares,
                allocation_mismatch_index=mismatch,
            )
        )
    return tuple(output)


def _headway_classification(
    actual: tuple[float, ...],
    balanced: tuple[float, ...],
    policy: ServiceAdjustmentPolicyV1,
) -> _HeadwayClassificationResult:
    allowed = set(balanced)
    conforming = sum(
        any(math.isclose(gap, target, rel_tol=0, abs_tol=1e-12) for target in allowed)
        for gap in actual
    )
    regular_rate = conforming / len(actual) if actual else 1.0
    minimum = min(actual, default=None)
    maximum = max(actual, default=None)
    headway_range = maximum - minimum if minimum is not None and maximum is not None else None
    zero_count = sum(math.isclose(item, 0.0, rel_tol=0, abs_tol=1e-12) for item in actual)
    if zero_count:
        classification = HeadwayRegularityClassificationV1.EXCEPTIONAL
    elif not actual or (headway_range is not None and math.isclose(headway_range, 0.0)):
        classification = HeadwayRegularityClassificationV1.REGULAR
    elif (
        headway_range is not None
        and headway_range <= policy.headway_rounding_tolerance_minutes
        and regular_rate >= policy.required_regular_headway_rate
    ):
        classification = HeadwayRegularityClassificationV1.BALANCED_ROUNDING
    else:
        classification = HeadwayRegularityClassificationV1.IRREGULAR
    return regular_rate, minimum, maximum, headway_range, zero_count, classification


def _diagnostic_lock_issues(
    context: ScheduleGenerationContextV1,
    scenario: ScenarioBInput,
) -> tuple[str, ...]:
    from .solver_problem import build_operating_parameter_locks_v1

    problem = context.problem
    source_fingerprint = problem.source_b_fingerprint
    core = build_operating_parameter_locks_v1(
        context.normalized_inputs.scenario_b,
        source_fingerprint,
        direction_trip_lock_mode=problem.direction_trip_lock_mode,
        fleet_constraint_mode=problem.fleet_constraint_mode,
        initial_fleet_positioning_mode=problem.initial_fleet_positioning_mode,
    )
    core_fields = {item.field for item in core}
    adapter_values = {
        item.field: item.value
        for item in problem.operating_parameter_locks
        if item.field not in core_fields
    }
    diagnostic = build_operating_parameter_locks_v1(
        scenario,
        source_fingerprint,
        direction_trip_lock_mode=problem.direction_trip_lock_mode,
        fleet_constraint_mode=problem.fleet_constraint_mode,
        initial_fleet_positioning_mode=problem.initial_fleet_positioning_mode,
        adapter_operating_lock_values=adapter_values,
    )
    expected = {item.field: item.value for item in problem.operating_parameter_locks}
    actual = {item.field: item.value for item in diagnostic}
    return tuple(
        f"DIAGNOSTIC_OPERATING_LOCK_MISMATCH:{field}"
        for field in sorted(set(expected) | set(actual))
        if expected.get(field) != actual.get(field)
    )


def _respace_diagnostic(
    context: ScheduleGenerationContextV1,
    departure_by_trip_id: dict[str, int],
) -> RespaceDiagnosticEvidenceV1:
    source = context.normalized_inputs.scenario_b
    diagnostic_trips = tuple(
        replace(
            trip,
            departure_time=departure_by_trip_id.get(trip.trip_id, trip.departure_time),
            arrival_time=(
                departure_by_trip_id.get(trip.trip_id, trip.departure_time)
                + trip.runtime_minutes * 60
                if trip.arrival_time is not None
                else None
            ),
        )
        for trip in source.exact_timetable
    )
    diagnostic = replace(source, exact_timetable=diagnostic_trips)
    changed_ids = tuple(
        sorted(
            trip.trip_id
            for trip in source.exact_timetable
            if departure_by_trip_id.get(trip.trip_id, trip.departure_time) != trip.departure_time
        )
    )
    validation = validate_scenario_input(diagnostic)
    scenario_issue_codes = tuple(sorted({item.code for item in validation.issues}))
    lock_issue_codes = _diagnostic_lock_issues(context, diagnostic)
    source_by_id = {trip.trip_id: trip for trip in source.exact_timetable}
    runtime_issues = tuple(
        sorted(
            trip.trip_id
            for trip in diagnostic.exact_timetable
            if trip.trip_id not in source_by_id
            or trip.runtime_minutes != source_by_id[trip.trip_id].runtime_minutes
            or trip.resolved_arrival_time
            != trip.departure_time + source_by_id[trip.trip_id].runtime_minutes * 60
        )
    )
    fleet = assess_scenario_b_fleet_v1(diagnostic)
    assignment_error = False
    try:
        fleet_assignment = assign_contract_v1_fleet(
            _raw_b_trips(diagnostic),
            source.exact_timetable,
            diagnostic.turnaround_minutes,
            diagnostic.available_fleet_limit,
        )
    except ContractFleetAssignmentError:
        assignment_error = True
        fleet_assignment = None
    _, turnaround_violations, _, turnaround_codes = _assigned_turnaround_evidence(diagnostic)
    turnaround_or_location_codes = list(turnaround_codes)
    if turnaround_violations:
        turnaround_or_location_codes.append(TURNAROUND_MARGIN_NEGATIVE)
    t1_min = min(
        (min(item.stock_before, item.stock_after) for item in fleet.terminal_1_events),
        default=fleet.recommended_initial_fleet_terminal_1,
    )
    t2_min = min(
        (min(item.stock_before, item.stock_after) for item in fleet.terminal_2_events),
        default=fleet.recommended_initial_fleet_terminal_2,
    )
    issue_codes: list[str] = []
    issue_codes.extend(f"DIAGNOSTIC_SCENARIO_INVALID:{code}" for code in scenario_issue_codes)
    issue_codes.extend(lock_issue_codes)
    if runtime_issues:
        issue_codes.append("DIAGNOSTIC_SOURCE_RUNTIME_INCONSISTENT")
    issue_codes.extend(f"DIAGNOSTIC_{code}" for code in sorted(set(turnaround_or_location_codes)))
    if not fleet.feasible:
        issue_codes.append("DIAGNOSTIC_TERMINAL_STOCK_FLEET_LIMIT_EXCEEDED")
    if assignment_error:
        issue_codes.append("DIAGNOSTIC_VEHICLE_ASSIGNMENT_INVALID")
    elif fleet_assignment is not None and not fleet_assignment.feasible:
        issue_codes.append("DIAGNOSTIC_VEHICLE_ASSIGNMENT_FLEET_LIMIT_EXCEEDED")
    if not changed_ids:
        issue_codes.append("DIAGNOSTIC_RESPACE_NO_CHANGE")
    normalized_issues = tuple(sorted(set(issue_codes)))
    return RespaceDiagnosticEvidenceV1(
        diagnostic_scenario_fingerprint=scenario_fingerprint(diagnostic),
        changed_trip_ids=changed_ids,
        scenario_validation_issue_codes=scenario_issue_codes,
        operating_lock_issue_codes=lock_issue_codes,
        runtime_issue_trip_ids=runtime_issues,
        turnaround_or_location_issue_codes=tuple(sorted(set(turnaround_or_location_codes))),
        minimum_required_fleet=fleet.minimum_required_fleet,
        available_fleet_limit=fleet.available_fleet_limit,
        minimum_terminal_stock_terminal_1=t1_min,
        minimum_terminal_stock_terminal_2=t2_min,
        fleet_assignment_vehicle_count=(
            fleet_assignment.vehicle_count if fleet_assignment is not None else 0
        ),
        issue_codes=normalized_issues,
        passed=not normalized_issues,
    )


def _headway_evidence(
    context: ScheduleGenerationContextV1,
    policy: ServiceAdjustmentPolicyV1,
) -> tuple[HeadwayRegimeEvidenceV1, ...]:
    scenario = context.normalized_inputs.scenario_b
    provisional: list[
        tuple[
            ContractDirection,
            int,
            ContinuousHeadwayRegimeV1,
            _HeadwayClassificationResult,
        ]
    ] = []
    departure_by_trip_id: dict[str, int] = {}
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        trips = tuple(
            sorted(
                (item for item in scenario.exact_timetable if item.direction == direction),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        for regime_index, regime in enumerate(
            segment_continuous_headway_regimes_v1(trips, policy),
            1,
        ):
            classification = _headway_classification(
                regime.actual_headway_sequence,
                regime.balanced_headway_sequence,
                policy,
            )
            provisional.append((direction, regime_index, regime, classification))
            if classification[-1] in {
                HeadwayRegularityClassificationV1.IRREGULAR,
                HeadwayRegularityClassificationV1.EXCEPTIONAL,
            }:
                departure_by_trip_id.update(
                    zip(
                        regime.ordered_trip_ids,
                        regime.balanced_departure_sequence,
                        strict=True,
                    )
                )
    needs_diagnostic = bool(departure_by_trip_id)
    diagnostic = _respace_diagnostic(context, departure_by_trip_id) if needs_diagnostic else None
    output: list[HeadwayRegimeEvidenceV1] = []
    for direction, regime_index, regime, classification_values in provisional:
        (
            regular_rate,
            minimum,
            maximum,
            headway_range,
            zero_count,
            classification,
        ) = classification_values
        considered_for_respace = classification in {
            HeadwayRegularityClassificationV1.IRREGULAR,
            HeadwayRegularityClassificationV1.EXCEPTIONAL,
        }
        output.append(
            HeadwayRegimeEvidenceV1(
                regime_id=f"B-HEADWAY-{direction.value.upper()}-R{regime_index:02d}",
                direction=direction,
                ordered_trip_ids=regime.ordered_trip_ids,
                first_departure=regime.first_departure,
                last_departure=regime.last_departure,
                actual_headway_sequence=regime.actual_headway_sequence,
                balanced_target_sequence=regime.balanced_headway_sequence,
                minimum_headway=minimum,
                maximum_headway=maximum,
                headway_range=headway_range,
                regular_headway_rate=regular_rate,
                zero_headway_count=zero_count,
                regularity_classification=classification,
                respace_technically_possible=bool(
                    considered_for_respace and diagnostic is not None and diagnostic.passed
                ),
                respace_diagnostic=diagnostic if considered_for_respace else None,
            )
        )
    return tuple(output)


def _raw_b_trips(scenario: ScenarioBInput) -> tuple[RawCandidateTripV1, ...]:
    return tuple(
        RawCandidateTripV1(
            c_trip_id=trip.trip_id,
            source_b_trip_id=trip.trip_id,
            direction=trip.direction,
            departure_terminal=trip.departure_terminal,
            b_departure_time=trip.departure_time,
            c_departure_time=trip.departure_time,
            arrival_time=trip.resolved_arrival_time,
            runtime_minutes=trip.runtime_minutes,
            shift_minutes=0.0,
            previous_b_headway=None,
            previous_c_headway=None,
            headway_regime_id=f"B-HEADWAY-{trip.direction.value.upper()}",
            change_reason="Scenario B technical evidence",
        )
        for trip in scenario.exact_timetable
    )


def _assigned_turnaround_evidence(
    scenario: ScenarioBInput,
) -> tuple[float | None, int, tuple[str, ...], tuple[str, ...]]:
    assigned = [item for item in scenario.exact_timetable if item.vehicle_assignment]
    if assigned and len(assigned) != len(scenario.exact_timetable):
        assigned = []

    margins: list[float] = []
    affected: list[str] = []
    issue_codes: list[str] = []
    if assigned:
        by_vehicle: dict[str, list[ExactTimetableTrip]] = {}
        for trip in assigned:
            assert trip.vehicle_assignment is not None
            by_vehicle.setdefault(trip.vehicle_assignment, []).append(trip)
        for vehicle_id in sorted(by_vehicle):
            trips = sorted(
                by_vehicle[vehicle_id],
                key=lambda item: (item.departure_time, item.trip_id),
            )
            for previous, current in zip(trips, trips[1:], strict=False):
                arrival_terminal = (
                    DepartureTerminal.TERMINAL_2
                    if previous.departure_terminal == DepartureTerminal.TERMINAL_1
                    else DepartureTerminal.TERMINAL_1
                )
                if current.departure_terminal != arrival_terminal:
                    issue_codes.append("VEHICLE_LOCATION_CONFLICT")
                    affected.extend((vehicle_id, previous.trip_id, current.trip_id))
                    continue
                turnaround = (
                    scenario.turnaround_minutes.terminal_1
                    if arrival_terminal == DepartureTerminal.TERMINAL_1
                    else scenario.turnaround_minutes.terminal_2
                )
                margin = (
                    current.departure_time - previous.resolved_arrival_time - turnaround * 60
                ) / 60
                margins.append(margin)
                if margin < 0:
                    issue_codes.append(TURNAROUND_MARGIN_NEGATIVE)
                    affected.extend((vehicle_id, previous.trip_id, current.trip_id))
    else:
        independent = assign_contract_v1_fleet(
            _raw_b_trips(scenario),
            scenario.exact_timetable,
            scenario.turnaround_minutes,
            scenario.available_fleet_limit,
        )
        by_vehicle_assignment: dict[str, list[Any]] = {}
        for assignment in independent.assignments:
            by_vehicle_assignment.setdefault(assignment.vehicle_id, []).append(assignment)
        for vehicle_id in sorted(by_vehicle_assignment):
            assignments = sorted(
                by_vehicle_assignment[vehicle_id],
                key=lambda item: (item.departure_time, item.c_trip_id),
            )
            margins.extend(
                (current.departure_time - previous.ready_time) / 60
                for previous, current in zip(assignments, assignments[1:], strict=False)
            )
    return (
        min(margins, default=None),
        sum(item < 0 for item in margins),
        tuple(sorted(set(affected))),
        tuple(sorted(set(issue_codes))),
    )


def _technical_evidence(
    context: ScheduleGenerationContextV1,
    context_issue_codes: tuple[str, ...],
) -> TechnicalAdjustmentEvidenceV1:
    scenario = context.normalized_inputs.scenario_b
    fleet: FleetAssessmentV1 = context.b_evaluation.fleet_assessment
    runtime_inconsistencies = tuple(
        sorted(
            trip.trip_id
            for trip in scenario.exact_timetable
            if trip.arrival_time is not None
            and trip.arrival_time != trip.departure_time + trip.runtime_minutes * 60
        )
    )
    by_terminal = {
        DepartureTerminal.TERMINAL_1: sorted(
            trip.departure_time
            for trip in scenario.exact_timetable
            if trip.departure_terminal == DepartureTerminal.TERMINAL_1
        ),
        DepartureTerminal.TERMINAL_2: sorted(
            trip.departure_time
            for trip in scenario.exact_timetable
            if trip.departure_terminal == DepartureTerminal.TERMINAL_2
        ),
    }
    first_last_failures: list[str] = []
    for terminal, first, last in (
        (
            DepartureTerminal.TERMINAL_1,
            scenario.first_departures.terminal_1,
            scenario.last_departures.terminal_1,
        ),
        (
            DepartureTerminal.TERMINAL_2,
            scenario.first_departures.terminal_2,
            scenario.last_departures.terminal_2,
        ),
    ):
        times = by_terminal[terminal]
        if not times or times[0] != first:
            first_last_failures.append(f"{terminal.value}:first")
        if not times or times[-1] != last:
            first_last_failures.append(f"{terminal.value}:last")

    actual_outbound = sum(
        item.direction == ContractDirection.OUTBOUND for item in scenario.exact_timetable
    )
    actual_inbound = sum(
        item.direction == ContractDirection.INBOUND for item in scenario.exact_timetable
    )
    count_inconsistencies: list[str] = []
    if len(scenario.exact_timetable) != scenario.total_daily_trips:
        count_inconsistencies.append("total_daily_trips")
    if actual_outbound != scenario.trips_by_direction.outbound:
        count_inconsistencies.append("outbound")
    if actual_inbound != scenario.trips_by_direction.inbound:
        count_inconsistencies.append("inbound")

    t1_min = min(
        (min(item.stock_before, item.stock_after) for item in fleet.terminal_1_events),
        default=fleet.recommended_initial_fleet_terminal_1,
    )
    t2_min = min(
        (min(item.stock_before, item.stock_after) for item in fleet.terminal_2_events),
        default=fleet.recommended_initial_fleet_terminal_2,
    )
    negative_events = [
        TechnicalEventEvidenceV1(
            terminal=terminal,
            event_time=item.event_time,
            event_type=item.event_type,
            trip_id=item.trip_id,
            stock_after=item.stock_after,
        )
        for terminal, events in (
            (DepartureTerminal.TERMINAL_1, fleet.terminal_1_events),
            (DepartureTerminal.TERMINAL_2, fleet.terminal_2_events),
        )
        for item in events
        if item.stock_after < 0
    ]
    first_negative = min(
        negative_events,
        key=lambda item: (
            item.event_time,
            item.terminal.value,
            item.event_type,
            item.trip_id,
        ),
        default=None,
    )
    minimum_margin, turnaround_violations, affected, assignment_codes = (
        _assigned_turnaround_evidence(scenario)
    )
    issue_codes: list[str] = list(assignment_codes)
    if not fleet.feasible:
        issue_codes.extend(("AVAILABLE_FLEET_LIMIT_EXCEEDED", FLEET_RATIO_ABOVE_ONE))
    if first_negative is not None:
        issue_codes.append(NEGATIVE_TERMINAL_STOCK)
    if turnaround_violations:
        issue_codes.append(TURNAROUND_MARGIN_NEGATIVE)
    if runtime_inconsistencies:
        issue_codes.append("RUNTIME_INCONSISTENCY")
    if first_last_failures:
        issue_codes.append("FIRST_LAST_DEPARTURE_LOCK_FAILURE")
    if count_inconsistencies:
        issue_codes.append("TRIP_COUNT_INCONSISTENCY")
    technical_context_codes = tuple(
        sorted(
            code
            for code in context_issue_codes
            if code
            in {
                "PROBLEM_LOCK_SET_INCOMPLETE",
                "PROBLEM_LOCK_DUPLICATE_FIELD",
                "PROBLEM_LOCK_SOURCE_MISMATCH",
                "PROBLEM_LOCK_VALUE_MISMATCH",
            }
        )
    )
    issue_codes.extend(technical_context_codes)
    normalized_issue_codes = tuple(sorted(set(issue_codes)))
    return TechnicalAdjustmentEvidenceV1(
        minimum_required_fleet=fleet.minimum_required_fleet,
        available_fleet_limit=fleet.available_fleet_limit,
        fleet_ratio=fleet.minimum_required_fleet / fleet.available_fleet_limit,
        fleet_margin=fleet.fleet_margin,
        independently_derived_initial_fleet_terminal_1=(fleet.recommended_initial_fleet_terminal_1),
        independently_derived_initial_fleet_terminal_2=(fleet.recommended_initial_fleet_terminal_2),
        minimum_terminal_stock_terminal_1=t1_min,
        minimum_terminal_stock_terminal_2=t2_min,
        first_negative_stock_event=first_negative,
        minimum_turnaround_margin_minutes=minimum_margin,
        turnaround_violation_count=turnaround_violations,
        affected_trip_or_vehicle_references=affected,
        runtime_inconsistencies=runtime_inconsistencies,
        first_last_departure_lock_failures=tuple(first_last_failures),
        trip_count_and_directional_count_inconsistencies=tuple(count_inconsistencies),
        context_validation_issue_codes=context_issue_codes,
        issue_codes=normalized_issue_codes,
        technically_feasible=not normalized_issue_codes and not context_issue_codes,
    )


def _trip_in_block(
    trip: ExactTimetableTrip,
    block: BlockAdjustmentEvidenceV1,
) -> bool:
    return block.block_start <= trip.departure_time < block.block_end and (
        block.direction == ContractDirection.COMBINED or trip.direction == block.direction
    )


def _endpoint_preserved_after_removal(
    scenario: ScenarioBInput,
    trip: ExactTimetableTrip,
) -> bool:
    remaining = tuple(item for item in scenario.exact_timetable if item.trip_id != trip.trip_id)
    same_terminal = tuple(
        item.departure_time
        for item in remaining
        if item.departure_terminal == trip.departure_terminal
    )
    if not same_terminal:
        return False
    if trip.departure_terminal == DepartureTerminal.TERMINAL_1:
        expected_first = scenario.first_departures.terminal_1
        expected_last = scenario.last_departures.terminal_1
    else:
        expected_first = scenario.first_departures.terminal_2
        expected_last = scenario.last_departures.terminal_2
    return min(same_terminal) == expected_first and max(same_terminal) == expected_last


def _scenario_without_trips(
    scenario: ScenarioBInput,
    trip_ids: tuple[str, ...],
) -> ScenarioBInput:
    removed = set(trip_ids)
    timetable = tuple(item for item in scenario.exact_timetable if item.trip_id not in removed)
    outbound = sum(item.direction == ContractDirection.OUTBOUND for item in timetable)
    inbound = sum(item.direction == ContractDirection.INBOUND for item in timetable)
    return replace(
        scenario,
        exact_timetable=timetable,
        total_daily_trips=len(timetable),
        trips_by_direction=TripsByDirection(outbound=outbound, inbound=inbound),
    )


def _joint_removal_is_technically_feasible(
    scenario: ScenarioBInput,
    trip_ids: tuple[str, ...],
    donor_blocks: tuple[BlockAdjustmentEvidenceV1, ...],
    policy: ServiceAdjustmentPolicyV1,
) -> bool:
    trial = _scenario_without_trips(scenario, trip_ids)
    for terminal, expected_first, expected_last in (
        (
            DepartureTerminal.TERMINAL_1,
            scenario.first_departures.terminal_1,
            scenario.last_departures.terminal_1,
        ),
        (
            DepartureTerminal.TERMINAL_2,
            scenario.first_departures.terminal_2,
            scenario.last_departures.terminal_2,
        ),
    ):
        times = tuple(
            trip.departure_time
            for trip in trial.exact_timetable
            if trip.departure_terminal == terminal
        )
        if not times or min(times) != expected_first or max(times) != expected_last:
            return False
    if (
        trial.trips_by_direction.outbound < policy.minimum_service_trips_per_direction
        or trial.trips_by_direction.inbound < policy.minimum_service_trips_per_direction
    ):
        return False
    if any(
        sum(_trip_in_block(trip, block) for trip in trial.exact_timetable)
        < block.required_trips_at_planning_ceiling
        for block in donor_blocks
    ):
        return False
    if not validate_scenario_input(trial).passed:
        return False
    if not assess_scenario_b_fleet_v1(trial).feasible:
        return False
    assignment = assign_contract_v1_fleet(
        _raw_b_trips(trial),
        scenario.exact_timetable,
        trial.turnaround_minutes,
        trial.available_fleet_limit,
    )
    if not assignment.feasible:
        return False
    _, turnaround_violations, _, assignment_codes = _assigned_turnaround_evidence(trial)
    return not turnaround_violations and not assignment_codes


def _joint_donor_validation(
    scenario: ScenarioBInput,
    blocks: tuple[BlockAdjustmentEvidenceV1, ...],
    coverage: DemandCoverageAssessmentV1,
    policy: ServiceAdjustmentPolicyV1,
    technical_feasible: bool,
) -> tuple[
    tuple[BlockAdjustmentEvidenceV1, ...],
    tuple[JointDonorValidationEvidenceV1, ...],
]:
    if not technical_feasible or not coverage.directional_c_generation_supported:
        evidence = tuple(
            JointDonorValidationEvidenceV1(
                direction=direction,
                shortage_quantity=sum(
                    block.shortage_trips for block in blocks if block.direction == direction
                ),
                candidate_trip_ids=(),
                selected_jointly_feasible_trip_ids=(),
                proven_joint_capacity=0,
                search_complete=True,
                search_state_count=0,
                issue_codes=(JOINT_DONOR_CAPACITY_NOT_PROVEN,),
            )
            for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
        )
        return blocks, evidence

    joint_evidence: list[JointDonorValidationEvidenceV1] = []
    selected_by_direction: dict[ContractDirection, tuple[str, ...]] = {}
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        shortage = sum(block.shortage_trips for block in blocks if block.direction == direction)
        donor_blocks = tuple(
            block
            for block in blocks
            if block.direction == direction and block.potential_surplus_trips > 0
        )
        candidate_trips = tuple(
            sorted(
                {
                    trip.trip_id: trip
                    for block in donor_blocks
                    for trip in scenario.exact_timetable
                    if _trip_in_block(trip, block)
                    and _endpoint_preserved_after_removal(scenario, trip)
                }.values(),
                key=lambda trip: (trip.departure_time, trip.trip_id),
            )
        )
        candidate_ids = tuple(trip.trip_id for trip in candidate_trips)
        selected: tuple[str, ...] = ()
        states = 0
        limit_reached = False
        target_proven = shortage == 0
        if shortage > 0:
            for quantity in range(1, min(shortage, len(candidate_ids)) + 1):
                for candidate_set in combinations(candidate_ids, quantity):
                    if states >= policy.maximum_joint_donor_search_states:
                        limit_reached = True
                        break
                    states += 1
                    if _joint_removal_is_technically_feasible(
                        scenario,
                        candidate_set,
                        donor_blocks,
                        policy,
                    ):
                        selected = candidate_set
                        if quantity == shortage:
                            target_proven = True
                            break
                if limit_reached or target_proven:
                    break
        search_complete = target_proven or not limit_reached
        issues: list[str] = []
        if shortage > len(candidate_ids):
            issues.append("INSUFFICIENT_JOINT_DONOR_CANDIDATES")
        if limit_reached and not target_proven:
            issues.append(JOINT_DONOR_SEARCH_LIMIT_REACHED)
        if shortage > 0 and not target_proven:
            issues.append(JOINT_DONOR_CAPACITY_NOT_PROVEN)
        selected_by_direction[direction] = selected
        joint_evidence.append(
            JointDonorValidationEvidenceV1(
                direction=direction,
                shortage_quantity=shortage,
                candidate_trip_ids=candidate_ids,
                selected_jointly_feasible_trip_ids=selected,
                proven_joint_capacity=len(selected),
                search_complete=search_complete,
                search_state_count=states,
                issue_codes=tuple(issues),
            )
        )

    trip_by_id = {trip.trip_id: trip for trip in scenario.exact_timetable}
    updated_blocks = tuple(
        replace(
            block,
            donor_eligible=bool(selected_ids),
            eligible_donor_trip_ids=selected_ids,
        )
        for block in blocks
        for selected_ids in (
            tuple(
                trip_id
                for trip_id in selected_by_direction.get(block.direction, ())
                if _trip_in_block(trip_by_id[trip_id], block)
            ),
        )
    )
    return updated_blocks, tuple(joint_evidence)


def _maximum_repeatably_supported_surplus(
    evidence: RepeatabilityEvidenceV1,
    minimum_rate: float,
) -> int:
    maximum = max(evidence.daily_surplus_sequence, default=0)
    supported = 0
    for quantity in range(1, maximum + 1):
        rate = (
            sum(value >= quantity for value in evidence.daily_surplus_sequence)
            / evidence.valid_observed_day_count
            if evidence.valid_observed_day_count
            else 0.0
        )
        if rate >= minimum_rate:
            supported = quantity
    return supported


def _reduction_candidates(
    scenario: ScenarioBInput,
    blocks: tuple[BlockAdjustmentEvidenceV1, ...],
    policy: ServiceAdjustmentPolicyV1,
) -> tuple[ExactTimetableTrip, ...]:
    surplus_blocks = tuple(block for block in blocks if block.potential_surplus_trips > 0)
    seen_ids: set[str] = set()
    candidates: list[ExactTimetableTrip] = []
    for trip in sorted(
        scenario.exact_timetable,
        key=lambda item: (
            _DIRECTION_ORDER[item.direction],
            item.departure_time,
            item.trip_id,
        ),
    ):
        if not trip.trip_id.strip() or trip.trip_id in seen_ids:
            continue
        seen_ids.add(trip.trip_id)
        if not any(_trip_in_block(trip, block) for block in surplus_blocks):
            continue
        if not _endpoint_preserved_after_removal(scenario, trip):
            continue
        remaining_outbound = scenario.trips_by_direction.outbound - (
            trip.direction == ContractDirection.OUTBOUND
        )
        remaining_inbound = scenario.trips_by_direction.inbound - (
            trip.direction == ContractDirection.INBOUND
        )
        if (
            remaining_outbound < policy.minimum_service_trips_per_direction
            or remaining_inbound < policy.minimum_service_trips_per_direction
        ):
            continue
        candidates.append(trip)
    return tuple(candidates)


def _retained_explicit_assignment_is_feasible(scenario: ScenarioBInput) -> bool:
    assigned = tuple(trip for trip in scenario.exact_timetable if trip.vehicle_assignment)
    by_vehicle: dict[str, list[ExactTimetableTrip]] = {}
    for trip in assigned:
        assert trip.vehicle_assignment is not None
        by_vehicle.setdefault(trip.vehicle_assignment, []).append(trip)
    for vehicle_id in sorted(by_vehicle):
        trips = sorted(
            by_vehicle[vehicle_id],
            key=lambda item: (item.departure_time, item.trip_id),
        )
        for previous, current in zip(trips, trips[1:], strict=False):
            arrival_terminal = (
                DepartureTerminal.TERMINAL_2
                if previous.departure_terminal == DepartureTerminal.TERMINAL_1
                else DepartureTerminal.TERMINAL_1
            )
            if current.departure_terminal != arrival_terminal:
                return False
            turnaround = (
                scenario.turnaround_minutes.terminal_1
                if arrival_terminal == DepartureTerminal.TERMINAL_1
                else scenario.turnaround_minutes.terminal_2
            )
            if current.departure_time < previous.resolved_arrival_time + turnaround * 60:
                return False
    return True


def _reduction_set_is_jointly_feasible(
    scenario: ScenarioBInput,
    trip_ids: tuple[str, ...],
    blocks: tuple[BlockAdjustmentEvidenceV1, ...],
    policy: ServiceAdjustmentPolicyV1,
) -> bool:
    source_by_id = {trip.trip_id: trip for trip in scenario.exact_timetable}
    if (
        len(source_by_id) != len(scenario.exact_timetable)
        or len(set(trip_ids)) != len(trip_ids)
        or any(trip_id not in source_by_id for trip_id in trip_ids)
    ):
        return False
    trial = _scenario_without_trips(scenario, trip_ids)
    expected_retained_ids = set(source_by_id).difference(trip_ids)
    retained_by_id = {trip.trip_id: trip for trip in trial.exact_timetable}
    if (
        len(retained_by_id) != len(trial.exact_timetable)
        or set(retained_by_id) != expected_retained_ids
        or len(trial.exact_timetable) != len(scenario.exact_timetable) - len(trip_ids)
    ):
        return False

    for terminal, expected_first, expected_last in (
        (
            DepartureTerminal.TERMINAL_1,
            scenario.first_departures.terminal_1,
            scenario.last_departures.terminal_1,
        ),
        (
            DepartureTerminal.TERMINAL_2,
            scenario.first_departures.terminal_2,
            scenario.last_departures.terminal_2,
        ),
    ):
        times = tuple(
            trip.departure_time
            for trip in trial.exact_timetable
            if trip.departure_terminal == terminal
        )
        if not times or min(times) != expected_first or max(times) != expected_last:
            return False
    if (
        trial.trips_by_direction.outbound < policy.minimum_service_trips_per_direction
        or trial.trips_by_direction.inbound < policy.minimum_service_trips_per_direction
    ):
        return False

    for block in blocks:
        remaining_count = sum(_trip_in_block(trip, block) for trip in trial.exact_timetable)
        if remaining_count < block.required_trips_at_planning_ceiling:
            return False
        if block.passenger_demand > 0 and remaining_count == 0:
            return False
        remaining_load_factor = (
            block.passenger_demand / (remaining_count * scenario.vehicle_capacity)
            if remaining_count
            else None
        )
        if remaining_load_factor is not None and (
            remaining_load_factor > policy.planning_load_factor_ceiling
            or remaining_load_factor > policy.critical_load_factor_ceiling
        ):
            return False

    if not validate_scenario_input(trial).passed:
        return False
    for trip_id, retained in retained_by_id.items():
        source = source_by_id[trip_id]
        if (
            retained.direction != source.direction
            or retained.departure_terminal != source.departure_terminal
            or retained.departure_time != source.departure_time
            or retained.runtime_minutes != source.runtime_minutes
            or retained.resolved_arrival_time
            != retained.departure_time + source.runtime_minutes * 60
        ):
            return False
    if not _retained_explicit_assignment_is_feasible(trial):
        return False

    try:
        assignment = assign_contract_v1_fleet(
            _raw_b_trips(trial),
            scenario.exact_timetable,
            trial.turnaround_minutes,
            trial.available_fleet_limit,
        )
    except ContractFleetAssignmentError:
        return False
    if not assignment.feasible or assignment.vehicle_count > trial.available_fleet_limit:
        return False

    fleet = assess_scenario_b_fleet_v1(trial)
    return not (
        not fleet.feasible
        or fleet.minimum_required_fleet > trial.available_fleet_limit
        or any(
            event.stock_before < 0 or event.stock_after < 0
            for event in (*fleet.terminal_1_events, *fleet.terminal_2_events)
        )
    )


def _joint_reduction_validation(
    scenario: ScenarioBInput,
    blocks: tuple[BlockAdjustmentEvidenceV1, ...],
    current_surplus: int,
    repeatably_supported_surplus: int,
    policy: ServiceAdjustmentPolicyV1,
) -> JointReductionValidationEvidenceV1:
    candidate_ids = tuple(trip.trip_id for trip in _reduction_candidates(scenario, blocks, policy))
    upper_bound = min(
        current_surplus,
        repeatably_supported_surplus,
        len(candidate_ids),
    )
    state_limit = policy.maximum_joint_reduction_search_states
    if upper_bound <= 0:
        return JointReductionValidationEvidenceV1(
            candidate_trip_ids=candidate_ids,
            selected_jointly_feasible_trip_ids=(),
            requested_upper_bound=upper_bound,
            proven_supported_quantity=0,
            maximum_proven=True,
            search_complete=True,
            search_state_count=0,
            search_state_limit=state_limit,
            issue_codes=(),
        )

    tested: set[tuple[str, ...]] = set()
    state_count = 0
    lower_bound: tuple[str, ...] = ()

    # Seed a useful lower bound before the descending maximum-proof pass. The
    # seed is never reported as a maximum unless every larger quantity is
    # subsequently exhausted.
    for trip_id in candidate_ids:
        candidate_set = (trip_id,)
        if state_count >= state_limit:
            break
        tested.add(candidate_set)
        state_count += 1
        if _reduction_set_is_jointly_feasible(
            scenario,
            candidate_set,
            blocks,
            policy,
        ):
            lower_bound = candidate_set
            break

    for quantity in range(upper_bound, 0, -1):
        if quantity == len(lower_bound):
            return JointReductionValidationEvidenceV1(
                candidate_trip_ids=candidate_ids,
                selected_jointly_feasible_trip_ids=lower_bound,
                requested_upper_bound=upper_bound,
                proven_supported_quantity=quantity,
                maximum_proven=True,
                search_complete=True,
                search_state_count=state_count,
                search_state_limit=state_limit,
                issue_codes=(),
            )
        for candidate_set in combinations(candidate_ids, quantity):
            if candidate_set in tested:
                continue
            if state_count >= state_limit:
                return JointReductionValidationEvidenceV1(
                    candidate_trip_ids=candidate_ids,
                    selected_jointly_feasible_trip_ids=lower_bound,
                    requested_upper_bound=upper_bound,
                    proven_supported_quantity=len(lower_bound),
                    maximum_proven=False,
                    search_complete=False,
                    search_state_count=state_count,
                    search_state_limit=state_limit,
                    issue_codes=(
                        JOINT_REDUCTION_SEARCH_LIMIT_REACHED,
                        JOINT_REDUCTION_MAXIMUM_NOT_PROVEN,
                    ),
                )
            tested.add(candidate_set)
            state_count += 1
            if _reduction_set_is_jointly_feasible(
                scenario,
                candidate_set,
                blocks,
                policy,
            ):
                return JointReductionValidationEvidenceV1(
                    candidate_trip_ids=candidate_ids,
                    selected_jointly_feasible_trip_ids=candidate_set,
                    requested_upper_bound=upper_bound,
                    proven_supported_quantity=quantity,
                    maximum_proven=True,
                    search_complete=True,
                    search_state_count=state_count,
                    search_state_limit=state_limit,
                    issue_codes=(),
                )

    return JointReductionValidationEvidenceV1(
        candidate_trip_ids=candidate_ids,
        selected_jointly_feasible_trip_ids=(),
        requested_upper_bound=upper_bound,
        proven_supported_quantity=0,
        maximum_proven=True,
        search_complete=True,
        search_state_count=state_count,
        search_state_limit=state_limit,
        issue_codes=(),
    )


def _repeatability_gate(
    evidence: RepeatabilityEvidenceV1 | None,
    policy: ServiceAdjustmentPolicyV1,
    current_surplus: int,
    scenario: ScenarioBInput,
    blocks: tuple[BlockAdjustmentEvidenceV1, ...],
) -> tuple[
    bool,
    JointReductionValidationEvidenceV1 | None,
    tuple[str, ...],
]:
    reasons: list[str] = []
    if evidence is None:
        return (
            False,
            None,
            (
                LOW_LOAD_REVIEW_ONLY,
                INSUFFICIENT_DAYS_FOR_REDUCTION_DECISION,
            ),
        )
    policy_matches = (
        evidence.configured_minimum_valid_day_count
        == policy.minimum_valid_observed_days_for_reduction
        and math.isclose(
            evidence.configured_minimum_surplus_consistency_rate,
            policy.minimum_surplus_consistency_rate,
            rel_tol=0,
            abs_tol=1e-12,
        )
    )
    if not policy_matches:
        reasons.extend(("REPEATABILITY_EVIDENCE_POLICY_MISMATCH", LOW_LOAD_REVIEW_ONLY))
        return False, None, tuple(reasons)
    if evidence.valid_observed_day_count < policy.minimum_valid_observed_days_for_reduction:
        reasons.extend((INSUFFICIENT_DAYS_FOR_REDUCTION_DECISION, LOW_LOAD_REVIEW_ONLY))
        return False, None, tuple(reasons)
    if evidence.surplus_consistency_rate < policy.minimum_surplus_consistency_rate:
        reasons.extend(("SURPLUS_CONSISTENCY_RATE_BELOW_REQUIRED", LOW_LOAD_REVIEW_ONLY))
        return False, None, tuple(reasons)
    repeatable_quantity = _maximum_repeatably_supported_surplus(
        evidence,
        policy.minimum_surplus_consistency_rate,
    )
    proof = _joint_reduction_validation(
        scenario,
        blocks,
        current_surplus,
        repeatable_quantity,
        policy,
    )
    if not proof.maximum_proven or not proof.search_complete:
        reasons.extend((*proof.issue_codes, LOW_LOAD_REVIEW_ONLY))
        return False, proof, tuple(reasons)
    if proof.proven_supported_quantity < policy.minimum_residual_surplus_trips_for_reduction:
        reasons.extend(("REDUCTION_TECHNICAL_PROTECTION_NOT_SATISFIED", LOW_LOAD_REVIEW_ONLY))
        return False, proof, tuple(reasons)
    return True, proof, (STABLE_RESIDUAL_TRIP_SURPLUS,)


def _fixed_resource_authorization(
    *,
    decision: ServiceAdjustmentDecisionV1,
    context: ScheduleGenerationContextV1,
    coverage: DemandCoverageAssessmentV1,
    technical: TechnicalAdjustmentEvidenceV1,
    policy: ServiceAdjustmentPolicyV1,
    donor_capacity_sufficient: bool,
    headway_respace_possible: bool,
) -> tuple[bool, str | None]:
    problem = context.problem
    supported_problem = (
        problem.solver_adapter == policy.fixed_resource_solver_adapter
        and problem.direction_trip_lock_mode == DirectionTripLockMode.FIXED_BY_DIRECTION
        and problem.fleet_constraint_mode == FleetConstraintMode.AVAILABLE_UPPER_BOUND
        and problem.initial_fleet_positioning_mode == InitialFleetPositioningMode.SOLVER_DETERMINED
        and problem.boundary_convention == BoundaryConvention.HALF_OPEN
        and coverage.directional_c_generation_supported
        and technical.technically_feasible
    )
    if decision not in policy.fixed_resource_authorized_decisions or not supported_problem:
        return False, None
    if decision == ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS:
        return (
            (True, "fixed_resource_trip_redistribution")
            if donor_capacity_sufficient
            else (False, None)
        )
    if decision == ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES:
        return (
            (True, "fixed_resource_departure_respace")
            if headway_respace_possible
            else (False, None)
        )
    return False, None


def _assessment_evidence(
    *,
    blocks: tuple[BlockAdjustmentEvidenceV1, ...],
    joint_donors: tuple[JointDonorValidationEvidenceV1, ...],
    daily: DailyAdjustmentEvidenceV1,
    allocation: tuple[DirectionalAllocationEvidenceV1, ...],
    headways: tuple[HeadwayRegimeEvidenceV1, ...],
    technical: TechnicalAdjustmentEvidenceV1,
    joint_reduction: JointReductionValidationEvidenceV1 | None,
) -> tuple[str, ...]:
    output = [
        f"daily.current_trips={daily.current_daily_trips}",
        f"daily.required_trips={daily.required_daily_trips}",
        f"daily.trip_gap={daily.daily_trip_gap}",
        f"daily.total_shortage_trips={daily.total_shortage_trips}",
        f"daily.total_potential_surplus_trips={daily.total_potential_surplus_trips}",
    ]
    output.extend(
        f"block.{item.direction.value}.{item.block_id}:"
        f"trips={item.current_trip_count},demand={item.passenger_demand:.12g},"
        f"load_factor={item.load_factor},"
        f"required_planning={item.required_trips_at_planning_ceiling},"
        f"required_critical={item.required_trips_at_critical_ceiling},"
        f"shortage_trips={item.shortage_trips},"
        f"potential_surplus_trips={item.potential_surplus_trips},"
        f"donor_eligible={str(item.donor_eligible).lower()}"
        for item in blocks
    )
    output.extend(
        f"donor.{item.direction.value}:shortage={item.shortage_quantity},"
        f"proven_joint_capacity={item.proven_joint_capacity},"
        f"selected={list(item.selected_jointly_feasible_trip_ids)},"
        f"states={item.search_state_count},complete={str(item.search_complete).lower()}"
        for item in joint_donors
    )
    output.extend(
        f"allocation.{item.direction.value}:mismatch_index={item.allocation_mismatch_index:.12g}"
        for item in allocation
    )
    output.extend(
        f"headway.{item.direction.value}:"
        f"actual={list(item.actual_headway_sequence)},"
        f"balanced={list(item.balanced_target_sequence)},"
        f"classification={item.regularity_classification.value}"
        for item in headways
    )
    output.extend(
        (
            f"technical.minimum_required_fleet={technical.minimum_required_fleet}",
            f"technical.available_fleet_limit={technical.available_fleet_limit}",
            f"technical.fleet_margin={technical.fleet_margin}",
            f"technical.minimum_turnaround_margin_minutes="
            f"{technical.minimum_turnaround_margin_minutes}",
        )
    )
    if joint_reduction is not None:
        output.append(
            "reduction:"
            f"upper_bound={joint_reduction.requested_upper_bound},"
            f"proven_quantity={joint_reduction.proven_supported_quantity},"
            f"maximum_proven={str(joint_reduction.maximum_proven).lower()},"
            f"selected={list(joint_reduction.selected_jointly_feasible_trip_ids)},"
            f"states={joint_reduction.search_state_count},"
            f"complete={str(joint_reduction.search_complete).lower()}"
        )
    return tuple(output)


def _fingerprint_payload(
    assessment: ServiceAdjustmentAssessmentV1,
    evaluation_policy: ScenarioBEvaluationPolicyV1,
    adjustment_policy: ServiceAdjustmentPolicyV1,
) -> dict[str, object]:
    return {
        "fingerprint_profile": EVALUATOR_FINGERPRINT_PROFILE,
        "source_problem_fingerprint": assessment.source_problem_fingerprint,
        "source_b_fingerprint": assessment.source_b_fingerprint,
        "observed_demand_fingerprint": assessment.observed_demand_fingerprint,
        "authoritative_b_evaluation_fingerprint": (
            assessment.authoritative_b_evaluation_fingerprint
        ),
        "evaluation_policy": _jsonable(asdict(evaluation_policy)),
        "adjustment_policy": _policy_payload(adjustment_policy),
        "block_metrics": _jsonable([asdict(item) for item in assessment.block_evidence]),
        "joint_donor_evidence": _jsonable(
            [asdict(item) for item in assessment.joint_donor_evidence]
        ),
        "daily_evidence": _jsonable(asdict(assessment.daily_evidence)),
        "allocation_evidence": _jsonable([asdict(item) for item in assessment.allocation_evidence]),
        "headway_evidence": _jsonable([asdict(item) for item in assessment.headway_evidence]),
        "technical_evidence": _jsonable(asdict(assessment.technical_evidence)),
        "repeatability_evidence": (
            _jsonable(asdict(assessment.repeatability_evidence))
            if assessment.repeatability_evidence is not None
            else None
        ),
        "joint_reduction_evidence": (
            _jsonable(asdict(assessment.joint_reduction_evidence))
            if assessment.joint_reduction_evidence is not None
            else None
        ),
        "maximum_supported_reduction_quantity": (assessment.maximum_supported_reduction_quantity),
        "primary_decision": assessment.primary_decision.value,
        "reason_codes": list(assessment.reason_codes),
        "limitations": list(assessment.limitations),
        "heuristic_authorized": assessment.heuristic_authorized,
        "authorized_generation_action": assessment.authorized_generation_action,
    }


def evaluate_service_adjustment_need_v1(
    context: ScheduleGenerationContextV1,
    policy: ServiceAdjustmentPolicyV1 | None = None,
    repeatability_evidence: RepeatabilityEvidenceV1 | None = None,
) -> ServiceAdjustmentAssessmentV1:
    """Evaluate quantitative service-adjustment need without mutating or generating a timetable."""
    from .problem_validation import validate_schedule_generation_context_v1

    effective_policy = _effective_policy(policy, context.evaluation_policy)
    policy_fingerprint = canonical_sha256(_policy_payload(effective_policy))
    context_validation = validate_schedule_generation_context_v1(context)
    context_issue_codes = tuple(issue.code for issue in context_validation.issues)
    coverage = _coverage(context)
    blocks = _block_evidence(context)
    technical = _technical_evidence(context, context_issue_codes)
    blocks, joint_donors = _joint_donor_validation(
        context.normalized_inputs.scenario_b,
        blocks,
        coverage,
        effective_policy,
        technical.technically_feasible,
    )
    daily = _daily_evidence(
        context.normalized_inputs.scenario_b,
        blocks,
        coverage,
    )
    allocation = _allocation_evidence(
        context.normalized_inputs.scenario_b,
        blocks,
        coverage,
    )
    headways = _headway_evidence(
        context,
        effective_policy,
    )

    reasons: list[str] = []
    limitations: list[str] = list(context.b_evaluation.evaluation.limitations)
    limitations.extend(coverage.limitations)
    if coverage.mode == DemandCoverageModeV1.COMBINED_ONLY:
        reasons.append(DIRECTIONAL_ACTION_NOT_SUPPORTED_BY_COMBINED_DEMAND)
        limitations.append("Combined-only demand is not divided or duplicated across directions.")
    if context_issue_codes:
        reasons.append(ADJUSTMENT_DECISION_DATA_INSUFFICIENT)
        reasons.extend(context_issue_codes)

    ceiling_policy_mismatch = (
        effective_policy.planning_load_factor_ceiling
        != context.evaluation_policy.planning_load_factor_ceiling
        or effective_policy.critical_load_factor_ceiling
        != context.evaluation_policy.critical_load_factor_ceiling
        or effective_policy.minimum_authoritative_demand_confidence
        != context.evaluation_policy.minimum_authoritative_demand_confidence
    )
    if ceiling_policy_mismatch:
        reasons.extend(
            (
                ADJUSTMENT_DECISION_DATA_INSUFFICIENT,
                "ADJUSTMENT_POLICY_EVALUATION_AUTHORITY_MISMATCH",
            )
        )
        limitations.append(
            "Adjustment ceilings/confidence must match the authoritative B evaluation policy."
        )

    if technical.issue_codes:
        reasons.extend(technical.issue_codes)
    if any(item.shortage_trips > 0 for item in blocks):
        reasons.append(BLOCK_TRIP_SHORTAGE)
    if any(item.proven_joint_capacity > 0 for item in joint_donors):
        reasons.append(ELIGIBLE_DONOR_SUPPLY_AVAILABLE)
    reasons.extend(
        code for item in joint_donors if item.shortage_quantity > 0 for code in item.issue_codes
    )
    if any(item.allocation_mismatch_index > 0 for item in allocation):
        reasons.append(TEMPORAL_TRIP_ALLOCATION_MISMATCH)
    low_load_threshold = effective_policy.low_load_review_threshold
    if any(
        item.load_factor is not None and item.load_factor < low_load_threshold for item in blocks
    ):
        reasons.append(LOW_LOAD_REVIEW_ONLY)

    for regime in headways:
        if (
            regime.headway_range is not None
            and regime.headway_range > effective_policy.headway_rounding_tolerance_minutes
        ):
            reasons.append(HEADWAY_RANGE_ABOVE_BALANCED_TOLERANCE)
        if regime.regular_headway_rate < effective_policy.required_regular_headway_rate:
            reasons.append(REGULAR_HEADWAY_RATE_BELOW_REQUIRED)
        if regime.zero_headway_count:
            reasons.append(ZERO_HEADWAY_EXCEPTION_PRESENT)
        if regime.respace_diagnostic is not None and not regime.respace_diagnostic.passed:
            reasons.append(RESPACE_DIAGNOSTIC_VALIDATION_FAILED)
            reasons.extend(regime.respace_diagnostic.issue_codes)

    donor_capacity_sufficient = bool(
        sum(item.shortage_quantity for item in joint_donors) > 0
        and all(item.proven_joint_capacity >= item.shortage_quantity for item in joint_donors)
    )
    irregular_headways = tuple(
        item
        for item in headways
        if item.regularity_classification
        in {
            HeadwayRegularityClassificationV1.IRREGULAR,
            HeadwayRegularityClassificationV1.EXCEPTIONAL,
        }
    )
    headway_respace_possible = bool(irregular_headways) and all(
        item.respace_technically_possible for item in irregular_headways
    )

    repeatability_passed = False
    joint_reduction: JointReductionValidationEvidenceV1 | None = None
    maximum_reduction = 0
    repeatability_reasons: tuple[str, ...] = ()
    if (
        daily.daily_trip_gap is not None
        and daily.daily_trip_gap < 0
        and daily.total_shortage_trips == 0
        and daily.no_service_with_demand_block_count == 0
        and daily.critical_block_count == 0
    ):
        repeatability_passed, joint_reduction, repeatability_reasons = _repeatability_gate(
            repeatability_evidence,
            effective_policy,
            -daily.daily_trip_gap,
            context.normalized_inputs.scenario_b,
            blocks,
        )
        if joint_reduction is not None and joint_reduction.maximum_proven:
            maximum_reduction = joint_reduction.proven_supported_quantity
        reasons.extend(repeatability_reasons)

    if context_issue_codes or ceiling_policy_mismatch:
        decision = ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA
        explanation = (
            "The authoritative generation context or evaluation policy cannot support "
            "a V1-D1 decision."
        )
    elif (
        context.b_evaluation.evaluation.disposition == BDisposition.PARAMETERS_INFEASIBLE
        or not technical.technically_feasible
    ):
        decision = ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED
        explanation = "Scenario B fails at least one hard technical feasibility or lock gate."
    elif not daily.fully_supported:
        decision = ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA
        reasons.append(ADJUSTMENT_DECISION_DATA_INSUFFICIENT)
        reasons.extend(
            code
            for code in (
                DEMAND_TEMPORAL_COVERAGE_GAP,
                DEMAND_SERVICE_WINDOW_NOT_COVERED,
                DEMAND_DEPARTURE_NOT_COVERED,
                DEMAND_DIRECTION_STREAM_MISSING,
                MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT,
                COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE,
            )
            if code in coverage.evaluation_issue_codes
        )
        explanation = (
            "Demand authority is incomplete for a whole-window service-adjustment decision."
        )
    elif daily.daily_trip_gap is not None and daily.daily_trip_gap > 0:
        decision = ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS
        reasons.append(TOTAL_TRIP_SUPPLY_SHORTAGE)
        explanation = "Required daily trips at the planning ceiling exceed current daily supply."
    elif donor_capacity_sufficient:
        decision = ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS
        explanation = (
            "Shortage blocks and technically eligible same-direction donor capacity "
            "coexist under fixed daily resources."
        )
    elif (
        coverage.mode == DemandCoverageModeV1.COMBINED_ONLY
        and daily.total_shortage_trips is not None
        and daily.total_shortage_trips > 0
    ):
        decision = ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA
        reasons.append(ADJUSTMENT_DECISION_DATA_INSUFFICIENT)
        explanation = (
            "Aggregate demand proves a local shortage, but combined-only evidence cannot "
            "authorize directional trip placement."
        )
    elif daily.total_shortage_trips is not None and daily.total_shortage_trips > 0:
        decision = ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA
        reasons.extend(
            (
                ADJUSTMENT_DECISION_DATA_INSUFFICIENT,
                "NO_TECHNICALLY_ELIGIBLE_DONOR_SUPPLY",
            )
        )
        explanation = (
            "A local shortage is proven, but no technically eligible donor capacity "
            "supports fixed-resource redistribution."
        )
    elif repeatability_passed:
        decision = ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS
        explanation = (
            "Repeatable residual whole-day surplus and all reduction protections support "
            f"a maximum reduction of {maximum_reduction} trip(s)."
        )
    elif headway_respace_possible:
        decision = ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES
        explanation = (
            "Demand supply is adequate, but at least one continuous directional headway "
            "regime is irregular and can be re-spaced under fixed resources."
        )
    else:
        decision = ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE
        explanation = (
            "All authoritative quantitative demand, technical, allocation, and headway "
            "gates pass without a supported adjustment."
        )

    heuristic_authorized, authorized_action = _fixed_resource_authorization(
        decision=decision,
        context=context,
        coverage=coverage,
        technical=technical,
        policy=effective_policy,
        donor_capacity_sufficient=donor_capacity_sufficient,
        headway_respace_possible=headway_respace_possible,
    )
    if heuristic_authorized:
        reasons.append(CURRENT_SOLVER_CAN_IMPLEMENT)
    elif decision == ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE:
        reasons.append("NO_GENERATION_REQUIRED")
    else:
        reasons.append(CURRENT_SOLVER_CAPABILITY_INSUFFICIENT)

    reason_codes = _deduplicate(reasons)
    normalized_limitations = _deduplicate(limitations)
    evidence = _assessment_evidence(
        blocks=blocks,
        joint_donors=joint_donors,
        daily=daily,
        allocation=allocation,
        headways=headways,
        technical=technical,
        joint_reduction=joint_reduction,
    )
    assessment = ServiceAdjustmentAssessmentV1(
        assessment_id="",
        evaluator_fingerprint="",
        evaluator_fingerprint_profile=EVALUATOR_FINGERPRINT_PROFILE,
        source_problem_fingerprint=context.problem.problem_fingerprint,
        source_b_fingerprint=context.problem.source_b_fingerprint,
        observed_demand_fingerprint=context.problem.observed_demand_fingerprint,
        authoritative_b_evaluation_fingerprint=context.problem.evaluation_fingerprint,
        adjustment_policy_fingerprint=policy_fingerprint,
        primary_decision=decision,
        reason_codes=reason_codes,
        explanation=explanation,
        evidence=evidence,
        block_evidence=blocks,
        joint_donor_evidence=joint_donors,
        daily_evidence=daily,
        allocation_evidence=allocation,
        headway_evidence=headways,
        technical_evidence=technical,
        repeatability_evidence=repeatability_evidence,
        joint_reduction_evidence=joint_reduction,
        maximum_supported_reduction_quantity=maximum_reduction,
        limitations=normalized_limitations,
        heuristic_authorized=heuristic_authorized,
        authorized_generation_action=authorized_action,
    )
    fingerprint = canonical_sha256(
        _fingerprint_payload(
            assessment,
            context.evaluation_policy,
            effective_policy,
        )
    )
    return replace(
        assessment,
        assessment_id=f"ADJUSTMENT-{fingerprint[:16].upper()}",
        evaluator_fingerprint=fingerprint,
    )


__all__ = [
    "EVALUATOR_FINGERPRINT_PROFILE",
    "BlockAdjustmentEvidenceV1",
    "BlockAllocationShareV1",
    "DailyAdjustmentEvidenceV1",
    "DirectionalAllocationEvidenceV1",
    "HeadwayRegimeEvidenceV1",
    "HeadwayRegularityClassificationV1",
    "JointDonorValidationEvidenceV1",
    "JointReductionValidationEvidenceV1",
    "RepeatabilityDayEvidenceV1",
    "RepeatabilityEvidenceV1",
    "RespaceDiagnosticEvidenceV1",
    "ServiceAdjustmentAssessmentV1",
    "ServiceAdjustmentDecisionV1",
    "ServiceAdjustmentPolicyV1",
    "TechnicalAdjustmentEvidenceV1",
    "TechnicalEventEvidenceV1",
    "evaluate_service_adjustment_need_v1",
]

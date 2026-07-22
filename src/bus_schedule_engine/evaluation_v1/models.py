from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from bus_schedule_engine.contracts_v1.models import (
    ContractDirection,
    DemandConfidence,
    DemandResolutionType,
)

CONTRACT_VERSION = "1.0.0"


class DemandBlockMode(StrEnum):
    NATIVE = "native"
    ADAPTIVE = "adaptive"
    MANUAL = "manual"


class AggregationMethod(StrEnum):
    NONE = "none"
    SUM = "sum"
    WEIGHTED_SUM = "weighted_sum"
    APPROVED_CUSTOM = "approved_custom"


class InterpolationStatus(StrEnum):
    NONE = "none"
    AGGREGATED = "aggregated"
    INTERPOLATED_SUPPORTED = "interpolated_supported"
    UNSUPPORTED = "unsupported"


class BlockBoundaryReason(StrEnum):
    SOURCE_BOUNDARY = "source_boundary"
    SUSTAINED_CHANGE = "sustained_change"
    MANUAL = "manual"
    OPERATING_WINDOW = "operating_window"
    CRITICAL_CONDITION_PROTECTION = "critical_condition_protection"
    DIRECTION_CHANGE_PROTECTION = "direction_change_protection"


class EvaluationConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class BlockDemandStatus(StrEnum):
    WITHIN_PLANNING_CEILING = "WITHIN_PLANNING_CEILING"
    WARNING_ABOVE_85 = "WARNING_ABOVE_85"
    CRITICAL_ABOVE_90 = "CRITICAL_ABOVE_90"
    NO_SERVICE_WITH_DEMAND = "NO_SERVICE_WITH_DEMAND"
    LOW_LOAD_REVIEW_ONLY = "LOW_LOAD_REVIEW_ONLY"
    ELIGIBLE_DONOR_PERIOD = "ELIGIBLE_DONOR_PERIOD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DimensionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_EVALUATED = "NOT_EVALUATED"


class IssueSeverity(StrEnum):
    BLOCKING = "BLOCKING"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ScenarioBDisposition(StrEnum):
    FEASIBLE_AND_SUITABLE = "B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE"
    FEASIBLE_BUT_DEMAND_UNSUITABLE = "B_TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE"
    TIMETABLE_INFEASIBLE_MAY_REDISTRIBUTE = (
        "B_TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION"
    )
    PARAMETERS_INFEASIBLE = "B_PARAMETERS_INFEASIBLE"
    INSUFFICIENT_DATA = "B_INSUFFICIENT_DATA"


@dataclass(frozen=True, slots=True)
class DemandResolutionPolicy:
    block_mode: DemandBlockMode = DemandBlockMode.NATIVE
    minimum_block_duration: int = 1
    maximum_block_duration: int = 240
    minimum_sustained_intervals: int = 2
    material_change_ratio: float = 0.25
    manual_boundaries: tuple[int, ...] = ()
    smoothing_method: str = "none"
    interpolation_method: str = "none"


@dataclass(frozen=True, slots=True)
class DemandResolutionEvidence:
    source_resolution_type: DemandResolutionType
    source_resolution_minutes: int | None
    source_is_timestamp_level: bool
    source_is_trip_level: bool
    source_is_irregular: bool
    block_mode: DemandBlockMode
    manual_boundaries: tuple[int, ...]
    minimum_block_duration: int
    maximum_block_duration: int
    minimum_sustained_intervals: int
    material_change_ratio: float
    smoothing_method: str
    interpolation_method: str
    confidence_level: DemandConfidence
    observation_days: int
    sample_count: int

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class DemandAnalysisBlock:
    block_id: str
    start_time: int
    end_time: int
    direction: ContractDirection
    observed_passengers: float
    source_interval_ids: tuple[str, ...]
    source_resolution_type: DemandResolutionType
    source_resolution_minutes: int | None
    block_mode: DemandBlockMode
    aggregation_method: AggregationMethod
    confidence: DemandConfidence
    interpolation_status: InterpolationStatus
    observation_days: int
    sample_count: int
    block_boundary_reason: BlockBoundaryReason

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    @property
    def duration_minutes(self) -> int:
        return (self.end_time - self.start_time) // 60

    @property
    def demand_rate_per_hour(self) -> float:
        if self.duration_minutes <= 0:
            return 0.0
        return self.observed_passengers * 60 / self.duration_minutes


@dataclass(frozen=True, slots=True)
class EvaluationIssue:
    code: str
    severity: IssueSeverity
    message: str
    references: tuple[str, ...] = ()
    suggestion: str = ""


@dataclass(frozen=True, slots=True)
class DimensionResult:
    status: DimensionStatus
    issues: tuple[EvaluationIssue, ...]
    evidence: tuple[str, ...]
    explanation: str
    confidence: EvaluationConfidence


@dataclass(frozen=True, slots=True)
class BlockEvaluationResult:
    block_id: str
    direction: ContractDirection
    trip_count: int
    demand: float
    nominal_capacity: float
    planning_capacity: float
    maximum_recommended_capacity: float
    load_factor: float | None
    required_trips_85: int
    required_trips_90: int
    shortage: float
    status: BlockDemandStatus
    confidence: EvaluationConfidence


@dataclass(frozen=True, slots=True)
class ScheduleEvaluationResultV1:
    disposition: ScenarioBDisposition
    input_validity: DimensionResult
    parameter_consistency: DimensionResult
    technical_feasibility: DimensionResult
    demand_suitability: DimensionResult
    fleet_feasibility: DimensionResult
    headway_quality: DimensionResult
    block_evaluations: tuple[BlockEvaluationResult, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    confidence: EvaluationConfidence

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    @property
    def scenario_id(self) -> str:
        return "B"

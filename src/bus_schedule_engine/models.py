from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class RouteType(StrEnum):
    INTRA_PROVINCIAL = "intra_provincial"
    INTER_PROVINCIAL = "inter_provincial"


class Direction(StrEnum):
    TERMINAL_1_TO_2 = "terminal_1_to_2"
    TERMINAL_2_TO_1 = "terminal_2_to_1"
    COMBINED = "combined"


class VolumeType(StrEnum):
    TOTAL_OBSERVATION_PERIOD = "total_observation_period"
    AVERAGE_DAY = "average_day"


class TripRidershipDirectionV1(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class TripRidershipMatchMethodV1(StrEnum):
    EXPLICIT_SCHEDULED_TRIP_ID = "EXPLICIT_SCHEDULED_TRIP_ID"
    SCHEDULED_DEPARTURE_TIME = "SCHEDULED_DEPARTURE_TIME"
    ACTUAL_DEPARTURE_TIME = "ACTUAL_DEPARTURE_TIME"
    NONE = "NONE"


class TripRidershipMatchStatusV1(StrEnum):
    MATCHED_EXACT = "MATCHED_EXACT"
    MATCHED_WITHIN_TOLERANCE = "MATCHED_WITHIN_TOLERANCE"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    COLLISION = "COLLISION"
    INVALID = "INVALID"


class TripRidershipDatasetStatusV1(StrEnum):
    NOT_PROVIDED = "NOT_PROVIDED"
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_WARNINGS = "COMPLETE_WITH_WARNINGS"
    NO_USABLE_MATCHES = "NO_USABLE_MATCHES"
    FAILED = "FAILED"


class Severity(StrEnum):
    BLOCKING = "BLOCKING"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class EvaluationStatus(StrEnum):
    SUITABLE = "PHÙ HỢP"
    MONITOR = "PHÙ HỢP NHƯNG CẦN THEO DÕI"
    UNSUITABLE = "CHƯA PHÙ HỢP"
    INSUFFICIENT_DATA = "KHÔNG ĐỦ DỮ LIỆU ĐỂ KẾT LUẬN"
    NO_SERVICE_WITH_DEMAND = "NO_SERVICE_WITH_DEMAND"


class ScenarioCStatus(StrEnum):
    SUITABLE_REGULAR = "PHÙ HỢP VÀ GIÃN CÁCH ỔN ĐỊNH"
    DEMAND_IMPROVED_NOT_REGULAR = "CẢI THIỆN NHU CẦU NHƯNG CHƯA ĐỦ ỔN ĐỊNH"
    REGULAR_STILL_UNDERSUPPLIED = "GIÃN CÁCH ỔN ĐỊNH NHƯNG VẪN THIẾU CUNG"
    NO_BETTER_REDISTRIBUTION = "KHÔNG CÓ PHƯƠNG ÁN TÁI PHÂN BỔ TỐT HƠN"
    INFEASIBLE_FIXED_RESOURCES = "KHÔNG KHẢ THI VỚI SỐ CHUYẾN VÀ SỐ XE HIỆN CÓ"
    INSUFFICIENT_DATA = "KHÔNG ĐỦ DỮ LIỆU ĐỂ TỐI ƯU"


class HeadwayType(StrEnum):
    REGULAR = "REGULAR"
    BALANCED_ROUNDING = "BALANCED_ROUNDING"
    TRANSITION = "TRANSITION"
    EXCEPTIONAL = "EXCEPTIONAL"


class RegimeBoundaryReason(StrEnum):
    SUSTAINED_DEMAND_CHANGE = "SUSTAINED_DEMAND_CHANGE"
    MATERIAL_FREQUENCY_CHANGE = "MATERIAL_FREQUENCY_CHANGE"
    FLEET_FEASIBILITY = "FLEET_FEASIBILITY"
    TURNAROUND_FEASIBILITY = "TURNAROUND_FEASIBILITY"
    FIRST_SERVICE_CONSTRAINT = "FIRST_SERVICE_CONSTRAINT"
    FINAL_SERVICE_CONSTRAINT = "FINAL_SERVICE_CONSTRAINT"
    OPERATING_WINDOW_BOUNDARY = "OPERATING_WINDOW_BOUNDARY"


@dataclass(frozen=True)
class ScenarioParameters:
    route_id: str
    route_name: str
    route_type: RouteType
    trip_runtime_minutes: int
    total_daily_trips: int
    terminal_1_name: str
    terminal_1_first_departure: int
    terminal_1_last_departure: int
    terminal_2_name: str
    terminal_2_first_departure: int
    terminal_2_last_departure: int
    vehicle_capacity_passengers: int | None
    target_load_factor: float = 0.85
    maximum_load_factor: float = 0.90
    time_block_minutes: int = 60
    minimum_layover_minutes: int | None = None
    allowed_trip_runtime_minutes: tuple[int, ...] = ()
    available_fleet_limit: int | None = None
    approved_active_fleet: int | None = None
    operating_day_type: str | None = None
    terminal_1_max_occupancy_vehicles: int | None = None
    terminal_2_max_occupancy_vehicles: int | None = None

    @property
    def regulatory_minimum_layover_minutes(self) -> int:
        return 5 if self.route_type == RouteType.INTRA_PROVINCIAL else 15

    @property
    def effective_layover_minutes(self) -> int:
        return (
            self.minimum_layover_minutes
            if self.minimum_layover_minutes is not None
            else self.regulatory_minimum_layover_minutes
        )

    @property
    def capacity(self) -> int:
        if self.vehicle_capacity_passengers is None:
            raise ValueError("Thiếu sức chứa phương tiện")
        return self.vehicle_capacity_passengers

    @property
    def runtime_options(self) -> tuple[int, ...]:
        values = self.allowed_trip_runtime_minutes or (self.trip_runtime_minutes,)
        return tuple(sorted(set(values)))

    @property
    def default_trip_runtime_minutes(self) -> int:
        """Conservative fallback used only when a trip has no explicit arrival time."""
        return max(self.runtime_options)

    @property
    def runtime_options_text(self) -> str:
        if len(self.runtime_options) == 1:
            return str(self.runtime_options[0])
        return f"{min(self.runtime_options)},{max(self.runtime_options)}"

    @property
    def runtime_range_text(self) -> str:
        if len(self.runtime_options) == 1:
            return str(self.runtime_options[0])
        return f"{min(self.runtime_options)}–{max(self.runtime_options)}"

    def accepts_trip_runtime(self, runtime_minutes: int) -> bool:
        return min(self.runtime_options) <= runtime_minutes <= max(self.runtime_options)

    def terminal_for_direction(self, direction: Direction) -> str:
        if direction == Direction.TERMINAL_1_TO_2:
            return self.terminal_1_name
        if direction == Direction.TERMINAL_2_TO_1:
            return self.terminal_2_name
        raise ValueError("Chiều combined không có một bến xuất phát duy nhất")

    def opposite_terminal(self, terminal: str) -> str:
        if terminal == self.terminal_1_name:
            return self.terminal_2_name
        if terminal == self.terminal_2_name:
            return self.terminal_1_name
        raise ValueError(f"Bến không thuộc tuyến: {terminal}")


@dataclass(frozen=True)
class Trip:
    scenario: str
    trip_id: str
    departure_terminal: str
    direction: Direction
    departure_seconds: int
    arrival_seconds: int | None = None
    vehicle_id: str | None = None
    vehicle_capacity_override: int | None = None
    source_b_trip_id: str | None = None
    source_b_departure_seconds: int | None = None

    def resolved_arrival_seconds(self, runtime_minutes: int) -> int:
        if self.arrival_seconds is not None:
            return self.arrival_seconds
        return self.departure_seconds + runtime_minutes * 60


@dataclass(frozen=True)
class DemandRecord:
    period_start: date
    period_end: date
    observation_days: int
    block_start_seconds: int
    block_end_seconds: int
    direction: Direction
    passenger_volume: float
    volume_type: VolumeType

    @property
    def average_daily_demand(self) -> float:
        if self.volume_type == VolumeType.AVERAGE_DAY:
            return float(self.passenger_volume)
        if self.observation_days <= 0:
            raise ValueError("observation_days phải lớn hơn 0")
        return float(self.passenger_volume) / self.observation_days


@dataclass(frozen=True, slots=True)
class TripRidershipDatasetMetadataV1:
    dataset_id: str
    source_type: str
    confidence: str
    observed_schedule_scenario: str
    operating_day_type: str
    match_tolerance_minutes: int
    source_notes: str | None = None


@dataclass(frozen=True, slots=True)
class TripRidershipObservationV1:
    observation_id: str
    service_date: date
    source_trip_id: str | None
    scheduled_trip_id: str | None
    direction: TripRidershipDirectionV1
    scheduled_departure_seconds: int | None
    actual_departure_seconds: int | None
    passenger_count: int
    vehicle_id: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class TripRidershipMatchPolicyV1:
    match_tolerance_minutes: int
    observed_schedule_scenario: str = "B"
    precedence: tuple[TripRidershipMatchMethodV1, ...] = (
        TripRidershipMatchMethodV1.EXPLICIT_SCHEDULED_TRIP_ID,
        TripRidershipMatchMethodV1.SCHEDULED_DEPARTURE_TIME,
        TripRidershipMatchMethodV1.ACTUAL_DEPARTURE_TIME,
    )


@dataclass(frozen=True, slots=True)
class TripRidershipMatchV1:
    observation_id: str
    service_date: date
    direction: TripRidershipDirectionV1
    source_trip_id: str | None
    supplied_scheduled_trip_id: str | None
    scheduled_departure_seconds: int | None
    actual_departure_seconds: int | None
    passenger_count: int
    match_method: TripRidershipMatchMethodV1
    match_status: TripRidershipMatchStatusV1
    matched_trip_id: str | None
    candidate_trip_ids: tuple[str, ...]
    absolute_time_offset_seconds: int | None
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TripRidershipTripSummaryV1:
    trip_id: str
    direction: TripRidershipDirectionV1
    departure_terminal: str
    scheduled_departure_seconds: int
    nominal_trip_capacity: int
    observation_count: int
    distinct_observation_day_count: int
    passenger_minimum: int | None
    passenger_maximum: int | None
    passenger_mean: float | None
    passenger_median: float | None
    passenger_p85: int | None
    passenger_p90: int | None
    mean_load_factor: float | None
    median_load_factor: float | None
    p85_load_factor: float | None
    p90_load_factor: float | None
    days_at_or_above_target_load_factor: int
    share_observed_days_at_or_above_target_load_factor: float | None
    days_above_maximum_load_factor: int
    share_observed_days_above_maximum_load_factor: float | None
    exact_match_count: int
    tolerance_match_count: int
    mean_absolute_matching_offset_minutes: float | None
    maximum_absolute_matching_offset_minutes: float | None
    descriptive_limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TripRidershipDirectionSummaryV1:
    direction: TripRidershipDirectionV1
    total_b_trips: int
    b_trips_with_usable_observation: int
    scheduled_trip_coverage_rate: float | None
    usable_matched_records: int
    exact_matches: int
    tolerance_matches: int
    ambiguous_records: int
    unmatched_records: int
    collided_records: int
    invalid_records: int
    distinct_service_dates: int
    observed_matched_passengers: int
    average_matched_passenger_count_per_observed_trip: float | None
    observed_matched_passengers_per_service_date: float | None
    matched_trip_date_coverage_rate: float | None
    coverage_adjusted_interpretation: str


@dataclass(frozen=True, slots=True)
class TripRidershipDatasetSummaryV1:
    status: TripRidershipDatasetStatusV1
    original_record_count: int
    total_b_trips: int
    b_trips_with_usable_observation: int
    scheduled_trip_coverage_rate: float | None
    usable_matched_records: int
    exact_matches: int
    tolerance_matches: int
    unmatched_records: int
    ambiguous_records: int
    collided_records: int
    invalid_records: int
    usable_match_rate: float | None
    exact_match_rate: float | None
    distinct_service_dates: int
    directions_with_usable_observations: int
    direction_coverage_rate: float | None
    observed_matched_passengers: int
    average_matched_passenger_count_per_observed_trip: float | None
    observed_matched_passengers_per_service_date: float | None
    matched_trip_date_coverage_rate: float | None
    minimum_absolute_matching_offset_minutes: float | None
    mean_absolute_matching_offset_minutes: float | None
    median_absolute_matching_offset_minutes: float | None
    p85_absolute_matching_offset_minutes: float | None
    p90_absolute_matching_offset_minutes: float | None
    maximum_absolute_matching_offset_minutes: float | None
    coverage_adjusted_interpretation: str


@dataclass(frozen=True, slots=True)
class TripRidershipAnalysisV1:
    dataset_id: str
    source_type: str
    confidence: str
    operating_day_type: str
    scenario_b_timetable_fingerprint: str
    match_policy: TripRidershipMatchPolicyV1
    matching_policy_fingerprint: str
    analysis_fingerprint: str
    original_record_count: int
    match_rows: tuple[TripRidershipMatchV1, ...]
    trip_summaries: tuple[TripRidershipTripSummaryV1, ...]
    directional_summaries: tuple[TripRidershipDirectionSummaryV1, ...]
    dataset_summary: TripRidershipDatasetSummaryV1
    issue_codes: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TripRidershipAnalysisFailureV1:
    code: str
    correlation_id: str
    sanitized_message: str
    dataset_id: str | None
    scenario_b_timetable_fingerprint: str


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    trip_ids: tuple[str, ...] = ()
    block: str | None = None
    suggestion: str = ""


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(
            issue.severity in {Severity.BLOCKING, Severity.ERROR} for issue in self.issues
        )

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


@dataclass(frozen=True)
class HeadwayStats:
    count: int
    mean_minutes: float | None
    minimum_minutes: float | None
    maximum_minutes: float | None
    standard_deviation_minutes: float | None
    coefficient_of_variation: float | None


@dataclass(frozen=True)
class BlockEvaluation:
    scenario: str
    block_start_seconds: int
    block_end_seconds: int
    direction: Direction
    trips: int
    nominal_capacity: float
    target_capacity: float
    maximum_recommended_capacity: float
    demand: float
    load_factor: float | None
    required_trips: int
    trip_gap_to_target: int
    status: EvaluationStatus
    headway: HeadwayStats
    data_note: str = ""


@dataclass(frozen=True)
class FleetTripAssignment:
    vehicle_id: str
    trip_id: str
    direction: Direction
    departure_terminal: str
    arrival_terminal: str
    departure_seconds: int
    arrival_seconds: int
    ready_seconds: int
    waiting_minutes: float


@dataclass
class FleetResult:
    minimum_vehicles: int
    assignments: list[FleetTripAssignment]
    vehicle_summaries: list[dict[str, Any]]
    conflicts: list[str] = field(default_factory=list)


@dataclass
class ScenarioEvaluation:
    scenario: str
    blocks: list[BlockEvaluation]
    overall_status: EvaluationStatus
    technical_status: EvaluationStatus
    demand_status: EvaluationStatus
    maximum_load_factor: float | None
    blocks_over_target: int
    blocks_over_maximum: int
    headway: HeadwayStats
    early_coverage_gap_minutes: float
    late_coverage_gap_minutes: float
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HeadwayRegime:
    regime_id: str
    direction: Direction
    start_seconds: int
    end_seconds: int
    first_trip_id: str
    last_trip_id: str
    trip_count: int
    target_headway_minutes: float
    actual_headway_sequence: tuple[float, ...]
    headway_status: str
    boundary_reason: RegimeBoundaryReason
    minimum_headway_minutes: float | None
    maximum_headway_minutes: float | None
    mean_headway_minutes: float | None
    standard_deviation_minutes: float | None
    coefficient_of_variation: float | None


@dataclass(frozen=True)
class TripTrace:
    c_trip_id: str
    source_b_trip_id: str
    direction: Direction
    departure_terminal: str
    b_departure_seconds: int
    c_departure_seconds: int
    shift_minutes: float
    retained_or_shifted: str
    original_previous_headway: float | None
    new_previous_headway: float | None
    original_next_headway: float | None
    new_next_headway: float | None
    original_demand_interval: str
    new_demand_interval: str
    headway_regime_id: str
    headway_type: HeadwayType
    change_reason: str
    exception_reason: str = ""


@dataclass(frozen=True)
class RegularityMetrics:
    number_of_headway_regimes: int
    number_of_material_frequency_changes: int
    number_of_regular_headways: int
    number_of_balanced_rounding_headways: int
    number_of_transition_headways: int
    number_of_exceptional_headways: int
    maximum_consecutive_headway_difference: float
    sum_absolute_consecutive_headway_changes: float
    headway_standard_deviation: float | None
    headway_coefficient_of_variation: float | None
    maximum_service_gap: float | None
    gate_passed: bool
    gate_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class OptimizationLog:
    candidate_count: int
    accepted_candidates: int
    rejected_candidates: int
    rejection_reason_counts: tuple[tuple[str, int], ...]
    objective_before: tuple[float, ...]
    objective_after: tuple[float, ...]
    regularity_gate_result: str
    generation_status: ScenarioCStatus
    configuration_version: str
    generation_timestamp: str


@dataclass
class ScenarioResult:
    name: str
    parameters: ScenarioParameters
    trips: list[Trip]
    validation: ValidationReport
    evaluation: ScenarioEvaluation
    fleet: FleetResult
    score: float | None
    recommendation_reason: str = ""
    strategy_id: str = ""
    resource_fleet_limit: int | None = None
    display_name: str = ""
    active_vehicle_count: int | None = None
    active_vehicle_ids: tuple[str, ...] = ()
    generation_status: ScenarioCStatus | None = None
    headway_regimes: list[HeadwayRegime] = field(default_factory=list)
    trip_traces: list[TripTrace] = field(default_factory=list)
    regularity: RegularityMetrics | None = None
    optimization_log: OptimizationLog | None = None
    timetable_fingerprint: str = ""
    source_timetable_fingerprint: str = ""
    generation_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedScenario:
    name: str
    parameters: ScenarioParameters
    trips: list[Trip]
    reason: str
    strategy_id: str
    resource_fleet_limit: int | None
    display_name: str = ""
    active_vehicle_count: int | None = None
    active_vehicle_ids: tuple[str, ...] = ()
    generation_status: ScenarioCStatus | None = None
    headway_regimes: list[HeadwayRegime] = field(default_factory=list)
    trip_traces: list[TripTrace] = field(default_factory=list)
    regularity: RegularityMetrics | None = None
    optimization_log: OptimizationLog | None = None
    timetable_fingerprint: str = ""
    source_timetable_fingerprint: str = ""
    generation_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationReport:
    feasible: bool
    scenarios: list[GeneratedScenario] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    minimum_required_total_trips: int | None = None
    missing_trips: int = 0
    blocks_requiring_more_trips: list[str] = field(default_factory=list)
    no_improvement: bool = False


@dataclass
class AnalysisBundle:
    scenarios: list[ScenarioResult]
    generation: GenerationReport
    limitations: list[str]

    def get(self, name: str) -> ScenarioResult | None:
        return next((item for item in self.scenarios if item.name == name), None)

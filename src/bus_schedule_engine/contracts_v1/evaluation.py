from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from statistics import mean, pstdev

from .demand_resolution import (
    BlockBoundaryReason,
    BlockMode,
    DemandAnalysisBlockV1,
    DemandBlockPolicyV1,
    DemandResolutionResultV1,
    InterpolationStatus,
    build_demand_analysis_blocks_v1,
)
from .models import (
    CONTRACT_VERSION,
    ContractDirection,
    DemandConfidence,
    NormalizedInputBundleV1,
    ScenarioAInput,
    ScenarioBInput,
    ScenarioId,
    ScenarioInputV1,
)
from .validation import validate_normalized_bundle


class ScenarioBEvaluationError(ValueError):
    """Raised when Scenario B cannot be evaluated from a valid normalized bundle."""


class DimensionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_EVALUATED = "NOT_EVALUATED"


class EvaluationIssueSeverity(StrEnum):
    BLOCKING = "BLOCKING"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class BlockSupplyStatus(StrEnum):
    WITHIN_PLANNING_CEILING = "WITHIN_PLANNING_CEILING"
    WARNING_ABOVE_85 = "WARNING_ABOVE_85"
    CRITICAL_ABOVE_90 = "CRITICAL_ABOVE_90"
    NO_SERVICE_WITH_DEMAND = "NO_SERVICE_WITH_DEMAND"
    LOW_LOAD_REVIEW_ONLY = "LOW_LOAD_REVIEW_ONLY"
    ELIGIBLE_DONOR_PERIOD = "ELIGIBLE_DONOR_PERIOD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class BDisposition(StrEnum):
    TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE = "B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE"
    TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE = "B_TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE"
    TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION = (
        "B_TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION"
    )
    PARAMETERS_INFEASIBLE = "B_PARAMETERS_INFEASIBLE"
    INSUFFICIENT_DATA = "B_INSUFFICIENT_DATA"


_CONFIDENCE_RANK = {
    DemandConfidence.UNKNOWN: 0,
    DemandConfidence.LOW: 1,
    DemandConfidence.MEDIUM: 2,
    DemandConfidence.HIGH: 3,
}


@dataclass(frozen=True, slots=True)
class ScenarioBEvaluationPolicyV1:
    demand_blocks: DemandBlockPolicyV1 = DemandBlockPolicyV1()
    planning_load_factor_ceiling: float = 0.85
    critical_load_factor_ceiling: float = 0.90
    low_load_review_threshold: float = 0.30
    minimum_authoritative_demand_confidence: DemandConfidence = DemandConfidence.MEDIUM
    headway_cv_warning_threshold: float = 0.30
    maximum_gap_to_mean_warning_ratio: float = 2.0


@dataclass(frozen=True, slots=True)
class EvaluationIssueV1:
    code: str
    severity: EvaluationIssueSeverity
    message: str
    references: tuple[str, ...] = ()
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationDimensionV1:
    status: DimensionStatus
    issues: tuple[EvaluationIssueV1, ...]
    evidence: tuple[str, ...]
    explanation: str
    confidence: DemandConfidence


@dataclass(frozen=True, slots=True)
class BlockSupplyPlanV1:
    scenario: ScenarioId
    direction: ContractDirection
    block_id: str
    block_start: int
    block_end: int
    duration_minutes: int
    passenger_demand: float
    demand_rate_per_hour: float
    vehicle_capacity: int
    a_trip_count: int | None
    b_trip_count: int | None
    c_planned_trip_count: int | None
    c_actual_trip_count: int | None
    trip_rate_per_hour: float
    required_trips_85: int
    required_trips_90: int
    required_trip_rate_85: float
    required_trip_rate_90: float
    nominal_capacity: float
    capacity_at_85: float
    capacity_at_90: float
    load_factor: float | None
    shortage: float
    status: BlockSupplyStatus
    allocation_reason: str
    confidence: DemandConfidence

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class BlockEvaluationV1:
    block_id: str
    direction: ContractDirection
    load_factor: float | None
    shortage: float
    status: BlockSupplyStatus
    confidence: DemandConfidence


@dataclass(frozen=True, slots=True)
class TerminalStockEventV1:
    event_time: int
    event_type: str
    trip_id: str
    stock_before: int
    stock_after: int


@dataclass(frozen=True, slots=True)
class FleetAssessmentV1:
    available_fleet_limit: int
    minimum_required_fleet: int
    recommended_initial_fleet_terminal_1: int
    recommended_initial_fleet_terminal_2: int
    fleet_margin: int
    feasible: bool
    terminal_1_events: tuple[TerminalStockEventV1, ...]
    terminal_2_events: tuple[TerminalStockEventV1, ...]


@dataclass(frozen=True, slots=True)
class ScheduleEvaluationResultV1:
    disposition: BDisposition
    input_validity: EvaluationDimensionV1
    parameter_consistency: EvaluationDimensionV1
    technical_feasibility: EvaluationDimensionV1
    demand_suitability: EvaluationDimensionV1
    fleet_feasibility: EvaluationDimensionV1
    headway_quality: EvaluationDimensionV1
    block_evaluations: tuple[BlockEvaluationV1, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    confidence: DemandConfidence

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    @property
    def scenario_id(self) -> ScenarioId:
        return ScenarioId.B


@dataclass(frozen=True, slots=True)
class ScenarioBEvaluationBundleV1:
    demand_resolution: DemandResolutionResultV1 | None
    a_block_supply: tuple[BlockSupplyPlanV1, ...]
    b_block_supply: tuple[BlockSupplyPlanV1, ...]
    fleet_assessment: FleetAssessmentV1
    evaluation: ScheduleEvaluationResultV1


def _confidence_at_least(value: DemandConfidence, minimum: DemandConfidence) -> bool:
    return _CONFIDENCE_RANK[value] >= _CONFIDENCE_RANK[minimum]


def _dimension(
    status: DimensionStatus,
    explanation: str,
    *,
    issues: tuple[EvaluationIssueV1, ...] = (),
    evidence: tuple[str, ...] = (),
    confidence: DemandConfidence = DemandConfidence.HIGH,
) -> EvaluationDimensionV1:
    return EvaluationDimensionV1(
        status=status,
        issues=issues,
        evidence=evidence,
        explanation=explanation,
        confidence=confidence,
    )


def _trip_count(scenario: ScenarioInputV1, block: DemandAnalysisBlockV1) -> int:
    return sum(
        block.start_time <= trip.departure_time < block.end_time
        and (block.direction == ContractDirection.COMBINED or trip.direction == block.direction)
        for trip in scenario.exact_timetable
    )


def _required_trips(demand: float, capacity: int, ceiling: float) -> int:
    if capacity <= 0 or ceiling <= 0:
        raise ScenarioBEvaluationError("Capacity and load-factor ceiling must be positive")
    return math.ceil(demand / (capacity * ceiling)) if demand > 0 else 0


def _block_status(
    *,
    demand: float,
    trip_count: int,
    load_factor: float | None,
    confidence: DemandConfidence,
    interpolation_status: InterpolationStatus,
    policy: ScenarioBEvaluationPolicyV1,
) -> BlockSupplyStatus:
    if interpolation_status == InterpolationStatus.UNSUPPORTED:
        return BlockSupplyStatus.INSUFFICIENT_DATA
    if demand > 0 and trip_count == 0:
        return BlockSupplyStatus.NO_SERVICE_WITH_DEMAND
    if not _confidence_at_least(confidence, policy.minimum_authoritative_demand_confidence):
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


def _block_plan(
    *,
    scenario: ScenarioInputV1,
    scenario_id: ScenarioId,
    block: DemandAnalysisBlockV1,
    scenario_a: ScenarioAInput | None,
    scenario_b: ScenarioBInput,
    policy: ScenarioBEvaluationPolicyV1,
) -> BlockSupplyPlanV1:
    a_count = _trip_count(scenario_a, block) if scenario_a is not None else None
    b_count = _trip_count(scenario_b, block)
    scenario_count = _trip_count(scenario, block)
    nominal_capacity = scenario_count * scenario.vehicle_capacity
    load_factor = block.observed_passengers / nominal_capacity if nominal_capacity > 0 else None
    required_85 = _required_trips(
        block.observed_passengers,
        scenario.vehicle_capacity,
        policy.planning_load_factor_ceiling,
    )
    required_90 = _required_trips(
        block.observed_passengers,
        scenario.vehicle_capacity,
        policy.critical_load_factor_ceiling,
    )
    capacity_85 = nominal_capacity * policy.planning_load_factor_ceiling
    capacity_90 = nominal_capacity * policy.critical_load_factor_ceiling
    status = _block_status(
        demand=block.observed_passengers,
        trip_count=scenario_count,
        load_factor=load_factor,
        confidence=block.confidence,
        interpolation_status=block.interpolation_status,
        policy=policy,
    )
    reason = {
        BlockSupplyStatus.WITHIN_PLANNING_CEILING: (
            "Demand is within the one-sided 85% planning ceiling."
        ),
        BlockSupplyStatus.WARNING_ABOVE_85: ("Load factor is above 85% but not above 90%."),
        BlockSupplyStatus.CRITICAL_ABOVE_90: ("Load factor is above the 90% critical ceiling."),
        BlockSupplyStatus.NO_SERVICE_WITH_DEMAND: (
            "Observed demand exists but no departure serves the interval."
        ),
        BlockSupplyStatus.LOW_LOAD_REVIEW_ONLY: (
            "Low load is reported for review only; it is not a trip-reduction instruction."
        ),
        BlockSupplyStatus.ELIGIBLE_DONOR_PERIOD: (
            "Donor eligibility requires separate minimum-service and feasibility proof."
        ),
        BlockSupplyStatus.INSUFFICIENT_DATA: (
            "Demand confidence or interpolation support is insufficient for an authoritative conclusion."
        ),
    }[status]
    return BlockSupplyPlanV1(
        scenario=scenario_id,
        direction=block.direction,
        block_id=block.block_id,
        block_start=block.start_time,
        block_end=block.end_time,
        duration_minutes=block.duration_minutes,
        passenger_demand=block.observed_passengers,
        demand_rate_per_hour=block.demand_rate_per_hour,
        vehicle_capacity=scenario.vehicle_capacity,
        a_trip_count=a_count,
        b_trip_count=b_count,
        c_planned_trip_count=None,
        c_actual_trip_count=None,
        trip_rate_per_hour=scenario_count * 60 / block.duration_minutes,
        required_trips_85=required_85,
        required_trips_90=required_90,
        required_trip_rate_85=required_85 * 60 / block.duration_minutes,
        required_trip_rate_90=required_90 * 60 / block.duration_minutes,
        nominal_capacity=nominal_capacity,
        capacity_at_85=capacity_85,
        capacity_at_90=capacity_90,
        load_factor=load_factor,
        shortage=max(0.0, block.observed_passengers - capacity_85),
        status=status,
        allocation_reason=reason,
        confidence=block.confidence,
    )


def build_block_supply_plans_v1(
    bundle: NormalizedInputBundleV1,
    resolution: DemandResolutionResultV1,
    policy: ScenarioBEvaluationPolicyV1,
) -> tuple[tuple[BlockSupplyPlanV1, ...], tuple[BlockSupplyPlanV1, ...]]:
    a_rows = (
        tuple(
            _block_plan(
                scenario=bundle.scenario_a,
                scenario_id=ScenarioId.A,
                block=block,
                scenario_a=bundle.scenario_a,
                scenario_b=bundle.scenario_b,
                policy=policy,
            )
            for block in resolution.blocks
        )
        if bundle.scenario_a is not None
        else ()
    )
    b_rows = tuple(
        _block_plan(
            scenario=bundle.scenario_b,
            scenario_id=ScenarioId.B,
            block=block,
            scenario_a=bundle.scenario_a,
            scenario_b=bundle.scenario_b,
            policy=policy,
        )
        for block in resolution.blocks
    )
    return a_rows, b_rows


def _terminal_events(
    scenario: ScenarioBInput,
    terminal: str,
) -> list[tuple[int, int, int, str, str]]:
    events: list[tuple[int, int, int, str, str]] = []
    for trip in scenario.exact_timetable:
        departure_terminal = (
            scenario.terminal_1_name
            if trip.direction == ContractDirection.OUTBOUND
            else scenario.terminal_2_name
        )
        arrival_terminal = (
            scenario.terminal_2_name
            if trip.direction == ContractDirection.OUTBOUND
            else scenario.terminal_1_name
        )
        if departure_terminal == terminal:
            events.append((trip.departure_time, 1, -1, "DEPARTURE", trip.trip_id))
        if arrival_terminal == terminal:
            turnaround = (
                scenario.turnaround_minutes.terminal_1
                if terminal == scenario.terminal_1_name
                else scenario.turnaround_minutes.terminal_2
            )
            ready_time = trip.resolved_arrival_time + turnaround * 60
            events.append((ready_time, 0, 1, "READY", trip.trip_id))
    return sorted(events, key=lambda item: (item[0], item[1], item[4]))


def _minimum_initial_stock(events: list[tuple[int, int, int, str, str]]) -> int:
    balance = 0
    minimum = 0
    for _, _, delta, _, _ in events:
        balance += delta
        minimum = min(minimum, balance)
    return -minimum


def _stock_profile(
    events: list[tuple[int, int, int, str, str]],
    initial_stock: int,
) -> tuple[TerminalStockEventV1, ...]:
    stock = initial_stock
    profile: list[TerminalStockEventV1] = []
    for event_time, _, delta, event_type, trip_id in events:
        before = stock
        stock += delta
        profile.append(
            TerminalStockEventV1(
                event_time=event_time,
                event_type=event_type,
                trip_id=trip_id,
                stock_before=before,
                stock_after=stock,
            )
        )
    return tuple(profile)


def assess_scenario_b_fleet_v1(scenario: ScenarioBInput) -> FleetAssessmentV1:
    terminal_1_events = _terminal_events(scenario, scenario.terminal_1_name)
    terminal_2_events = _terminal_events(scenario, scenario.terminal_2_name)
    initial_1 = _minimum_initial_stock(terminal_1_events)
    initial_2 = _minimum_initial_stock(terminal_2_events)
    minimum_required = initial_1 + initial_2
    return FleetAssessmentV1(
        available_fleet_limit=scenario.available_fleet_limit,
        minimum_required_fleet=minimum_required,
        recommended_initial_fleet_terminal_1=initial_1,
        recommended_initial_fleet_terminal_2=initial_2,
        fleet_margin=scenario.available_fleet_limit - minimum_required,
        feasible=minimum_required <= scenario.available_fleet_limit,
        terminal_1_events=_stock_profile(terminal_1_events, initial_1),
        terminal_2_events=_stock_profile(terminal_2_events, initial_2),
    )


def _headway_dimension(
    scenario: ScenarioBInput,
    policy: ScenarioBEvaluationPolicyV1,
) -> EvaluationDimensionV1:
    issues: list[EvaluationIssueV1] = []
    evidence: list[str] = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        times = sorted(
            trip.departure_time for trip in scenario.exact_timetable if trip.direction == direction
        )
        if len(times) < 2:
            issues.append(
                EvaluationIssueV1(
                    code="HEADWAY_NOT_MEASURABLE",
                    severity=EvaluationIssueSeverity.WARNING,
                    message=f"Fewer than two departures exist for {direction.value}.",
                    references=(direction.value,),
                )
            )
            continue
        gaps = [(right - left) / 60 for left, right in zip(times, times[1:], strict=False)]
        average = mean(gaps)
        deviation = pstdev(gaps)
        cv = deviation / average if average > 0 else 0.0
        maximum_gap = max(gaps)
        evidence.append(
            f"{direction.value}: trips={len(times)}, mean_headway={average:.3f}, "
            f"max_gap={maximum_gap:.3f}, cv={cv:.6f}"
        )
        if cv > policy.headway_cv_warning_threshold:
            issues.append(
                EvaluationIssueV1(
                    code="HEADWAY_VARIATION_WARNING",
                    severity=EvaluationIssueSeverity.WARNING,
                    message=(f"Headway CV for {direction.value} exceeds the configured threshold."),
                    references=(direction.value,),
                    suggestion=(
                        "Review continuous headway regimes rather than resetting at demand blocks."
                    ),
                )
            )
        if average > 0 and maximum_gap > average * policy.maximum_gap_to_mean_warning_ratio:
            issues.append(
                EvaluationIssueV1(
                    code="EXCESSIVE_SERVICE_GAP",
                    severity=EvaluationIssueSeverity.WARNING,
                    message=(
                        f"Maximum gap for {direction.value} materially exceeds its mean headway."
                    ),
                    references=(direction.value,),
                )
            )
    return _dimension(
        DimensionStatus.WARNING if issues else DimensionStatus.PASS,
        "Headway quality is diagnostic and does not override hard technical feasibility.",
        issues=tuple(issues),
        evidence=tuple(evidence),
        confidence=DemandConfidence.HIGH,
    )


def _protect_adaptive_critical_conditions(
    bundle: NormalizedInputBundleV1,
    resolution: DemandResolutionResultV1,
    policy: ScenarioBEvaluationPolicyV1,
) -> DemandResolutionResultV1:
    if (
        policy.demand_blocks.block_mode != BlockMode.ADAPTIVE
        or bundle.observed_demand is None
        or not resolution.blocks
    ):
        return resolution
    native_policy = replace(
        policy.demand_blocks,
        block_mode=BlockMode.NATIVE,
        manual_boundaries=(),
    )
    native_resolution = build_demand_analysis_blocks_v1(
        bundle.observed_demand,
        native_policy,
    )
    _, native_b_supply = build_block_supply_plans_v1(
        bundle,
        native_resolution,
        policy,
    )
    protected_source_ids: set[str] = set()
    native_by_source: dict[str, DemandAnalysisBlockV1] = {}
    for block, plan in zip(native_resolution.blocks, native_b_supply, strict=True):
        for source_id in block.source_interval_ids:
            native_by_source[source_id] = block
        if plan.status in {
            BlockSupplyStatus.NO_SERVICE_WITH_DEMAND,
            BlockSupplyStatus.CRITICAL_ABOVE_90,
        }:
            protected_source_ids.update(block.source_interval_ids)
    if not protected_source_ids:
        return resolution

    expanded: list[DemandAnalysisBlockV1] = []
    split_applied = False
    for block in resolution.blocks:
        if len(block.source_interval_ids) > 1 and protected_source_ids.intersection(
            block.source_interval_ids
        ):
            split_applied = True
            for source_id in block.source_interval_ids:
                native = native_by_source[source_id]
                expanded.append(
                    replace(
                        native,
                        block_mode=BlockMode.ADAPTIVE,
                        block_boundary_reason=(BlockBoundaryReason.CRITICAL_CONDITION_PROTECTION),
                    )
                )
        else:
            expanded.append(block)
    if not split_applied:
        return resolution

    counters: dict[ContractDirection, int] = {}
    renumbered: list[DemandAnalysisBlockV1] = []
    for block in sorted(
        expanded,
        key=lambda item: (item.direction.value, item.start_time, item.end_time),
    ):
        counters[block.direction] = counters.get(block.direction, 0) + 1
        renumbered.append(
            replace(
                block,
                block_id=(f"DB-{block.direction.value.upper()}-{counters[block.direction]:04d}"),
            )
        )
    return DemandResolutionResultV1(
        contract=resolution.contract,
        blocks=tuple(renumbered),
        warnings=resolution.warnings
        + ("Adaptive merging was split to preserve native critical/no-service evidence.",),
        limitations=resolution.limitations,
    )


def _demand_dimension(
    plans: tuple[BlockSupplyPlanV1, ...],
    resolution: DemandResolutionResultV1 | None,
) -> EvaluationDimensionV1:
    if resolution is None or not resolution.blocks:
        return _dimension(
            DimensionStatus.INSUFFICIENT_DATA,
            "No authoritative intraday demand blocks are available.",
            confidence=DemandConfidence.UNKNOWN,
        )
    statuses = {item.status for item in plans}
    confidence = min(
        (item.confidence for item in plans),
        key=lambda item: _CONFIDENCE_RANK[item],
        default=DemandConfidence.UNKNOWN,
    )
    issues: list[EvaluationIssueV1] = []
    if BlockSupplyStatus.NO_SERVICE_WITH_DEMAND in statuses:
        issues.append(
            EvaluationIssueV1(
                code="NO_SERVICE_WITH_DEMAND",
                severity=EvaluationIssueSeverity.ERROR,
                message=("At least one authoritative demand block has demand but no service."),
                references=tuple(
                    item.block_id
                    for item in plans
                    if item.status == BlockSupplyStatus.NO_SERVICE_WITH_DEMAND
                ),
            )
        )
    if BlockSupplyStatus.CRITICAL_ABOVE_90 in statuses:
        issues.append(
            EvaluationIssueV1(
                code="CRITICAL_LOAD_FACTOR_ABOVE_90",
                severity=EvaluationIssueSeverity.ERROR,
                message=(
                    "At least one authoritative demand block exceeds the 90% critical ceiling."
                ),
                references=tuple(
                    item.block_id
                    for item in plans
                    if item.status == BlockSupplyStatus.CRITICAL_ABOVE_90
                ),
            )
        )
    if BlockSupplyStatus.WARNING_ABOVE_85 in statuses:
        issues.append(
            EvaluationIssueV1(
                code="LOAD_FACTOR_ABOVE_85",
                severity=EvaluationIssueSeverity.WARNING,
                message=(
                    "At least one authoritative demand block exceeds the 85% planning ceiling."
                ),
                references=tuple(
                    item.block_id
                    for item in plans
                    if item.status == BlockSupplyStatus.WARNING_ABOVE_85
                ),
            )
        )
    if BlockSupplyStatus.INSUFFICIENT_DATA in statuses:
        status = DimensionStatus.INSUFFICIENT_DATA
    elif any(item.severity == EvaluationIssueSeverity.ERROR for item in issues):
        status = DimensionStatus.FAIL
    elif issues:
        status = DimensionStatus.WARNING
    else:
        status = DimensionStatus.PASS
    evidence = tuple(
        f"{item.block_id}/{item.direction.value}: trips={item.b_trip_count}, "
        f"demand={item.passenger_demand:.6f}, lf={item.load_factor}, "
        f"required_85={item.required_trips_85}, "
        f"required_90={item.required_trips_90}, "
        f"shortage={item.shortage:.6f}, status={item.status.value}"
        for item in plans
    )
    return _dimension(
        status,
        "Demand suitability uses one-sided 85% and 90% ceilings; low load is review-only.",
        issues=tuple(issues),
        evidence=evidence,
        confidence=confidence,
    )


def evaluate_scenario_b_v1(
    bundle: NormalizedInputBundleV1,
    policy: ScenarioBEvaluationPolicyV1 | None = None,
) -> ScenarioBEvaluationBundleV1:
    policy = policy or ScenarioBEvaluationPolicyV1()
    if not (0 < policy.planning_load_factor_ceiling <= policy.critical_load_factor_ceiling <= 1):
        raise ScenarioBEvaluationError(
            "Load-factor ceilings must satisfy 0 < planning <= critical <= 1"
        )
    validation = validate_normalized_bundle(bundle)
    if not validation.passed:
        codes = ", ".join(validation.error_codes)
        raise ScenarioBEvaluationError(
            f"Scenario B evaluator requires a valid normalized bundle; errors: {codes}"
        )

    input_validity = _dimension(
        DimensionStatus.PASS,
        "Normalized Contract V1 input is valid.",
        evidence=(f"scenario_b_fingerprint={bundle.scenario_b_fingerprint}",),
    )
    parameter_consistency = _dimension(
        DimensionStatus.PASS,
        (
            "Declared B totals, directional counts, endpoints, windows and exact timetable reconcile."
        ),
        evidence=(
            f"declared_total={bundle.scenario_b.total_daily_trips}",
            f"outbound={bundle.scenario_b.trips_by_direction.outbound}",
            f"inbound={bundle.scenario_b.trips_by_direction.inbound}",
        ),
    )

    fleet = assess_scenario_b_fleet_v1(bundle.scenario_b)
    fleet_issue = (
        (
            EvaluationIssueV1(
                code="AVAILABLE_FLEET_LIMIT_EXCEEDED",
                severity=EvaluationIssueSeverity.ERROR,
                message=(
                    "The submitted B timetable requires more vehicles than the available upper bound."
                ),
                references=("scenario_b.available_fleet_limit",),
                suggestion=(
                    "Search for a redistributed timetable under the same locked parameters."
                ),
            ),
        )
        if not fleet.feasible
        else ()
    )
    fleet_status = DimensionStatus.PASS if fleet.feasible else DimensionStatus.FAIL
    fleet_evidence = (
        f"available_fleet_limit={fleet.available_fleet_limit}",
        f"minimum_required_fleet={fleet.minimum_required_fleet}",
        f"initial_terminal_1={fleet.recommended_initial_fleet_terminal_1}",
        f"initial_terminal_2={fleet.recommended_initial_fleet_terminal_2}",
        f"fleet_margin={fleet.fleet_margin}",
    )
    fleet_feasibility = _dimension(
        fleet_status,
        (
            "Fleet need is derived from continuous two-terminal event balances; "
            "ready events precede departures at the same time."
        ),
        issues=fleet_issue,
        evidence=fleet_evidence,
    )
    technical_feasibility = _dimension(
        fleet_status,
        (
            "The submitted B exact timetable is technically feasible under "
            "solver-determined initial positioning."
            if fleet.feasible
            else "The submitted B exact timetable is technically infeasible under "
            "the available fleet limit; this does not prove B's locked parameters infeasible."
        ),
        issues=fleet_issue,
        evidence=fleet_evidence,
    )
    headway_quality = _headway_dimension(bundle.scenario_b, policy)

    resolution: DemandResolutionResultV1 | None = None
    a_supply: tuple[BlockSupplyPlanV1, ...] = ()
    b_supply: tuple[BlockSupplyPlanV1, ...] = ()
    if bundle.observed_demand is not None:
        resolution = build_demand_analysis_blocks_v1(
            bundle.observed_demand,
            policy.demand_blocks,
        )
        resolution = _protect_adaptive_critical_conditions(
            bundle,
            resolution,
            policy,
        )
        a_supply, b_supply = build_block_supply_plans_v1(
            bundle,
            resolution,
            policy,
        )
    demand_suitability = _demand_dimension(b_supply, resolution)

    if not fleet.feasible:
        disposition = BDisposition.TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION
    elif demand_suitability.status == DimensionStatus.INSUFFICIENT_DATA:
        disposition = BDisposition.INSUFFICIENT_DATA
    elif demand_suitability.status in {
        DimensionStatus.FAIL,
        DimensionStatus.WARNING,
    }:
        disposition = BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE
    else:
        disposition = BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE

    block_evaluations = tuple(
        BlockEvaluationV1(
            block_id=item.block_id,
            direction=item.direction,
            load_factor=item.load_factor,
            shortage=item.shortage,
            status=item.status,
            confidence=item.confidence,
        )
        for item in b_supply
    )
    warnings = tuple(
        issue.message
        for dimension in (
            demand_suitability,
            headway_quality,
            fleet_feasibility,
        )
        for issue in dimension.issues
        if issue.severity
        in {
            EvaluationIssueSeverity.WARNING,
            EvaluationIssueSeverity.ERROR,
        }
    )
    limitations = [
        "Demand is evaluated in static mode; this is not a ridership-response forecast.",
        (
            "PR-02 evaluates the submitted B timetable but does not prove global "
            "infeasibility of B's locked parameters."
        ),
    ]
    if resolution is not None:
        limitations.extend(resolution.limitations)
    if resolution is not None and any(
        block.direction == ContractDirection.COMBINED for block in resolution.blocks
    ):
        limitations.append(
            "Combined demand supports aggregate conclusions only and is not "
            "apportioned into observed directional demand."
        )

    evaluation = ScheduleEvaluationResultV1(
        disposition=disposition,
        input_validity=input_validity,
        parameter_consistency=parameter_consistency,
        technical_feasibility=technical_feasibility,
        demand_suitability=demand_suitability,
        fleet_feasibility=fleet_feasibility,
        headway_quality=headway_quality,
        block_evaluations=block_evaluations,
        warnings=warnings,
        limitations=tuple(limitations),
        confidence=demand_suitability.confidence,
    )
    return ScenarioBEvaluationBundleV1(
        demand_resolution=resolution,
        a_block_supply=a_supply,
        b_block_supply=b_supply,
        fleet_assessment=fleet,
        evaluation=evaluation,
    )

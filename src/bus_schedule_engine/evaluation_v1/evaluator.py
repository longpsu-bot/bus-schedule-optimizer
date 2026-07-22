from __future__ import annotations

from dataclasses import replace
from math import ceil
from statistics import mean, pstdev

from bus_schedule_engine.contracts_v1.models import (
    ContractDirection,
    NormalizedInputBundleV1,
    ScenarioBInput,
)
from bus_schedule_engine.contracts_v1.validation import validate_scenario_input
from bus_schedule_engine.fleet import assign_fleet
from bus_schedule_engine.models import Direction, RouteType, ScenarioParameters, Trip

from .demand import build_demand_blocks
from .models import (
    BlockDemandStatus,
    BlockEvaluationResult,
    DemandAnalysisBlock,
    DemandResolutionPolicy,
    DimensionResult,
    DimensionStatus,
    EvaluationConfidence,
    EvaluationIssue,
    IssueSeverity,
    ScenarioBDisposition,
    ScheduleEvaluationResultV1,
)


def _confidence(value: str) -> EvaluationConfidence:
    return EvaluationConfidence(value)


def _dimension(
    status: DimensionStatus,
    explanation: str,
    *,
    issues: tuple[EvaluationIssue, ...] = (),
    evidence: tuple[str, ...] = (),
    confidence: EvaluationConfidence = EvaluationConfidence.HIGH,
) -> DimensionResult:
    return DimensionResult(status, issues, evidence, explanation, confidence)


def _legacy_scenario(scenario: ScenarioBInput) -> tuple[ScenarioParameters, list[Trip]]:
    parameters = ScenarioParameters(
        route_id=scenario.route_id,
        route_name=scenario.route_name,
        route_type=scenario.route_type,
        trip_runtime_minutes=scenario.trip_runtime_minutes,
        total_daily_trips=scenario.total_daily_trips,
        terminal_1_name=scenario.terminal_1_name,
        terminal_1_first_departure=scenario.first_departures.terminal_1,
        terminal_1_last_departure=scenario.last_departures.terminal_1,
        terminal_2_name=scenario.terminal_2_name,
        terminal_2_first_departure=scenario.first_departures.terminal_2,
        terminal_2_last_departure=scenario.last_departures.terminal_2,
        vehicle_capacity_passengers=scenario.vehicle_capacity,
        minimum_layover_minutes=min(
            scenario.turnaround_minutes.terminal_1,
            scenario.turnaround_minutes.terminal_2,
        ),
        available_fleet_limit=scenario.available_fleet_limit,
        approved_active_fleet=scenario.approved_active_fleet,
        operating_day_type=scenario.operating_day_type.value,
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=item.trip_id,
            departure_terminal=(
                scenario.terminal_1_name
                if item.departure_terminal.value == "terminal_1"
                else scenario.terminal_2_name
            ),
            direction=(
                Direction.TERMINAL_1_TO_2
                if item.direction == ContractDirection.OUTBOUND
                else Direction.TERMINAL_2_TO_1
            ),
            departure_seconds=item.departure_time,
            arrival_seconds=item.resolved_arrival_time,
            vehicle_id=item.vehicle_assignment,
        )
        for item in scenario.exact_timetable
    ]
    return parameters, trips


def _technical_dimensions(scenario: ScenarioBInput) -> tuple[DimensionResult, DimensionResult, DimensionResult]:
    validation = validate_scenario_input(scenario)
    if not validation.passed:
        issues = tuple(
            EvaluationIssue(
                code=item.code,
                severity=IssueSeverity.ERROR,
                message=item.message,
                references=(item.path,),
            )
            for item in validation.issues
        )
        failed = _dimension(
            DimensionStatus.FAIL,
            "Scenario B failed normalized input and parameter consistency checks.",
            issues=issues,
            confidence=EvaluationConfidence.HIGH,
        )
        return failed, failed, _dimension(
            DimensionStatus.NOT_EVALUATED,
            "Fleet feasibility was not evaluated because normalized input validation failed.",
        )

    parameters, trips = _legacy_scenario(scenario)
    fleet = assign_fleet(trips, parameters)
    fleet_ok = fleet.minimum_vehicles <= scenario.available_fleet_limit
    fleet_dimension = _dimension(
        DimensionStatus.PASS if fleet_ok else DimensionStatus.FAIL,
        (
            "Minimum practical fleet is within the available upper bound."
            if fleet_ok
            else "Submitted timetable requires more vehicles than the available upper bound."
        ),
        evidence=(
            f"minimum_required_fleet={fleet.minimum_vehicles}",
            f"available_fleet_limit={scenario.available_fleet_limit}",
        ),
        issues=(
            ()
            if fleet_ok
            else (
                EvaluationIssue(
                    "FLEET_LIMIT_EXCEEDED",
                    IssueSeverity.ERROR,
                    "Scenario B requires more vehicles than available.",
                    ("scenario_b.available_fleet_limit",),
                    "Redistribute departures or revise locked operating parameters.",
                ),
            )
        ),
    )
    technical = _dimension(
        DimensionStatus.PASS if fleet_ok else DimensionStatus.FAIL,
        (
            "Scenario B is technically feasible under the current two-terminal no-deadhead model."
            if fleet_ok
            else "Scenario B exact timetable is technically infeasible under the fleet upper bound."
        ),
        evidence=fleet_dimension.evidence,
        issues=fleet_dimension.issues,
    )
    consistency = _dimension(
        DimensionStatus.PASS,
        "Declared parameters reconcile with the exact timetable.",
        evidence=(f"total_daily_trips={scenario.total_daily_trips}",),
    )
    return technical, consistency, fleet_dimension


def _trip_count(scenario: ScenarioBInput, block: DemandAnalysisBlock) -> int:
    return sum(
        block.start_time <= trip.departure_time < block.end_time
        and (
            block.direction == ContractDirection.COMBINED
            or trip.direction == block.direction
        )
        for trip in scenario.exact_timetable
    )


def _block_evaluation(
    scenario: ScenarioBInput,
    block: DemandAnalysisBlock,
    *,
    planning_ceiling: float,
    critical_ceiling: float,
    low_load_review_threshold: float,
) -> BlockEvaluationResult:
    trips = _trip_count(scenario, block)
    nominal = trips * scenario.vehicle_capacity
    load_factor = block.observed_passengers / nominal if nominal > 0 else None
    required_85 = ceil(block.observed_passengers / (scenario.vehicle_capacity * planning_ceiling))
    required_90 = ceil(block.observed_passengers / (scenario.vehicle_capacity * critical_ceiling))
    shortage = max(0.0, block.observed_passengers - nominal * planning_ceiling)
    if block.interpolation_status.value == "unsupported":
        status = BlockDemandStatus.INSUFFICIENT_DATA
    elif block.observed_passengers > 0 and trips == 0:
        status = BlockDemandStatus.NO_SERVICE_WITH_DEMAND
    elif load_factor is not None and load_factor > critical_ceiling:
        status = BlockDemandStatus.CRITICAL_ABOVE_90
    elif load_factor is not None and load_factor > planning_ceiling:
        status = BlockDemandStatus.WARNING_ABOVE_85
    elif load_factor is not None and load_factor < low_load_review_threshold:
        status = BlockDemandStatus.LOW_LOAD_REVIEW_ONLY
    else:
        status = BlockDemandStatus.WITHIN_PLANNING_CEILING
    return BlockEvaluationResult(
        block_id=block.block_id,
        direction=block.direction,
        trip_count=trips,
        demand=block.observed_passengers,
        nominal_capacity=nominal,
        planning_capacity=nominal * planning_ceiling,
        maximum_recommended_capacity=nominal * critical_ceiling,
        load_factor=load_factor,
        required_trips_85=required_85,
        required_trips_90=required_90,
        shortage=shortage,
        status=status,
        confidence=_confidence(block.confidence.value),
    )


def _headway_quality(scenario: ScenarioBInput) -> DimensionResult:
    cvs: list[float] = []
    maximum_gap = 0.0
    issues: list[EvaluationIssue] = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        departures = sorted(
            trip.departure_time for trip in scenario.exact_timetable if trip.direction == direction
        )
        gaps = [(right - left) / 60 for left, right in zip(departures, departures[1:])]
        if gaps:
            maximum_gap = max(maximum_gap, max(gaps))
            average = mean(gaps)
            if average > 0 and len(gaps) > 1:
                cvs.append(pstdev(gaps) / average)
    maximum_cv = max(cvs, default=0.0)
    status = DimensionStatus.WARNING if maximum_cv > 0.35 else DimensionStatus.PASS
    if status == DimensionStatus.WARNING:
        issues.append(
            EvaluationIssue(
                "IRREGULAR_HEADWAY_REVIEW",
                IssueSeverity.WARNING,
                "Headway coefficient of variation exceeds the review threshold.",
                ("scenario_b.exact_timetable",),
            )
        )
    return _dimension(
        status,
        "Headway quality is descriptive and does not override technical or demand failures.",
        issues=tuple(issues),
        evidence=(f"maximum_headway_cv={maximum_cv:.4f}", f"maximum_gap_minutes={maximum_gap:.2f}"),
        confidence=EvaluationConfidence.MEDIUM,
    )


def evaluate_scenario_b(
    bundle: NormalizedInputBundleV1,
    *,
    policy: DemandResolutionPolicy | None = None,
    planning_ceiling: float = 0.85,
    critical_ceiling: float = 0.90,
    low_load_review_threshold: float = 0.30,
) -> ScheduleEvaluationResultV1:
    scenario = bundle.scenario_b
    contract_validation = validate_scenario_input(scenario)
    input_validity = _dimension(
        DimensionStatus.PASS if contract_validation.passed else DimensionStatus.FAIL,
        "Normalized Scenario B input is valid." if contract_validation.passed else "Scenario B input is invalid.",
        issues=tuple(
            EvaluationIssue(item.code, IssueSeverity.ERROR, item.message, (item.path,))
            for item in contract_validation.issues
        ),
    )
    technical, consistency, fleet = _technical_dimensions(scenario)
    headway = _headway_quality(scenario)

    limitations: list[str] = [
        "Static demand mode does not forecast induced or suppressed ridership.",
        "Low load is review-only and does not imply a trip-removal recommendation.",
    ]
    warnings: list[str] = []
    block_results: tuple[BlockEvaluationResult, ...] = ()
    if bundle.observed_demand is None or bundle.scenario_a is None:
        demand_dimension = _dimension(
            DimensionStatus.INSUFFICIENT_DATA,
            "Observed demand under Scenario A is unavailable.",
            confidence=EvaluationConfidence.UNKNOWN,
        )
        disposition = ScenarioBDisposition.INSUFFICIENT_DATA
    else:
        resolution, blocks = build_demand_blocks(bundle.observed_demand, policy)
        if not blocks:
            demand_dimension = _dimension(
                DimensionStatus.INSUFFICIENT_DATA,
                "Demand source has no authoritative intraday resolution.",
                evidence=(f"source_resolution_type={resolution.source_resolution_type.value}",),
                confidence=_confidence(resolution.confidence_level.value),
            )
            disposition = ScenarioBDisposition.INSUFFICIENT_DATA
        else:
            block_results = tuple(
                _block_evaluation(
                    scenario,
                    block,
                    planning_ceiling=planning_ceiling,
                    critical_ceiling=critical_ceiling,
                    low_load_review_threshold=low_load_review_threshold,
                )
                for block in blocks
            )
            failures = {
                BlockDemandStatus.NO_SERVICE_WITH_DEMAND,
                BlockDemandStatus.CRITICAL_ABOVE_90,
                BlockDemandStatus.WARNING_ABOVE_85,
            }
            unsuitable = any(item.status in failures for item in block_results)
            demand_dimension = _dimension(
                DimensionStatus.FAIL if unsuitable else DimensionStatus.PASS,
                (
                    "One or more authoritative blocks exceed the one-sided demand ceiling."
                    if unsuitable
                    else "All authoritative blocks are within the planning ceiling or review-only low load."
                ),
                evidence=(
                    f"authoritative_blocks={len(block_results)}",
                    f"blocks_above_85={sum(item.status in failures for item in block_results)}",
                ),
                confidence=_confidence(resolution.confidence_level.value),
            )
            if technical.status == DimensionStatus.FAIL:
                disposition = ScenarioBDisposition.TIMETABLE_INFEASIBLE_MAY_REDISTRIBUTE
            elif unsuitable:
                disposition = ScenarioBDisposition.FEASIBLE_BUT_DEMAND_UNSUITABLE
            else:
                disposition = ScenarioBDisposition.FEASIBLE_AND_SUITABLE
    if input_validity.status == DimensionStatus.FAIL:
        disposition = ScenarioBDisposition.PARAMETERS_INFEASIBLE
    elif demand_dimension.status == DimensionStatus.INSUFFICIENT_DATA:
        disposition = ScenarioBDisposition.INSUFFICIENT_DATA
    elif technical.status == DimensionStatus.FAIL:
        disposition = ScenarioBDisposition.TIMETABLE_INFEASIBLE_MAY_REDISTRIBUTE

    confidence_values = [
        input_validity.confidence,
        consistency.confidence,
        technical.confidence,
        fleet.confidence,
        demand_dimension.confidence,
    ]
    confidence = min(
        confidence_values,
        key=lambda value: {
            EvaluationConfidence.UNKNOWN: 0,
            EvaluationConfidence.LOW: 1,
            EvaluationConfidence.MEDIUM: 2,
            EvaluationConfidence.HIGH: 3,
        }[value],
    )
    return ScheduleEvaluationResultV1(
        disposition=disposition,
        input_validity=input_validity,
        parameter_consistency=consistency,
        technical_feasibility=technical,
        demand_suitability=demand_dimension,
        fleet_feasibility=fleet,
        headway_quality=headway,
        block_evaluations=block_results,
        warnings=tuple(warnings),
        limitations=tuple(limitations),
        confidence=confidence,
    )

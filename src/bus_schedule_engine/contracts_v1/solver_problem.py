from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Any

from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    ScenarioParameters,
    Trip,
)

from .evaluation import (
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
)
from .evaluation_fingerprints import evaluation_fingerprint
from .models import (
    ContractDirection,
    DepartureTerminal,
    NormalizedInputBundleV1,
)
from .public_api import evaluate_scenario_b_v1
from .serialization import canonical_sha256
from .solver_models import ScheduleProblemV1

PROBLEM_FINGERPRINT_PROFILE = "contract_v1_h1_problem"
NUMERIC_RECONCILIATION_TOLERANCE_MINUTES = 1e-9
ANALYTICAL_BLOCK_MEMBERSHIP_CONVENTION = "start_inclusive_end_exclusive"
SUPPORTED_OPERATING_MODES = {
    "fleet_constraint_mode": "available_upper_bound",
    "initial_fleet_positioning_mode": "solver_determined",
    "direction_trip_lock_mode": "fixed_by_direction",
}


class ScheduleProblemError(ValueError):
    """Raised when legacy heuristic inputs do not reconcile with Contract V1."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def contract_direction(direction: Direction) -> ContractDirection:
    if direction == Direction.TERMINAL_1_TO_2:
        return ContractDirection.OUTBOUND
    if direction == Direction.TERMINAL_2_TO_1:
        return ContractDirection.INBOUND
    return ContractDirection.COMBINED


def legacy_direction(direction: ContractDirection) -> Direction:
    if direction == ContractDirection.OUTBOUND:
        return Direction.TERMINAL_1_TO_2
    if direction == ContractDirection.INBOUND:
        return Direction.TERMINAL_2_TO_1
    raise ScheduleProblemError("Timetable candidates cannot use combined direction")


def departure_terminal(direction: ContractDirection) -> DepartureTerminal:
    if direction == ContractDirection.OUTBOUND:
        return DepartureTerminal.TERMINAL_1
    if direction == ContractDirection.INBOUND:
        return DepartureTerminal.TERMINAL_2
    raise ScheduleProblemError("Timetable candidates cannot use combined direction")


def _validate_legacy_parameters(
    normalized: NormalizedInputBundleV1,
    legacy: ScenarioParameters,
) -> None:
    scenario_b = normalized.scenario_b
    comparisons = {
        "route_id": (legacy.route_id, scenario_b.route_id),
        "route_name": (legacy.route_name, scenario_b.route_name),
        "route_type": (legacy.route_type, scenario_b.route_type),
        "terminal_1_name": (legacy.terminal_1_name, scenario_b.terminal_1_name),
        "terminal_2_name": (legacy.terminal_2_name, scenario_b.terminal_2_name),
        "total_daily_trips": (
            legacy.total_daily_trips,
            scenario_b.total_daily_trips,
        ),
        "vehicle_capacity": (legacy.capacity, scenario_b.vehicle_capacity),
        "trip_runtime_minutes": (
            legacy.default_trip_runtime_minutes,
            scenario_b.trip_runtime_minutes,
        ),
        "terminal_1_first_departure": (
            legacy.terminal_1_first_departure,
            scenario_b.first_departures.terminal_1,
        ),
        "terminal_2_first_departure": (
            legacy.terminal_2_first_departure,
            scenario_b.first_departures.terminal_2,
        ),
        "terminal_1_last_departure": (
            legacy.terminal_1_last_departure,
            scenario_b.last_departures.terminal_1,
        ),
        "terminal_2_last_departure": (
            legacy.terminal_2_last_departure,
            scenario_b.last_departures.terminal_2,
        ),
    }
    mismatches = [
        field
        for field, (legacy_value, normalized_value) in comparisons.items()
        if legacy_value != normalized_value
    ]
    if mismatches:
        raise ScheduleProblemError(
            "Legacy parameters do not reconcile with Scenario B: " + ", ".join(mismatches)
        )
    if not (
        legacy.effective_layover_minutes
        == scenario_b.turnaround_minutes.terminal_1
        == scenario_b.turnaround_minutes.terminal_2
    ):
        raise ScheduleProblemError(
            "The heuristic adapter supports equal terminal turnaround values only"
        )


def _validate_legacy_timetable(
    normalized: NormalizedInputBundleV1,
    legacy_trips_b: tuple[Trip, ...],
) -> None:
    normalized_by_id = {trip.trip_id: trip for trip in normalized.scenario_b.exact_timetable}
    legacy_by_id = {trip.trip_id: trip for trip in legacy_trips_b}
    if len(legacy_by_id) != len(legacy_trips_b):
        raise ScheduleProblemError("Legacy Scenario B contains duplicate trip IDs")
    if set(normalized_by_id) != set(legacy_by_id):
        raise ScheduleProblemError(
            "Legacy and normalized Scenario B trip identities do not reconcile"
        )
    for trip_id, normalized_trip in normalized_by_id.items():
        legacy_trip = legacy_by_id[trip_id]
        expected_direction = contract_direction(legacy_trip.direction)
        expected_terminal = departure_terminal(expected_direction)
        arrival = legacy_trip.resolved_arrival_seconds(normalized.scenario_b.trip_runtime_minutes)
        if (
            expected_direction != normalized_trip.direction
            or expected_terminal != normalized_trip.departure_terminal
            or legacy_trip.departure_seconds != normalized_trip.departure_time
            or arrival != normalized_trip.resolved_arrival_time
        ):
            raise ScheduleProblemError(
                f"Legacy and normalized Scenario B differ for trip {trip_id}"
            )


def _validate_legacy_demand(
    normalized: NormalizedInputBundleV1,
    legacy_demand: tuple[DemandRecord, ...],
) -> None:
    observed = normalized.observed_demand
    if observed is None:
        if legacy_demand:
            raise ScheduleProblemError(
                "Legacy demand is present while normalized observed demand is absent"
            )
        return
    if len(observed.observations) != len(legacy_demand):
        raise ScheduleProblemError("Legacy and normalized demand row counts do not reconcile")
    normalized_rows = sorted(
        (
            observation.direction.value,
            observation.interval_start,
            observation.interval_end,
            float(observation.passenger_count),
            observation.volume_classification.value,
        )
        for observation in observed.observations
    )
    legacy_rows = sorted(
        (
            contract_direction(record.direction).value,
            record.block_start_seconds,
            record.block_end_seconds,
            float(record.passenger_volume),
            record.volume_type.value,
        )
        for record in legacy_demand
    )
    if normalized_rows != legacy_rows:
        raise ScheduleProblemError("Legacy and normalized demand observations do not reconcile")


def build_schedule_problem_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    legacy_parameters: ScenarioParameters,
    legacy_trips_b: list[Trip] | tuple[Trip, ...],
    legacy_demand: list[DemandRecord] | tuple[DemandRecord, ...],
    heuristic_config: ScenarioCConfig,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
) -> ScheduleProblemV1:
    effective_policy = evaluation_policy or ScenarioBEvaluationPolicyV1()
    trips = tuple(legacy_trips_b)
    demand = tuple(legacy_demand)
    _validate_legacy_parameters(normalized_inputs, legacy_parameters)
    _validate_legacy_timetable(normalized_inputs, trips)
    _validate_legacy_demand(normalized_inputs, demand)

    authoritative_evaluation = evaluate_scenario_b_v1(
        normalized_inputs,
        effective_policy,
    )
    authoritative_evaluation_fingerprint = evaluation_fingerprint(
        normalized_inputs,
        authoritative_evaluation,
        effective_policy,
    )
    supplied_evaluation_fingerprint = evaluation_fingerprint(
        normalized_inputs,
        b_evaluation,
        effective_policy,
    )
    if supplied_evaluation_fingerprint != authoritative_evaluation_fingerprint:
        code = "B_EVALUATION_PROVENANCE_MISMATCH"
        raise ScheduleProblemError(
            f"{code}: supplied Scenario B evaluation does not match "
            "the authoritative current evaluation",
            code=code,
        )

    payload = {
        "fingerprint_profile": PROBLEM_FINGERPRINT_PROFILE,
        "contract_version": normalized_inputs.scenario_b.contract_version,
        "scenario_a_fingerprint": normalized_inputs.scenario_a_fingerprint,
        "scenario_b_fingerprint": normalized_inputs.scenario_b_fingerprint,
        "observed_demand_fingerprint": normalized_inputs.observed_demand_fingerprint,
        "authoritative_evaluation_fingerprint": (authoritative_evaluation_fingerprint),
        "evaluation_policy": jsonable(asdict(effective_policy)),
        "heuristic_config": jsonable(asdict(heuristic_config)),
        "supported_operating_modes": SUPPORTED_OPERATING_MODES,
        "analytical_block_membership_convention": (ANALYTICAL_BLOCK_MEMBERSHIP_CONVENTION),
        "numeric_reconciliation_tolerance_minutes": (NUMERIC_RECONCILIATION_TOLERANCE_MINUTES),
        "regime_membership_source": "raw_trip_headway_regime_id",
        "directional_ordering": ["departure_time", "trip_id"],
        "regime_endpoint_convention": "inclusive_member_departure_endpoints",
    }
    return ScheduleProblemV1(
        normalized_inputs=normalized_inputs,
        b_evaluation=authoritative_evaluation,
        evaluation_policy=effective_policy,
        legacy_parameters=legacy_parameters,
        legacy_trips_b=trips,
        legacy_demand=demand,
        heuristic_config=heuristic_config,
        problem_fingerprint=canonical_sha256(payload),
    )

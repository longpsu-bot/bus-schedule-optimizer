"""Neutral contracts for deterministic uniform-headway schedule compilation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from .serialization import canonical_sha256

COMPILER_INPUT_PROFILE_V1 = "uniform_headway_compiler_input_v1"
TEMPORARY_AUTHORITATIVE_BRIDGE_V1 = "TEMPORARY_AUTHORITATIVE_BRIDGE_V1"


class CompilationStatusV1(StrEnum):
    COMPILED = "COMPILED"
    UNCOMPILABLE_ALLOCATION = "UNCOMPILABLE_ALLOCATION"


class FleetValidationStatusV1(StrEnum):
    NOT_FLEET_VALIDATED = "NOT_FLEET_VALIDATED"


@dataclass(frozen=True, slots=True)
class CompilerDemandRegimeInputV1:
    regime_id: str
    start_minute: int
    end_minute: int
    allocated_trip_count: int

    def __post_init__(self) -> None:
        if not self.regime_id.strip():
            raise ValueError("compiler demand-regime id must be non-empty")
        if self.end_minute <= self.start_minute:
            raise ValueError("compiler demand regime must have a positive duration")
        if (
            isinstance(self.allocated_trip_count, bool)
            or not isinstance(self.allocated_trip_count, int)
            or self.allocated_trip_count < 1
        ):
            raise ValueError("allocated_trip_count must be a positive integer")

    @property
    def duration_minutes(self) -> int:
        return self.end_minute - self.start_minute


def compiler_input_payload(value: CompilerInputV1) -> dict[str, object]:
    return {
        "profile": value.profile,
        "source_provenance": value.source_provenance,
        "route_id": value.route_id,
        "direction": value.direction,
        "allocation_candidate_id": value.allocation_candidate_id,
        "service_start_minute": value.service_start_minute,
        "service_end_minute": value.service_end_minute,
        "total_trip_count": value.total_trip_count,
        "demand_regime_fingerprint_assertion": (value.demand_regime_fingerprint_assertion),
        "trip_allocation_fingerprint_assertion": (value.trip_allocation_fingerprint_assertion),
        "demand_regimes": [
            {
                "regime_id": item.regime_id,
                "start_minute": item.start_minute,
                "end_minute": item.end_minute,
                "allocated_trip_count": item.allocated_trip_count,
            }
            for item in value.demand_regimes
        ],
    }


@dataclass(frozen=True, slots=True)
class CompilerInputV1:
    source_provenance: str
    route_id: str
    direction: str
    allocation_candidate_id: str
    service_start_minute: int
    service_end_minute: int
    total_trip_count: int
    demand_regime_fingerprint_assertion: str
    trip_allocation_fingerprint_assertion: str
    demand_regimes: tuple[CompilerDemandRegimeInputV1, ...]
    profile: str = COMPILER_INPUT_PROFILE_V1

    def __post_init__(self) -> None:
        if self.profile != COMPILER_INPUT_PROFILE_V1:
            raise ValueError("compiler input profile is invalid")
        if not all(
            value.strip()
            for value in (
                self.source_provenance,
                self.route_id,
                self.direction,
                self.allocation_candidate_id,
            )
        ):
            raise ValueError("compiler source/route/direction/candidate identity is required")
        if self.service_end_minute <= self.service_start_minute:
            raise ValueError("compiler service window must have a positive duration")
        if not self.demand_regimes:
            raise ValueError("compiler input requires at least one demand regime")
        if len({item.regime_id for item in self.demand_regimes}) != len(self.demand_regimes):
            raise ValueError("compiler demand-regime ids must be unique")
        if self.demand_regimes[0].start_minute != self.service_start_minute:
            raise ValueError("demand regimes must start at service_start_minute")
        if self.demand_regimes[-1].end_minute != self.service_end_minute:
            raise ValueError("demand regimes must end at service_end_minute")
        if any(
            left.end_minute != right.start_minute
            for left, right in zip(self.demand_regimes, self.demand_regimes[1:], strict=False)
        ):
            raise ValueError("demand regimes must partition the service window exactly")
        if sum(item.allocated_trip_count for item in self.demand_regimes) != (
            self.total_trip_count
        ):
            raise ValueError("demand-regime allocations must reproduce total_trip_count")
        for name, fingerprint in (
            ("demand", self.demand_regime_fingerprint_assertion),
            ("allocation", self.trip_allocation_fingerprint_assertion),
        ):
            if len(fingerprint) != 64 or any(
                character not in "0123456789ABCDEFabcdef" for character in fingerprint
            ):
                raise ValueError(f"{name} fingerprint assertion must be 64 hexadecimal chars")

    @property
    def input_fingerprint(self) -> str:
        return canonical_sha256(compiler_input_payload(self))


@dataclass(frozen=True, slots=True)
class DemandRegimeCompilationV1:
    regime_id: str
    start_minute: int
    end_minute: int
    duration_minutes: int
    allocated_trip_count: int
    nominal_headway: Fraction
    selected_integer_headway: int | None
    phase_offset_minutes: int
    first_departure_minute: int
    last_departure_minute: int
    leading_slack_minutes: int
    trailing_slack_minutes: int
    internal_headway_count: int
    quantization_error: Fraction
    actual_trip_count: int
    count_verified: bool


@dataclass(frozen=True, slots=True)
class ServiceRegimeV1:
    service_regime_id: str
    start_minute: int
    end_minute: int
    headway_minutes: int | None
    departure_count: int
    first_departure_minute: int
    last_departure_minute: int
    member_demand_regime_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompiledDepartureV1:
    trip_sequence: int
    departure_minute: int
    source_demand_regime_id: str
    service_regime_id: str


@dataclass(frozen=True, slots=True)
class CompiledScheduleCandidateV1:
    route_id: str
    direction: str
    source_allocation_candidate_id: str
    source_provenance: str
    source_compiler_input_fingerprint: str
    demand_regime_fingerprint_assertion: str
    trip_allocation_fingerprint_assertion: str
    service_start_minute: int
    service_end_minute: int
    total_trip_count: int
    demand_regime_compilations: tuple[DemandRegimeCompilationV1, ...]
    service_regimes: tuple[ServiceRegimeV1, ...]
    exact_departures: tuple[CompiledDepartureV1, ...]
    worst_gap_excess: Fraction | None
    total_gap_excess: Fraction | None
    total_quantization_error: Fraction | None
    service_regime_count: int
    transition_shape_error: Fraction | None
    edge_balance_error: int | None
    service_start_gap_minutes: int | None
    service_end_gap_minutes: int | None
    worst_transition_or_edge_gap_minutes: int | None
    minimum_actual_gap_minutes: int | None
    maximum_actual_gap_minutes: int | None
    median_actual_gap_minutes: Fraction | None
    status: CompilationStatusV1
    fleet_validation_status: FleetValidationStatusV1
    failure_evidence: tuple[str, ...] = ()


__all__ = [
    "COMPILER_INPUT_PROFILE_V1",
    "TEMPORARY_AUTHORITATIVE_BRIDGE_V1",
    "CompilationStatusV1",
    "CompiledDepartureV1",
    "CompiledScheduleCandidateV1",
    "CompilerDemandRegimeInputV1",
    "CompilerInputV1",
    "DemandRegimeCompilationV1",
    "FleetValidationStatusV1",
    "ServiceRegimeV1",
    "compiler_input_payload",
]

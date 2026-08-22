"""Temporary fixture adapter for the compiler-neutral :class:`CompilerInputV1`.

The compiler does not import this module.  A future real allocator adapter can
produce the same neutral DTO without changing compilation algorithms.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .serialization import canonical_sha256
from .uniform_headway_compiler_models import (
    TEMPORARY_AUTHORITATIVE_BRIDGE_V1,
    CompilerDemandRegimeInputV1,
    CompilerInputV1,
)


class CompilerInputAdapterV1(Protocol):
    def load(self) -> tuple[CompilerInputV1, ...]: ...


@dataclass(frozen=True, slots=True)
class BridgeScenarioBComparisonV1:
    route_id: str
    status: str
    reason: str
    regime_counts_by_direction: tuple[tuple[str, tuple[int, ...]], ...]


@dataclass(frozen=True, slots=True)
class TemporaryAuthoritativeBridgeBundleV1:
    fixture_path: Path
    fixture_fingerprint: str
    inputs: tuple[CompilerInputV1, ...]
    scenario_b_comparison: BridgeScenarioBComparisonV1


def _parse_hhmm(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"expected HH:MM, got {value!r}")
    hour, minute = (int(item) for item in parts)
    if hour < 0 or minute < 0 or minute >= 60:
        raise ValueError(f"invalid service minute {value!r}")
    return hour * 60 + minute


@dataclass(frozen=True, slots=True)
class TemporaryAuthoritativeAllocationFixtureAdapterV1:
    fixture_path: Path

    def load_bundle(self) -> TemporaryAuthoritativeBridgeBundleV1:
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if payload.get("bridge_profile") != TEMPORARY_AUTHORITATIVE_BRIDGE_V1:
            raise ValueError("temporary compiler bridge provenance profile is invalid")
        route_id = str(payload["route_id"])
        service_start = _parse_hhmm(payload["service_start"])
        service_end = _parse_hhmm(payload["service_end"])
        total = int(payload["direction_total_trip_count"])
        inputs: list[CompilerInputV1] = []
        b_counts: list[tuple[str, tuple[int, ...]]] = []
        for direction_payload in payload["directions"]:
            direction = str(direction_payload["direction"])
            regimes_payload = direction_payload["demand_regimes"]
            candidate_counts = direction_payload["allocation_candidates"]
            scenario_b_counts = tuple(
                int(value) for value in direction_payload["scenario_b_regime_counts"]
            )
            if len(scenario_b_counts) != len(regimes_payload) or sum(scenario_b_counts) != total:
                raise ValueError(
                    f"Route {route_id} {direction} Scenario B regime counts are invalid"
                )
            b_counts.append((direction, scenario_b_counts))
            for candidate_id, raw_counts in candidate_counts.items():
                counts = tuple(int(value) for value in raw_counts)
                if len(counts) != len(regimes_payload) or sum(counts) != total:
                    raise ValueError(
                        f"Route {route_id} {direction} {candidate_id} counts are invalid"
                    )
                regimes = tuple(
                    CompilerDemandRegimeInputV1(
                        regime_id=str(regime_payload["regime_id"]),
                        start_minute=_parse_hhmm(regime_payload["start"]),
                        end_minute=_parse_hhmm(regime_payload["end"]),
                        allocated_trip_count=count,
                    )
                    for regime_payload, count in zip(regimes_payload, counts, strict=True)
                )
                inputs.append(
                    CompilerInputV1(
                        source_provenance=TEMPORARY_AUTHORITATIVE_BRIDGE_V1,
                        route_id=route_id,
                        direction=direction,
                        allocation_candidate_id=str(candidate_id),
                        service_start_minute=service_start,
                        service_end_minute=service_end,
                        total_trip_count=total,
                        demand_regime_fingerprint_assertion=str(
                            payload["demand_regime_fingerprint_assertion"]
                        ),
                        trip_allocation_fingerprint_assertion=str(
                            payload["trip_allocation_fingerprint_assertion"]
                        ),
                        demand_regimes=regimes,
                    )
                )
        comparison = payload["scenario_b_exact_timetable"]
        return TemporaryAuthoritativeBridgeBundleV1(
            fixture_path=self.fixture_path,
            fixture_fingerprint=canonical_sha256(payload),
            inputs=tuple(
                sorted(
                    inputs,
                    key=lambda item: (
                        item.route_id,
                        item.direction,
                        item.allocation_candidate_id,
                    ),
                )
            ),
            scenario_b_comparison=BridgeScenarioBComparisonV1(
                route_id=route_id,
                status=str(comparison["status"]),
                reason=str(comparison["reason"]),
                regime_counts_by_direction=tuple(sorted(b_counts)),
            ),
        )

    def load(self) -> tuple[CompilerInputV1, ...]:
        return self.load_bundle().inputs


__all__ = [
    "BridgeScenarioBComparisonV1",
    "CompilerInputAdapterV1",
    "TemporaryAuthoritativeAllocationFixtureAdapterV1",
    "TemporaryAuthoritativeBridgeBundleV1",
]

"""Current production one-trip-TE post-search timetable selection policy.

V1 remains the historical strict-SSE-first selector.  V2 uses SSE and trip-
equivalent error (TE) only to establish a unique common demand-fit anchor,
then permits rhythm and fleet selection inside a fixed one-pair-trip TE band.

A 1.0 trip-equivalent concession is an operational service-allocation
quantum: equivalent service mass displaced across demand buckets.  It is not
a fractional physical trip, a timetable-edit count, a trip movement
instruction, or a replacement for SSE.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Any

from .operational_selection_policy import (
    NUMERICAL_EPSILON,
    OperationalSelectionCandidateV1,
    build_operational_selection_candidate_v1,
)

OPERATIONAL_SELECTION_PROFILE_V2 = "one_trip_te_materiality_operational_selector_v2"
TE_MATERIALITY_BAND_TRIPS_V2 = 1.0
PRIORITY_ORDER_V2 = (
    "HARD_OPERATIONAL_FEASIBILITY",
    "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
    "COMMON_SSE_TE_DEMAND_FIT_ANCHOR",
    "ONE_TRIP_TE_MATERIALITY_ENVELOPE",
    "RHYTHM_SIMPLICITY",
    "FLEET_EFFICIENCY",
)


@dataclass(frozen=True, slots=True)
class OperationalSelectionPolicyV2:
    profile: str = OPERATIONAL_SELECTION_PROFILE_V2
    priority_order: tuple[str, ...] = PRIORITY_ORDER_V2
    numerical_epsilon: float = NUMERICAL_EPSILON
    te_materiality_band_trips: float = TE_MATERIALITY_BAND_TRIPS_V2


@dataclass(frozen=True, slots=True)
class OperationalSelectionCandidateV2:
    v1_candidate: OperationalSelectionCandidateV1
    outbound_trip_equivalent_error: float
    inbound_trip_equivalent_error: float
    pair_trip_equivalent_error: float
    diagnostics: Mapping[str, Any]

    def __getattr__(self, name: str) -> Any:
        """Expose the frozen V1 feasibility and operational metrics unchanged."""

        return getattr(self.v1_candidate, name)


@dataclass(frozen=True, slots=True)
class OperationalSelectionRejectionV2:
    fingerprint: str
    stage: str
    reason: str
    relevant_metric_values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class OperationalSelectionStageTraceV2:
    stage: str
    input_count: int
    retained_count: int
    retained_fingerprints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationalSelectionResultV2:
    profile: str
    route_id: str
    candidate_universe_count: int
    hard_feasible_count: int
    passenger_access_safe_count: int
    sse_best_count: int
    te_best_count: int
    common_anchor_fingerprint: str | None
    common_anchor_sse: float | None
    common_anchor_te: float | None
    materiality_band_trips: float
    materiality_set_count: int
    best_rhythm_count: int
    best_fleet_efficiency_count: int
    selected_pair_fingerprint: str | None
    selected_stage: str | None
    classification: str
    stage_trace: tuple[OperationalSelectionStageTraceV2, ...]
    rejected_candidates: tuple[OperationalSelectionRejectionV2, ...]
    selected_delta_te_from_anchor: float | None
    selected_is_anchor: bool | None
    top_anchor_concordant: bool
    pair_fingerprint_is_quality_objective: bool = False


DEFAULT_OPERATIONAL_SELECTION_POLICY_V2 = OperationalSelectionPolicyV2()


def directional_trip_equivalent_error_v2(metrics: Any, *, total_trips: int) -> float:
    """Return the directional service-allocation error in trip equivalents."""

    counts = tuple(metrics.bucket_service_counts)
    demand_shares = tuple(metrics.bucket_demand_shares)
    service_shares = tuple(metrics.bucket_service_shares)
    if not counts or len(counts) != len(demand_shares) or len(counts) != len(service_shares):
        raise ValueError("TE vectors must be non-empty and equal length")
    if not isinstance(total_trips, int) or isinstance(total_trips, bool) or total_trips <= 0:
        raise ValueError("exact directional trip count must be a positive integer")
    if any(not isinstance(count, int) or isinstance(count, bool) or count < 0 for count in counts):
        raise ValueError("bucket service counts must be non-negative integers")
    if sum(counts) != total_trips:
        raise ValueError("bucket service counts must equal the exact directional trip count")
    if any(not isfinite(share) for share in (*demand_shares, *service_shares)):
        raise ValueError("bucket demand and service shares must be finite")
    if abs(sum(demand_shares) - 1.0) > NUMERICAL_EPSILON:
        raise ValueError("bucket demand shares must sum to one")
    if abs(sum(service_shares) - 1.0) > NUMERICAL_EPSILON:
        raise ValueError("bucket service shares must sum to one")
    if any(
        abs(service_share - count / total_trips) > NUMERICAL_EPSILON
        for count, service_share in zip(counts, service_shares, strict=True)
    ):
        raise ValueError("bucket service shares must correspond to counts / total trips")
    directional_tv = 0.5 * sum(
        abs(service_share - demand_share)
        for service_share, demand_share in zip(
            service_shares,
            demand_shares,
            strict=True,
        )
    )
    return total_trips * directional_tv


def build_operational_selection_candidate_v2(
    *, context: Any, candidate: Any
) -> OperationalSelectionCandidateV2:
    """Reuse V1 feasibility authority and enrich it with exact production TE."""

    v1_candidate = build_operational_selection_candidate_v1(context=context, candidate=candidate)
    outbound_te = directional_trip_equivalent_error_v2(
        candidate.outbound.metrics,
        total_trips=candidate.outbound.state.total_trips,
    )
    inbound_te = directional_trip_equivalent_error_v2(
        candidate.inbound.metrics,
        total_trips=candidate.inbound.state.total_trips,
    )
    return OperationalSelectionCandidateV2(
        v1_candidate=v1_candidate,
        outbound_trip_equivalent_error=outbound_te,
        inbound_trip_equivalent_error=inbound_te,
        pair_trip_equivalent_error=outbound_te + inbound_te,
        diagnostics={
            "te_authority": "ActualServiceMetricsV1",
            "outbound_total_trips": candidate.outbound.state.total_trips,
            "inbound_total_trips": candidate.inbound.state.total_trips,
        },
    )


def _rhythm_tuple(candidate: OperationalSelectionCandidateV2) -> tuple[int, int, int, int]:
    return (
        candidate.total_directional_sustained_headway_level_count,
        candidate.actual_service_regime_count,
        candidate.total_directional_effective_palette_count,
        candidate.total_single_gap_regime_count,
    )


def _fleet_tuple(candidate: OperationalSelectionCandidateV2) -> tuple[int, int, int]:
    return (
        candidate.fleet_required,
        candidate.total_excess_terminal_wait,
        candidate.max_excess_terminal_wait,
    )


def select_operational_timetable_v2(
    *,
    context: Any,
    candidates: Sequence[Any],
    policy: OperationalSelectionPolicyV2 = DEFAULT_OPERATIONAL_SELECTION_POLICY_V2,
) -> OperationalSelectionResultV2:
    """Project and select from a completed immutable coordinator Pareto frontier."""

    from bus_schedule_engine import service_plan_coordinator as coordinator

    snapshots = tuple(
        build_operational_selection_candidate_v2(context=context, candidate=item)
        for item in candidates
    )
    scenario_b_access = {
        direction: coordinator.expected_passenger_wait_metrics_v1(
            context.scenario_b_departures[direction], context.demand_buckets[direction]
        )[1]
        for direction in ("outbound", "inbound")
    }
    return select_operational_candidates_v2(
        route_id=context.route_id,
        candidates=snapshots,
        scenario_b_directional_maximum_wait_minutes=scenario_b_access,
        policy=policy,
    )


def select_operational_candidates_v2(
    *,
    route_id: str,
    candidates: Sequence[OperationalSelectionCandidateV2],
    scenario_b_directional_maximum_wait_minutes: Mapping[str, float],
    policy: OperationalSelectionPolicyV2 = DEFAULT_OPERATIONAL_SELECTION_POLICY_V2,
) -> OperationalSelectionResultV2:
    """Select one candidate using the frozen V2 policy, failing closed on anchor ambiguity."""

    if set(scenario_b_directional_maximum_wait_minutes) != {"outbound", "inbound"}:
        raise ValueError("Scenario B maximum access authority must be directional")

    ordered = tuple(sorted(candidates, key=lambda item: item.fingerprint))
    feasible = tuple(item for item in ordered if item.hard_feasible)
    rejected: list[OperationalSelectionRejectionV2] = [
        OperationalSelectionRejectionV2(
            fingerprint=item.fingerprint,
            stage="HARD_OPERATIONAL_FEASIBILITY",
            reason=item.hard_feasibility_reasons[0] if item.hard_feasibility_reasons else "FAILED",
            relevant_metric_values=item.hard_feasibility_metrics,
        )
        for item in ordered
        if not item.hard_feasible
    ]
    traces = [
        OperationalSelectionStageTraceV2(
            stage="HARD_OPERATIONAL_FEASIBILITY",
            input_count=len(ordered),
            retained_count=len(feasible),
            retained_fingerprints=tuple(item.fingerprint for item in feasible),
        )
    ]

    access_safe: list[OperationalSelectionCandidateV2] = []
    for item in feasible:
        failed = tuple(
            direction
            for direction, value in (
                ("outbound", item.outbound_maximum_bucket_expected_wait_minutes),
                ("inbound", item.inbound_maximum_bucket_expected_wait_minutes),
            )
            if value
            > float(scenario_b_directional_maximum_wait_minutes[direction])
            + policy.numerical_epsilon
        )
        if not failed:
            access_safe.append(item)
            continue
        reason = (
            f"{failed[0].upper()}_MAX_ACCESS_REGRESSION"
            if len(failed) == 1
            else "BOTH_DIRECTIONS_MAX_ACCESS_REGRESSION"
        )
        rejected.append(
            OperationalSelectionRejectionV2(
                fingerprint=item.fingerprint,
                stage="SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
                reason=reason,
                relevant_metric_values={
                    "candidate_outbound_maximum_bucket_expected_wait_minutes": (
                        item.outbound_maximum_bucket_expected_wait_minutes
                    ),
                    "scenario_b_outbound_maximum_bucket_expected_wait_minutes": float(
                        scenario_b_directional_maximum_wait_minutes["outbound"]
                    ),
                    "candidate_inbound_maximum_bucket_expected_wait_minutes": (
                        item.inbound_maximum_bucket_expected_wait_minutes
                    ),
                    "scenario_b_inbound_maximum_bucket_expected_wait_minutes": float(
                        scenario_b_directional_maximum_wait_minutes["inbound"]
                    ),
                },
            )
        )
    access_safe_tuple = tuple(access_safe)
    traces.append(
        OperationalSelectionStageTraceV2(
            stage="SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
            input_count=len(feasible),
            retained_count=len(access_safe_tuple),
            retained_fingerprints=tuple(item.fingerprint for item in access_safe_tuple),
        )
    )

    sse_best = ()
    te_best = ()
    if access_safe_tuple:
        best_sse = min(item.observed_demand_mismatch for item in access_safe_tuple)
        best_te = min(item.pair_trip_equivalent_error for item in access_safe_tuple)
        sse_best = tuple(
            item
            for item in access_safe_tuple
            if item.observed_demand_mismatch <= best_sse + policy.numerical_epsilon
        )
        te_best = tuple(
            item
            for item in access_safe_tuple
            if item.pair_trip_equivalent_error <= best_te + policy.numerical_epsilon
        )

    anchor = (
        sse_best[0]
        if len(sse_best) == len(te_best) == 1 and sse_best[0].fingerprint == te_best[0].fingerprint
        else None
    )
    traces.append(
        OperationalSelectionStageTraceV2(
            stage="COMMON_SSE_TE_DEMAND_FIT_ANCHOR",
            input_count=len(access_safe_tuple),
            retained_count=len(access_safe_tuple) if anchor is not None else 0,
            retained_fingerprints=(
                tuple(item.fingerprint for item in access_safe_tuple) if anchor is not None else ()
            ),
        )
    )

    if not feasible:
        classification = "NO_HARD_FEASIBLE_CANDIDATE"
    elif not access_safe_tuple:
        classification = "ACCESS_GUARDRAIL_TOO_RESTRICTIVE"
    elif len(sse_best) != 1 or len(te_best) != 1:
        classification = "DEMAND_FIT_ANCHOR_NOT_UNIQUE"
    elif anchor is None:
        classification = "DEMAND_FIT_ANCHOR_CONFLICT"
    else:
        classification = ""

    materiality: tuple[OperationalSelectionCandidateV2, ...] = ()
    best_rhythm: tuple[OperationalSelectionCandidateV2, ...] = ()
    best_fleet: tuple[OperationalSelectionCandidateV2, ...] = ()
    selected: OperationalSelectionCandidateV2 | None = None
    selected_stage: str | None = None
    if anchor is not None:
        deltas = {
            item.fingerprint: item.pair_trip_equivalent_error - anchor.pair_trip_equivalent_error
            for item in access_safe_tuple
        }
        if any(delta < -policy.numerical_epsilon for delta in deltas.values()):
            classification = "TE_ANCHOR_INCONSISTENCY"
        else:
            materiality = tuple(
                item
                for item in access_safe_tuple
                if deltas[item.fingerprint]
                <= policy.te_materiality_band_trips + policy.numerical_epsilon
            )
            for item in access_safe_tuple:
                if item not in materiality:
                    rejected.append(
                        OperationalSelectionRejectionV2(
                            fingerprint=item.fingerprint,
                            stage="ONE_TRIP_TE_MATERIALITY_ENVELOPE",
                            reason="OUTSIDE_ONE_TRIP_TE_MATERIALITY_ENVELOPE",
                            relevant_metric_values={
                                "candidate_pair_trip_equivalent_error": (
                                    item.pair_trip_equivalent_error
                                ),
                                "anchor_pair_trip_equivalent_error": (
                                    anchor.pair_trip_equivalent_error
                                ),
                                "delta_trip_equivalent_error": deltas[item.fingerprint],
                                "materiality_band_trips": policy.te_materiality_band_trips,
                            },
                        )
                    )
            best_rhythm_value = min(_rhythm_tuple(item) for item in materiality)
            best_rhythm = tuple(
                item for item in materiality if _rhythm_tuple(item) == best_rhythm_value
            )
            for item in materiality:
                if item not in best_rhythm:
                    rejected.append(
                        OperationalSelectionRejectionV2(
                            fingerprint=item.fingerprint,
                            stage="RHYTHM_SIMPLICITY",
                            reason="NOT_IN_BEST_RHYTHM_SET",
                            relevant_metric_values={
                                "rhythm_simplicity_tuple": _rhythm_tuple(item),
                                "best_rhythm_simplicity_tuple": best_rhythm_value,
                            },
                        )
                    )
            best_fleet_value = min(_fleet_tuple(item) for item in best_rhythm)
            best_fleet = tuple(
                item for item in best_rhythm if _fleet_tuple(item) == best_fleet_value
            )
            for item in best_rhythm:
                if item not in best_fleet:
                    rejected.append(
                        OperationalSelectionRejectionV2(
                            fingerprint=item.fingerprint,
                            stage="FLEET_EFFICIENCY",
                            reason="NOT_IN_BEST_FLEET_EFFICIENCY_SET",
                            relevant_metric_values={
                                "fleet_efficiency_tuple": _fleet_tuple(item),
                                "best_fleet_efficiency_tuple": best_fleet_value,
                            },
                        )
                    )
            selected = min(best_fleet, key=lambda item: item.fingerprint)
            if len(best_fleet) > 1:
                classification = "METRICALLY_EQUIVALENT_DETERMINISTIC_TIEBREAK"
                selected_stage = "FINAL_DETERMINISTIC_TIEBREAK"
                for item in best_fleet:
                    if item is not selected:
                        rejected.append(
                            OperationalSelectionRejectionV2(
                                fingerprint=item.fingerprint,
                                stage="FINAL_DETERMINISTIC_TIEBREAK",
                                reason="LEXICOGRAPHICALLY_LARGER_FINGERPRINT",
                                relevant_metric_values={
                                    "selected_pair_fingerprint": selected.fingerprint,
                                    "pair_fingerprint_is_quality_objective": False,
                                },
                            )
                        )
            elif selected.fingerprint == anchor.fingerprint:
                classification = "ONE_TRIP_MATERIALITY_SELECTS_ANCHOR"
            else:
                classification = "ONE_TRIP_MATERIALITY_SELECTS_SIMPLER_ALTERNATIVE"
            if len(best_fleet) == 1:
                if len(materiality) == 1:
                    selected_stage = "ONE_TRIP_TE_MATERIALITY_ENVELOPE"
                elif len(best_rhythm) == 1:
                    selected_stage = "RHYTHM_SIMPLICITY"
                else:
                    selected_stage = "FLEET_EFFICIENCY"

    if anchor is not None:
        traces.extend(
            (
                OperationalSelectionStageTraceV2(
                    stage="ONE_TRIP_TE_MATERIALITY_ENVELOPE",
                    input_count=len(access_safe_tuple),
                    retained_count=len(materiality),
                    retained_fingerprints=tuple(item.fingerprint for item in materiality),
                ),
                OperationalSelectionStageTraceV2(
                    stage="RHYTHM_SIMPLICITY",
                    input_count=len(materiality),
                    retained_count=len(best_rhythm),
                    retained_fingerprints=tuple(item.fingerprint for item in best_rhythm),
                ),
                OperationalSelectionStageTraceV2(
                    stage="FLEET_EFFICIENCY",
                    input_count=len(best_rhythm),
                    retained_count=len(best_fleet),
                    retained_fingerprints=tuple(item.fingerprint for item in best_fleet),
                ),
            )
        )

    return OperationalSelectionResultV2(
        profile=policy.profile,
        route_id=route_id,
        candidate_universe_count=len(ordered),
        hard_feasible_count=len(feasible),
        passenger_access_safe_count=len(access_safe_tuple),
        sse_best_count=len(sse_best),
        te_best_count=len(te_best),
        common_anchor_fingerprint=anchor.fingerprint if anchor is not None else None,
        common_anchor_sse=anchor.observed_demand_mismatch if anchor is not None else None,
        common_anchor_te=anchor.pair_trip_equivalent_error if anchor is not None else None,
        materiality_band_trips=policy.te_materiality_band_trips,
        materiality_set_count=len(materiality),
        best_rhythm_count=len(best_rhythm),
        best_fleet_efficiency_count=len(best_fleet),
        selected_pair_fingerprint=selected.fingerprint if selected is not None else None,
        selected_stage=selected_stage,
        classification=classification,
        stage_trace=tuple(traces),
        rejected_candidates=tuple(rejected),
        selected_delta_te_from_anchor=(
            selected.pair_trip_equivalent_error - anchor.pair_trip_equivalent_error
            if selected is not None and anchor is not None
            else None
        ),
        selected_is_anchor=(
            selected.fingerprint == anchor.fingerprint
            if selected is not None and anchor is not None
            else None
        ),
        top_anchor_concordant=anchor is not None,
    )

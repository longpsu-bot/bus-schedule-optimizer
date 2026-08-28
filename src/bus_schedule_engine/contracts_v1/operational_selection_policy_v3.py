"""Legacy-calibrated phase-robust operational timetable selector V3."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Any

from .operational_selection_policy import NUMERICAL_EPSILON
from .operational_selection_policy_v2 import (
    OperationalSelectionCandidateV2,
    build_operational_selection_candidate_v2,
)

OPERATIONAL_SELECTION_PROFILE_V3 = "legacy_calibrated_continuous_exposure_operational_selector_v3"
LEGACY_TE_CALIBRATION_BAND_TRIPS_V3 = 1.0
PRIMARY_MATERIALITY_METRIC_V3 = "continuous_exposure_equivalent"
PRIORITY_ORDER_V3 = (
    "HARD_OPERATIONAL_FEASIBILITY",
    "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
    "COMMON_SSE_TE_DEMAND_FIT_ANCHOR",
    "LEGACY_ONE_TRIP_TE_SEMANTIC_CALIBRATION",
    "ROUTE_LOCAL_CONTINUOUS_EXPOSURE_MATERIALITY_ENVELOPE",
    "RHYTHM_SIMPLICITY",
    "FLEET_EFFICIENCY",
)


@dataclass(frozen=True, slots=True)
class OperationalSelectionPolicyV3:
    profile: str = OPERATIONAL_SELECTION_PROFILE_V3
    priority_order: tuple[str, ...] = PRIORITY_ORDER_V3
    numerical_epsilon: float = NUMERICAL_EPSILON
    legacy_te_calibration_band_trips: float = LEGACY_TE_CALIBRATION_BAND_TRIPS_V3
    primary_materiality_metric: str = PRIMARY_MATERIALITY_METRIC_V3


DEFAULT_OPERATIONAL_SELECTION_POLICY_V3 = OperationalSelectionPolicyV3()


@dataclass(frozen=True, slots=True)
class OperationalSelectionCandidateV3:
    v2_candidate: OperationalSelectionCandidateV2
    outbound_continuous_exposure_equivalent: float
    inbound_continuous_exposure_equivalent: float
    pair_continuous_exposure_equivalent: float
    diagnostics: Mapping[str, Any]

    def __getattr__(self, name: str) -> Any:
        """Expose unchanged V1 feasibility and V2 production demand-fit metrics."""

        return getattr(self.v2_candidate, name)


@dataclass(frozen=True, slots=True)
class OperationalSelectionRejectionV3:
    fingerprint: str
    stage: str
    reason: str
    relevant_metric_values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class OperationalSelectionStageTraceV3:
    stage: str
    input_count: int
    retained_count: int
    retained_fingerprints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationalSelectionResultV3:
    profile: str
    priority_order: tuple[str, ...]
    route_id: str
    candidate_universe_count: int
    hard_feasible_count: int
    passenger_access_safe_count: int
    sse_best_count: int
    te_best_count: int
    common_anchor_fingerprint: str | None
    common_anchor_sse: float | None
    common_anchor_te: float | None
    anchor_continuous_exposure_equivalent: float | None
    legacy_te_calibration_band_trips: float
    legacy_calibration_set_count: int
    legacy_calibration_fingerprints: tuple[str, ...]
    continuous_preservation_bound: float | None
    phase_robust_materiality_set_count: int
    phase_robust_materiality_fingerprints: tuple[str, ...]
    best_rhythm_count: int
    best_fleet_efficiency_count: int
    selected_pair_fingerprint: str | None
    selected_stage: str | None
    selected_delta_continuous_from_anchor: float | None
    selected_delta_te_from_anchor: float | None
    selected_inside_legacy_te_calibration_set: bool | None
    selected_is_anchor: bool | None
    classification: str
    stage_trace: tuple[OperationalSelectionStageTraceV3, ...]
    rejected_candidates: tuple[OperationalSelectionRejectionV3, ...]
    pair_fingerprint_is_quality_objective: bool = False


def _validated_continuous_inputs_v3(
    departures: Sequence[int | float], buckets: Sequence[Mapping[str, Any]]
) -> tuple[tuple[float, ...], tuple[tuple[float, float, float], ...]]:
    exact_departures = tuple(float(value) for value in departures)
    if len(exact_departures) < 2 or any(not isfinite(value) for value in exact_departures):
        raise ValueError("at least two finite exact departures are required")
    if any(
        left >= right for left, right in zip(exact_departures, exact_departures[1:], strict=False)
    ):
        raise ValueError("exact departures must be strictly increasing")

    normalized: list[tuple[float, float, float]] = []
    for bucket in buckets:
        start = float(bucket["start"])
        end = float(bucket["end"])
        demand = float(bucket["observed_demand"])
        if not all(isfinite(value) for value in (start, end, demand)):
            raise ValueError("demand support values must be finite")
        if start >= end or demand < 0:
            raise ValueError("demand support buckets must have positive width and demand >= 0")
        normalized.append((start, end, demand))
    if not normalized:
        raise ValueError("demand support must not be empty")
    if any(left[1] != right[0] for left, right in zip(normalized, normalized[1:], strict=False)):
        raise ValueError("demand support must be ordered, gap-free, and non-overlapping")
    if exact_departures[0] < normalized[0][0] or exact_departures[-1] > normalized[-1][1]:
        raise ValueError("demand support must cover the complete service operating span")
    if sum(bucket[2] for bucket in normalized) <= 0:
        raise ValueError("total observed demand must be positive")
    return exact_departures, tuple(normalized)


def continuous_exposure_metrics_v3(
    departures: Sequence[int | float], buckets: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    """Exactly integrate phase-robust demand and interdeparture exposure densities."""

    exact_departures, demand_buckets = _validated_continuous_inputs_v3(departures, buckets)
    total_demand = sum(bucket[2] for bucket in demand_buckets)
    demand_shares = tuple(bucket[2] / total_demand for bucket in demand_buckets)
    domain_start = demand_buckets[0][0]
    domain_end = demand_buckets[-1][1]
    breakpoints = tuple(
        sorted(
            {
                domain_start,
                domain_end,
                *exact_departures,
                *(bucket[0] for bucket in demand_buckets),
                *(bucket[1] for bucket in demand_buckets),
            }
        )
    )
    exposure_units = float(len(exact_departures) - 1)
    absolute_integral = 0.0
    demand_integral = 0.0
    service_integral = 0.0
    for left, right in zip(breakpoints, breakpoints[1:], strict=False):
        width = right - left
        demand_index = next(
            index for index, bucket in enumerate(demand_buckets) if bucket[0] <= left < bucket[1]
        )
        demand_density = demand_shares[demand_index] / (
            demand_buckets[demand_index][1] - demand_buckets[demand_index][0]
        )
        unnormalized_service_density = 0.0
        for departure_left, departure_right in zip(
            exact_departures, exact_departures[1:], strict=False
        ):
            if departure_left <= left < departure_right:
                unnormalized_service_density = 1.0 / (departure_right - departure_left)
                break
        service_density = unnormalized_service_density / exposure_units
        absolute_integral += width * abs(service_density - demand_density)
        demand_integral += width * demand_density * total_demand
        service_integral += width * unnormalized_service_density
    tv = 0.5 * absolute_integral
    return {
        "analysis_domain": (domain_start, domain_end),
        "breakpoints": breakpoints,
        "total_demand": total_demand,
        "demand_integral": demand_integral,
        "service_exposure_integral": service_integral,
        "tv": tv,
        "equivalent": len(exact_departures) * tv,
    }


def _demand_bucket_payloads_v3(buckets: Sequence[Any]) -> tuple[Mapping[str, float], ...]:
    return tuple(
        {
            "start": float(bucket.start),
            "end": float(bucket.end),
            "observed_demand": float(bucket.observed_demand),
        }
        for bucket in buckets
    )


def build_operational_selection_candidate_v3(
    *, context: Any, candidate: Any
) -> OperationalSelectionCandidateV3:
    """Reuse V2 projection and add the exact production-side continuous metric."""

    v2_candidate = build_operational_selection_candidate_v2(context=context, candidate=candidate)
    equivalents: dict[str, float] = {}
    for direction in ("outbound", "inbound"):
        directional = getattr(candidate, direction)
        departures = directional.compile_variant.compilation.exact_departures
        buckets = _demand_bucket_payloads_v3(context.demand_buckets[direction])
        equivalents[direction] = float(
            continuous_exposure_metrics_v3(departures, buckets)["equivalent"]
        )
    return OperationalSelectionCandidateV3(
        v2_candidate=v2_candidate,
        outbound_continuous_exposure_equivalent=equivalents["outbound"],
        inbound_continuous_exposure_equivalent=equivalents["inbound"],
        pair_continuous_exposure_equivalent=(equivalents["outbound"] + equivalents["inbound"]),
        diagnostics={
            "continuous_exposure_authority": "EXACT_INTERDEPARTURE_EXPOSURE_INTEGRAL_V3",
            "primary_materiality_metric": PRIMARY_MATERIALITY_METRIC_V3,
        },
    )


def _rhythm_tuple_v3(candidate: Any) -> tuple[int, int, int, int]:
    return (
        candidate.total_directional_sustained_headway_level_count,
        candidate.actual_service_regime_count,
        candidate.total_directional_effective_palette_count,
        candidate.total_single_gap_regime_count,
    )


def _fleet_tuple_v3(candidate: Any) -> tuple[int, int, int]:
    return (
        candidate.fleet_required,
        candidate.total_excess_terminal_wait,
        candidate.max_excess_terminal_wait,
    )


def select_operational_timetable_v3(
    *,
    context: Any,
    candidates: Sequence[Any],
    policy: OperationalSelectionPolicyV3 = DEFAULT_OPERATIONAL_SELECTION_POLICY_V3,
) -> OperationalSelectionResultV3:
    """Project an existing completed frontier without changing production search."""

    from bus_schedule_engine import service_plan_coordinator as coordinator

    snapshots = tuple(
        build_operational_selection_candidate_v3(context=context, candidate=item)
        for item in candidates
    )
    scenario_b_access = {
        direction: coordinator.expected_passenger_wait_metrics_v1(
            context.scenario_b_departures[direction], context.demand_buckets[direction]
        )[1]
        for direction in ("outbound", "inbound")
    }
    return select_operational_candidates_v3(
        route_id=context.route_id,
        candidates=snapshots,
        scenario_b_directional_maximum_wait_minutes=scenario_b_access,
        policy=policy,
    )


def select_operational_candidates_v3(
    *,
    route_id: str,
    candidates: Sequence[OperationalSelectionCandidateV3],
    scenario_b_directional_maximum_wait_minutes: Mapping[str, float],
    policy: OperationalSelectionPolicyV3 = DEFAULT_OPERATIONAL_SELECTION_POLICY_V3,
) -> OperationalSelectionResultV3:
    """Apply legacy-calibrated continuous materiality and the frozen domain hierarchy."""

    if set(scenario_b_directional_maximum_wait_minutes) != {"outbound", "inbound"}:
        raise ValueError("Scenario B maximum access authority must be directional")
    if any(
        not isfinite(float(value)) for value in scenario_b_directional_maximum_wait_minutes.values()
    ):
        raise ValueError("Scenario B maximum access authority must be finite")

    ordered = tuple(sorted(candidates, key=lambda item: item.fingerprint))
    feasible = tuple(item for item in ordered if item.hard_feasible)
    rejected: list[OperationalSelectionRejectionV3] = [
        OperationalSelectionRejectionV3(
            fingerprint=item.fingerprint,
            stage="HARD_OPERATIONAL_FEASIBILITY",
            reason=item.hard_feasibility_reasons[0] if item.hard_feasibility_reasons else "FAILED",
            relevant_metric_values=item.hard_feasibility_metrics,
        )
        for item in ordered
        if not item.hard_feasible
    ]
    traces = [
        OperationalSelectionStageTraceV3(
            stage="HARD_OPERATIONAL_FEASIBILITY",
            input_count=len(ordered),
            retained_count=len(feasible),
            retained_fingerprints=tuple(item.fingerprint for item in feasible),
        )
    ]

    access_safe: list[OperationalSelectionCandidateV3] = []
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
        rejected.append(
            OperationalSelectionRejectionV3(
                fingerprint=item.fingerprint,
                stage="SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
                reason=(
                    f"{failed[0].upper()}_MAX_ACCESS_REGRESSION"
                    if len(failed) == 1
                    else "BOTH_DIRECTIONS_MAX_ACCESS_REGRESSION"
                ),
                relevant_metric_values={
                    "candidate_outbound_maximum_bucket_expected_wait_minutes": (
                        item.outbound_maximum_bucket_expected_wait_minutes
                    ),
                    "candidate_inbound_maximum_bucket_expected_wait_minutes": (
                        item.inbound_maximum_bucket_expected_wait_minutes
                    ),
                    "scenario_b_outbound_maximum_bucket_expected_wait_minutes": float(
                        scenario_b_directional_maximum_wait_minutes["outbound"]
                    ),
                    "scenario_b_inbound_maximum_bucket_expected_wait_minutes": float(
                        scenario_b_directional_maximum_wait_minutes["inbound"]
                    ),
                },
            )
        )
    access_safe_tuple = tuple(access_safe)
    traces.append(
        OperationalSelectionStageTraceV3(
            stage="SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
            input_count=len(feasible),
            retained_count=len(access_safe_tuple),
            retained_fingerprints=tuple(item.fingerprint for item in access_safe_tuple),
        )
    )

    invalid_continuous = tuple(
        item
        for item in access_safe_tuple
        if (
            any(
                not isfinite(float(value))
                for value in (
                    item.outbound_continuous_exposure_equivalent,
                    item.inbound_continuous_exposure_equivalent,
                    item.pair_continuous_exposure_equivalent,
                )
            )
            or abs(
                item.outbound_continuous_exposure_equivalent
                + item.inbound_continuous_exposure_equivalent
                - item.pair_continuous_exposure_equivalent
            )
            > policy.numerical_epsilon
        )
    )
    sse_best: tuple[OperationalSelectionCandidateV3, ...] = ()
    te_best: tuple[OperationalSelectionCandidateV3, ...] = ()
    if access_safe_tuple and not invalid_continuous:
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
        OperationalSelectionStageTraceV3(
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
    elif invalid_continuous:
        classification = "INVALID_CONTINUOUS_EXPOSURE_METRIC"
        for item in invalid_continuous:
            rejected.append(
                OperationalSelectionRejectionV3(
                    fingerprint=item.fingerprint,
                    stage="ROUTE_LOCAL_CONTINUOUS_EXPOSURE_MATERIALITY_ENVELOPE",
                    reason="NON_FINITE_CONTINUOUS_EXPOSURE_EQUIVALENT",
                    relevant_metric_values={
                        "outbound_continuous_exposure_equivalent": (
                            item.outbound_continuous_exposure_equivalent
                        ),
                        "inbound_continuous_exposure_equivalent": (
                            item.inbound_continuous_exposure_equivalent
                        ),
                        "pair_continuous_exposure_equivalent": (
                            item.pair_continuous_exposure_equivalent
                        ),
                    },
                )
            )
    elif len(sse_best) != 1 or len(te_best) != 1:
        classification = "DEMAND_FIT_ANCHOR_NOT_UNIQUE"
    elif anchor is None:
        classification = "DEMAND_FIT_ANCHOR_CONFLICT"
    else:
        classification = ""

    calibration: tuple[OperationalSelectionCandidateV3, ...] = ()
    materiality: tuple[OperationalSelectionCandidateV3, ...] = ()
    best_rhythm: tuple[OperationalSelectionCandidateV3, ...] = ()
    best_fleet: tuple[OperationalSelectionCandidateV3, ...] = ()
    bound: float | None = None
    selected: OperationalSelectionCandidateV3 | None = None
    selected_stage: str | None = None
    te_deltas: dict[str, float] = {}
    continuous_deltas: dict[str, float] = {}
    if anchor is not None:
        te_deltas = {
            item.fingerprint: item.pair_trip_equivalent_error - anchor.pair_trip_equivalent_error
            for item in access_safe_tuple
        }
        continuous_deltas = {
            item.fingerprint: item.pair_continuous_exposure_equivalent
            - anchor.pair_continuous_exposure_equivalent
            for item in access_safe_tuple
        }
        calibration = tuple(
            item
            for item in access_safe_tuple
            if te_deltas[item.fingerprint]
            <= policy.legacy_te_calibration_band_trips + policy.numerical_epsilon
        )
        if not any(item.fingerprint == anchor.fingerprint for item in calibration):
            classification = "LEGACY_CALIBRATION_ANCHOR_MISSING"
        else:
            bound = max(continuous_deltas[item.fingerprint] for item in calibration)
            if any(delta < -policy.numerical_epsilon for delta in continuous_deltas.values()):
                classification = "PHASE_ROBUST_REFERENCE_CONFLICT"
                for item in access_safe_tuple:
                    if continuous_deltas[item.fingerprint] < -policy.numerical_epsilon:
                        rejected.append(
                            OperationalSelectionRejectionV3(
                                fingerprint=item.fingerprint,
                                stage="ROUTE_LOCAL_CONTINUOUS_EXPOSURE_MATERIALITY_ENVELOPE",
                                reason="BETTER_THAN_COMMON_ANCHOR_UNDER_CONTINUOUS_EXPOSURE",
                                relevant_metric_values={
                                    "delta_continuous_exposure_from_anchor": (
                                        continuous_deltas[item.fingerprint]
                                    )
                                },
                            )
                        )
            else:
                materiality = tuple(
                    item
                    for item in access_safe_tuple
                    if continuous_deltas[item.fingerprint] <= bound + policy.numerical_epsilon
                )
                for item in access_safe_tuple:
                    if item not in materiality:
                        rejected.append(
                            OperationalSelectionRejectionV3(
                                fingerprint=item.fingerprint,
                                stage=("ROUTE_LOCAL_CONTINUOUS_EXPOSURE_MATERIALITY_ENVELOPE"),
                                reason="OUTSIDE_ROUTE_LOCAL_CONTINUOUS_EXPOSURE_ENVELOPE",
                                relevant_metric_values={
                                    "candidate_pair_continuous_exposure_equivalent": (
                                        item.pair_continuous_exposure_equivalent
                                    ),
                                    "anchor_pair_continuous_exposure_equivalent": (
                                        anchor.pair_continuous_exposure_equivalent
                                    ),
                                    "delta_continuous_exposure_from_anchor": (
                                        continuous_deltas[item.fingerprint]
                                    ),
                                    "continuous_preservation_bound": bound,
                                },
                            )
                        )
                best_rhythm_value = min(_rhythm_tuple_v3(item) for item in materiality)
                best_rhythm = tuple(
                    item for item in materiality if _rhythm_tuple_v3(item) == best_rhythm_value
                )
                for item in materiality:
                    if item not in best_rhythm:
                        rejected.append(
                            OperationalSelectionRejectionV3(
                                fingerprint=item.fingerprint,
                                stage="RHYTHM_SIMPLICITY",
                                reason="NOT_IN_BEST_RHYTHM_SET",
                                relevant_metric_values={
                                    "rhythm_simplicity_tuple": _rhythm_tuple_v3(item),
                                    "best_rhythm_simplicity_tuple": best_rhythm_value,
                                },
                            )
                        )
                best_fleet_value = min(_fleet_tuple_v3(item) for item in best_rhythm)
                best_fleet = tuple(
                    item for item in best_rhythm if _fleet_tuple_v3(item) == best_fleet_value
                )
                for item in best_rhythm:
                    if item not in best_fleet:
                        rejected.append(
                            OperationalSelectionRejectionV3(
                                fingerprint=item.fingerprint,
                                stage="FLEET_EFFICIENCY",
                                reason="NOT_IN_BEST_FLEET_EFFICIENCY_SET",
                                relevant_metric_values={
                                    "fleet_efficiency_tuple": _fleet_tuple_v3(item),
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
                                OperationalSelectionRejectionV3(
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
                    classification = "PHASE_ROBUST_MATERIALITY_SELECTS_ANCHOR"
                elif any(item.fingerprint == selected.fingerprint for item in calibration):
                    classification = "PHASE_ROBUST_MATERIALITY_SELECTS_LEGACY_ELIGIBLE_ALTERNATIVE"
                else:
                    classification = "PHASE_ROBUST_MATERIALITY_SELECTS_TRANSLATED_ALTERNATIVE"
                if selected_stage is None:
                    if len(materiality) == 1:
                        selected_stage = "ROUTE_LOCAL_CONTINUOUS_EXPOSURE_MATERIALITY_ENVELOPE"
                    elif len(best_rhythm) == 1:
                        selected_stage = "RHYTHM_SIMPLICITY"
                    else:
                        selected_stage = "FLEET_EFFICIENCY"

    if anchor is not None:
        traces.extend(
            (
                OperationalSelectionStageTraceV3(
                    stage="LEGACY_ONE_TRIP_TE_SEMANTIC_CALIBRATION",
                    input_count=len(access_safe_tuple),
                    retained_count=len(calibration),
                    retained_fingerprints=tuple(item.fingerprint for item in calibration),
                ),
                OperationalSelectionStageTraceV3(
                    stage="ROUTE_LOCAL_CONTINUOUS_EXPOSURE_MATERIALITY_ENVELOPE",
                    input_count=len(access_safe_tuple),
                    retained_count=len(materiality),
                    retained_fingerprints=tuple(item.fingerprint for item in materiality),
                ),
                OperationalSelectionStageTraceV3(
                    stage="RHYTHM_SIMPLICITY",
                    input_count=len(materiality),
                    retained_count=len(best_rhythm),
                    retained_fingerprints=tuple(item.fingerprint for item in best_rhythm),
                ),
                OperationalSelectionStageTraceV3(
                    stage="FLEET_EFFICIENCY",
                    input_count=len(best_rhythm),
                    retained_count=len(best_fleet),
                    retained_fingerprints=tuple(item.fingerprint for item in best_fleet),
                ),
            )
        )

    return OperationalSelectionResultV3(
        profile=policy.profile,
        priority_order=policy.priority_order,
        route_id=route_id,
        candidate_universe_count=len(ordered),
        hard_feasible_count=len(feasible),
        passenger_access_safe_count=len(access_safe_tuple),
        sse_best_count=len(sse_best),
        te_best_count=len(te_best),
        common_anchor_fingerprint=anchor.fingerprint if anchor is not None else None,
        common_anchor_sse=anchor.observed_demand_mismatch if anchor is not None else None,
        common_anchor_te=anchor.pair_trip_equivalent_error if anchor is not None else None,
        anchor_continuous_exposure_equivalent=(
            anchor.pair_continuous_exposure_equivalent if anchor is not None else None
        ),
        legacy_te_calibration_band_trips=policy.legacy_te_calibration_band_trips,
        legacy_calibration_set_count=len(calibration),
        legacy_calibration_fingerprints=tuple(item.fingerprint for item in calibration),
        continuous_preservation_bound=bound,
        phase_robust_materiality_set_count=len(materiality),
        phase_robust_materiality_fingerprints=tuple(item.fingerprint for item in materiality),
        best_rhythm_count=len(best_rhythm),
        best_fleet_efficiency_count=len(best_fleet),
        selected_pair_fingerprint=selected.fingerprint if selected is not None else None,
        selected_stage=selected_stage,
        selected_delta_continuous_from_anchor=(
            continuous_deltas[selected.fingerprint] if selected is not None else None
        ),
        selected_delta_te_from_anchor=(
            te_deltas[selected.fingerprint] if selected is not None else None
        ),
        selected_inside_legacy_te_calibration_set=(
            any(item.fingerprint == selected.fingerprint for item in calibration)
            if selected is not None
            else None
        ),
        selected_is_anchor=(
            selected.fingerprint == anchor.fingerprint
            if selected is not None and anchor is not None
            else None
        ),
        classification=classification,
        stage_trace=tuple(traces),
        rejected_candidates=tuple(rejected),
    )

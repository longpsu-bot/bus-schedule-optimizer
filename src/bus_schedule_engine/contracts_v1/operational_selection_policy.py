"""Frozen domain-priority post-search timetable selection policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

OPERATIONAL_SELECTION_PROFILE_V1 = "domain_priority_operational_selector_v1"
NUMERICAL_EPSILON = 1e-12
PRIORITY_ORDER_V1 = (
    "HARD_OPERATIONAL_FEASIBILITY",
    "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
    "OBSERVED_DEMAND_MISMATCH",
    "RHYTHM_SIMPLICITY",
    "FLEET_EFFICIENCY",
)


@dataclass(frozen=True, slots=True)
class OperationalSelectionPolicyV1:
    profile: str = OPERATIONAL_SELECTION_PROFILE_V1
    priority_order: tuple[str, ...] = PRIORITY_ORDER_V1
    numerical_epsilon: float = NUMERICAL_EPSILON


@dataclass(frozen=True, slots=True)
class OperationalSelectionCandidateV1:
    fingerprint: str
    hard_feasible: bool
    hard_feasibility_reasons: tuple[str, ...]
    observed_demand_mismatch: float
    outbound_maximum_bucket_expected_wait_minutes: float
    inbound_maximum_bucket_expected_wait_minutes: float
    total_directional_sustained_headway_level_count: int
    actual_service_regime_count: int
    total_directional_effective_palette_count: int
    total_single_gap_regime_count: int
    fleet_required: int
    total_excess_terminal_wait: int
    max_excess_terminal_wait: int
    diagnostics: Mapping[str, Any]
    hard_feasibility_metrics: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class OperationalSelectionRejectionV1:
    fingerprint: str
    stage: str
    reason: str
    relevant_metric_values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class OperationalSelectionStageTraceV1:
    stage: str
    input_count: int
    retained_count: int
    retained_fingerprints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationalSelectionResultV1:
    profile: str
    route_id: str
    candidate_universe_count: int
    hard_feasible_count: int
    passenger_access_safe_count: int
    best_demand_fit_count: int
    best_rhythm_count: int
    best_fleet_efficiency_count: int
    selected_pair_fingerprint: str | None
    selected_stage: str | None
    classification: str
    stage_trace: tuple[OperationalSelectionStageTraceV1, ...]
    rejected_candidates: tuple[OperationalSelectionRejectionV1, ...]


DEFAULT_OPERATIONAL_SELECTION_POLICY_V1 = OperationalSelectionPolicyV1()


def _hard_feasibility_reasons(checks: Mapping[str, bool]) -> tuple[str, ...]:
    reason_by_check = {
        "fixed_directional_trip_totals": "FIXED_DIRECTIONAL_TRIP_TOTALS_VIOLATION",
        "fixed_first_last_departures": "FIXED_ENDPOINT_VIOLATION",
        "strictly_increasing_departures": "NON_INCREASING_DEPARTURES",
        "whole_minute_departures": "NON_WHOLE_MINUTE_DEPARTURE",
        "uniform_actual_service_regimes": "NON_UNIFORM_ACTUAL_SERVICE_REGIME",
        "clean_boundary_compiler_validation": "CLEAN_BOUNDARY_COMPILER_VALIDATION_FAILED",
        "translated_protected_service_authority": "PROTECTED_SERVICE_AUTHORITY_VIOLATION",
        "demand_justified_slowest_tail_eligibility": "TAIL_ORDERING_INELIGIBLE",
        "authoritative_runtime": "AUTHORITATIVE_RUNTIME_VIOLATION",
        "authoritative_minimum_layover": "MINIMUM_LAYOVER_VIOLATION",
        "minimum_layover_witness_matches_exact_plan": ("MINIMUM_LAYOVER_WITNESS_MISMATCH"),
        "exact_minimum_fleet_path_cover": "EXACT_MINIMUM_FLEET_REVALIDATION_FAILED",
        "fleet_required_within_ceiling": "FLEET_CEILING_EXCEEDED",
        "exact_connections_meet_minimum_layover": "MINIMUM_LAYOVER_VIOLATION",
        "no_invented_deadhead": "INVENTED_DEADHEAD",
        "no_settlement": "SETTLEMENT_PRESENT",
        "no_manual_timestamp_edits": "MANUAL_TIMESTAMP_EDIT_DETECTED",
    }
    return tuple(
        dict.fromkeys(reason_by_check[key] for key, passed in checks.items() if not passed)
    )


def build_operational_selection_candidate_v1(
    *,
    context: Any,
    candidate: Any,
) -> OperationalSelectionCandidateV1:
    """Revalidate one exact coordinator pair and project immutable selector metrics."""

    from bus_schedule_engine import service_plan_coordinator as coordinator
    from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (
        CLEAN_BOUNDARY_COMPILER_PROFILE_V1,
        DemandRegimeAllocationV1,
        validate_clean_boundary_compilation_v1,
    )
    from bus_schedule_engine.contracts_v1.clean_compile_frontier import (
        clean_compilation_fingerprint_v1,
    )
    from bus_schedule_engine.contracts_v1.closed_loop_service_protection import (
        validate_closed_loop_service_protection_v1,
    )
    from bus_schedule_engine.contracts_v1.service_plan_state import (
        service_plan_fingerprint_v1,
    )

    checks = {
        "fixed_directional_trip_totals": True,
        "fixed_first_last_departures": True,
        "strictly_increasing_departures": True,
        "whole_minute_departures": True,
        "uniform_actual_service_regimes": True,
        "clean_boundary_compiler_validation": True,
        "translated_protected_service_authority": True,
        "demand_justified_slowest_tail_eligibility": True,
        "authoritative_runtime": context.runtime_minutes > 0,
        "authoritative_minimum_layover": (
            context.minimum_layover_minutes >= 0
            and (
                candidate.minimum_connection_layover_minutes is None
                or candidate.minimum_connection_layover_minutes >= context.minimum_layover_minutes
            )
        ),
        "minimum_layover_witness_matches_exact_plan": True,
        "exact_minimum_fleet_path_cover": True,
        "fleet_required_within_ceiling": (
            candidate.metrics.fleet_required <= context.fleet_ceiling
            and candidate.fleet_ceiling == context.fleet_ceiling
        ),
        "exact_connections_meet_minimum_layover": True,
        "no_invented_deadhead": True,
        "no_settlement": True,
        "no_manual_timestamp_edits": True,
    }
    recomputed_directional: dict[str, Any] = {}
    protection_status: dict[str, str] = {}
    exact_departure_counts: dict[str, int] = {}

    for direction in ("outbound", "inbound"):
        record = getattr(candidate, direction)
        state = record.state
        variant = record.compile_variant
        compilation = variant.compilation
        departures = compilation.exact_departures
        authority = context.endpoint_authority[direction]
        exact_departure_counts[direction] = len(departures)

        checks["fixed_directional_trip_totals"] &= (
            state.total_trips == len(departures) == len(context.scenario_b_departures[direction])
        )
        checks["fixed_first_last_departures"] &= bool(
            departures
            and state.fixed_first_departure == authority.fixed_first_departure
            and state.fixed_last_departure == authority.fixed_last_departure
            and departures[0] == authority.fixed_first_departure
            and departures[-1] == authority.fixed_last_departure
        )
        checks["strictly_increasing_departures"] &= all(
            left < right for left, right in zip(departures, departures[1:], strict=False)
        )
        checks["whole_minute_departures"] &= all(
            isinstance(item, int) and not isinstance(item, bool) and item % 60 == 0
            for item in departures
        )
        checks["no_manual_timestamp_edits"] &= (
            record.state_fingerprint == service_plan_fingerprint_v1(state)
            and variant.compilation_fingerprint == clean_compilation_fingerprint_v1(compilation)
        )
        checks["no_settlement"] &= (
            compilation.compiler_profile == CLEAN_BOUNDARY_COMPILER_PROFILE_V1
            and all("settlement" not in entry.lower() for entry in record.history)
        )

        regimes = tuple(
            DemandRegimeAllocationV1(
                regime_id=f"PLAN-{direction.upper()}-{index:02d}",
                start_time=regime.start,
                end_time=regime.end,
                allocated_trip_count=regime.trip_count,
                nominal_headway=regime.duration_minutes / regime.trip_count,
            )
            for index, regime in enumerate(state.service_regimes, start=1)
        )
        try:
            validate_clean_boundary_compilation_v1(compilation, regimes)
        except ValueError:
            checks["clean_boundary_compiler_validation"] = False
            checks["uniform_actual_service_regimes"] = False
        else:
            checks["uniform_actual_service_regimes"] &= all(
                all(
                    later - earlier == service.uniform_headway_minutes * 60
                    for earlier, later in zip(
                        service.departures, service.departures[1:], strict=False
                    )
                )
                for service in compilation.service_regimes
            )

        protection = validate_closed_loop_service_protection_v1(
            authority=context.service_protection_authority,
            direction=direction,
            exact_departures=departures,
        )
        protection_status[direction] = protection.status
        checks["translated_protected_service_authority"] &= protection.passed
        metrics, _ = coordinator.evaluate_actual_service_v1(
            variant,
            demand_buckets=context.demand_buckets[direction],
            scenario_b_departures=context.scenario_b_departures[direction],
            demand_response_regimes=(
                None
                if context.demand_response_regimes is None
                else context.demand_response_regimes[direction]
            ),
            protection_authority=context.service_protection_authority,
            protection_validation=protection,
        )
        recomputed_directional[direction] = metrics
        checks["demand_justified_slowest_tail_eligibility"] &= metrics.tail_ordering.eligible
        checks["no_manual_timestamp_edits"] &= metrics == record.metrics

    outbound = candidate.outbound.compile_variant.compilation
    inbound = candidate.inbound.compile_variant.compilation
    fleet_plan = coordinator.build_minimum_fleet_plan_v1(
        route_id=context.route_id,
        outbound_candidate_id=outbound.candidate_id,
        inbound_candidate_id=inbound.candidate_id,
        outbound_departures=outbound.exact_departures,
        inbound_departures=inbound.exact_departures,
        runtime_minutes=context.runtime_minutes,
        minimum_layover_minutes=context.minimum_layover_minutes,
    )
    checks["exact_minimum_fleet_path_cover"] &= (
        fleet_plan.fleet_requirement == candidate.metrics.fleet_required
    )
    checks["minimum_layover_witness_matches_exact_plan"] &= (
        fleet_plan.minimum_connection_layover_minutes
        == candidate.minimum_connection_layover_minutes
    )
    checks["fleet_required_within_ceiling"] &= fleet_plan.fleet_requirement <= context.fleet_ceiling
    connections = tuple(
        item for item in fleet_plan.assignments if item.connection_layover_minutes is not None
    )
    checks["exact_connections_meet_minimum_layover"] &= all(
        item.connection_layover_minutes >= context.minimum_layover_minutes for item in connections
    )
    assignment_by_id = {item.trip_id: item for item in fleet_plan.assignments}
    checks["no_invented_deadhead"] &= all(
        item.next_trip_id is None or assignment_by_id[item.next_trip_id].direction != item.direction
        for item in fleet_plan.assignments
    )
    revalidated_pair, _ = coordinator.evaluate_operating_pair_v1(
        candidate.outbound,
        candidate.inbound,
        context=context,
    )
    checks["exact_minimum_fleet_path_cover"] &= bool(
        revalidated_pair is not None
        and revalidated_pair.pair_fingerprint == candidate.pair_fingerprint
        and revalidated_pair.metrics == candidate.metrics
    )

    outbound_metrics = recomputed_directional["outbound"]
    inbound_metrics = recomputed_directional["inbound"]
    feedback_codes = {
        direction: {item.code for item in getattr(candidate, direction).feedback}
        for direction in ("outbound", "inbound")
    }
    diagnostics = {
        "observed_demand_mismatch": candidate.metrics.observed_demand_mismatch,
        "directional_bucket_service_shares": {
            "outbound": list(outbound_metrics.bucket_service_shares),
            "inbound": list(inbound_metrics.bucket_service_shares),
        },
        "demand_response_direction_accuracy": {
            "outbound": outbound_metrics.demand_response_direction_accuracy,
            "inbound": inbound_metrics.demand_response_direction_accuracy,
        },
        "sqrt_response_deviation": {
            "outbound": outbound_metrics.sqrt_seed_response_deviation,
            "inbound": inbound_metrics.sqrt_seed_response_deviation,
        },
        "under_over_feedback_presence": {
            direction: {
                "under": coordinator.DEMAND_UNDERSERVED_INTERVAL in feedback_codes[direction],
                "over": coordinator.DEMAND_OVERSERVED_INTERVAL in feedback_codes[direction],
            }
            for direction in ("outbound", "inbound")
        },
    }
    hard_metrics = {
        "checks": checks,
        "runtime_minutes": context.runtime_minutes,
        "minimum_layover_minutes": context.minimum_layover_minutes,
        "fleet_required": fleet_plan.fleet_requirement,
        "fleet_ceiling": context.fleet_ceiling,
        "minimum_connection_layover_minutes": fleet_plan.minimum_connection_layover_minutes,
        "exact_departure_counts": exact_departure_counts,
        "protection_status": protection_status,
    }
    reasons = _hard_feasibility_reasons(checks)
    return OperationalSelectionCandidateV1(
        fingerprint=candidate.pair_fingerprint,
        hard_feasible=not reasons,
        hard_feasibility_reasons=reasons,
        observed_demand_mismatch=candidate.metrics.observed_demand_mismatch,
        outbound_maximum_bucket_expected_wait_minutes=(
            outbound_metrics.maximum_bucket_expected_wait_minutes
        ),
        inbound_maximum_bucket_expected_wait_minutes=(
            inbound_metrics.maximum_bucket_expected_wait_minutes
        ),
        total_directional_sustained_headway_level_count=(
            candidate.metrics.total_directional_sustained_headway_level_count
        ),
        actual_service_regime_count=candidate.metrics.actual_service_regime_count,
        total_directional_effective_palette_count=(
            candidate.metrics.total_directional_effective_palette_count
        ),
        total_single_gap_regime_count=candidate.metrics.total_single_gap_regime_count,
        fleet_required=candidate.metrics.fleet_required,
        total_excess_terminal_wait=candidate.metrics.total_excess_terminal_wait,
        max_excess_terminal_wait=candidate.metrics.max_excess_terminal_wait,
        diagnostics=diagnostics,
        hard_feasibility_metrics=hard_metrics,
    )


def select_operational_timetable_v1(
    *,
    context: Any,
    candidates: Sequence[Any],
    policy: OperationalSelectionPolicyV1 = DEFAULT_OPERATIONAL_SELECTION_POLICY_V1,
) -> OperationalSelectionResultV1:
    """Apply the frozen policy after coordinator search without mutating its frontier."""

    from bus_schedule_engine import service_plan_coordinator as coordinator

    snapshots = tuple(
        build_operational_selection_candidate_v1(context=context, candidate=item)
        for item in candidates
    )
    scenario_b_access = {
        direction: coordinator.expected_passenger_wait_metrics_v1(
            context.scenario_b_departures[direction], context.demand_buckets[direction]
        )[1]
        for direction in ("outbound", "inbound")
    }
    return select_operational_candidates_v1(
        route_id=context.route_id,
        candidates=snapshots,
        scenario_b_directional_maximum_wait_minutes=scenario_b_access,
        policy=policy,
    )


def select_operational_candidates_v1(
    *,
    route_id: str,
    candidates: Sequence[OperationalSelectionCandidateV1],
    scenario_b_directional_maximum_wait_minutes: Mapping[str, float],
    policy: OperationalSelectionPolicyV1 = DEFAULT_OPERATIONAL_SELECTION_POLICY_V1,
) -> OperationalSelectionResultV1:
    """Select from independently assessed immutable operating-pair snapshots."""

    if set(scenario_b_directional_maximum_wait_minutes) != {"outbound", "inbound"}:
        raise ValueError("Scenario B maximum access authority must be directional")
    ordered = tuple(sorted(candidates, key=lambda item: item.fingerprint))
    feasible = tuple(item for item in ordered if item.hard_feasible)
    rejected: list[OperationalSelectionRejectionV1] = [
        OperationalSelectionRejectionV1(
            fingerprint=item.fingerprint,
            stage="HARD_OPERATIONAL_FEASIBILITY",
            reason=(
                item.hard_feasibility_reasons[0] if item.hard_feasibility_reasons else "FAILED"
            ),
            relevant_metric_values=item.hard_feasibility_metrics,
        )
        for item in ordered
        if not item.hard_feasible
    ]
    access_safe: list[OperationalSelectionCandidateV1] = []
    for item in feasible:
        failed_directions = tuple(
            direction
            for direction, candidate_value in (
                ("outbound", item.outbound_maximum_bucket_expected_wait_minutes),
                ("inbound", item.inbound_maximum_bucket_expected_wait_minutes),
            )
            if candidate_value
            > float(scenario_b_directional_maximum_wait_minutes[direction])
            + policy.numerical_epsilon
        )
        if failed_directions:
            reason = (
                f"{failed_directions[0].upper()}_MAX_ACCESS_REGRESSION"
                if len(failed_directions) == 1
                else "BOTH_DIRECTIONS_MAX_ACCESS_REGRESSION"
            )
            rejected.append(
                OperationalSelectionRejectionV1(
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
        else:
            access_safe.append(item)
    access_safe_tuple = tuple(access_safe)
    if access_safe_tuple:
        best_mismatch = min(item.observed_demand_mismatch for item in access_safe_tuple)
        best_demand = tuple(
            item
            for item in access_safe_tuple
            if item.observed_demand_mismatch <= best_mismatch + policy.numerical_epsilon
        )
        for item in access_safe_tuple:
            if item not in best_demand:
                rejected.append(
                    OperationalSelectionRejectionV1(
                        fingerprint=item.fingerprint,
                        stage="OBSERVED_DEMAND_MISMATCH",
                        reason="NOT_IN_BEST_DEMAND_FIT_SET",
                        relevant_metric_values={
                            "observed_demand_mismatch": item.observed_demand_mismatch,
                            "best_access_safe_observed_demand_mismatch": best_mismatch,
                            "delta_mismatch_vs_best_access_safe": (
                                item.observed_demand_mismatch - best_mismatch
                            ),
                        },
                    )
                )
    else:
        best_demand = ()
    if len(best_demand) > 1:
        best_rhythm_tuple = min(
            (
                item.total_directional_sustained_headway_level_count,
                item.actual_service_regime_count,
                item.total_directional_effective_palette_count,
                item.total_single_gap_regime_count,
            )
            for item in best_demand
        )
        best_rhythm = tuple(
            item
            for item in best_demand
            if (
                item.total_directional_sustained_headway_level_count,
                item.actual_service_regime_count,
                item.total_directional_effective_palette_count,
                item.total_single_gap_regime_count,
            )
            == best_rhythm_tuple
        )
        for item in best_demand:
            if item not in best_rhythm:
                rejected.append(
                    OperationalSelectionRejectionV1(
                        fingerprint=item.fingerprint,
                        stage="RHYTHM_SIMPLICITY",
                        reason="NOT_IN_BEST_RHYTHM_SET",
                        relevant_metric_values={
                            "rhythm_simplicity_tuple": [
                                item.total_directional_sustained_headway_level_count,
                                item.actual_service_regime_count,
                                item.total_directional_effective_palette_count,
                                item.total_single_gap_regime_count,
                            ],
                            "best_rhythm_simplicity_tuple": list(best_rhythm_tuple),
                        },
                    )
                )
    else:
        best_rhythm = best_demand
    if len(best_rhythm) > 1:
        best_fleet_tuple = min(
            (
                item.fleet_required,
                item.total_excess_terminal_wait,
                item.max_excess_terminal_wait,
            )
            for item in best_rhythm
        )
        best_fleet = tuple(
            item
            for item in best_rhythm
            if (
                item.fleet_required,
                item.total_excess_terminal_wait,
                item.max_excess_terminal_wait,
            )
            == best_fleet_tuple
        )
        for item in best_rhythm:
            if item not in best_fleet:
                rejected.append(
                    OperationalSelectionRejectionV1(
                        fingerprint=item.fingerprint,
                        stage="FLEET_EFFICIENCY",
                        reason="NOT_IN_BEST_FLEET_EFFICIENCY_SET",
                        relevant_metric_values={
                            "fleet_efficiency_tuple": [
                                item.fleet_required,
                                item.total_excess_terminal_wait,
                                item.max_excess_terminal_wait,
                            ],
                            "best_fleet_efficiency_tuple": list(best_fleet_tuple),
                        },
                    )
                )
    else:
        best_fleet = best_rhythm
    selected = best_fleet[0].fingerprint if best_fleet else None
    selected_stage = None
    classification = "NO_HARD_FEASIBLE_CANDIDATE"
    if selected:
        classification = "UNIQUE_DOMAIN_PRIORITY_SELECTION"
        if len(best_demand) == 1:
            selected_stage = "OBSERVED_DEMAND_MISMATCH"
        elif len(best_rhythm) == 1:
            selected_stage = "RHYTHM_SIMPLICITY"
        elif len(best_fleet) == 1:
            selected_stage = "FLEET_EFFICIENCY"
        else:
            selected_stage = "FINAL_DETERMINISTIC_TIEBREAK"
            classification = "METRICALLY_EQUIVALENT_DETERMINISTIC_TIEBREAK"
            for item in best_fleet[1:]:
                rejected.append(
                    OperationalSelectionRejectionV1(
                        fingerprint=item.fingerprint,
                        stage="FINAL_DETERMINISTIC_TIEBREAK",
                        reason="LEXICOGRAPHICALLY_LATER_PAIR_FINGERPRINT",
                        relevant_metric_values={
                            "selected_pair_fingerprint": selected,
                            "pair_fingerprint_is_quality_objective": False,
                        },
                    )
                )
    elif feasible:
        classification = "ACCESS_GUARDRAIL_TOO_RESTRICTIVE"
    trace = (
        OperationalSelectionStageTraceV1(
            stage="HARD_OPERATIONAL_FEASIBILITY",
            input_count=len(ordered),
            retained_count=len(feasible),
            retained_fingerprints=tuple(item.fingerprint for item in feasible),
        ),
        OperationalSelectionStageTraceV1(
            stage="SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
            input_count=len(feasible),
            retained_count=len(access_safe_tuple),
            retained_fingerprints=tuple(item.fingerprint for item in access_safe_tuple),
        ),
        OperationalSelectionStageTraceV1(
            stage="OBSERVED_DEMAND_MISMATCH",
            input_count=len(access_safe_tuple),
            retained_count=len(best_demand),
            retained_fingerprints=tuple(item.fingerprint for item in best_demand),
        ),
        OperationalSelectionStageTraceV1(
            stage="RHYTHM_SIMPLICITY",
            input_count=len(best_demand),
            retained_count=len(best_rhythm),
            retained_fingerprints=tuple(item.fingerprint for item in best_rhythm),
        ),
        OperationalSelectionStageTraceV1(
            stage="FLEET_EFFICIENCY",
            input_count=len(best_rhythm),
            retained_count=len(best_fleet),
            retained_fingerprints=tuple(item.fingerprint for item in best_fleet),
        ),
    )
    return OperationalSelectionResultV1(
        profile=policy.profile,
        route_id=route_id,
        candidate_universe_count=len(ordered),
        hard_feasible_count=len(feasible),
        passenger_access_safe_count=len(access_safe_tuple),
        best_demand_fit_count=len(best_demand),
        best_rhythm_count=len(best_rhythm),
        best_fleet_efficiency_count=len(best_fleet),
        selected_pair_fingerprint=selected,
        selected_stage=selected_stage,
        classification=classification,
        stage_trace=trace,
        rejected_candidates=tuple(rejected),
    )

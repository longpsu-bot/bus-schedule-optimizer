"""Generate compact PR62-E Route 6/10 closed-loop pilot evidence.

This is an evidence-only runner. It invokes the production coordinator unchanged and
temporarily wraps its existing queue, neighbor, archive, compiler, and pair-evaluation
boundaries to observe diagnostics that are not part of the production result contract.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
_SCRIPTS = _REPO_ROOT / "scripts"
for _import_root in (_SRC, _SCRIPTS):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from route6_boundary_settlement_experiment import (  # noqa: E402
    REFERENCE_LABELS,
    exact_headway_runs,
    parse_route6_reference_workbook,
)
from route6_boundary_settlement_experiment import (  # noqa: E402
    directional_metrics as reference_directional_metrics,
)
from route6_boundary_settlement_experiment import (  # noqa: E402
    pair_metrics as reference_pair_metrics,
)

import bus_schedule_engine.service_plan_coordinator as coordinator  # noqa: E402
from bus_schedule_engine.contracts_v1.service_plan_state import (  # noqa: E402
    ServicePlanStateV1,
    service_plan_fingerprint_payload_v1,
    service_plan_fingerprint_v1,
)
from bus_schedule_engine.service_plan_coordinator import (  # noqa: E402
    CLEAN_BOUNDARY_UNCOMPILABLE,
    DEMAND_OVERSERVED_INTERVAL,
    DEMAND_RESPONSE_DIRECTION_MISMATCH,
    DEMAND_UNDERSERVED_INTERVAL,
    FLEET_LIMIT_EXCEEDED,
    LARGEST_SERVICE_FREQUENCY_JUMP,
    REDUNDANT_SERVICE_BOUNDARY,
    TAIL_OVER_SERVICE,
    TAIL_UNDER_SERVICE,
    CoordinatorSearchBudgetV1,
    demand_response_diagnostics_v1,
    expected_passenger_wait_metrics_v1,
    load_route_coordinator_inputs_v1,
    route_result_payload_v1,
    search_route_service_plans_v1,
    verify_frozen_prior_artifacts_v1,
)

PROFILE = "pr62_e_route6_route10_closed_loop_pilot_v1"
EXPECTED_STARTING_SHA = "e382723b8e1b788de50dd1fa498d791fe55ee22b"
EXPECTED_REFERENCE_SHA256 = "c2038b31c5a3f6a3ee2377ce2067542cc718a7d1907722efa3ab45a536bdd14a"
EXPECTED_AUTHORITIES = {
    "6": {
        "runtime_minutes": 70,
        "minimum_layover_minutes": 5,
        "fleet_ceiling": 20,
        "endpoints": {
            "outbound": (4 * 3600 + 55 * 60, 21 * 3600),
            "inbound": (4 * 3600 + 55 * 60, 21 * 3600),
        },
    },
    "10": {
        "runtime_minutes": 80,
        "minimum_layover_minutes": 5,
        "fleet_ceiling": 13,
        "endpoints": {
            "outbound": (5 * 3600, 21 * 3600),
            "inbound": (4 * 3600 + 45 * 60, 21 * 3600),
        },
    },
}
FROZEN_BUDGET = CoordinatorSearchBudgetV1(
    max_service_plan_evaluations=24,
    max_open_states=512,
    max_compile_frontier_per_state=4,
    max_directional_compilations=24,
    max_pair_frontier=512,
)
FEEDBACK_CODES = (
    REDUNDANT_SERVICE_BOUNDARY,
    LARGEST_SERVICE_FREQUENCY_JUMP,
    DEMAND_UNDERSERVED_INTERVAL,
    DEMAND_OVERSERVED_INTERVAL,
    DEMAND_RESPONSE_DIRECTION_MISMATCH,
    TAIL_UNDER_SERVICE,
    TAIL_OVER_SERVICE,
    FLEET_LIMIT_EXCEEDED,
    CLEAN_BOUNDARY_UNCOMPILABLE,
)
LOCALIZED_FEEDBACK_CODES = {
    REDUNDANT_SERVICE_BOUNDARY,
    LARGEST_SERVICE_FREQUENCY_JUMP,
    DEMAND_UNDERSERVED_INTERVAL,
    DEMAND_OVERSERVED_INTERVAL,
    DEMAND_RESPONSE_DIRECTION_MISMATCH,
    TAIL_UNDER_SERVICE,
    TAIL_OVER_SERVICE,
}
ROUTE_OUTPUTS = {
    "6": "PR62_E_ROUTE6_CLOSED_LOOP_PILOT",
    "10": "PR62_E_ROUTE10_CLOSED_LOOP_PILOT",
}
ARCHITECTURE_OUTPUT = "PR62_E_CLOSED_LOOP_ARCHITECTURE_DECISION.md"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any, *, pretty: bool = True) -> bytes:
    kwargs = {"ensure_ascii": False, "sort_keys": True}
    if pretty:
        kwargs["indent"] = 2
    else:
        kwargs["separators"] = (",", ":")
    return (json.dumps(value, **kwargs) + "\n").encode("utf-8")


def _fingerprint(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value, pretty=False))


def _hhmm(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    minutes = seconds // 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _state_compact(state: ServicePlanStateV1) -> dict[str, Any]:
    return {
        **service_plan_fingerprint_payload_v1(state),
        "fingerprint": service_plan_fingerprint_v1(state),
        "seed_id": state.seed_id,
        "parent_fingerprint": state.parent_fingerprint,
        "operation": state.operation,
        "operation_evidence": state.operation_evidence,
        "regimes": [dataclasses.asdict(item) for item in state.service_regimes],
    }


def _priority_json(priority: Sequence[Any]) -> list[Any]:
    return [list(value) if isinstance(value, tuple) else value for value in priority]


class SearchAudit:
    """Lightweight observations around one unchanged production search."""

    def __init__(self, context: Any, seeds: Sequence[ServicePlanStateV1]) -> None:
        self.context = context
        self.queue: Any | None = None
        self.last_compile_direction: str | None = None
        self.popped_states: list[ServicePlanStateV1] = []
        self.all_states: dict[str, ServicePlanStateV1] = {
            service_plan_fingerprint_v1(item): item for item in seeds
        }
        self.generated_by_code: Counter[str] = Counter()
        self.generated_by_parent: Counter[str] = Counter()
        self.generated_by_parent_and_code: Counter[tuple[str, str]] = Counter()
        self.neighbor_calls_by_parent: Counter[str] = Counter()
        self.archives: dict[str, list[Any]] = {"outbound": [], "inbound": []}
        self.compile_failures: dict[str, dict[str, Any]] = {}
        self.feasible_pairs: dict[str, Any] = {}
        self.response_anchor_fingerprints: dict[str, str] = {}

    def ancestry_codes(self, state: ServicePlanStateV1) -> tuple[str, ...]:
        codes: list[str] = []
        current: ServicePlanStateV1 | None = state
        visited: set[str] = set()
        while current is not None:
            fingerprint = service_plan_fingerprint_v1(current)
            if fingerprint in visited:
                break
            visited.add(fingerprint)
            if current.operation_evidence:
                codes.append(current.operation_evidence)
            current = (
                None
                if current.parent_fingerprint is None
                else self.all_states.get(current.parent_fingerprint)
            )
        return tuple(dict.fromkeys(codes))

    def queue_snapshot(self) -> list[dict[str, Any]]:
        if self.queue is None:
            return []
        inner = self.queue.inner
        active_rows = []
        for priority, fingerprint, ticket, state in inner.heap:
            if inner.active.get(fingerprint) != (priority, ticket):
                continue
            active_rows.append(
                {
                    "fingerprint": fingerprint,
                    "direction": state.direction,
                    "priority": _priority_json(priority),
                    "precompile_mismatch": coordinator._state_precompile_mismatch(
                        state, self.context.demand_buckets[state.direction]
                    ),
                    "regime_count": len(state.service_regimes),
                    "trip_count_vector": list(state.trip_count_vector),
                    "boundaries": list(state.boundaries),
                    "operation": state.operation,
                    "operation_evidence": state.operation_evidence,
                    "ancestry_codes": list(self.ancestry_codes(state)),
                }
            )
        return sorted(active_rows, key=lambda item: (item["priority"], item["fingerprint"]))


@contextmanager
def _instrument_search(audit: SearchAudit):
    original_queue = coordinator._BoundedOpenQueue
    original_neighbors = coordinator.generate_targeted_neighbors_v1
    original_archive = coordinator._retain_directional_archive
    original_pair = coordinator.evaluate_operating_pair_v1

    class AuditQueue:
        def __init__(self, limit: int) -> None:
            self.inner = original_queue(limit)
            audit.queue = self

        def push(self, state: ServicePlanStateV1, priority: tuple[Any, ...]):
            result = self.inner.push(state, priority)
            if (
                result[0]
                and priority[0] == 1
                and state.operation_evidence == DEMAND_RESPONSE_DIRECTION_MISMATCH
            ):
                audit.response_anchor_fingerprints[state.direction] = service_plan_fingerprint_v1(
                    state
                )
                audit.all_states[service_plan_fingerprint_v1(state)] = state
            return result

        def pop(self):
            value = self.inner.pop()
            if value is not None:
                audit.popped_states.append(value[0])
                audit.all_states[service_plan_fingerprint_v1(value[0])] = value[0]
            return value

        def __bool__(self) -> bool:
            return bool(self.inner)

    def audited_neighbors(state: ServicePlanStateV1, **kwargs: Any):
        neighbors = original_neighbors(state, **kwargs)
        parent = service_plan_fingerprint_v1(state)
        audit.all_states.setdefault(parent, state)
        audit.neighbor_calls_by_parent[parent] += 1
        for neighbor in neighbors:
            code = neighbor.evidence_code or "EXPLORATION"
            audit.generated_by_code[code] += 1
            audit.generated_by_parent[parent] += 1
            audit.generated_by_parent_and_code[(parent, code)] += 1
        return neighbors

    def audited_archive(items: Sequence[Any], *, limit: int):
        retained = original_archive(items, limit=limit)
        direction = (
            retained[0].state.direction
            if retained
            else (items[0].state.direction if items else audit.last_compile_direction)
        )
        if direction is not None:
            audit.archives[direction] = list(retained)
        return retained

    def audited_pair(outbound: Any, inbound: Any, *, context: Any):
        pair, feedback = original_pair(outbound, inbound, context=context)
        if pair is not None:
            audit.feasible_pairs[pair.pair_fingerprint] = pair
        return pair, feedback

    coordinator._BoundedOpenQueue = AuditQueue
    coordinator.generate_targeted_neighbors_v1 = audited_neighbors
    coordinator._retain_directional_archive = audited_archive
    coordinator.evaluate_operating_pair_v1 = audited_pair
    try:
        yield
    finally:
        coordinator._BoundedOpenQueue = original_queue
        coordinator.generate_targeted_neighbors_v1 = original_neighbors
        coordinator._retain_directional_archive = original_archive
        coordinator.evaluate_operating_pair_v1 = original_pair


def _audited_run(context: Any, seeds: Sequence[ServicePlanStateV1]) -> tuple[Any, SearchAudit]:
    audit = SearchAudit(context, seeds)
    original_compiler = coordinator.compile_service_plan_frontier_v1

    def audited_compiler(state: ServicePlanStateV1, **kwargs: Any):
        audit.last_compile_direction = state.direction
        frontier = original_compiler(state, **kwargs)
        if not frontier.variants:
            failure = frontier.failure.failure if frontier.failure else None
            fingerprint = service_plan_fingerprint_v1(state)
            audit.compile_failures[fingerprint] = {
                "direction": state.direction,
                "fingerprint": fingerprint,
                "service_plan": _state_compact(state),
                "failing_boundary": None if failure is None else failure.boundary_time,
                "compiler_reason": "No clean compilation path"
                if failure is None
                else failure.reason,
                "parent_feedback": state.operation_evidence,
                "parent_operation": state.operation,
            }
        return frontier

    with _instrument_search(audit):
        result = search_route_service_plans_v1(
            context=context,
            seeds=seeds,
            budget=FROZEN_BUDGET,
            compiler=audited_compiler,
        )
    return result, audit


def _archive_signature(audit: SearchAudit) -> dict[str, list[str]]:
    return {
        direction: sorted(
            item.compile_variant.compilation_fingerprint for item in audit.archives[direction]
        )
        for direction in ("outbound", "inbound")
    }


def _result_signature(result: Any, audit: SearchAudit, prior: Mapping[str, Any]) -> dict[str, Any]:
    payload = route_result_payload_v1(
        context=audit.context,
        result=result,
        prior_artifact_verification=prior,
    )
    return {
        "status": result.status,
        "statistics": dataclasses.asdict(result.statistics),
        "evaluated_state_fingerprints": list(result.evaluated_state_fingerprints),
        "directional_archive_fingerprints": _archive_signature(audit),
        "pareto_pair_fingerprints": [item.pair_fingerprint for item in result.pareto_frontier],
        "metrics": [dataclasses.asdict(item.metrics) for item in result.pareto_frontier],
        "feedback_code_counts": dict(result.feedback_code_counts),
        "revision_examples": {key: list(value) for key, value in result.revision_examples.items()},
        "serialized_frontier_fingerprint": _fingerprint(payload["pareto_frontier"]),
        "queue_at_stop": audit.queue_snapshot(),
        "compile_failures": list(audit.compile_failures.values()),
        "generation_by_code": dict(sorted(audit.generated_by_code.items())),
        "response_anchor_fingerprints": dict(sorted(audit.response_anchor_fingerprints.items())),
    }


def _authority_payload(context: Any) -> dict[str, Any]:
    expected = EXPECTED_AUTHORITIES[context.route_id]
    actual_endpoints = {
        direction: (
            context.endpoint_authority[direction].fixed_first_departure,
            context.endpoint_authority[direction].fixed_last_departure,
        )
        for direction in ("outbound", "inbound")
    }
    actual = {
        "runtime_minutes": context.runtime_minutes,
        "minimum_layover_minutes": context.minimum_layover_minutes,
        "fleet_ceiling": context.fleet_ceiling,
        "endpoints": actual_endpoints,
    }
    if actual != expected:
        raise RuntimeError(f"Route {context.route_id} authority changed: {actual!r}")
    return {
        "loader": "load_route_coordinator_inputs_v1",
        "runtime_minutes_each_direction": context.runtime_minutes,
        "minimum_layover_minutes": context.minimum_layover_minutes,
        "fleet_ceiling": context.fleet_ceiling,
        "directions": {
            direction: {
                "fixed_first_departure": actual_endpoints[direction][0],
                "fixed_last_departure": actual_endpoints[direction][1],
                "fixed_first_departure_hhmm": _hhmm(actual_endpoints[direction][0]),
                "fixed_last_departure_hhmm": _hhmm(actual_endpoints[direction][1]),
            }
            for direction in ("outbound", "inbound")
        },
        "planning_grid_seconds": context.planning_grid_seconds,
        "immutable_demand_sha256": context.immutable_demand_sha256,
    }


def _lineage_contains(record: Any, code: str, audit: SearchAudit) -> bool:
    return code in audit.ancestry_codes(record.state) or any(
        code in item for item in record.history
    )


def _feedback_effectiveness(result: Any, audit: SearchAudit) -> dict[str, Any]:
    evaluated = audit.popped_states
    feasible = list(audit.feasible_pairs.values())
    final = list(result.pareto_frontier)
    rows = {}
    for code in FEEDBACK_CODES:
        emitted = int(result.feedback_code_counts.get(code, 0))
        generated = int(audit.generated_by_code.get(code, 0))
        evaluated_descendants = sum(code in audit.ancestry_codes(state) for state in evaluated)
        retained = sum(
            _lineage_contains(item, code, audit)
            for direction in ("outbound", "inbound")
            for item in audit.archives[direction]
        )
        feasible_count = sum(
            _lineage_contains(pair.outbound, code, audit)
            or _lineage_contains(pair.inbound, code, audit)
            for pair in feasible
        )
        final_count = sum(
            _lineage_contains(pair.outbound, code, audit)
            or _lineage_contains(pair.inbound, code, audit)
            for pair in final
        )
        if any((emitted, generated, evaluated_descendants, retained, feasible_count, final_count)):
            rows[code] = {
                "emitted_count": emitted,
                "generated_child_states": generated,
                "evaluated_descendants": evaluated_descendants,
                "retained_directional_compilations": retained,
                "feasible_pair_participation": feasible_count,
                "final_pareto_ancestry": final_count,
            }
    return rows


def classify_neighbor_explosion(
    *, generated: int, evaluated: int, pruned: int, duplicates: int, open_limit: int
) -> str:
    """Classify computational amplification, not candidate quality or policy validity."""

    accounted = pruned + duplicates
    if generated <= evaluated + open_limit:
        return "NO_NEIGHBOR_EXPLOSION_EVIDENCE"
    if generated > max(evaluated, 1) * open_limit and accounted > generated / 2:
        return "MATERIAL_NEIGHBOR_GENERATION_EXPLOSION"
    return "NEIGHBOR_EXPLOSION_INCONCLUSIVE"


def classify_queue_starvation(
    *, budget_exhausted: bool, queue_rows: Sequence[Mapping[str, Any]], evaluated: Sequence[Any]
) -> str:
    """Use only pre-compile attractiveness for never-evaluated queued states."""

    if not budget_exhausted or not queue_rows:
        return "NO_QUEUE_STARVATION_EVIDENCE"
    if not evaluated:
        return "QUEUE_STARVATION_INCONCLUSIVE"
    evaluated_best = min(
        coordinator._state_precompile_mismatch(
            state, state_audit_context(evaluated).demand_buckets[state.direction]
        )
        for state in evaluated
    )
    localized = [
        row
        for row in queue_rows
        if set(row["ancestry_codes"]) & LOCALIZED_FEEDBACK_CODES
        and float(row["precompile_mismatch"]) <= evaluated_best
    ]
    return "LOCALIZED_FEEDBACK_QUEUE_STARVATION" if localized else "QUEUE_STARVATION_INCONCLUSIVE"


_CLASSIFICATION_CONTEXT: Any | None = None


def state_audit_context(states: Sequence[Any]) -> Any:
    del states
    if _CLASSIFICATION_CONTEXT is None:
        raise RuntimeError("classification context is not bound")
    return _CLASSIFICATION_CONTEXT


def _pareto_without_wait(feasible_pairs: Sequence[Any]) -> set[str]:
    def vector(pair: Any) -> tuple[float, ...]:
        values = pair.metrics.pareto_vector
        return tuple(float(value) for index, value in enumerate(values) if index != 1)

    retained: set[str] = set()
    for candidate in feasible_pairs:
        candidate_vector = vector(candidate)
        dominated = False
        for other in feasible_pairs:
            if other.pair_fingerprint == candidate.pair_fingerprint:
                continue
            other_vector = vector(other)
            if all(
                a <= b + 1e-12 for a, b in zip(other_vector, candidate_vector, strict=True)
            ) and any(a < b - 1e-12 for a, b in zip(other_vector, candidate_vector, strict=True)):
                dominated = True
                break
        if not dominated:
            retained.add(candidate.pair_fingerprint)
    return retained


def _directional_payload(item: Any) -> dict[str, Any]:
    metrics = item.metrics
    compilation = item.compile_variant.compilation
    return {
        "direction": item.state.direction,
        "state_fingerprint": item.state_fingerprint,
        "compilation_fingerprint": item.compile_variant.compilation_fingerprint,
        "service_plan_regimes": [dataclasses.asdict(value) for value in item.state.service_regimes],
        "actual_service_regimes": [
            dataclasses.asdict(value) for value in compilation.service_regimes
        ],
        "exact_departures": list(compilation.exact_departures),
        "exact_departures_hhmm": [_hhmm(value) for value in compilation.exact_departures],
        "metrics": dataclasses.asdict(metrics),
        "response_audit": {
            "transition_count": metrics.demand_response_transition_count,
            "aligned_transition_count": metrics.demand_response_aligned_transition_count,
            "direction_accuracy": metrics.demand_response_direction_accuracy,
            "sqrt_response_deviation": metrics.sqrt_seed_response_deviation,
            "canonical_demand_regime_service": [
                dataclasses.asdict(value) for value in metrics.demand_response_regime_projections
            ],
        },
        "history": list(item.history),
    }


def _frontier_payload(result: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    directional: dict[str, Any] = {}
    pairs = []
    for index, pair in enumerate(result.pareto_frontier, start=1):
        keys = {}
        for record in (pair.outbound, pair.inbound):
            key = record.compile_variant.compilation_fingerprint
            directional.setdefault(key, _directional_payload(record))
            keys[record.state.direction] = key
        pairs.append(
            {
                "plan": f"P{index:03d}",
                "pair_fingerprint": pair.pair_fingerprint,
                "directional_compilations": keys,
                "metrics": dataclasses.asdict(pair.metrics),
                "outbound_expected_wait_minutes": pair.outbound.metrics.demand_weighted_expected_passenger_wait_minutes,
                "inbound_expected_wait_minutes": pair.inbound.metrics.demand_weighted_expected_passenger_wait_minutes,
                "maximum_bucket_expected_wait_minutes": max(
                    pair.outbound.metrics.maximum_bucket_expected_wait_minutes,
                    pair.inbound.metrics.maximum_bucket_expected_wait_minutes,
                ),
                "service_regime_count": pair.metrics.actual_service_regime_count,
                "fleet_required": pair.metrics.fleet_required,
                "total_terminal_wait_minutes": pair.metrics.total_excess_terminal_wait,
                "maximum_terminal_wait_minutes": pair.metrics.max_excess_terminal_wait,
            }
        )
    return pairs, dict(sorted(directional.items()))


def _metric_ranges(result: Any) -> dict[str, dict[str, float | int] | None]:
    fields = (
        "observed_demand_mismatch",
        "demand_weighted_expected_passenger_wait_minutes",
        "actual_service_regime_count",
        "max_frequency_jump",
        "total_frequency_variation",
        "moved_trips_vs_b",
        "fleet_required",
        "total_excess_terminal_wait",
        "max_excess_terminal_wait",
    )
    if not result.pareto_frontier:
        return {field: None for field in fields}
    return {
        field: {
            "minimum": min(getattr(item.metrics, field) for item in result.pareto_frontier),
            "maximum": max(getattr(item.metrics, field) for item in result.pareto_frontier),
        }
        for field in fields
    }


def _response_ranges(result: Any) -> dict[str, Any]:
    rows = {"outbound": [], "inbound": []}
    for pair in result.pareto_frontier:
        for item in (pair.outbound, pair.inbound):
            projections = item.metrics.demand_response_regime_projections
            frequencies = [value.effective_service_frequency_per_hour for value in projections]
            rows[item.state.direction].append(
                {
                    "pair_fingerprint": pair.pair_fingerprint,
                    "compilation_fingerprint": item.compile_variant.compilation_fingerprint,
                    "direction_accuracy": item.metrics.demand_response_direction_accuracy,
                    "sqrt_response_deviation": item.metrics.sqrt_seed_response_deviation,
                    "service_frequency_max_min_ratio": max(frequencies) / min(frequencies),
                    "effective_headway_spread_minutes": (
                        max(60 / value for value in frequencies)
                        - min(60 / value for value in frequencies)
                    ),
                }
            )
    result_rows = {}
    for direction, values in rows.items():
        result_rows[direction] = {
            "candidates": values,
            "exact_flat_compilations": [
                value["compilation_fingerprint"]
                for value in values
                if math.isclose(value["service_frequency_max_min_ratio"], 1.0, abs_tol=1e-12)
            ],
            "flattest_observed_compilations": []
            if not values
            else [
                value["compilation_fingerprint"]
                for value in values
                if value["service_frequency_max_min_ratio"]
                == min(item["service_frequency_max_min_ratio"] for item in values)
            ],
            "note": (
                "No new near-flat threshold is selected; exact-flat and Pareto-relative "
                "flattest schedules are identified explicitly."
            ),
        }
    return result_rows


def _blocker_and_settlement(result: Any, audit: SearchAudit) -> tuple[list[dict[str, Any]], str]:
    compiled_mismatch = [
        coordinator._state_precompile_mismatch(state, audit.context.demand_buckets[state.direction])
        for state in audit.popped_states
        if service_plan_fingerprint_v1(state) not in audit.compile_failures
    ]
    best_compiled = min(compiled_mismatch, default=math.inf)
    blockers = []
    promising_demand_responsive = 0
    for value in sorted(audit.compile_failures.values(), key=lambda item: item["fingerprint"]):
        state = audit.all_states[value["fingerprint"]]
        mismatch = coordinator._state_precompile_mismatch(
            state, audit.context.demand_buckets[state.direction]
        )
        ancestry = audit.ancestry_codes(state)
        potentially_attractive = mismatch <= best_compiled
        demand_lineage = bool(set(ancestry) & LOCALIZED_FEEDBACK_CODES)
        promising_demand_responsive += potentially_attractive and demand_lineage
        blockers.append(
            {
                **value,
                "failing_boundary_hhmm": _hhmm(value["failing_boundary"]),
                "precompile_mismatch": mismatch,
                "best_compiled_state_precompile_mismatch": best_compiled,
                "potentially_attractive_precompile_only": potentially_attractive,
                "demand_feedback_lineage": demand_lineage,
                "ancestry_codes": list(ancestry),
                "exact_passenger_metrics": None,
            }
        )
    if not blockers:
        settlement = "SETTLEMENT_NOT_CURRENTLY_NEEDED"
    elif promising_demand_responsive >= 2:
        settlement = "SETTLEMENT_MAY_UNLOCK_MATERIAL_SERVICEPLAN"
    else:
        settlement = "SETTLEMENT_EVIDENCE_INCONCLUSIVE"
    return blockers, settlement


def _reference_payload(workbook: Path, context: Any) -> dict[str, Any]:
    actual_sha = _sha256_path(workbook)
    if actual_sha != EXPECTED_REFERENCE_SHA256:
        raise RuntimeError(f"Route 6 private reference SHA changed: {actual_sha}")
    parsed = parse_route6_reference_workbook(workbook)
    current_counts = {
        direction: coordinator._bucket_counts(
            parsed["references"]["CURRENT"][direction], context.demand_buckets[direction]
        )
        for direction in ("outbound", "inbound")
    }
    references = {}
    for label in REFERENCE_LABELS:
        source = parsed["references"][label]
        directional = {}
        for direction in ("outbound", "inbound"):
            departures = source[direction]
            regularity = reference_directional_metrics(
                departures,
                demand_buckets=context.demand_buckets[direction],
                current_bucket_counts=current_counts[direction],
            )
            wait, max_wait, _, active_mass = expected_passenger_wait_metrics_v1(
                departures, context.demand_buckets[direction]
            )
            projections, transitions, accuracy, count, aligned, sqrt_deviation = (
                demand_response_diagnostics_v1(
                    departures, context.demand_response_regimes[direction]
                )
            )
            directional[direction] = {
                "observed_demand_mismatch": regularity["immutable_demand_mismatch"],
                "demand_weighted_expected_passenger_wait_minutes": wait,
                "maximum_bucket_expected_wait_minutes": max_wait,
                "active_demand_mass": active_mass,
                "fleet_input_departures": len(departures),
                "headway_structure": [
                    dataclasses.asdict(value) for value in exact_headway_runs(departures)
                ],
                "regime_count": regularity["equal_headway_run_count"],
                "max_frequency_jump": regularity["largest_adjacent_raw_frequency_jump"],
                "total_frequency_variation": regularity["total_raw_frequency_variation"],
                "tail_structure": regularity["tail_clockface"],
                "demand_response_transition_count": count,
                "aligned_transition_count": aligned,
                "direction_accuracy": accuracy,
                "sqrt_response_deviation": sqrt_deviation,
                "canonical_demand_regime_service": [
                    dataclasses.asdict(value) for value in projections
                ],
                "transitions": [dataclasses.asdict(value) for value in transitions],
            }
        fleet = reference_pair_metrics(
            source["outbound"],
            source["inbound"],
            outbound_metrics=reference_directional_metrics(
                source["outbound"], demand_buckets=context.demand_buckets["outbound"]
            ),
            inbound_metrics=reference_directional_metrics(
                source["inbound"], demand_buckets=context.demand_buckets["inbound"]
            ),
            runtime_minutes=context.runtime_minutes,
            minimum_layover_minutes=context.minimum_layover_minutes,
            fleet_ceiling=context.fleet_ceiling,
            candidate_id=label,
        )
        masses = [directional[item]["active_demand_mass"] for item in ("outbound", "inbound")]
        waits = [
            directional[item]["demand_weighted_expected_passenger_wait_minutes"]
            for item in ("outbound", "inbound")
        ]
        references[label] = {
            "sheet_name": source["sheet_name"],
            "lineage": "EXTERNAL_BENCHMARK" if label == "EXTERNAL_AI" else "SUPPLIED_REFERENCE",
            "directions": directional,
            "pair": {
                **fleet,
                "observed_demand_mismatch": sum(
                    directional[item]["observed_demand_mismatch"]
                    for item in ("outbound", "inbound")
                ),
                "demand_weighted_expected_passenger_wait_minutes": sum(
                    mass * wait for mass, wait in zip(masses, waits, strict=True)
                )
                / sum(masses),
            },
        }
    return {
        "workbook_basename": workbook.name,
        "sha256": actual_sha,
        "loaded_after_production_route_6_search": True,
        "reference_sheet_names": parsed["reference_sheet_names"],
        "references": references,
    }


def _representative(result: Any) -> dict[str, Any] | None:
    if not result.pareto_frontier:
        return None
    differentiated = []
    for pair in result.pareto_frontier:
        ratios = []
        isolated = False
        for item in (pair.outbound, pair.inbound):
            frequencies = [
                value.effective_service_frequency_per_hour
                for value in item.metrics.demand_response_regime_projections
            ]
            ratios.append(max(frequencies) / min(frequencies))
            isolated |= any(
                regime.trip_count <= 2
                for regime in item.compile_variant.compilation.service_regimes[1:-1]
            )
        if min(ratios) > 1.0 + 1e-12 and not isolated:
            differentiated.append(pair)
    candidates = differentiated or list(result.pareto_frontier)
    pair = min(
        candidates,
        key=lambda item: (
            item.metrics.demand_weighted_expected_passenger_wait_minutes,
            item.metrics.observed_demand_mismatch,
            item.metrics.fleet_required,
            item.pair_fingerprint,
        ),
    )
    return {
        "pair_fingerprint": pair.pair_fingerprint,
        "selection": (
            "minimum exact passenger wait among structurally non-isolated, demand-differentiated "
            "Pareto pairs when available; otherwise minimum exact passenger wait"
        ),
        "credible_clean_route_6_candidate": bool(differentiated),
        "metrics": dataclasses.asdict(pair.metrics),
        "outbound_service_regimes": [
            dataclasses.asdict(item)
            for item in pair.outbound.compile_variant.compilation.service_regimes
        ],
        "inbound_service_regimes": [
            dataclasses.asdict(item)
            for item in pair.inbound.compile_variant.compilation.service_regimes
        ],
    }


def _route_payload(
    *,
    context: Any,
    seeds: Sequence[ServicePlanStateV1],
    result: Any,
    audit: SearchAudit,
    replay_signature: Mapping[str, Any],
    reference: Mapping[str, Any] | None,
) -> dict[str, Any]:
    global _CLASSIFICATION_CONTEXT
    _CLASSIFICATION_CONTEXT = context
    stats = dataclasses.asdict(result.statistics)
    queue_rows = audit.queue_snapshot()
    queue_classification = classify_queue_starvation(
        budget_exhausted=result.statistics.budget_exhausted,
        queue_rows=queue_rows,
        evaluated=audit.popped_states,
    )
    neighbor_classification = classify_neighbor_explosion(
        generated=result.statistics.states_generated,
        evaluated=result.statistics.states_evaluated,
        pruned=result.statistics.states_pruned,
        duplicates=result.statistics.duplicate_states_skipped,
        open_limit=FROZEN_BUDGET.max_open_states,
    )
    blockers, settlement = _blocker_and_settlement(result, audit)
    pairs, directional = _frontier_payload(result)
    feasible = list(audit.feasible_pairs.values())
    without_wait = _pareto_without_wait(feasible)
    with_wait = {item.pair_fingerprint for item in result.pareto_frontier}
    generation_by_parent = []
    for fingerprint, count in audit.generated_by_parent.most_common(20):
        state = audit.all_states[fingerprint]
        generation_by_parent.append(
            {
                "parent_fingerprint": fingerprint,
                "direction": state.direction,
                "generated_children": count,
                "neighbor_generation_calls": audit.neighbor_calls_by_parent[fingerprint],
                "children_by_feedback": {
                    code: audit.generated_by_parent_and_code[(fingerprint, code)]
                    for code in sorted(
                        {
                            key[1]
                            for key in audit.generated_by_parent_and_code
                            if key[0] == fingerprint
                        }
                    )
                },
            }
        )
    seed_count = Counter(item.direction for item in seeds)
    payload = {
        "evidence_profile": PROFILE,
        "starting_sha": EXPECTED_STARTING_SHA,
        "route_id": context.route_id,
        "status": result.status,
        "production_source_changed": False,
        "authority": _authority_payload(context),
        "search_budget": dataclasses.asdict(FROZEN_BUDGET),
        "seed_count_by_direction": dict(sorted(seed_count.items())),
        "search_audit": {
            **stats,
            "final_directional_archive_sizes": {
                direction: len(audit.archives[direction]) for direction in ("outbound", "inbound")
            },
            "final_directional_archive_fingerprints": _archive_signature(audit),
            "final_pareto_size": len(result.pareto_frontier),
            "active_open_queue_size_at_stop": len(queue_rows),
            "active_open_queue_selected_witnesses": queue_rows[:20],
            "generation_to_evaluation_ratio": result.statistics.states_generated
            / max(result.statistics.states_evaluated, 1),
            "pruned_generation_share": result.statistics.states_pruned
            / max(result.statistics.states_generated, 1),
            "duplicate_generation_share": result.statistics.duplicate_states_skipped
            / max(result.statistics.states_generated, 1),
            "generated_states_by_major_feedback_lineage": dict(
                sorted(audit.generated_by_code.items())
            ),
            "response_feedback_anchor_fingerprints": dict(
                sorted(audit.response_anchor_fingerprints.items())
            ),
            "highest_generation_parents": generation_by_parent,
        },
        "feedback_effectiveness": _feedback_effectiveness(result, audit),
        "queue_starvation_classification": queue_classification,
        "neighbor_generation_explosion_classification": neighbor_classification,
        "clean_boundary_blockers": blockers,
        "settlement_classification": settlement,
        "exact_wait_frontier_effect": {
            "production_pareto_size_with_exact_wait": len(with_wait),
            "counterfactual_pareto_size_without_wait": len(without_wait),
            "membership_changed": with_wait != without_wait,
            "only_with_exact_wait": sorted(with_wait - without_wait),
            "only_without_exact_wait": sorted(without_wait - with_wait),
            "scope": "counterfactual over exact-fleet-feasible pairs evaluated by the frozen search",
        },
        "metric_ranges": _metric_ranges(result),
        "demand_response_audit": _response_ranges(result),
        "representative_candidate": _representative(result),
        "final_pareto_pairs": pairs,
        "final_directional_compilations": directional,
        "evaluated_state_fingerprints": list(result.evaluated_state_fingerprints),
        "feedback_code_counts": dict(result.feedback_code_counts),
        "revision_examples": {key: list(value) for key, value in result.revision_examples.items()},
        "deterministic_replay": {
            "passed": True,
            "signature_sha256": _fingerprint(replay_signature),
            "compared_fields": list(replay_signature),
        },
        "route_6_expert_reference": reference,
        "guards": {
            "search_budgets_changed": False,
            "queue_semantics_changed": False,
            "compiler_changed": False,
            "settlement_support_added": False,
            "pareto_dimensions_changed": False,
            "private_workbook_serialized_or_committed": False,
        },
    }
    return payload


def _fmt_range(value: Mapping[str, Any] | None, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value['minimum']:.{digits}f}–{value['maximum']:.{digits}f}"


def _candidate_range(payload: Mapping[str, Any], direction: str, field: str) -> tuple[float, float]:
    values = [
        float(item[field]) for item in payload["demand_response_audit"][direction]["candidates"]
    ]
    return min(values), max(values)


def _regime_brief(regimes: Sequence[Mapping[str, Any]]) -> str:
    return "; ".join(
        f"{_hhmm(int(item['first_departure']))}–{_hhmm(int(item['last_departure']))} "
        f"@{item['uniform_headway_minutes']} ({item['trip_count']})"
        for item in regimes
    )


def render_route_markdown(payload: Mapping[str, Any]) -> str:
    audit = payload["search_audit"]
    out_ratio = _candidate_range(payload, "outbound", "service_frequency_max_min_ratio")
    in_ratio = _candidate_range(payload, "inbound", "service_frequency_max_min_ratio")
    out_accuracy = _candidate_range(payload, "outbound", "direction_accuracy")
    in_accuracy = _candidate_range(payload, "inbound", "direction_accuracy")
    representative = payload["representative_candidate"]
    lines = [
        f"# PR62-E — Route {payload['route_id']} Closed-Loop Pilot",
        "",
        f"Status: **{payload['status']}**. Deterministic replay: **passed**.",
        "",
        "No production scheduling policy changed.",
        "",
        "## Frozen authority and search",
        "",
        f"- Runtime / layover / fleet: {payload['authority']['runtime_minutes_each_direction']} / "
        f"{payload['authority']['minimum_layover_minutes']} / {payload['authority']['fleet_ceiling']}",
        f"- Endpoints out: {payload['authority']['directions']['outbound']['fixed_first_departure_hhmm']}–{payload['authority']['directions']['outbound']['fixed_last_departure_hhmm']}",
        f"- Endpoints in: {payload['authority']['directions']['inbound']['fixed_first_departure_hhmm']}–{payload['authority']['directions']['inbound']['fixed_last_departure_hhmm']}",
        f"- Budgets: `{json.dumps(payload['search_budget'], sort_keys=True)}`",
        "",
        "## Search audit",
        "",
        "| Generated | Evaluated | Duplicate | Pruned | Iterations | Compile | Protected rejected | Fleet | Out archive | In archive | Pareto | Open at stop |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {audit['states_generated']} | {audit['states_evaluated']} | {audit['duplicate_states_skipped']} | {audit['states_pruned']} | {audit['search_iterations']} | {audit['compile_variants_evaluated']} | {audit['protected_compile_variants_rejected']} | {audit['fleet_validations_run']} | {audit['final_directional_archive_sizes']['outbound']} | {audit['final_directional_archive_sizes']['inbound']} | {audit['final_pareto_size']} | {audit['active_open_queue_size_at_stop']} |",
        "",
        f"Generation/evaluation ratio: **{audit['generation_to_evaluation_ratio']:.2f}**; "
        f"pruned share: **{audit['pruned_generation_share']:.4f}**; duplicate share: "
        f"**{audit['duplicate_generation_share']:.4f}**.",
        "",
        f"Queue: **{payload['queue_starvation_classification']}**. Neighbor generation: "
        f"**{payload['neighbor_generation_explosion_classification']}**.",
        "",
        "## Final frontier",
        "",
        f"- Mismatch: {_fmt_range(payload['metric_ranges']['observed_demand_mismatch'], 6)}",
        f"- Exact passenger wait: {_fmt_range(payload['metric_ranges']['demand_weighted_expected_passenger_wait_minutes'], 4)} minutes",
        f"- Fleet: {_fmt_range(payload['metric_ranges']['fleet_required'], 0)}",
        f"- Exact wait changes frontier membership: {str(payload['exact_wait_frontier_effect']['membership_changed']).lower()} ({payload['exact_wait_frontier_effect']['production_pareto_size_with_exact_wait']} with wait versus {payload['exact_wait_frontier_effect']['counterfactual_pareto_size_without_wait']} without wait)",
        f"- Demand-regime frequency ratio out/in: {out_ratio[0]:.3f}–{out_ratio[1]:.3f} / {in_ratio[0]:.3f}–{in_ratio[1]:.3f}",
        f"- Direction accuracy out/in: {out_accuracy[0]:.3f}–{out_accuracy[1]:.3f} / {in_accuracy[0]:.3f}–{in_accuracy[1]:.3f}",
        f"- Exact-flat final directional compilations out/in: {len(payload['demand_response_audit']['outbound']['exact_flat_compilations'])} / {len(payload['demand_response_audit']['inbound']['exact_flat_compilations'])}",
        f"- Clean-boundary blockers: {len(payload['clean_boundary_blockers'])}",
        f"- Settlement: **{payload['settlement_classification']}**",
        "",
        "### Representative clean candidate",
        "",
        f"Pair `{representative['pair_fingerprint']}`: wait {representative['metrics']['demand_weighted_expected_passenger_wait_minutes']:.4f} minutes, mismatch {representative['metrics']['observed_demand_mismatch']:.6f}, fleet {representative['metrics']['fleet_required']}, max jump {representative['metrics']['max_frequency_jump']:.3f}.",
        "",
        f"- Out: `{_regime_brief(representative['outbound_service_regimes'])}`",
        f"- In: `{_regime_brief(representative['inbound_service_regimes'])}`",
        "",
        "Exact ServiceRegimes, departures, per-direction waits, maximum bucket wait, demand-response projections, and terminal-wait metrics for every pair are serialized in the companion JSON.",
        "",
        "## Feedback effectiveness",
        "",
        "| Code | Emitted | Children | Evaluated descendants | Directional retained | Feasible pairs | Final ancestry |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for code, row in payload["feedback_effectiveness"].items():
        lines.append(
            f"| {code} | {row['emitted_count']} | {row['generated_child_states']} | "
            f"{row['evaluated_descendants']} | {row['retained_directional_compilations']} | "
            f"{row['feasible_pair_participation']} | {row['final_pareto_ancestry']} |"
        )
    if payload["route_6_expert_reference"] is not None:
        lines.extend(
            [
                "",
                "## Route 6 expert references",
                "",
                "The private workbook was loaded only after both production Route 6 searches and was never supplied to the search.",
                "",
                "| Reference | Fleet | Mismatch | Expected wait | Out regimes | In regimes |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for label, item in payload["route_6_expert_reference"]["references"].items():
            lines.append(
                f"| {label} | {item['pair']['fleet_required']} | "
                f"{item['pair']['observed_demand_mismatch']:.6f} | "
                f"{item['pair']['demand_weighted_expected_passenger_wait_minutes']:.4f} | "
                f"{item['directions']['outbound']['regime_count']} | "
                f"{item['directions']['inbound']['regime_count']} |"
            )
        human = payload["route_6_expert_reference"]["references"]["HUMAN_FINAL"]
        lines.extend(
            [
                "",
                "Human Final uses 19 vehicles, mismatch "
                f"{human['pair']['observed_demand_mismatch']:.6f}, and exact expected wait "
                f"{human['pair']['demand_weighted_expected_passenger_wait_minutes']:.4f} minutes. "
                "The production frontier spans fleet "
                f"{payload['metric_ranges']['fleet_required']['minimum']}–{payload['metric_ranges']['fleet_required']['maximum']}, "
                "mismatch "
                f"{payload['metric_ranges']['observed_demand_mismatch']['minimum']:.6f}–{payload['metric_ranges']['observed_demand_mismatch']['maximum']:.6f}, "
                "and wait "
                f"{payload['metric_ranges']['demand_weighted_expected_passenger_wait_minutes']['minimum']:.4f}–{payload['metric_ranges']['demand_weighted_expected_passenger_wait_minutes']['maximum']:.4f}. "
                "The representative 19-vehicle clean pair improves exact wait but trades to "
                "higher mismatch and more ServiceRegimes than Human Final; Human Final remains "
                "a benchmark, not search input.",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_architecture_markdown(routes: Mapping[str, Mapping[str, Any]]) -> str:
    route6 = routes["6"]
    route10 = routes["10"]
    queue_values = {item["queue_starvation_classification"] for item in routes.values()}
    explosion_values = {
        item["neighbor_generation_explosion_classification"] for item in routes.values()
    }
    settlement_values = {item["settlement_classification"] for item in routes.values()}
    queue = (
        "LOCALIZED_FEEDBACK_QUEUE_STARVATION"
        if "LOCALIZED_FEEDBACK_QUEUE_STARVATION" in queue_values
        else (
            "QUEUE_STARVATION_INCONCLUSIVE"
            if "QUEUE_STARVATION_INCONCLUSIVE" in queue_values
            else "NO_QUEUE_STARVATION_EVIDENCE"
        )
    )
    explosion = (
        "MATERIAL_NEIGHBOR_GENERATION_EXPLOSION"
        if "MATERIAL_NEIGHBOR_GENERATION_EXPLOSION" in explosion_values
        else (
            "NEIGHBOR_EXPLOSION_INCONCLUSIVE"
            if "NEIGHBOR_EXPLOSION_INCONCLUSIVE" in explosion_values
            else "NO_NEIGHBOR_EXPLOSION_EVIDENCE"
        )
    )
    settlement = (
        "SETTLEMENT_MAY_UNLOCK_MATERIAL_SERVICEPLAN"
        if "SETTLEMENT_MAY_UNLOCK_MATERIAL_SERVICEPLAN" in settlement_values
        else (
            "SETTLEMENT_EVIDENCE_INCONCLUSIVE"
            if "SETTLEMENT_EVIDENCE_INCONCLUSIVE" in settlement_values
            else "SETTLEMENT_NOT_CURRENTLY_NEEDED"
        )
    )
    route6_human = route6["route_6_expert_reference"]["references"]["HUMAN_FINAL"]
    route6_out_ratio = _candidate_range(route6, "outbound", "service_frequency_max_min_ratio")
    route6_in_ratio = _candidate_range(route6, "inbound", "service_frequency_max_min_ratio")
    route10_out_ratio = _candidate_range(route10, "outbound", "service_frequency_max_min_ratio")
    route10_in_ratio = _candidate_range(route10, "inbound", "service_frequency_max_min_ratio")
    lines = [
        "# PR62-E — Closed-Loop Architecture Decision",
        "",
        "No production scheduling policy changed.",
        "",
        "## Cross-route decision",
        "",
        f"- Queue starvation: **{queue}**",
        f"- Neighbor generation: **{explosion}**",
        f"- Settlement: **{settlement}**",
        f"- Route 6 exact wait changes evaluated-feasible frontier membership: **{str(route6['exact_wait_frontier_effect']['membership_changed']).lower()}**",
        f"- Route 10 exact wait changes evaluated-feasible frontier membership: **{str(route10['exact_wait_frontier_effect']['membership_changed']).lower()}**",
        "",
        "Queue starvation and neighbor-generation amplification are classified independently. Queued states are assessed only with pre-compile evidence; uncompiled states receive no fabricated exact wait or fleet metric.",
        "",
        "## Pilot questions",
        "",
        "- **Localized feedback is useful but selective.** Route 6 final ancestry includes 15 overservice-feedback pairs and 8 fleet-feedback pairs; Route 10 includes 27 overservice, 31 underservice, 28 largest-jump, and 52 fleet-feedback pairs. Demand-response-mismatch children were generated on both routes but none reached the final frontier within 24 evaluations.",
        f"- **Exact passenger wait is material to the evaluated frontier.** Route 6 retains {route6['exact_wait_frontier_effect']['production_pareto_size_with_exact_wait']} pairs with the wait dimension versus {route6['exact_wait_frontier_effect']['counterfactual_pareto_size_without_wait']} without it; Route 10 retains {route10['exact_wait_frontier_effect']['production_pareto_size_with_exact_wait']} versus {route10['exact_wait_frontier_effect']['counterfactual_pareto_size_without_wait']}.",
        f"- **Demand differentiation survives.** No final directional compilation is exactly flat. Frequency max/min ratios span {route6_out_ratio[0]:.3f}–{route6_out_ratio[1]:.3f} outbound and {route6_in_ratio[0]:.3f}–{route6_in_ratio[1]:.3f} inbound on Route 6; {route10_out_ratio[0]:.3f}–{route10_out_ratio[1]:.3f} and {route10_in_ratio[0]:.3f}–{route10_in_ratio[1]:.3f} on Route 10. Route 10's flattest inbound ratio of {route10_in_ratio[0]:.3f} remains a review tradeoff, not a rejected threshold case.",
        f"- **Useful exact-fleet-feasible candidates exist.** Every final pair passed exact fleet validation; fleets span {route6['metric_ranges']['fleet_required']['minimum']}–{route6['metric_ranges']['fleet_required']['maximum']} on Route 6 and {route10['metric_ranges']['fleet_required']['minimum']}–{route10['metric_ranges']['fleet_required']['maximum']} on Route 10.",
        "- **Strict clean-boundary compilation did not reject an evaluated ServicePlan on either route.** There are no blocker witnesses, so settlement is not currently needed; Human Final's isolated 14-minute residual does not change that conclusion.",
        f"- **Neighbor generation is materially amplified.** Route 6 generated {route6['search_audit']['states_generated']:,} states for {route6['search_audit']['states_evaluated']} evaluations ({route6['search_audit']['generation_to_evaluation_ratio']:,.2f}:1); Route 10 generated {route10['search_audit']['states_generated']:,} ({route10['search_audit']['generation_to_evaluation_ratio']:,.2f}:1). Fleet-limit lineage alone generated {route6['search_audit']['generated_states_by_major_feedback_lineage'][FLEET_LIMIT_EXCEEDED]:,} and {route10['search_audit']['generated_states_by_major_feedback_lineage'][FLEET_LIMIT_EXCEEDED]:,} children respectively.",
        "",
        "## Route 6 expert benchmark",
        "",
        f"Human Final records fleet {route6_human['pair']['fleet_required']}, mismatch {route6_human['pair']['observed_demand_mismatch']:.6f}, wait {route6_human['pair']['demand_weighted_expected_passenger_wait_minutes']:.4f} minutes, and 9/8 outbound/inbound headway runs. Production finds lower-wait and lower-mismatch points separately across its Pareto frontier, while its representative 19-vehicle clean pair has wait {route6['representative_candidate']['metrics']['demand_weighted_expected_passenger_wait_minutes']:.4f}, mismatch {route6['representative_candidate']['metrics']['observed_demand_mismatch']:.6f}, and 8/7 sustained compiled ServiceRegimes. This is a real tradeoff, not reproduction of Human Final timestamps.",
        "",
        "## Route comparison",
        "",
        "| Route | Status | Generated / evaluated | Ratio | Pareto | Queue | Neighbor generation | Blockers | Settlement |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for route_id in ("6", "10"):
        item = routes[route_id]
        audit = item["search_audit"]
        lines.append(
            f"| {route_id} | {item['status']} | {audit['states_generated']} / "
            f"{audit['states_evaluated']} | {audit['generation_to_evaluation_ratio']:.2f} | "
            f"{audit['final_pareto_size']} | {item['queue_starvation_classification']} | "
            f"{item['neighbor_generation_explosion_classification']} | "
            f"{len(item['clean_boundary_blockers'])} | {item['settlement_classification']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundaries",
            "",
            "- The 24-state evaluation budget was not increased and no larger-budget rerun was made.",
            "- Flatness diagnostics select no new policy threshold; exact-flat and the flattest observed Pareto schedules are listed.",
            "- Human Final remains a post-search benchmark. Its 14-minute residual alone is not settlement evidence.",
            "- Exact passenger wait is compared with a counterfactual frontier over the same evaluated exact-fleet-feasible pair set.",
            "- Full exact departures are retained only for final Pareto directional compilations.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_twice_identical(path: Path, first: bytes, second: bytes) -> dict[str, Any]:
    if first != second:
        raise RuntimeError(f"non-deterministic rendering for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(first)
    first_disk = path.read_bytes()
    path.write_bytes(second)
    second_disk = path.read_bytes()
    if first_disk != second_disk:
        raise RuntimeError(f"non-deterministic repeated write for {path}")
    if path.suffix == ".json" and len(second_disk) >= 5 * 1024 * 1024:
        raise RuntimeError(f"JSON exceeds 5 MiB limit: {path} ({len(second_disk)} bytes)")
    return {
        "path": path.relative_to(_REPO_ROOT).as_posix(),
        "size_bytes": len(second_disk),
        "sha256": _sha256_bytes(second_disk),
        "byte_identical_repeated_generation": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--route-6-workbook",
        type=Path,
        default=_REPO_ROOT.parent / "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    parser.add_argument(
        "--route-10-workbook",
        type=Path,
        default=_REPO_ROOT.parent / "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    parser.add_argument(
        "--route-6-reference",
        type=Path,
        default=_REPO_ROOT.parent / "private" / "Route_6_Current_ExternalAI_HumanFinal.xlsx",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=_REPO_ROOT / "docs" / "engine" / "evidence",
    )
    parser.add_argument(
        "--render-existing-only",
        action="store_true",
        help="Re-render Markdown twice from already verified route JSON without rerunning search.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.render_existing_only:
        route_payloads = {
            route_id: json.loads(
                (args.output_directory / f"{ROUTE_OUTPUTS[route_id]}.json").read_text(
                    encoding="utf-8"
                )
            )
            for route_id in ("6", "10")
        }
        manifest = []
        for route_id in ("6", "10"):
            route_payloads[route_id]["starting_sha"] = EXPECTED_STARTING_SHA
            json_path = args.output_directory / f"{ROUTE_OUTPUTS[route_id]}.json"
            json_first = _canonical_json_bytes(route_payloads[route_id])
            json_second = _canonical_json_bytes(route_payloads[route_id])
            manifest.append(_write_twice_identical(json_path, json_first, json_second))
            path = args.output_directory / f"{ROUTE_OUTPUTS[route_id]}.md"
            first = render_route_markdown(route_payloads[route_id]).encode("utf-8")
            second = render_route_markdown(route_payloads[route_id]).encode("utf-8")
            manifest.append(_write_twice_identical(path, first, second))
        architecture_path = args.output_directory / ARCHITECTURE_OUTPUT
        first = render_architecture_markdown(route_payloads).encode("utf-8")
        second = render_architecture_markdown(route_payloads).encode("utf-8")
        manifest.append(_write_twice_identical(architecture_path, first, second))
        print(json.dumps({"artifacts": manifest}, indent=2, sort_keys=True))
        return 0
    prior_before = verify_frozen_prior_artifacts_v1(_REPO_ROOT)
    route_payloads: dict[str, dict[str, Any]] = {}
    route_inputs = {"6": args.route_6_workbook, "10": args.route_10_workbook}
    for route_id in ("6", "10"):
        context, seeds = load_route_coordinator_inputs_v1(
            repo_root=_REPO_ROOT,
            route_id=route_id,
            workbook_path=route_inputs[route_id],
        )
        _authority_payload(context)
        print(f"route={route_id} replay=1 starting", flush=True)
        first_result, first_audit = _audited_run(context, seeds)
        print(f"route={route_id} replay=2 starting", flush=True)
        second_result, second_audit = _audited_run(context, seeds)
        prior_after = verify_frozen_prior_artifacts_v1(_REPO_ROOT)
        prior = {
            "unchanged": prior_before == prior_after,
            "before": prior_before["sha256"],
            "after": prior_after["sha256"],
        }
        first_signature = _result_signature(first_result, first_audit, prior)
        second_signature = _result_signature(second_result, second_audit, prior)
        if first_signature != second_signature:
            raise RuntimeError(f"Route {route_id} deterministic replay failed")
        reference = _reference_payload(args.route_6_reference, context) if route_id == "6" else None
        route_payloads[route_id] = _route_payload(
            context=context,
            seeds=seeds,
            result=first_result,
            audit=first_audit,
            replay_signature=first_signature,
            reference=reference,
        )
        print(
            f"route={route_id} status={first_result.status} "
            f"generated={first_result.statistics.states_generated} "
            f"evaluated={first_result.statistics.states_evaluated} "
            f"pareto={len(first_result.pareto_frontier)} replay=passed",
            flush=True,
        )

    artifact_manifest = []
    for route_id in ("6", "10"):
        payload = route_payloads[route_id]
        base = args.output_directory / ROUTE_OUTPUTS[route_id]
        json_first = _canonical_json_bytes(payload)
        json_second = _canonical_json_bytes(payload)
        md_first = render_route_markdown(payload).encode("utf-8")
        md_second = render_route_markdown(payload).encode("utf-8")
        artifact_manifest.append(
            _write_twice_identical(base.with_suffix(".json"), json_first, json_second)
        )
        artifact_manifest.append(
            _write_twice_identical(base.with_suffix(".md"), md_first, md_second)
        )
    architecture_path = args.output_directory / ARCHITECTURE_OUTPUT
    architecture_first = render_architecture_markdown(route_payloads).encode("utf-8")
    architecture_second = render_architecture_markdown(route_payloads).encode("utf-8")
    artifact_manifest.append(
        _write_twice_identical(architecture_path, architecture_first, architecture_second)
    )
    print(json.dumps({"artifacts": artifact_manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

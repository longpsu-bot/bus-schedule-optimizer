"""Explicit, non-authoritative PR62-U6 certification; never an application entry point."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from bus_schedule_engine import kbest_shadow_refinement as shadow
from bus_schedule_engine import service_plan_coordinator as coordinator
from bus_schedule_engine.contracts_v1.clean_boundary_compiler import OperationalEndpointAuthorityV1
from bus_schedule_engine.contracts_v1.kbest_dag_frontier import (
    compile_service_plan_family_kbest_v1,
    kbest_dag_candidate_payload_v1,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy_v3 import (
    select_operational_timetable_v3,
)
from bus_schedule_engine.contracts_v1.service_plan_state import (
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    service_plan_fingerprint_v1,
)

ROUTE10_PATH = Path(
    "E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u/"
    ".pr62-u-local/certification/route_10_complete_base.pickle"
)
ROUTE10_SHA256 = "d2ba609ffd8fa4450e0a0662a0c9255dcdf1d8d2b759e63a8de6cf44fbfb114b"
ROUTE10_BASE = "6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16"
ROUTE10_SOURCE = "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24"
U5_FIXTURE_SHA256 = "1b65a2f34c6bf06e9e2b94a8371e1e2d447b1e1b6fd2464510e7cd9066294a0f"
U5_RAW_SHA256 = "71092c883923e6d5460980a8c528f263a275255986e887bb03c3c1ef16c17601"
FROZEN_BUDGET = coordinator.CoordinatorSearchBudgetV1(24, 512, 4, 24, 512)
EVIDENCE_JSON = "PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json"
EVIDENCE_MD = "PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md"


class CertificationError(RuntimeError):
    """A certification gate failed; callers must not launch the next stage."""


def require(condition: bool, classification: str) -> None:
    if not condition:
        raise CertificationError(classification)


def canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def semantic_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)


@contextmanager
def zero_global_calls():
    """Make any accidental coordinator invocation fail before it executes."""
    original = coordinator.search_route_service_plans_v1
    observed = {"global_coordinator_executions": 0}

    def forbidden(*args, **kwargs):
        observed["global_coordinator_executions"] += 1
        raise CertificationError("U6_ROUTE10_GLOBAL_CALL_PROHIBITED")

    coordinator.search_route_service_plans_v1 = forbidden
    try:
        yield observed
    finally:
        coordinator.search_route_service_plans_v1 = original


@dataclass(frozen=True, slots=True)
class LoadedRoute10:
    context: Any
    base: Any
    selection: Any
    input_authority: dict[str, Any]
    global_coordinator_executions: int = 0


def certify_route10_base(context: Any, base: Any):
    label = "U6_ROUTE10_GLOBAL_BASE_MISMATCH"
    require(
        isinstance(context, coordinator.RouteCoordinatorContextV1)
        and isinstance(base, coordinator.RouteCoordinatorResultV1)
        and context.route_id == "10"
        and base.search_budget == FROZEN_BUDGET
        and len(base.pareto_frontier) == 11,
        label,
    )
    selection = select_operational_timetable_v3(context=context, candidates=base.pareto_frontier)
    require(
        selection.passenger_access_safe_count == 7
        and selection.selected_pair_fingerprint == ROUTE10_BASE
        and ROUTE10_SOURCE in selection.phase_robust_materiality_fingerprints,
        label,
    )
    return selection


def load_route10_saved_result(path: Path) -> LoadedRoute10:
    label = "U6_ROUTE10_SAVED_BASE_AUTHORITY_MISMATCH"
    require(path.resolve() == ROUTE10_PATH.resolve(), label)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    require(len(data) == 70577 and digest == ROUTE10_SHA256, label)
    # Deserialize the exact bytes already verified; never reopen after checking.
    with zero_global_calls():
        context, base = pickle.loads(data)
        selection = certify_route10_base(context, base)
    return LoadedRoute10(
        context,
        base,
        selection,
        {
            "path": path.resolve().as_posix(),
            "size": len(data),
            "sha256": digest,
            "context_sha256": semantic_hash(asdict(context)),
            "demand_sha256": context.immutable_demand_sha256,
            "endpoint_authority": {k: asdict(v) for k, v in context.endpoint_authority.items()},
            "global_budget": asdict(base.search_budget),
        },
    )


def run_parity(fixture_path: Path) -> dict[str, Any]:
    label = "U6_PRODUCTION_PORT_DIVERGED_FROM_U5"
    data = fixture_path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == U5_FIXTURE_SHA256, label)
    payload = json.loads(data)
    states = tuple(
        ServicePlanStateV1(
            **{
                **row,
                "service_regimes": tuple(
                    ServiceRegimeDecisionV1(**r) for r in row["service_regimes"]
                ),
            }
        )
        for row in payload["states"]
    )
    result = compile_service_plan_family_kbest_v1(
        states=states,
        endpoint_authority=OperationalEndpointAuthorityV1(**payload["endpoint_authority"]),
        raw_limit=256,
    )
    indices = {
        service_plan_fingerprint_v1(s): i
        for i, s in enumerate(sorted(states, key=service_plan_fingerprint_v1))
    }
    records = [
        kbest_dag_candidate_payload_v1(c, state_index=indices[c.state_fingerprint])
        for c in result.candidates
    ]
    tiers = []
    for row in records:
        if row["integer_objective"] not in tiers:
            tiers.append(row["integer_objective"])
    decorated = [
        {
            **row,
            "tier_index": tiers.index(row["integer_objective"]),
            "delta_from_tier0": [
                v - b
                for v, b in zip(
                    row["integer_objective"], records[0]["integer_objective"], strict=True
                )
            ],
            "unscaled_quantization": row["objective"][0],
        }
        for row in records
    ]
    encoded = (
        json.dumps(decorated, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    require(
        len(states) == 49
        and len(records) == 256
        and records[0]["fingerprint"]
        == "8e06dbcafc0194e5d338bc96b28569825bff30a79f96eaec8b5eda3c778ca7f6"
        and tiers[:3] == [[8214, 7, 74], [9264, 7, 51], [10734, 7, 58]]
        and digest == U5_RAW_SHA256,
        label,
    )
    return {
        "classification": "U5_EXACT_PRODUCTION_PORT_PARITY",
        "fixture_sha256": U5_FIXTURE_SHA256,
        "family_manifest_sha256": payload["family_manifest_sha256"],
        "state_count": len(states),
        "raw_count": len(records),
        "top1_fingerprint": records[0]["fingerprint"],
        "top_objective": records[0]["integer_objective"],
        "first_distinct_objective_tiers": tiers[:3],
        "raw_top256_sha256": digest,
    }


def plain(value: Any) -> Any:
    """Semantic fields only; telemetry and cache provenance cannot influence hashes."""
    if is_dataclass(value):
        return {
            field.name: plain(getattr(value, field.name))
            for field in fields(value)
            if not field.name.endswith("seconds")
            and field.name not in {"telemetry", "cache_key", "cache_hit", "dag_call_count"}
        }
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


@contextmanager
def instrument_shadow_gates():
    """Observe existing authorities and stop before the next phase on a failed gate."""
    started = perf_counter()
    observed = {
        "hard_eligibility_seconds": 0.0,
        "diversity_seconds": 0.0,
        "pair_fleet_seconds": 0.0,
        "pareto_v3_seconds": 0.0,
        "family_generation_seconds": 0.0,
        "dag_seconds": 0.0,
        "max_family_dag_seconds": 0.0,
        "global_coordinator_executions": 0,
        "fleet_valid_pairs": {},
    }
    stage_names = {
        "enumerate_local_rhythm_states_v1": "family_generation_seconds",
        "compile_service_plan_family_kbest_v1": "dag_seconds",
        "evaluate_kbest_dag_hard_eligibility_v1": "hard_eligibility_seconds",
        "retain_kbest_dag_directional_frontier_v1": "diversity_seconds",
        "evaluate_operating_pair_v1": "pair_fleet_seconds",
        "update_operating_pair_pareto_v1": "pareto_v3_seconds",
        "select_operational_timetable_v3": "pareto_v3_seconds",
    }
    originals = {name: getattr(shadow, name) for name in stage_names}

    def wrap(name, original):
        def checked(*args, **kwargs):
            require(perf_counter() - started <= 300, "U6_ROUTE10_SHADOW_OPERATIONALLY_INTRACTABLE")
            before = perf_counter()
            result = original(*args, **kwargs)
            elapsed = perf_counter() - before
            observed[stage_names[name]] += elapsed
            if name == "evaluate_operating_pair_v1" and result[0] is not None:
                pair = result[0]
                require(
                    pair.metrics.fleet_required <= kwargs["context"].fleet_ceiling,
                    "U6_ROUTE10_EXACT_FLEET_CONTRACT_MISMATCH",
                )
                observed["fleet_valid_pairs"].setdefault(pair.pair_fingerprint, _pair_payload(pair))
            if name == "compile_service_plan_family_kbest_v1":
                observed["max_family_dag_seconds"] = max(
                    observed["max_family_dag_seconds"], elapsed
                )
                require(elapsed <= 60, "U6_ROUTE10_FAMILY_DAG_OPERATIONALLY_INTRACTABLE")
            elif name == "evaluate_kbest_dag_hard_eligibility_v1":
                require(
                    result.structural_rejects == 0, "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH"
                )
            elif name == "retain_kbest_dag_directional_frontier_v1":
                require(
                    result.source_rejection != "structural"
                    and result.pre_diversity_truncation_count == 0,
                    "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH",
                )
            require(perf_counter() - started <= 300, "U6_ROUTE10_SHADOW_OPERATIONALLY_INTRACTABLE")
            return result

        return checked

    with zero_global_calls() as calls:
        try:
            for name, original in originals.items():
                setattr(shadow, name, wrap(name, original))
            yield observed
        finally:
            for name, original in originals.items():
                setattr(shadow, name, original)
            observed["global_coordinator_executions"] = calls["global_coordinator_executions"]
            observed["total_seconds"] = perf_counter() - started


def _directional_payload(candidate):
    return {
        "fingerprint": candidate.compile_variant.compilation_fingerprint,
        "state_fingerprint": candidate.state_fingerprint,
        "state": plain(candidate.state),
        "departures": list(candidate.compile_variant.compilation.exact_departures),
        "metrics": plain(candidate.metrics),
    }


def _pair_payload(pair):
    return {
        "fingerprint": pair.pair_fingerprint,
        "outbound": pair.outbound.compile_variant.compilation_fingerprint,
        "inbound": pair.inbound.compile_variant.compilation_fingerprint,
        "metrics": plain(pair.metrics),
        "pareto_vector": list(pair.metrics.pareto_vector),
        "rhythm": list(shadow.pair_rhythm_tuple_v1(pair)),
        "fleet_ceiling": pair.fleet_ceiling,
    }


def _source_once_valid(result):
    order = result.processed_source_pair_fingerprints
    if len(order) != len(set(order)) or len(result.selection_history) != len(order) + 1:
        return False
    queued = set(result.base_v3_selection.phase_robust_materiality_fingerprints)
    processed = set()
    parents = {p.child_fingerprint: p for p in result.generated_pair_parents}
    for index, fingerprint in enumerate(order):
        if not queued or fingerprint != min(queued):
            return False
        queued.remove(fingerprint)
        processed.add(fingerprint)
        source = result.source_refinements[index]
        if source.source_pair_fingerprint != fingerprint:
            return False
        present = {p.pair_fingerprint for p in source.frontier}
        for child in result.selection_history[index + 1].phase_robust_materiality_fingerprints:
            if child in processed or child in queued or child not in present:
                continue
            parent = parents.get(child)
            if parent is not None:
                if (
                    parent.parent_fingerprint not in processed
                    or parent.child_rhythm >= parent.parent_rhythm
                ):
                    return False
                queued.add(child)
    return not queued and all(
        p.child_rhythm < p.parent_rhythm and p.child_fingerprint in order
        for p in result.continuation_history
    )


def project_shadow_result(result, *, context, observed, cap):
    families = []
    sources = []
    family_timings = []
    hard_valid = result.statistics.structural_rejects == 0
    pair_valid = True
    for source in result.source_refinements:
        for family in source.families:
            require(
                family.classification in {"FAMILY_REALIZED", "NO_ENDPOINT_VALID_STATES"},
                "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH",
            )
            raw = []
            eligible = []
            graph = None
            rejects = None
            if family.shadow:
                frontier = family.shadow.frontier
                indices = {fp: i for i, fp in enumerate(family.valid_state_fingerprints)}
                raw = [
                    kbest_dag_candidate_payload_v1(c, state_index=indices[c.state_fingerprint])
                    for c in frontier.candidates
                ]
                eligible = list(family.shadow.eligibility.eligible_fingerprints)
                graph = plain(frontier.graph_statistics)
                rejects = {
                    name: getattr(family.shadow.eligibility, name)
                    for name in (
                        "structural_rejects",
                        "protection_rejects",
                        "tail_rejects",
                        "strict_progress_rejects",
                    )
                }
                require(
                    frontier.requested_raw_limit == 256,
                    "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH",
                )
                family_timings.append(
                    {
                        "source": source.source_pair_fingerprint,
                        "direction": family.direction,
                        "family_index": family.family_index,
                        "total_seconds": family.total_seconds,
                        "dag": asdict(frontier.telemetry),
                        "cache_hit": family.cache_hit,
                        "dag_call_count": family.dag_call_count,
                    }
                )
            families.append(
                {
                    "source": source.source_pair_fingerprint,
                    "direction": family.direction,
                    "family_index": family.family_index,
                    "family": plain(family.family),
                    "planning_indices": list(family.planning_indices),
                    "generated_states": list(family.generated_state_fingerprints),
                    "valid_states": list(family.valid_state_fingerprints),
                    "endpoint_rejected_states": list(family.endpoint_rejected_state_fingerprints),
                    "state_manifest_hash": family.state_manifest_hash,
                    "graph_hash": family.graph_hash,
                    "graph_statistics": graph,
                    "raw_hash": family.raw_hash,
                    "raw": raw,
                    "eligible_hash": family.eligible_hash,
                    "eligible": eligible,
                    "rejects": rejects,
                    "classification": family.classification,
                }
            )
        retentions = []
        for direction, retention in source.directional_retentions:
            hard_valid &= retention.pre_diversity_truncation_count == 0
            hard_valid &= (
                retention.retained_count <= cap and retention.source_rejection != "structural"
            )
            for candidate in retention.candidates:
                validation = shadow.validate_closed_loop_service_protection_v1(
                    authority=context.service_protection_authority,
                    direction=direction,
                    exact_departures=candidate.compile_variant.compilation.exact_departures,
                )
                hard_valid &= validation.passed and candidate.metrics.tail_ordering.eligible
            retentions.append(
                {
                    "direction": direction,
                    **{
                        f.name: plain(getattr(retention, f.name))
                        for f in fields(retention)
                        if f.name not in {"candidates", "selector_seconds"}
                    },
                    "candidates": [_directional_payload(c) for c in retention.candidates],
                }
            )
        decisions = () if source.pair_evaluation is None else source.pair_evaluation.decisions
        for decision in decisions:
            if decision.decision in {"PARETO_ADMITTED", "PARETO_REJECTED"}:
                pair_valid &= (
                    decision.pair_fingerprint is not None
                    and decision.generated_rhythm < decision.source_rhythm
                    and decision.pair_fingerprint in observed["fleet_valid_pairs"]
                )
        sources.append(
            {
                "source": source.source_pair_fingerprint,
                "retentions": retentions,
                "retained_hashes": plain(source.retained_hashes),
                "pair_decisions": plain(decisions),
                "pareto": [_pair_payload(p) for p in source.frontier],
            }
        )
    # Independently rerun unchanged exact pair evaluation for every final admitted identity.
    for pair in result.augmented_pareto_frontier:
        checked, _ = coordinator.evaluate_operating_pair_v1(
            pair.outbound, pair.inbound, context=context
        )
        pair_valid &= checked is not None and checked.pair_fingerprint == pair.pair_fingerprint
        pair_valid &= pair.metrics.fleet_required <= context.fleet_ceiling
    final_pareto = [_pair_payload(p) for p in result.augmented_pareto_frontier]
    statistics = plain(result.statistics)
    statistics.pop("dag_graphs_built")  # Physical cache misses belong only in telemetry.
    semantic = {
        "directional_cap": cap,
        "global_coordinator_executions": observed["global_coordinator_executions"]
        + result.statistics.global_coordinator_executions,
        "processed_source_order": list(result.processed_source_pair_fingerprints),
        "raw_hashes": [f["raw_hash"] for f in families],
        "eligible_hashes": [f["eligible_hash"] for f in families],
        "retained_hashes": [s["retained_hashes"] for s in sources],
        "pair_fingerprints": list(result.generated_pair_fingerprints),
        "fleet_valid_pairs": [
            observed["fleet_valid_pairs"][fp] for fp in sorted(observed["fleet_valid_pairs"])
        ],
        "final_pareto_hash": semantic_hash(final_pareto),
        "final_v3_fingerprint": result.final_v3_selection.selected_pair_fingerprint,
        "source_once": _source_once_valid(result),
        "hard_valid": bool(hard_valid),
        "exact_fleet_valid": bool(pair_valid),
        "statistics": statistics,
        "families": families,
        "sources": sources,
        "base_pareto": [_pair_payload(p) for p in result.base_coordinator_result.pareto_frontier],
        "base_selection": plain(result.base_v3_selection),
        "final_pareto": final_pareto,
        "final_selection": plain(result.final_v3_selection),
        "parents": plain(result.generated_pair_parents),
        "continuations": plain(result.continuation_history),
        "selection_history": plain(result.selection_history),
        "pareto_history": list(result.pareto_history_hashes),
    }
    return {
        "semantic": semantic,
        "semantic_sha256": semantic_hash(semantic),
        "timings": {
            **{k: v for k, v in observed.items() if k != "fleet_valid_pairs"},
            "families": family_timings,
        },
        "execution": {
            "pid": os.getpid(),
            "initial_cache_entries": 0,
            "dag_graphs_built": result.statistics.dag_graphs_built,
        },
    }


def _validate_route10_hard_gates(payload):
    semantic, timings = payload["semantic"], payload["timings"]
    statistics = semantic.get("statistics", {})
    source_order = semantic["processed_source_order"]
    require(
        payload["semantic_sha256"] == semantic_hash(semantic),
        "U6_ROUTE10_SEMANTIC_PAYLOAD_CORRUPTED",
    )
    for condition, label in (
        (
            semantic["global_coordinator_executions"] == 0
            and timings.get("global_coordinator_executions", 0) == 0
            and statistics.get("global_coordinator_executions", 0) == 0,
            "U6_ROUTE10_GLOBAL_CALL_PROHIBITED",
        ),
        (
            semantic["source_once"] and len(source_order) == len(set(source_order)),
            "U6_ROUTE10_SOURCE_ONCE_CONTRACT_MISMATCH",
        ),
        (
            semantic["hard_valid"] and statistics.get("structural_rejects", 0) == 0,
            "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH",
        ),
        (semantic["exact_fleet_valid"], "U6_ROUTE10_EXACT_FLEET_CONTRACT_MISMATCH"),
        (0 <= timings["total_seconds"] <= 300, "U6_ROUTE10_SHADOW_OPERATIONALLY_INTRACTABLE"),
        (
            0 <= timings["max_family_dag_seconds"] <= 60
            and all(
                0 <= family["dag"]["total_seconds"] <= 60 for family in timings.get("families", [])
            ),
            "U6_ROUTE10_FAMILY_DAG_OPERATIONALLY_INTRACTABLE",
        ),
    ):
        require(condition, label)
    if "final_pareto" in semantic:
        require(
            semantic["final_pareto_hash"] == semantic_hash(semantic["final_pareto"])
            and semantic["final_selection"].get("selected_pair_fingerprint")
            == semantic["final_v3_fingerprint"],
            "U6_ROUTE10_SEMANTIC_PAYLOAD_CORRUPTED",
        )


def validate_route10_payload(payload, *, diagnostic_final_selection=False):
    _validate_route10_hard_gates(payload)
    semantic = payload["semantic"]
    require(
        semantic["final_v3_fingerprint"] is not None
        or (
            diagnostic_final_selection
            and semantic.get("final_selection", {}).get("classification")
            == "DEMAND_FIT_ANCHOR_CONFLICT"
        ),
        "U6_ROUTE10_FINAL_V3_SELECTION_UNAVAILABLE",
    )


def _compare_route10_semantics(canonical, repeat):
    require(
        canonical["semantic"] == repeat["semantic"]
        and canonical["semantic_sha256"] == repeat["semantic_sha256"],
        "U6_ROUTE10_SHADOW_NONDETERMINISTIC",
    )


def compare_route10_repeat(canonical, repeat):
    executions = [run.get("execution", {}) for run in (canonical, repeat)]
    artifacts = [run.get("persisted_artifact", {}) for run in (canonical, repeat)]
    require(
        canonical is not repeat
        and all(type(e.get("pid")) is int and e["pid"] > 0 for e in executions)
        and executions[0]["pid"] != executions[1]["pid"]
        and all(e.get("initial_cache_entries") == 0 for e in executions)
        and all(a.get("path") and a.get("sha256") for a in artifacts)
        and Path(artifacts[0]["path"]).resolve() != Path(artifacts[1]["path"]).resolve()
        and artifacts[0]["sha256"] != artifacts[1]["sha256"],
        "U6_ROUTE10_REPEAT_PROVENANCE_INVALID",
    )
    _compare_route10_semantics(canonical, repeat)
    return {
        "identical": True,
        "semantic_sha256": canonical["semantic_sha256"],
        "fresh_process": True,
        "cold_initial_caches": True,
        "canonical_pid": executions[0]["pid"],
        "repeat_pid": executions[1]["pid"],
        "canonical_artifact": artifacts[0],
        "repeat_artifact": artifacts[1],
    }


def validate_route10_sensitivity(sensitivity, *, canonical, port):
    """Recheck saved cases and derive the summary without launching any route stage.

    A saved V3 result may be reused only for an exactly equal normalized frontier.
    If the union is novel, this evidence-only path fails closed: it cannot invent
    a selector result from the summary or run a new Route 10 experiment.
    """
    label = "U6_ROUTE10_SENSITIVITY_AUTHORITY_MISMATCH"
    runs = sensitivity.get("independent_runs", {})
    require(set(runs) == {"16", "32", "64"}, label)
    # All hard/runtime gates take precedence over the provisional selection blocker.
    for run in runs.values():
        _validate_route10_hard_gates(run)
    for cap, run in runs.items():
        require(
            run["semantic"].get("directional_cap") == int(cap)
            and run.get("input_authority") == canonical.get("input_authority")
            and run.get("implementation_authority_sha256")
            == canonical.get("implementation_authority_sha256")
            == port.get("implementation_authority_sha256")
            and run["semantic"].get("base_pareto") == canonical["semantic"].get("base_pareto")
            and run["semantic"].get("base_selection")
            == canonical["semantic"].get("base_selection"),
            label,
        )
    require(
        sensitivity.get("canonical_cap32_semantic_sha256") == canonical["semantic_sha256"],
        "U6_ROUTE10_SHADOW_NONDETERMINISTIC",
    )
    # Sensitivity legitimately shares raw/eligible caches; it is not the cold repeat.
    _compare_route10_semantics(canonical, runs["32"])
    by_fingerprint = {}
    for cap in ("32", "64"):
        for pair in runs[cap]["semantic"]["final_pareto"]:
            previous = by_fingerprint.setdefault(pair["fingerprint"], pair)
            require(previous == pair, label)
    normalized = ()
    for fingerprint in sorted(by_fingerprint):
        pair = by_fingerprint[fingerprint]
        normalized = coordinator.update_operating_pair_pareto_v1(
            normalized,
            SimpleNamespace(
                pair_fingerprint=fingerprint,
                metrics=SimpleNamespace(pareto_vector=tuple(pair["pareto_vector"])),
            ),
            limit=None,
        )
    union = [by_fingerprint[p.pair_fingerprint] for p in normalized]
    require(sensitivity.get("normalized_union") == union, label)
    matching_caps = [cap for cap in ("32", "64") if runs[cap]["semantic"]["final_pareto"] == union]
    require(bool(matching_caps), "U6_ROUTE10_UNION_SELECTION_AUTHORITY_UNAVAILABLE")
    selection = runs[matching_caps[0]]["semantic"]["final_selection"]
    require(
        all(runs[cap]["semantic"]["final_selection"] == selection for cap in matching_caps)
        and sensitivity.get("normalized_union_selection") == selection,
        label,
    )
    winner = selection["selected_pair_fingerprint"]
    fingerprints = {
        cap: {p["fingerprint"] for p in runs[cap]["semantic"]["final_pareto"]}
        for cap in ("32", "64")
    }
    binding = winner != runs["32"]["semantic"]["final_v3_fingerprint"]
    derived = {
        "binding": binding,
        "classification": "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING"
        if binding
        else "U6_DIRECTIONAL_FRONTIER_32_CAP_NON_BINDING",
        "normalized_union_winner_cap32_present": winner in fingerprints["32"],
        "normalized_union_winner_cap64_only": winner in fingerprints["64"]
        and winner not in fingerprints["32"],
    }
    require(all(sensitivity.get(key) == value for key, value in derived.items()), label)
    return {
        "all_case_hard_runtime_gates_revalidated": True,
        "case_payload_sha256": {cap: semantic_hash(run) for cap, run in runs.items()},
        "normalized_union_sha256": semantic_hash(union),
        "normalized_union_selection_sha256": semantic_hash(selection),
        "selection_authority": "IDENTICAL_VALIDATED_FINAL_FRONTIER",
        "selection_authority_caps": matching_caps,
        **derived,
    }


def observe_q_after_freeze(frozen, fingerprint):
    semantic = frozen["semantic"]
    require(
        frozen.get("semantic_sha256") == semantic_hash(semantic),
        "U6_Q_OBSERVATION_REQUIRES_FROZEN_OUTPUT",
    )
    families = semantic.get("families", [])
    retentions = [r for s in semantic.get("sources", []) for r in s["retentions"]]
    return {
        "policy": "HISTORICAL_REFERENCE_ONLY",
        "raw_present": any(r["fingerprint"] == fingerprint for f in families for r in f["raw"]),
        "eligible_present": any(fingerprint in f["eligible"] for f in families),
        "retained_present": any(
            c["fingerprint"] == fingerprint for r in retentions for c in r["candidates"]
        ),
        "pair_present": fingerprint in semantic["pair_fingerprints"],
        "final_present": any(
            p["fingerprint"] == fingerprint for p in semantic.get("final_pareto", [])
        ),
    }


def build_evidence(
    *, parity, canonical, repeat, sensitivity, port, diagnostic_final_selection=False
):
    require(
        parity["classification"] == "U5_EXACT_PRODUCTION_PORT_PARITY",
        "U6_PRODUCTION_PORT_DIVERGED_FROM_U5",
    )
    require(port["protected_authority_unchanged"], "U6_UNEXPECTED_PRODUCTION_AUTHORITY_CHANGE")
    require(
        canonical.get("input_authority", {}).get("sha256") == ROUTE10_SHA256
        and repeat.get("input_authority") == canonical.get("input_authority"),
        "U6_ROUTE10_SAVED_BASE_AUTHORITY_MISMATCH",
    )
    require(
        canonical.get("implementation_authority_sha256")
        == repeat.get("implementation_authority_sha256")
        == port.get("implementation_authority_sha256"),
        "U6_UNEXPECTED_PRODUCTION_AUTHORITY_CHANGE",
    )
    _validate_route10_hard_gates(canonical)
    _validate_route10_hard_gates(repeat)
    sensitivity_validation = validate_route10_sensitivity(
        sensitivity, canonical=canonical, port=port
    )
    comparison = compare_route10_repeat(canonical, repeat)
    require(
        not sensitivity["binding"] or diagnostic_final_selection,
        "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING",
    )
    for run in (canonical, repeat, *sensitivity["independent_runs"].values()):
        validate_route10_payload(run, diagnostic_final_selection=diagnostic_final_selection)
    classification = "ROUTE10_KBEST_DAG_SHADOW_VALIDATED"
    if sensitivity["binding"]:
        classification = "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING"
    elif canonical["semantic"]["final_v3_fingerprint"] is None:
        classification = "U6_ROUTE10_FINAL_V3_SELECTION_UNAVAILABLE"
    return {
        "PORT": {**port, "u5_parity": parity},
        "ROUTE 10": {
            "classification": classification,
            "canonical": canonical,
            "repeat": repeat,
            "determinism": comparison,
            "sensitivity": sensitivity,
            "sensitivity_validation": sensitivity_validation,
        },
        "ROUTE 6": {
            "state": "NOT_RUN_ROUTE10_GATE_PENDING"
            if classification == "ROUTE10_KBEST_DAG_SHADOW_VALIDATED"
            else "NOT_RUN_ROUTE10_GATE_FAILED",
            "global_coordinator_executions": 0,
        },
        "Q": {
            "policy": "HISTORICAL_REFERENCE_ONLY",
            "state": "NOT_OBSERVED_ROUTE6_CANONICAL_PENDING",
            "classification_effect": False,
        },
        "READINESS": {
            "DAG shadow backend authoritative": False,
            "legacy backend removed": False,
            "production default changed": False,
            "READY_FOR_FINAL_PILOT_USE": False,
            "READY_FOR_PR62_COMPLETION_REVIEW": False,
        },
    }


def render_evidence(evidence, output_dir):
    route10 = evidence["ROUTE 10"]
    rebuilt = build_evidence(
        parity=evidence["PORT"]["u5_parity"],
        port={k: v for k, v in evidence["PORT"].items() if k != "u5_parity"},
        canonical=route10["canonical"],
        repeat=route10["repeat"],
        sensitivity=route10["sensitivity"],
        diagnostic_final_selection=True,
    )
    require(evidence == rebuilt, "U6_RENDER_EVIDENCE_AUTHORITY_MISMATCH")
    output_dir.mkdir(parents=True, exist_ok=False)
    write_once(output_dir / EVIDENCE_JSON, canonical_bytes(evidence))
    lines = ["# PR62-U6 k-best DAG shadow integration", ""]
    for section in ("PORT", "ROUTE 10", "ROUTE 6", "Q", "READINESS"):
        lines.extend([f"## {section}", ""])
        value = evidence[section]
        if section == "ROUTE 10":
            if value["canonical"]["semantic"]["final_v3_fingerprint"] is None:
                lines.extend(
                    [
                        "Route 10 has no selected timetable under unchanged V3. "
                        "The diagnostic repeat and cap comparison cannot authorize Route 6 or production use.",
                        "",
                    ]
                )
            lines.extend(
                [
                    value["classification"],
                    "",
                    "Canonical semantic SHA-256: `" + value["canonical"]["semantic_sha256"] + "`",
                    "",
                ]
            )
            for name in ("canonical", "repeat"):
                run = value[name]
                lines.extend(
                    [
                        f"### {name.title()}",
                        "",
                        "```json",
                        json.dumps(
                            {
                                "statistics": run["semantic"].get("statistics", {}),
                                "selected": run["semantic"]["final_v3_fingerprint"],
                                "v3_classification": run["semantic"]
                                .get("final_selection", {})
                                .get("classification"),
                                "pareto_sha256": run["semantic"]["final_pareto_hash"],
                                "timings": {
                                    k: v for k, v in run["timings"].items() if k != "families"
                                },
                            },
                            indent=2,
                            sort_keys=True,
                        ),
                        "```",
                        "",
                    ]
                )
            lines.extend(
                [
                    "Full source, family, raw/eligible/retained, pair, Pareto, and V3 histories are in the companion JSON.",
                    "",
                ]
            )
            sensitivity = value["sensitivity"]
            lines.extend(
                [
                    "### Independent cap sensitivity",
                    "",
                    "| Cap | Sources | Families | Raw | Eligible | Retained | Pairs | Pareto | V3 | Local seconds |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for cap, run in sorted(
                sensitivity.get("independent_runs", {}).items(), key=lambda item: int(item[0])
            ):
                stats = run["semantic"]["statistics"]
                values = [
                    cap,
                    *[
                        stats[key]
                        for key in (
                            "processed_source_count",
                            "families_processed",
                            "raw_paths_produced",
                            "hard_eligible_paths",
                            "retained_directional_candidates",
                            "pair_cross_products_evaluated",
                            "final_frontier_count",
                        )
                    ],
                    run["semantic"]["final_selection"]["classification"],
                    f"{run['timings']['total_seconds']:.6f}",
                ]
                lines.append("| " + " | ".join(map(str, values)) + " |")
            lines.extend(
                [
                    "",
                    "```json",
                    json.dumps(
                        {
                            k: v
                            for k, v in sensitivity.items()
                            if k
                            not in {
                                "independent_runs",
                                "normalized_union",
                                "normalized_union_selection",
                            }
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    "```",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "```json",
                    json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False),
                    "```",
                    "",
                ]
            )
    write_once(output_dir / EVIDENCE_MD, ("\n".join(lines).rstrip() + "\n").encode("utf-8"))


def authority_audit(repo_root):
    protected = [
        "src/bus_schedule_engine/contracts_v1/clean_boundary_compiler.py",
        "src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py",
        "src/bus_schedule_engine/service_plan_coordinator.py",
        # Coordinator imports the exact fleet builder/validator from this module.
        "src/bus_schedule_engine/clean_boundary_pilot.py",
        "src/bus_schedule_engine/local_rhythm_refinement.py",
        "src/bus_schedule_engine/contracts_v1/operational_selection_policy_v3.py",
        # V3 imports V2 and V1; V2 calls the unchanged V1 hard-feasibility builder.
        "src/bus_schedule_engine/contracts_v1/operational_selection_policy_v2.py",
        "src/bus_schedule_engine/contracts_v1/operational_selection_policy.py",
        "src/bus_schedule_engine/contracts_v1/closed_loop_service_protection.py",
        "src/bus_schedule_engine/contracts_v1/end_tail_settlement.py",
        "src/bus_schedule_engine/contracts_v1/fleet_assignment.py",
        "streamlit_app.py",
        "app_pages",
        "outputs/final_pilot",
        "pyproject.toml",
    ]
    result = subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            "59b892d3b367182b20734ad4e4405e264ba14024",
            "--",
            *protected,
        ],
        cwd=repo_root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    require(result.returncode == 0, "U6_UNEXPECTED_PRODUCTION_AUTHORITY_CHANGE")
    files = [
        p
        for path in protected
        for p in (
            [repo_root / path]
            if (repo_root / path).is_file()
            else sorted((repo_root / path).rglob("*"))
        )
        if p.is_file() and "__pycache__" not in p.parts
    ]
    implementation = [
        repo_root / "src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py",
        repo_root / "src/bus_schedule_engine/kbest_shadow_refinement.py",
        Path(__file__),
    ]
    return {
        "protected_authority_unchanged": True,
        "comparison_base": "59b892d3b367182b20734ad4e4405e264ba14024",
        "production_file_sha256": {
            p.relative_to(repo_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files + implementation
        },
        "port_audit_sha256": hashlib.sha256(
            (repo_root / "docs/engine/evidence/PR62_U6_KBEST_PORT_AUDIT.md").read_bytes()
        ).hexdigest(),
        "implementation_authority_sha256": shadow.kbest_dag_implementation_authority_hash_v1(),
    }


def _read_payload(path):
    require(path is not None, "U6_EXPLICIT_INPUT_PATH_REQUIRED")
    data = path.read_bytes()
    payload = json.loads(data)
    # The reader, never an embedded claim, supplies the artifact identity.
    payload["persisted_artifact"] = {
        "path": path.resolve().as_posix(),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "parity",
            "route10-canonical",
            "route10-repeat",
            "route10-sensitivity",
            "route6-global-once",
            "route6-canonical",
            "route6-repeat",
            "route6-sensitivity",
            "render-evidence",
        ),
    )
    for name in (
        "output-dir",
        "repo-root",
        "fixture",
        "saved-base",
        "canonical-payload",
        "repeat-payload",
        "sensitivity-payload",
        "parity-payload",
    ):
        parser.add_argument("--" + name, type=Path, required=name == "output-dir")
    parser.add_argument(
        "--diagnostic-final-selection",
        action="store_true",
        help="Continue diagnostics on the authorized final V3 anchor-conflict blocker; never certify it.",
    )
    args = parser.parse_args(argv)
    require(not args.stage.startswith("route6-"), "U6_ROUTE6_NOT_AUTHORIZED_IN_TASK7")
    if args.stage == "render-evidence":
        evidence = build_evidence(
            parity=_read_payload(args.parity_payload),
            canonical=_read_payload(args.canonical_payload),
            repeat=_read_payload(args.repeat_payload),
            sensitivity=_read_payload(args.sensitivity_payload),
            port=authority_audit(args.repo_root),
            diagnostic_final_selection=args.diagnostic_final_selection,
        )
        render_evidence(evidence, args.output_dir)
        return 0
    require(args.fixture is not None, "U6_EXPLICIT_INPUT_PATH_REQUIRED")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    try:
        parity = run_parity(args.fixture)
        write_once(args.output_dir / "parity.json", canonical_bytes(parity))
        if args.stage == "parity":
            return 0
        require(
            args.saved_base is not None and args.repo_root is not None,
            "U6_EXPLICIT_INPUT_PATH_REQUIRED",
        )
        port = authority_audit(args.repo_root)
        loaded = load_route10_saved_result(args.saved_base)
        write_once(
            args.output_dir / "input-authority.json", canonical_bytes(loaded.input_authority)
        )
        original_run = shadow.run_kbest_dag_shadow_from_completed_result_v1
        projected = {}

        def measured_run(**kwargs):
            cap = kwargs["directional_frontier_limit"]
            cache_size = len(kwargs.get("semantic_cache", {}))
            with instrument_shadow_gates() as observed:
                result = original_run(**kwargs)
            payload = project_shadow_result(
                result, context=loaded.context, observed=observed, cap=cap
            )
            payload["input_authority"] = loaded.input_authority
            payload["execution"]["initial_cache_entries"] = cache_size
            payload["implementation_authority_sha256"] = port["implementation_authority_sha256"]
            write_once(args.output_dir / f"cap{cap}.json", canonical_bytes(payload))
            validate_route10_payload(
                payload, diagnostic_final_selection=args.diagnostic_final_selection
            )
            projected[cap] = _read_payload(args.output_dir / f"cap{cap}.json")
            return result

        if args.stage == "route10-sensitivity":
            canonical = _read_payload(args.canonical_payload)
            validate_route10_payload(
                canonical, diagnostic_final_selection=args.diagnostic_final_selection
            )
            try:
                shadow.run_kbest_dag_shadow_from_completed_result_v1 = measured_run
                sensitivity = shadow.run_kbest_dag_cap_sensitivity_v1(
                    base_coordinator_result=loaded.base,
                    context=loaded.context,
                    coordinator_budget=FROZEN_BUDGET,
                    semantic_cache={},
                )
            finally:
                shadow.run_kbest_dag_shadow_from_completed_result_v1 = original_run
            _compare_route10_semantics(canonical, projected[32])
            binding = sensitivity.cap_binding
            payload = {
                "binding": binding.binding,
                "classification": binding.classification,
                "canonical_cap32_semantic_sha256": projected[32]["semantic_sha256"],
                "normalized_union": [_pair_payload(p) for p in binding.normalized_union_frontier],
                "normalized_union_selection": plain(binding.normalized_union_selection),
                "normalized_union_winner_cap32_present": binding.normalized_union_winner_cap32_present,
                "normalized_union_winner_cap64_only": binding.normalized_union_winner_cap64_only,
                "independent_runs": projected,
            }
            write_once(args.output_dir / "sensitivity.json", canonical_bytes(payload))
            require(not binding.binding, "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING")
        else:
            measured_run(
                base_coordinator_result=loaded.base,
                context=loaded.context,
                coordinator_budget=FROZEN_BUDGET,
                directional_frontier_limit=32,
                semantic_cache={},
            )
            if args.stage == "route10-repeat":
                comparison = compare_route10_repeat(
                    _read_payload(args.canonical_payload), projected[32]
                )
                write_once(args.output_dir / "repeat-comparison.json", canonical_bytes(comparison))
        return 0
    except (CertificationError, ValueError) as error:
        write_once(
            args.output_dir / "failure.json",
            canonical_bytes(
                {
                    "classification": str(error)
                    if isinstance(error, CertificationError)
                    else "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH",
                    "detail": str(error),
                    "stage": args.stage,
                    "global_coordinator_executions": 0,
                }
            ),
        )
        raise


if __name__ == "__main__":
    sys.exit(main())

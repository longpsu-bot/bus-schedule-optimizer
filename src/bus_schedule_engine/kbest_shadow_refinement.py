"""Explicit completed-result DAG shadow refinement under unchanged route authorities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

from .contracts_v1.clean_boundary_compiler import (
    CleanBoundaryCompilationStatusV1,
    _PhaseCandidate,
    validate_clean_boundary_compilation_v1,
)
from .contracts_v1.clean_compile_frontier import (
    CleanCompileVariantV1,
    _FrontierPath,
    _regimes_from_state,
    _select_diverse_paths,
)
from .contracts_v1.closed_loop_service_protection import (
    validate_closed_loop_service_protection_v1,
)
from .contracts_v1.kbest_dag_frontier import (
    KBestDagCandidateV1,
    KBestDagFrontierV1,
    KBestDagTelemetryV1,
    compile_service_plan_family_kbest_v1,
    service_plan_matches_endpoint_contract_v1,
)
from .contracts_v1.operational_selection_policy_v3 import (
    OperationalSelectionResultV3,
    select_operational_timetable_v3,
)
from .contracts_v1.service_plan_state import service_plan_fingerprint_v1
from .local_rhythm_refinement import (
    LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID,
    LocalRhythmFamilyPlanMappingError,
    LocalRhythmFamilyV1,
    LocalRhythmStateGenerationV1,
    detect_local_rhythm_families_v1,
    enumerate_local_rhythm_states_v1,
    map_actual_family_to_planning_indices_v1,
    pair_rhythm_tuple_v1,
    retain_strict_directional_canonicalizations_v1,
    strict_pair_rhythm_progress_v1,
)
from .service_plan_coordinator import (
    CoordinatorSearchBudgetV1,
    DirectionalCompilationCandidateV1,
    RouteCoordinatorContextV1,
    RouteCoordinatorResultV1,
    evaluate_actual_service_v1,
    evaluate_operating_pair_v1,
    update_operating_pair_pareto_v1,
)


@dataclass(frozen=True, slots=True)
class KBestDagEligibilityResultV1:
    raw_candidates: tuple[KBestDagCandidateV1, ...]
    eligible_candidates: tuple[DirectionalCompilationCandidateV1, ...]
    candidates: tuple[DirectionalCompilationCandidateV1, ...]
    structural_rejects: int
    protection_rejects: int
    tail_rejects: int
    strict_progress_rejects: int

    @property
    def eligible_fingerprints(self) -> tuple[str, ...]:
        return tuple(
            item.compile_variant.compilation_fingerprint for item in self.eligible_candidates
        )


@dataclass(frozen=True, slots=True)
class KBestDagFamilyShadowV1:
    family_index: int
    frontier: KBestDagFrontierV1
    eligibility: KBestDagEligibilityResultV1


@dataclass(frozen=True, slots=True)
class KBestDagDirectionalRetentionV1:
    candidates: tuple[DirectionalCompilationCandidateV1, ...]
    family_count: int
    raw_candidates_before_cross_family_dedupe: int
    eligible_candidates_before_cross_family_dedupe: int
    aggregate_eligible_count_after_dedupe: int
    source_added: bool
    source_rejection: str | None
    selector_seconds: float
    retained_count: int
    pre_diversity_truncation_count: int

    @property
    def retained_fingerprints(self) -> tuple[str, ...]:
        return tuple(item.compile_variant.compilation_fingerprint for item in self.candidates)


def _hard_eligible_candidate_v1(
    raw: KBestDagCandidateV1,
    *,
    source_directional: DirectionalCompilationCandidateV1,
    context: Any,
    rank: int,
) -> tuple[DirectionalCompilationCandidateV1 | None, str | None]:
    compilation = raw.compilation
    try:
        if compilation.status != CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES:
            raise ValueError("candidate does not contain a clean compilation")
        validate_clean_boundary_compilation_v1(compilation, _regimes_from_state(raw.state))
        authority = context.endpoint_authority[source_directional.state.direction]
        if (
            not service_plan_matches_endpoint_contract_v1(raw.state, authority)
            or compilation.route_id != authority.route_id
            or compilation.direction != authority.direction
            or compilation.endpoint_authority != authority
            or compilation.exact_departures[0] != authority.fixed_first_departure
            or compilation.exact_departures[-1] != authority.fixed_last_departure
        ):
            raise ValueError("candidate differs from the fixed endpoint authority")
        if (
            raw.state.total_trips != source_directional.state.total_trips
            or len(compilation.exact_departures) != source_directional.state.total_trips
        ):
            raise ValueError("candidate differs from the fixed trip total")
    except ValueError:
        # Structural/authority mismatches remain distinguishable from operational rejection.
        return None, "structural"

    protection = validate_closed_loop_service_protection_v1(
        authority=context.service_protection_authority,
        direction=raw.state.direction,
        exact_departures=compilation.exact_departures,
    )
    if not protection.passed:
        return None, "protection"
    variant = CleanCompileVariantV1(
        compilation_fingerprint=raw.compilation_fingerprint,
        frontier_rank=rank,
        headway_quantization=float(raw.compiler_objective[0]),
        actual_service_regime_count=raw.compiler_objective[1],
        phase_edge_quality_minutes=raw.compiler_objective[2],
        compilation=compilation,
    )
    metrics, feedback = evaluate_actual_service_v1(
        variant,
        demand_buckets=context.demand_buckets[raw.state.direction],
        scenario_b_departures=context.scenario_b_departures[raw.state.direction],
        demand_response_regimes=(
            None
            if context.demand_response_regimes is None
            else context.demand_response_regimes[raw.state.direction]
        ),
        protection_authority=context.service_protection_authority,
        protection_validation=protection,
    )
    if not metrics.tail_ordering.eligible:
        return None, "tail"
    return DirectionalCompilationCandidateV1(
        state=raw.state,
        state_fingerprint=raw.state_fingerprint,
        compile_variant=variant,
        metrics=metrics,
        feedback=feedback,
        history=("KBEST_DAG_SHADOW_GENERATED",),
    ), None


def evaluate_kbest_dag_hard_eligibility_v1(
    *,
    source_directional: DirectionalCompilationCandidateV1,
    candidates: Sequence[KBestDagCandidateV1],
    context: Any,
) -> KBestDagEligibilityResultV1:
    """Revalidate every raw identity before applying the existing strict-progress gate."""
    raw_candidates = tuple(candidates)
    eligible = []
    rejects = {"structural": 0, "protection": 0, "tail": 0}
    for rank, raw in enumerate(raw_candidates, start=1):
        candidate, rejection = _hard_eligible_candidate_v1(
            raw,
            source_directional=source_directional,
            context=context,
            rank=rank,
        )
        if rejection is not None:
            rejects[rejection] += 1
        else:
            eligible.append(candidate)
    return _eligibility_with_progress_v1(
        source_directional=source_directional,
        raw_candidates=raw_candidates,
        eligible=tuple(eligible),
        structural_rejects=rejects["structural"],
        protection_rejects=rejects["protection"],
        tail_rejects=rejects["tail"],
    )


def _eligibility_with_progress_v1(
    *,
    source_directional: DirectionalCompilationCandidateV1,
    raw_candidates: tuple[KBestDagCandidateV1, ...],
    eligible: tuple[DirectionalCompilationCandidateV1, ...],
    structural_rejects: int,
    protection_rejects: int,
    tail_rejects: int,
) -> KBestDagEligibilityResultV1:
    progressing = (
        retain_strict_directional_canonicalizations_v1(source_directional, eligible)
        if eligible
        else ()
    )
    return KBestDagEligibilityResultV1(
        raw_candidates=raw_candidates,
        eligible_candidates=tuple(eligible),
        candidates=tuple(progressing),
        structural_rejects=structural_rejects,
        protection_rejects=protection_rejects,
        tail_rejects=tail_rejects,
        strict_progress_rejects=len(eligible) - len(progressing),
    )


@dataclass(frozen=True, slots=True)
class _AggregateEntryV1:
    raw: KBestDagCandidateV1
    directional: DirectionalCompilationCandidateV1
    projection: _FrontierPath

    @property
    def order_key(self) -> tuple[Any, ...]:
        return (
            *self.raw.compiler_objective,
            self.raw.headway_vector,
            self.raw.departure_vector,
            self.raw.state_fingerprint,
            self.raw.compilation_fingerprint,
            self.directional.compile_variant.frontier_rank,
            self.directional.compile_variant.compilation.candidate_id,
        )


def _exact_compiler_objective_v1(
    candidate: DirectionalCompilationCandidateV1,
) -> tuple[Fraction, int, int]:
    compilation = candidate.compile_variant.compilation
    quantization = Fraction(0)
    for item in compilation.demand_regime_slices:
        duration = (item.demand_regime_end - item.demand_regime_start) // 60
        quantization += Fraction(
            abs(item.uniform_headway_minutes * item.authoritative_trip_count - duration),
            duration,
        )
    return (
        quantization,
        len(compilation.service_regimes),
        sum(item.phase_imbalance_minutes for item in compilation.demand_regime_slices),
    )


def _source_raw_candidate_v1(
    source: DirectionalCompilationCandidateV1,
) -> KBestDagCandidateV1:
    compilation = source.compile_variant.compilation
    objective = _exact_compiler_objective_v1(source)
    headways = tuple(item.uniform_headway_minutes for item in compilation.demand_regime_slices)
    departures = tuple(value // 60 for value in compilation.exact_departures)
    return KBestDagCandidateV1(
        state=source.state,
        state_fingerprint=source.state_fingerprint,
        compilation=compilation,
        compilation_fingerprint=source.compile_variant.compilation_fingerprint,
        compiler_objective=objective,
        exact_scaled_quantization=objective[0].numerator,
        path_score=(
            objective[0].numerator,
            objective[1],
            objective[2],
            headways,
            departures,
        ),
        phase_indices=(0,) * len(headways),
        headway_vector=headways,
        departure_vector=departures,
    )


def _frontier_projection_v1(raw: KBestDagCandidateV1) -> _FrontierPath:
    phases = tuple(
        _PhaseCandidate(
            first_minute=item.first_departure // 60,
            headway_minutes=item.uniform_headway_minutes,
            last_minute=item.last_departure // 60,
            departures_minutes=tuple(value // 60 for value in item.departures),
            quantization_error=Fraction(0),
            phase_imbalance_minutes=item.phase_imbalance_minutes,
        )
        for item in raw.compilation.demand_regime_slices
    )
    return _FrontierPath(phases, *raw.compiler_objective)


def _entry_v1(
    raw: KBestDagCandidateV1,
    directional: DirectionalCompilationCandidateV1,
) -> _AggregateEntryV1:
    variant = replace(
        directional.compile_variant,
        compilation_fingerprint=raw.compilation_fingerprint,
        headway_quantization=float(raw.compiler_objective[0]),
        actual_service_regime_count=raw.compiler_objective[1],
        phase_edge_quality_minutes=raw.compiler_objective[2],
        compilation=raw.compilation,
    )
    normalized = replace(
        directional,
        state=raw.state,
        state_fingerprint=raw.state_fingerprint,
        compile_variant=variant,
    )
    return _AggregateEntryV1(raw, normalized, _frontier_projection_v1(raw))


def retain_kbest_dag_directional_frontier_v1(
    *,
    source_directional: DirectionalCompilationCandidateV1,
    family_results: Sequence[KBestDagFamilyShadowV1],
    context: Any,
    limit: int,
) -> KBestDagDirectionalRetentionV1:
    """Revalidate the source, deduplicate exact identities, then apply 59b diversity."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    families = tuple(family_results)
    raw_count = sum(len(family.frontier.candidates) for family in families)
    eligible_count = sum(len(family.eligibility.eligible_candidates) for family in families)
    aggregate: dict[str, _AggregateEntryV1] = {}

    for family in families:
        for directional in family.eligibility.candidates:
            fingerprint = directional.compile_variant.compilation_fingerprint
            matching_raws = (
                raw
                for raw in family.frontier.candidates
                if raw.compilation_fingerprint == fingerprint
                and raw.state_fingerprint == directional.state_fingerprint
                and raw.compilation == directional.compile_variant.compilation
            )
            raw = min(
                matching_raws,
                key=lambda item: (
                    *item.compiler_objective,
                    item.headway_vector,
                    item.departure_vector,
                    item.state_fingerprint,
                ),
            )
            entry = _entry_v1(raw, directional)
            incumbent = aggregate.get(fingerprint)
            if incumbent is None or entry.order_key < incumbent.order_key:
                aggregate[fingerprint] = entry

    source_raw = _source_raw_candidate_v1(source_directional)
    validated_source, source_rejection = _hard_eligible_candidate_v1(
        source_raw,
        source_directional=source_directional,
        context=context,
        rank=source_directional.compile_variant.frontier_rank,
    )
    source_added = False
    if validated_source is not None:
        source_entry = _entry_v1(
            source_raw,
            replace(validated_source, history=source_directional.history),
        )
        incumbent = aggregate.get(source_raw.compilation_fingerprint)
        if incumbent is None:
            aggregate[source_raw.compilation_fingerprint] = source_entry
            source_added = True
        elif source_entry.order_key < incumbent.order_key:
            aggregate[source_raw.compilation_fingerprint] = source_entry

    ordered_entries = sorted(aggregate.values(), key=lambda item: item.order_key)
    paths = [entry.projection for entry in ordered_entries]
    by_departures = {entry.projection.departures: entry for entry in reversed(ordered_entries)}
    started = perf_counter()
    selected = _select_diverse_paths(paths, limit=limit)
    selector_seconds = perf_counter() - started
    retained = tuple(by_departures[path.departures].directional for path in selected)
    return KBestDagDirectionalRetentionV1(
        candidates=retained,
        family_count=len(families),
        raw_candidates_before_cross_family_dedupe=raw_count,
        eligible_candidates_before_cross_family_dedupe=eligible_count,
        aggregate_eligible_count_after_dedupe=len(aggregate),
        source_added=source_added,
        source_rejection=source_rejection,
        selector_seconds=selector_seconds,
        retained_count=len(retained),
        pre_diversity_truncation_count=0,
    )


@dataclass(frozen=True, slots=True)
class KBestDagFamilyManifestV1:
    direction: str
    family_index: int
    family: LocalRhythmFamilyV1
    planning_indices: tuple[int, ...]
    generation: LocalRhythmStateGenerationV1 | None
    generated_state_fingerprints: tuple[str, ...]
    valid_state_fingerprints: tuple[str, ...]
    endpoint_rejected_state_fingerprints: tuple[str, ...]
    shadow: KBestDagFamilyShadowV1 | None
    dag_call_count: int
    state_manifest_hash: str
    graph_hash: str | None
    raw_hash: str
    eligible_hash: str
    classification: str
    total_seconds: float
    cache_key: KBestDagSemanticCacheKeyV1 | None = None
    cache_hit: bool = False


def _semantic_hash_v1(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class KBestDagSemanticCacheKeyV1:
    source_pair_fingerprint: str
    source_directional_hash: str
    direction: str
    family_identity_hash: str
    sorted_state_manifest: tuple[tuple[str, str], ...]
    endpoint_authority_hash: str
    protection_authority_hash: str
    demand_authority_hash: str
    tail_context_authority_hash: str
    raw_limit: int
    implementation_authority_hash: str


@dataclass(frozen=True, slots=True)
class KBestDagSemanticCacheValueV1:
    """Only immutable raw DAG and hard-eligible semantics; no strict/retained selection."""

    frontier: KBestDagFrontierV1
    eligible_candidates: tuple[DirectionalCompilationCandidateV1, ...]
    structural_rejects: int
    protection_rejects: int
    tail_rejects: int


def kbest_dag_implementation_authority_hash_v1() -> str:
    """Bind U6 realization and its existing compilation/eligibility authorities to source bytes."""
    root = Path(__file__).parent
    relative_paths = (
        "contracts_v1/clean_boundary_compiler.py",
        "contracts_v1/clean_compile_frontier.py",
        "contracts_v1/closed_loop_service_protection.py",
        "contracts_v1/kbest_dag_frontier.py",
        "contracts_v1/service_plan_state.py",
        "kbest_shadow_refinement.py",
        "local_rhythm_refinement.py",
        "service_plan_coordinator.py",
    )
    return _semantic_hash_v1(
        {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in relative_paths}
    )


def _family_cache_key_v1(
    *,
    source_pair_fingerprint: str,
    source_directional: DirectionalCompilationCandidateV1,
    family_index: int,
    family: LocalRhythmFamilyV1,
    planning_indices: tuple[int, ...],
    states: Sequence[Any],
    context: Any,
    implementation_authority_hash: str,
) -> KBestDagSemanticCacheKeyV1:
    direction = source_directional.state.direction
    protection = context.service_protection_authority
    protection_hash = _semantic_hash_v1(None if protection is None else asdict(protection))
    response = context.demand_response_regimes
    demand_hash = _semantic_hash_v1(
        {
            "immutable_demand_sha256": getattr(context, "immutable_demand_sha256", None),
            "demand_buckets": [asdict(bucket) for bucket in context.demand_buckets[direction]],
            "demand_response_regimes": None
            if response is None
            else [asdict(regime) for regime in response[direction]],
        }
    )
    return KBestDagSemanticCacheKeyV1(
        source_pair_fingerprint=source_pair_fingerprint,
        source_directional_hash=_semantic_hash_v1(
            {
                "state_fingerprint": source_directional.state_fingerprint,
                "state": asdict(source_directional.state),
                "compilation_fingerprint": source_directional.compile_variant.compilation_fingerprint,
                "compilation": asdict(source_directional.compile_variant.compilation),
            }
        ),
        direction=direction,
        family_identity_hash=_semantic_hash_v1(
            {
                "family_index": family_index,
                "family": asdict(family),
                "planning_indices": planning_indices,
            }
        ),
        sorted_state_manifest=tuple(
            sorted(
                (service_plan_fingerprint_v1(state), _semantic_hash_v1(asdict(state)))
                for state in states
            )
        ),
        endpoint_authority_hash=_semantic_hash_v1(asdict(context.endpoint_authority[direction])),
        protection_authority_hash=protection_hash,
        demand_authority_hash=demand_hash,
        tail_context_authority_hash=_semantic_hash_v1(
            {
                "protection_authority": protection_hash,
                "demand_authority": demand_hash,
                "scenario_b_departures": tuple(context.scenario_b_departures[direction]),
            }
        ),
        raw_limit=256,
        implementation_authority_hash=implementation_authority_hash,
    )


def _validate_semantic_cache_value_v1(value: Any) -> None:
    schemas = {}

    def frozen(item: Any, schema: Any) -> bool:
        origin, arguments = get_origin(schema), get_args(schema)
        if origin is UnionType:
            return any(frozen(item, option) for option in arguments)
        if origin is tuple:
            if type(item) is not tuple:
                return False
            if len(arguments) == 2 and arguments[1] is Ellipsis:
                return all(frozen(child, arguments[0]) for child in item)
            return len(item) == len(arguments) and all(
                frozen(child, expected) for child, expected in zip(item, arguments, strict=True)
            )
        if is_dataclass(schema):
            if type(item) is not schema or not schema.__dataclass_params__.frozen:
                return False
            if schema not in schemas:
                schemas[schema] = get_type_hints(schema)
            return all(
                frozen(getattr(item, field.name), schemas[schema][field.name])
                for field in fields(schema)
            )
        return type(item) is schema or (schema is float and type(item) is int)

    if not frozen(value, KBestDagSemanticCacheValueV1) or value.frontier.requested_raw_limit != 256:
        raise ValueError(
            "semantic cache values must contain only frozen raw/eligible family results"
        )


def realize_kbest_dag_families_v1(
    *,
    source_directional: DirectionalCompilationCandidateV1,
    context: Any,
    source_pair_fingerprint: str | None = None,
    semantic_cache: dict[KBestDagSemanticCacheKeyV1, KBestDagSemanticCacheValueV1] | None = None,
    implementation_authority_hash: str | None = None,
) -> tuple[KBestDagFamilyManifestV1, ...]:
    """Realize each unchanged local family once after endpoint preflight."""
    if semantic_cache is not None:
        if not source_pair_fingerprint:
            raise ValueError("semantic cache requires the source pair fingerprint")
        if implementation_authority_hash is None:
            implementation_authority_hash = kbest_dag_implementation_authority_hash_v1()
    compilation = source_directional.compile_variant.compilation
    direction = source_directional.state.direction
    authority = context.endpoint_authority[direction]
    records = []
    for family_index, family in enumerate(
        detect_local_rhythm_families_v1(compilation.service_regimes)
    ):
        started = perf_counter()
        indices = ()
        generation = None
        generated_fingerprints = valid_fingerprints = rejected_fingerprints = ()
        shadow = None
        graph_hash = None
        cache_key = None
        cache_hit = False
        dag_call_count = 0
        classification = "NO_ENDPOINT_VALID_STATES"
        try:
            indices = map_actual_family_to_planning_indices_v1(
                state=source_directional.state, compilation=compilation, family=family
            )
        except LocalRhythmFamilyPlanMappingError:
            classification = LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID
        else:
            generation = enumerate_local_rhythm_states_v1(
                source=source_directional.state,
                planning_indices=indices,
                planning_grid_seconds=context.planning_grid_seconds,
            )
            ordered = sorted(generation.states, key=service_plan_fingerprint_v1)
            generated_fingerprints = tuple(service_plan_fingerprint_v1(state) for state in ordered)
            valid = tuple(
                state
                for state in ordered
                if service_plan_matches_endpoint_contract_v1(state, authority)
            )
            valid_fingerprints = tuple(service_plan_fingerprint_v1(state) for state in valid)
            valid_set = set(valid_fingerprints)
            rejected_fingerprints = tuple(
                fp for fp in generated_fingerprints if fp not in valid_set
            )
            if valid:
                cached = None
                if semantic_cache is not None:
                    cache_key = _family_cache_key_v1(
                        source_pair_fingerprint=source_pair_fingerprint,
                        source_directional=source_directional,
                        family_index=family_index,
                        family=family,
                        planning_indices=indices,
                        states=valid,
                        context=context,
                        implementation_authority_hash=implementation_authority_hash,
                    )
                    if cache_key in semantic_cache:
                        cached = semantic_cache[cache_key]
                        _validate_semantic_cache_value_v1(cached)
                        cache_hit = True
                if cached is None:
                    frontier = compile_service_plan_family_kbest_v1(
                        states=valid, endpoint_authority=authority, raw_limit=256
                    )
                    dag_call_count = 1
                    eligibility = evaluate_kbest_dag_hard_eligibility_v1(
                        source_directional=source_directional,
                        candidates=frontier.candidates,
                        context=context,
                    )
                    if semantic_cache is not None:
                        cached = KBestDagSemanticCacheValueV1(
                            # Cached semantics cannot attribute a previous run's wall-clock work.
                            frontier=replace(
                                frontier, telemetry=KBestDagTelemetryV1(0, 0, 0, 0, 0)
                            ),
                            eligible_candidates=eligibility.eligible_candidates,
                            structural_rejects=eligibility.structural_rejects,
                            protection_rejects=eligibility.protection_rejects,
                            tail_rejects=eligibility.tail_rejects,
                        )
                        _validate_semantic_cache_value_v1(cached)
                        semantic_cache[cache_key] = cached
                else:
                    frontier = cached.frontier
                    eligibility = _eligibility_with_progress_v1(
                        source_directional=source_directional,
                        raw_candidates=frontier.candidates,
                        eligible=cached.eligible_candidates,
                        structural_rejects=cached.structural_rejects,
                        protection_rejects=cached.protection_rejects,
                        tail_rejects=cached.tail_rejects,
                    )
                shadow = KBestDagFamilyShadowV1(family_index, frontier, eligibility)
                # The semantic graph manifest binds its complete inputs and structural counts.
                graph_hash = _semantic_hash_v1(
                    {
                        "states": valid_fingerprints,
                        "endpoint_authority": asdict(authority),
                        "graph_statistics": {
                            name: getattr(frontier.graph_statistics, name)
                            for name in (
                                "state_count",
                                "layer_count",
                                "node_count",
                                "legal_transition_edge_count",
                                "source_edge_count",
                                "sink_edge_count",
                                "reachability_trimmed_node_count",
                            )
                        },
                    }
                )
                classification = "FAMILY_REALIZED"
        manifest = {
            "direction": direction,
            "family": asdict(family),
            "planning_indices": indices,
            "generated": generated_fingerprints,
            "valid": valid_fingerprints,
            "endpoint_rejected": rejected_fingerprints,
        }
        records.append(
            KBestDagFamilyManifestV1(
                direction=direction,
                family_index=family_index,
                family=family,
                planning_indices=indices,
                generation=generation,
                generated_state_fingerprints=generated_fingerprints,
                valid_state_fingerprints=valid_fingerprints,
                endpoint_rejected_state_fingerprints=rejected_fingerprints,
                shadow=shadow,
                dag_call_count=dag_call_count,
                state_manifest_hash=_semantic_hash_v1(manifest),
                graph_hash=graph_hash,
                raw_hash=_semantic_hash_v1(shadow.frontier.ordered_fingerprints if shadow else ()),
                eligible_hash=_semantic_hash_v1(
                    shadow.eligibility.eligible_fingerprints if shadow else ()
                ),
                classification=classification,
                total_seconds=perf_counter() - started,
                cache_key=cache_key,
                cache_hit=cache_hit,
            )
        )
    return tuple(records)


@dataclass(frozen=True, slots=True)
class KBestDagDescendantV1:
    parent_fingerprint: str
    child_fingerprint: str
    parent_rhythm: tuple[int, int, int, int]
    child_rhythm: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class KBestDagPairDecisionV1:
    outbound_fingerprint: str
    inbound_fingerprint: str
    pair_fingerprint: str | None
    decision: str
    source_rhythm: tuple[int, int, int, int]
    generated_rhythm: tuple[int, int, int, int] | None
    feedback: tuple[Any, ...]
    pareto_before_hash: str
    pareto_after_hash: str
    total_seconds: float


@dataclass(frozen=True, slots=True)
class KBestDagPairEvaluationV1:
    frontier: tuple[Any, ...]
    decisions: tuple[KBestDagPairDecisionV1, ...]
    generated_pair_fingerprints: tuple[str, ...]
    admitted_descendants: tuple[KBestDagDescendantV1, ...]


def _pareto_hash_v1(frontier: Sequence[Any]) -> str:
    return _semantic_hash_v1(
        [
            {
                "pair_fingerprint": pair.pair_fingerprint,
                "pareto_vector": pair.metrics.pareto_vector,
                "rhythm": pair_rhythm_tuple_v1(pair),
            }
            for pair in sorted(frontier, key=lambda item: item.pair_fingerprint)
        ]
    )


def evaluate_kbest_dag_pairs_v1(
    *,
    source_pair: Any,
    outbound_options: Sequence[DirectionalCompilationCandidateV1],
    inbound_options: Sequence[DirectionalCompilationCandidateV1],
    context: Any,
    frontier: Sequence[Any],
    pair_frontier_limit: int,
    already_generated: set[str],
) -> KBestDagPairEvaluationV1:
    """Cross retained directions through exact fleet, strict rhythm, and Pareto authority."""
    current = tuple(frontier)
    decisions = []
    generated = []
    descendants = []
    source_rhythm = pair_rhythm_tuple_v1(source_pair)
    outbound = sorted(
        outbound_options, key=lambda item: item.compile_variant.compilation_fingerprint
    )
    inbound = sorted(inbound_options, key=lambda item: item.compile_variant.compilation_fingerprint)
    for ob in outbound:
        for ib in inbound:
            started = perf_counter()
            before_hash = _pareto_hash_v1(current)
            pair, feedback = evaluate_operating_pair_v1(ob, ib, context=context)
            fingerprint = None if pair is None else pair.pair_fingerprint
            rhythm = None if pair is None else pair_rhythm_tuple_v1(pair)
            if pair is None:
                decision = "FLEET_REJECTED"
            elif fingerprint in already_generated:
                decision = "DUPLICATE_PAIR"
            else:
                already_generated.add(fingerprint)
                generated.append(fingerprint)
                if not strict_pair_rhythm_progress_v1(source_pair, pair):
                    decision = "NON_STRICT_RHYTHM"
                else:
                    before = {item.pair_fingerprint for item in current}
                    current = update_operating_pair_pareto_v1(
                        current, pair, limit=pair_frontier_limit
                    )
                    admitted = fingerprint not in before and any(
                        item.pair_fingerprint == fingerprint for item in current
                    )
                    decision = "PARETO_ADMITTED" if admitted else "PARETO_REJECTED"
                    if admitted:
                        descendants.append(
                            KBestDagDescendantV1(
                                source_pair.pair_fingerprint, fingerprint, source_rhythm, rhythm
                            )
                        )
            decisions.append(
                KBestDagPairDecisionV1(
                    outbound_fingerprint=ob.compile_variant.compilation_fingerprint,
                    inbound_fingerprint=ib.compile_variant.compilation_fingerprint,
                    pair_fingerprint=fingerprint,
                    decision=decision,
                    source_rhythm=source_rhythm,
                    generated_rhythm=rhythm,
                    feedback=tuple(feedback),
                    pareto_before_hash=before_hash,
                    pareto_after_hash=_pareto_hash_v1(current),
                    total_seconds=perf_counter() - started,
                )
            )
    return KBestDagPairEvaluationV1(current, tuple(decisions), tuple(generated), tuple(descendants))


@dataclass(frozen=True, slots=True)
class KBestDagSourceRefinementV1:
    source_pair_fingerprint: str
    frontier: tuple[Any, ...]
    families: tuple[KBestDagFamilyManifestV1, ...] = ()
    directional_retentions: tuple[tuple[str, KBestDagDirectionalRetentionV1], ...] = ()
    retained_hashes: tuple[tuple[str, str], ...] = ()
    pair_evaluation: KBestDagPairEvaluationV1 | None = None
    total_seconds: float = 0.0


def _validate_directional_limit_v1(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("directional_frontier_limit must be a positive integer")


def refine_kbest_dag_source_pair_v1(
    *,
    source_pair: Any,
    context: RouteCoordinatorContextV1,
    frontier: Sequence[Any],
    pair_frontier_limit: int,
    already_generated: set[str],
    directional_frontier_limit: int = 32,
    semantic_cache: dict[KBestDagSemanticCacheKeyV1, KBestDagSemanticCacheValueV1] | None = None,
    implementation_authority_hash: str | None = None,
) -> KBestDagSourceRefinementV1:
    """Realize all families, retain each aggregate once, then cross only retained candidates."""
    _validate_directional_limit_v1(directional_frontier_limit)
    started = perf_counter()
    families = []
    retained = {}
    for direction in ("outbound", "inbound"):
        source = getattr(source_pair, direction)
        manifests = realize_kbest_dag_families_v1(
            source_directional=source,
            context=context,
            source_pair_fingerprint=source_pair.pair_fingerprint,
            semantic_cache=semantic_cache,
            implementation_authority_hash=implementation_authority_hash,
        )
        families.extend(manifests)
        retained[direction] = retain_kbest_dag_directional_frontier_v1(
            source_directional=source,
            family_results=tuple(item.shadow for item in manifests if item.shadow is not None),
            context=context,
            limit=directional_frontier_limit,
        )
        retained[direction] = replace(retained[direction], family_count=len(manifests))
    pairs = evaluate_kbest_dag_pairs_v1(
        source_pair=source_pair,
        outbound_options=retained["outbound"].candidates,
        inbound_options=retained["inbound"].candidates,
        context=context,
        frontier=frontier,
        pair_frontier_limit=pair_frontier_limit,
        already_generated=already_generated,
    )
    return KBestDagSourceRefinementV1(
        source_pair_fingerprint=source_pair.pair_fingerprint,
        frontier=pairs.frontier,
        families=tuple(families),
        directional_retentions=tuple(retained.items()),
        retained_hashes=tuple(
            (direction, _semantic_hash_v1(value.retained_fingerprints))
            for direction, value in retained.items()
        ),
        pair_evaluation=pairs,
        total_seconds=perf_counter() - started,
    )


@dataclass(frozen=True, slots=True)
class KBestDagShadowStatisticsV1:
    global_coordinator_executions: int
    source_materiality_pair_count: int
    processed_source_count: int
    refinement_iterations: int
    families_processed: int
    dag_graphs_built: int
    raw_paths_produced: int
    endpoint_preflight_rejects: int
    structural_rejects: int
    protection_rejects: int
    tail_rejects: int
    directional_strict_progress_rejects: int
    hard_eligible_paths: int
    retained_directional_candidates: int
    pair_cross_products_evaluated: int
    fleet_rejects: int
    strict_rhythm_rejects: int
    duplicate_pair_rejects: int
    pareto_admitted_generated_pairs: int
    base_frontier_count: int
    final_frontier_count: int
    total_seconds: float


@dataclass(frozen=True, slots=True)
class KBestDagShadowResultV1:
    base_coordinator_result: RouteCoordinatorResultV1
    base_v3_selection: OperationalSelectionResultV3
    augmented_pareto_frontier: tuple[Any, ...]
    final_v3_selection: OperationalSelectionResultV3
    statistics: KBestDagShadowStatisticsV1
    processed_source_pair_fingerprints: tuple[str, ...]
    generated_pair_fingerprints: tuple[str, ...]
    source_refinements: tuple[KBestDagSourceRefinementV1, ...]
    generated_pair_parents: tuple[KBestDagDescendantV1, ...]
    continuation_history: tuple[KBestDagDescendantV1, ...]
    selection_history: tuple[OperationalSelectionResultV3, ...]
    pareto_history_hashes: tuple[str, ...]


def run_kbest_dag_shadow_from_completed_result_v1(
    *,
    base_coordinator_result: RouteCoordinatorResultV1,
    context: RouteCoordinatorContextV1,
    coordinator_budget: CoordinatorSearchBudgetV1,
    directional_frontier_limit: int = 32,
    semantic_cache: dict[KBestDagSemanticCacheKeyV1, KBestDagSemanticCacheValueV1] | None = None,
    implementation_authority_hash: str | None = None,
) -> KBestDagShadowResultV1:
    """Consume a completed search with a sorted, source-once strict-descendant worklist."""
    _validate_directional_limit_v1(directional_frontier_limit)
    started = perf_counter()
    frontier = tuple(item for item in base_coordinator_result.pareto_frontier)
    cache_options = {}
    if semantic_cache is not None:
        cache_options = {
            "semantic_cache": semantic_cache,
            "implementation_authority_hash": implementation_authority_hash
            or kbest_dag_implementation_authority_hash_v1(),
        }
    base_selection = select_operational_timetable_v3(context=context, candidates=frontier)
    selection = base_selection
    base_by_fingerprint = {item.pair_fingerprint: item for item in frontier}
    queued = {
        fp: base_by_fingerprint[fp]
        for fp in sorted(set(base_selection.phase_robust_materiality_fingerprints))
        if fp in base_by_fingerprint
    }
    base_source_count = len(queued)
    processed = set()
    processed_order = []
    generated = set()
    parents = {}
    continuations = []
    source_results = []
    selection_history = [selection]
    pareto_history = [_pareto_hash_v1(frontier)]
    while queued:
        fingerprint = min(queued)
        source = queued.pop(fingerprint)
        processed.add(fingerprint)
        processed_order.append(fingerprint)
        refined = refine_kbest_dag_source_pair_v1(
            source_pair=source,
            context=context,
            frontier=frontier,
            pair_frontier_limit=coordinator_budget.max_pair_frontier,
            directional_frontier_limit=directional_frontier_limit,
            already_generated=generated,
            **cache_options,
        )
        source_results.append(refined)
        frontier = refined.frontier
        if refined.pair_evaluation is not None:
            generated.update(refined.pair_evaluation.generated_pair_fingerprints)
            for record in refined.pair_evaluation.admitted_descendants:
                if (
                    record.parent_fingerprint == fingerprint
                    and record.parent_rhythm == pair_rhythm_tuple_v1(source)
                    and record.child_rhythm < record.parent_rhythm
                    and record.child_fingerprint
                    in refined.pair_evaluation.generated_pair_fingerprints
                ):
                    parents.setdefault(record.child_fingerprint, record)
        selection = select_operational_timetable_v3(context=context, candidates=frontier)
        selection_history.append(selection)
        pareto_history.append(_pareto_hash_v1(frontier))
        by_fingerprint = {item.pair_fingerprint: item for item in frontier}
        for child in sorted(set(selection.phase_robust_materiality_fingerprints)):
            if child in processed or child in queued or child not in by_fingerprint:
                continue
            record = parents.get(child)
            if record is None or pair_rhythm_tuple_v1(by_fingerprint[child]) != record.child_rhythm:
                continue
            queued[child] = by_fingerprint[child]
            continuations.append(record)
    families = tuple(family for result in source_results for family in result.families)
    realized = tuple(family.shadow for family in families if family.shadow is not None)
    decisions = tuple(
        decision
        for result in source_results
        if result.pair_evaluation is not None
        for decision in result.pair_evaluation.decisions
    )
    statistics = KBestDagShadowStatisticsV1(
        global_coordinator_executions=0,
        source_materiality_pair_count=base_source_count,
        processed_source_count=len(processed),
        refinement_iterations=len(source_results),
        families_processed=len(families),
        dag_graphs_built=sum(family.dag_call_count for family in families),
        raw_paths_produced=sum(len(family.frontier.candidates) for family in realized),
        endpoint_preflight_rejects=sum(
            len(family.endpoint_rejected_state_fingerprints) for family in families
        ),
        structural_rejects=sum(family.eligibility.structural_rejects for family in realized),
        protection_rejects=sum(family.eligibility.protection_rejects for family in realized),
        tail_rejects=sum(family.eligibility.tail_rejects for family in realized),
        directional_strict_progress_rejects=sum(
            family.eligibility.strict_progress_rejects for family in realized
        ),
        hard_eligible_paths=sum(len(family.eligibility.eligible_candidates) for family in realized),
        retained_directional_candidates=sum(
            retention.retained_count
            for result in source_results
            for _, retention in result.directional_retentions
        ),
        pair_cross_products_evaluated=len(decisions),
        fleet_rejects=sum(item.decision == "FLEET_REJECTED" for item in decisions),
        strict_rhythm_rejects=sum(item.decision == "NON_STRICT_RHYTHM" for item in decisions),
        duplicate_pair_rejects=sum(item.decision == "DUPLICATE_PAIR" for item in decisions),
        pareto_admitted_generated_pairs=sum(
            item.decision == "PARETO_ADMITTED" for item in decisions
        ),
        base_frontier_count=len(base_coordinator_result.pareto_frontier),
        final_frontier_count=len(frontier),
        total_seconds=perf_counter() - started,
    )
    return KBestDagShadowResultV1(
        base_coordinator_result=base_coordinator_result,
        base_v3_selection=base_selection,
        augmented_pareto_frontier=frontier,
        final_v3_selection=selection,
        statistics=statistics,
        processed_source_pair_fingerprints=tuple(processed_order),
        generated_pair_fingerprints=tuple(sorted(generated)),
        source_refinements=tuple(source_results),
        generated_pair_parents=tuple(parents[key] for key in sorted(parents)),
        continuation_history=tuple(continuations),
        selection_history=tuple(selection_history),
        pareto_history_hashes=tuple(pareto_history),
    )


@dataclass(frozen=True, slots=True)
class KBestDagCapBindingResultV1:
    normalized_union_frontier: tuple[Any, ...]
    normalized_union_selection: OperationalSelectionResultV3
    cap32_final_v3_selection: OperationalSelectionResultV3
    binding: bool
    normalized_union_winner_cap32_present: bool
    normalized_union_winner_cap64_only: bool
    classification: str


def adjudicate_kbest_dag_cap_binding_v1(
    *,
    cap32: KBestDagShadowResultV1,
    cap64: KBestDagShadowResultV1,
    context: RouteCoordinatorContextV1,
) -> KBestDagCapBindingResultV1:
    """Normalize the final 32/64 union before V3; compare outcomes, irrespective of provenance."""
    by_fingerprint = {}
    for candidate in (*cap32.augmented_pareto_frontier, *cap64.augmented_pareto_frontier):
        by_fingerprint.setdefault(candidate.pair_fingerprint, candidate)
    normalized = ()
    for fingerprint in sorted(by_fingerprint):
        normalized = update_operating_pair_pareto_v1(
            normalized, by_fingerprint[fingerprint], limit=None
        )
    selection = select_operational_timetable_v3(context=context, candidates=normalized)
    winner = selection.selected_pair_fingerprint
    binding = winner != cap32.final_v3_selection.selected_pair_fingerprint
    cap32_fingerprints = {item.pair_fingerprint for item in cap32.augmented_pareto_frontier}
    cap64_fingerprints = {item.pair_fingerprint for item in cap64.augmented_pareto_frontier}
    return KBestDagCapBindingResultV1(
        normalized_union_frontier=normalized,
        normalized_union_selection=selection,
        cap32_final_v3_selection=cap32.final_v3_selection,
        binding=binding,
        normalized_union_winner_cap32_present=winner in cap32_fingerprints,
        normalized_union_winner_cap64_only=(
            winner in cap64_fingerprints and winner not in cap32_fingerprints
        ),
        classification=(
            "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING"
            if binding
            else "U6_DIRECTIONAL_FRONTIER_32_CAP_NON_BINDING"
        ),
    )


@dataclass(frozen=True, slots=True)
class KBestDagSensitivityResultV1:
    cap16: KBestDagShadowResultV1
    cap32: KBestDagShadowResultV1
    cap64: KBestDagShadowResultV1
    cap_binding: KBestDagCapBindingResultV1


def run_kbest_dag_cap_sensitivity_v1(
    *,
    base_coordinator_result: RouteCoordinatorResultV1,
    context: RouteCoordinatorContextV1,
    coordinator_budget: CoordinatorSearchBudgetV1,
    semantic_cache: dict[KBestDagSemanticCacheKeyV1, KBestDagSemanticCacheValueV1] | None = None,
    fresh_repeat: bool = False,
    implementation_authority_hash: str | None = None,
) -> KBestDagSensitivityResultV1:
    """Run three independent completed-result worklists; share only family raw/eligible results."""
    cache = {} if fresh_repeat or semantic_cache is None else semantic_cache
    implementation_hash = (
        implementation_authority_hash or kbest_dag_implementation_authority_hash_v1()
    )
    runs = tuple(
        run_kbest_dag_shadow_from_completed_result_v1(
            base_coordinator_result=base_coordinator_result,
            context=context,
            coordinator_budget=coordinator_budget,
            directional_frontier_limit=cap,
            semantic_cache=cache,
            implementation_authority_hash=implementation_hash,
        )
        for cap in (16, 32, 64)
    )
    return KBestDagSensitivityResultV1(
        *runs,
        cap_binding=adjudicate_kbest_dag_cap_binding_v1(
            cap32=runs[1], cap64=runs[2], context=context
        ),
    )

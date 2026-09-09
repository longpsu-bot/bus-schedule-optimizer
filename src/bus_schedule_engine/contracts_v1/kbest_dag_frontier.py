"""Exact, bounded realization of a canonical ServicePlan family as layered DAGs."""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, replace
from fractions import Fraction
from time import perf_counter
from typing import Any

from .clean_boundary_compiler import (
    CleanBoundaryCompilationV1,
    DemandRegimeAllocationV1,
    OperationalEndpointAuthorityV1,
    _candidate_path,
    _phase_candidates,
    _PhaseCandidate,
    validate_clean_boundary_compilation_v1,
)
from .clean_compile_frontier import (
    _bounded_phase_candidates,
    _compilation_from_path,
    _FrontierPath,
    _regimes_from_state,
    clean_compilation_fingerprint_v1,
)
from .service_plan_state import ServicePlanStateV1, service_plan_fingerprint_v1

_PathKeyV1 = tuple[int, int, int, tuple[int, ...], tuple[int, ...]]
_ExactPathKeyV1 = tuple[Fraction, int, int, tuple[int, ...], tuple[int, ...]]


@dataclass(frozen=True, slots=True)
class KBestDagCandidateV1:
    state: ServicePlanStateV1
    state_fingerprint: str
    compilation: CleanBoundaryCompilationV1
    compilation_fingerprint: str
    compiler_objective: tuple[Fraction, int, int]
    exact_scaled_quantization: int
    path_score: _PathKeyV1
    phase_indices: tuple[int, ...]
    headway_vector: tuple[int, ...]
    departure_vector: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class KBestDagGraphStatisticsV1:
    state_count: int
    layer_count: int
    node_count: int
    legal_transition_edge_count: int
    source_edge_count: int
    sink_edge_count: int
    reachability_trimmed_node_count: int
    retained_partial_path_count: int
    truncated_node_count: int
    duplicate_departure_path_count: int


@dataclass(frozen=True, slots=True)
class KBestDagTelemetryV1:
    graph_construction_seconds: float
    dynamic_programming_seconds: float
    final_merge_seconds: float
    decoding_seconds: float
    total_seconds: float


@dataclass(frozen=True, slots=True)
class KBestDagFrontierV1:
    candidates: tuple[KBestDagCandidateV1, ...]
    ordered_fingerprints: tuple[str, ...]
    requested_raw_limit: int
    natural_exhaustion: bool
    graph_statistics: KBestDagGraphStatisticsV1
    telemetry: KBestDagTelemetryV1


@dataclass(frozen=True, slots=True)
class _PartialPathV1:
    state_index: int
    phase_indices: tuple[int, ...]
    q_scaled: int
    quantization_scale: int
    actual_regime_count: int
    phase_imbalance: int
    headway_vector: tuple[int, ...]
    departure_vector: tuple[int, ...]

    @property
    def key(self) -> _PathKeyV1:
        return (
            self.q_scaled,
            self.actual_regime_count,
            self.phase_imbalance,
            self.headway_vector,
            self.departure_vector,
        )

    @property
    def exact_key(self) -> _ExactPathKeyV1:
        return (Fraction(self.q_scaled, self.quantization_scale), *self.key[1:])


@dataclass(frozen=True, slots=True)
class _LayeredDomainV1:
    state_index: int
    layers: tuple[tuple[_PhaseCandidate, ...], ...]
    edges: tuple[tuple[tuple[int, int], ...], ...]
    quantization_scale: int
    graph_statistics: KBestDagGraphStatisticsV1


@dataclass(frozen=True, slots=True)
class _DomainEnumerationV1:
    paths: tuple[_PartialPathV1, ...]
    graph_statistics: KBestDagGraphStatisticsV1
    natural_exhaustion: bool


@dataclass(frozen=True, slots=True)
class _MergeResultV1:
    paths: tuple[_PartialPathV1, ...]
    truncated: bool
    duplicates_suppressed: int


def _validate_raw_limit_v1(raw_limit: int) -> None:
    if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or not 1 <= raw_limit <= 256:
        raise ValueError("raw_limit must be an integer from 1 through 256")


def service_plan_matches_endpoint_contract_v1(
    state: ServicePlanStateV1, endpoint_authority: OperationalEndpointAuthorityV1
) -> bool:
    """Check identity and membership in the first and final half-open regimes."""
    if not state.service_regimes:
        return False
    first, final = state.service_regimes[0], state.service_regimes[-1]
    return (
        state.route_id == endpoint_authority.route_id
        and state.direction == endpoint_authority.direction
        and state.fixed_first_departure == endpoint_authority.fixed_first_departure
        and state.fixed_last_departure == endpoint_authority.fixed_last_departure
        and first.start == endpoint_authority.analysis_window_start
        and final.end == endpoint_authority.analysis_window_end
        and first.start <= state.fixed_first_departure < first.end
        and final.start <= state.fixed_last_departure < final.end
    )


def _build_layered_domain_v1(
    phase_layers: Sequence[Sequence[_PhaseCandidate]], *, state_index: int = 0
) -> _LayeredDomainV1:
    """Build legal adjacency and retain only nodes on complete source-sink paths."""
    layers = tuple(tuple(layer) for layer in phase_layers)
    edges = []
    for lefts, rights in zip(layers, layers[1:], strict=False):
        starts: dict[int, list[int]] = {}
        predecessors: dict[int, list[int]] = {}
        for right_index, right in enumerate(rights):
            starts.setdefault(right.first_minute, []).append(right_index)
            predecessors.setdefault(right.first_minute - right.headway_minutes, []).append(
                right_index
            )
        arcs = []
        for left_index, left in enumerate(lefts):
            legal = set(starts.get(left.last_minute + left.headway_minutes, ()))
            legal.update(predecessors.get(left.last_minute, ()))
            arcs.extend((left_index, right_index) for right_index in sorted(legal))
        edges.append(tuple(arcs))

    forward = [set(range(len(layers[0])))] if layers else []
    for index, arcs in enumerate(edges):
        forward.append({right for left, right in arcs if left in forward[index]})
    backward: list[set[int]] = [set() for _ in layers]
    if layers:
        backward[-1] = set(range(len(layers[-1])))
    for index in range(len(edges) - 1, -1, -1):
        backward[index] = {left for left, right in edges[index] if right in backward[index + 1]}
    retained = [sorted(a & b) for a, b in zip(forward, backward, strict=True)]
    maps = [{old: new for new, old in enumerate(indices)} for indices in retained]
    trimmed = tuple(
        tuple(layer[index] for index in indices)
        for layer, indices in zip(layers, retained, strict=True)
    )
    trimmed_edges = tuple(
        tuple(
            (maps[index][left], maps[index + 1][right])
            for left, right in arcs
            if left in maps[index] and right in maps[index + 1]
        )
        for index, arcs in enumerate(edges)
    )
    node_count = sum(map(len, trimmed))
    return _LayeredDomainV1(
        state_index=state_index,
        layers=trimmed,
        edges=trimmed_edges,
        quantization_scale=math.lcm(
            *(phase.quantization_error.denominator for layer in trimmed for phase in layer)
        ),
        graph_statistics=KBestDagGraphStatisticsV1(
            state_count=1,
            layer_count=len(layers),
            node_count=node_count,
            legal_transition_edge_count=sum(map(len, trimmed_edges)),
            source_edge_count=len(trimmed[0]) if trimmed else 0,
            sink_edge_count=len(trimmed[-1]) if trimmed else 0,
            reachability_trimmed_node_count=sum(map(len, layers)) - node_count,
            retained_partial_path_count=0,
            truncated_node_count=0,
            duplicate_departure_path_count=0,
        ),
    )


def _scaled_quantization_v1(candidate: _PhaseCandidate, scale: int) -> int:
    scaled = candidate.quantization_error * scale
    if scaled.denominator != 1:
        raise ValueError("scale does not exactly represent every quantization score")
    return scaled.numerator


def _first_path_v1(domain: _LayeredDomainV1, index: int) -> _PartialPathV1:
    candidate = domain.layers[0][index]
    return _PartialPathV1(
        state_index=domain.state_index,
        phase_indices=(index,),
        q_scaled=_scaled_quantization_v1(candidate, domain.quantization_scale),
        quantization_scale=domain.quantization_scale,
        actual_regime_count=1,
        phase_imbalance=candidate.phase_imbalance_minutes,
        headway_vector=(candidate.headway_minutes,),
        departure_vector=candidate.departures_minutes,
    )


def _extend_path_v1(
    prefix: _PartialPathV1, index: int, candidate: _PhaseCandidate
) -> _PartialPathV1:
    return _PartialPathV1(
        state_index=prefix.state_index,
        phase_indices=(*prefix.phase_indices, index),
        q_scaled=prefix.q_scaled + _scaled_quantization_v1(candidate, prefix.quantization_scale),
        quantization_scale=prefix.quantization_scale,
        actual_regime_count=(
            prefix.actual_regime_count + (prefix.headway_vector[-1] != candidate.headway_minutes)
        ),
        phase_imbalance=prefix.phase_imbalance + candidate.phase_imbalance_minutes,
        headway_vector=(*prefix.headway_vector, candidate.headway_minutes),
        departure_vector=(*prefix.departure_vector, *candidate.departures_minutes),
    )


def _enumerate_state_domain_v1(domain: _LayeredDomainV1, *, raw_limit: int) -> _DomainEnumerationV1:
    _validate_raw_limit_v1(raw_limit)
    if not domain.layers or any(not layer for layer in domain.layers):
        return _DomainEnumerationV1((), domain.graph_statistics, True)
    if len(domain.edges) != len(domain.layers) - 1:
        raise ValueError("layered domain requires one edge set per pair of adjacent layers")
    retained = [(_first_path_v1(domain, index),) for index in range(len(domain.layers[0]))]
    count = len(retained)
    truncated = 0
    duplicates = 0
    for layer_index, layer in enumerate(domain.layers[1:], start=1):
        predecessors: list[list[int]] = [[] for _ in layer]
        for left, right in domain.edges[layer_index - 1]:
            if not (0 <= left < len(retained) and 0 <= right < len(layer)):
                raise ValueError("domain edge index is outside its adjacent layers")
            if retained[left]:
                predecessors[right].append(left)
        next_retained = []
        for node_index, candidate in enumerate(layer):
            sources = tuple(retained[index] for index in sorted(set(predecessors[node_index])))
            # A fixed successor preserves each predecessor's canonical prefix order.
            merged = _merge_sorted_sources_v1(
                sources,
                raw_limit=raw_limit,
                transform=lambda prefix, index=node_index, phase=candidate: _extend_path_v1(
                    prefix, index, phase
                ),
            )
            next_retained.append(merged.paths)
            count += len(merged.paths)
            truncated += merged.truncated
            duplicates += merged.duplicates_suppressed
        retained = next_retained
    terminal = _merge_sorted_sources_v1(retained, raw_limit=raw_limit)
    return _DomainEnumerationV1(
        terminal.paths,
        replace(
            domain.graph_statistics,
            retained_partial_path_count=count,
            truncated_node_count=truncated,
            duplicate_departure_path_count=duplicates + terminal.duplicates_suppressed,
        ),
        not truncated and not terminal.truncated,
    )


def _merge_sorted_sources_v1(
    sources: Sequence[Sequence[_PartialPathV1]],
    *,
    raw_limit: int,
    transform: Callable[[_PartialPathV1], _PartialPathV1] | None = None,
    exact_order: bool = False,
) -> _MergeResultV1:
    """Keep K distinct departure paths, proving truncation with the next unique path.

    Technical source/item indices prevent equal keys from comparing path objects.
    Integer keys apply within a scaled domain; the family terminal merge compares
    the rational compiler objective before all other canonical tie fields.
    """
    heap: list[tuple[_PathKeyV1 | _ExactPathKeyV1, int, int, _PartialPathV1]] = []

    def push(source_index: int, item_index: int) -> None:
        path = sources[source_index][item_index]
        if transform is not None:
            path = transform(path)
        key = path.exact_key if exact_order else path.key
        heapq.heappush(heap, (key, source_index, item_index, path))

    for source_index, source in enumerate(sources):
        if source:
            push(source_index, 0)
    retained = []
    seen: set[tuple[int, ...]] = set()
    duplicates = 0
    while heap:
        _, source_index, item_index, path = heapq.heappop(heap)
        if item_index + 1 < len(sources[source_index]):
            push(source_index, item_index + 1)
        if path.departure_vector in seen:
            duplicates += 1
            continue
        if len(retained) == raw_limit:
            return _MergeResultV1(tuple(retained), True, duplicates)
        seen.add(path.departure_vector)
        retained.append(path)
    return _MergeResultV1(tuple(retained), False, duplicates)


def _decode_path_v1(
    path: _PartialPathV1,
    *,
    domain: _LayeredDomainV1,
    state: ServicePlanStateV1,
    authority: OperationalEndpointAuthorityV1,
    regimes: tuple[DemandRegimeAllocationV1, ...],
    rank: int,
) -> KBestDagCandidateV1:
    phases = tuple(
        layer[index] for layer, index in zip(domain.layers, path.phase_indices, strict=True)
    )
    objective = (Fraction(path.q_scaled, path.quantization_scale), *path.key[1:3])
    reconstructed = (
        sum((phase.quantization_error for phase in phases), Fraction(0)),
        1
        + sum(
            left.headway_minutes != right.headway_minutes
            for left, right in zip(phases, phases[1:], strict=False)
        ),
        sum(phase.phase_imbalance_minutes for phase in phases),
    )
    if objective != reconstructed:
        raise AssertionError("exact DP score differs from reconstructed phase objective")
    fingerprint = service_plan_fingerprint_v1(state)
    compilation = _compilation_from_path(
        state=state,
        state_fingerprint=fingerprint,
        authority=authority,
        regimes=regimes,
        path=_FrontierPath(phases, *objective),
        rank=rank,
    )
    validate_clean_boundary_compilation_v1(compilation, regimes)
    quantization = Fraction(0)
    for item in compilation.demand_regime_slices:
        duration = (item.demand_regime_end - item.demand_regime_start) // 60
        quantization += Fraction(
            abs(item.uniform_headway_minutes * item.authoritative_trip_count - duration),
            duration,
        )
    decoded_objective = (
        quantization,
        len(compilation.service_regimes),
        sum(item.phase_imbalance_minutes for item in compilation.demand_regime_slices),
    )
    if decoded_objective != objective:
        raise AssertionError("decoded compilation objective differs from exact DP score")
    if (
        tuple(value // 60 for value in compilation.exact_departures) != path.departure_vector
        or tuple(phase.headway_minutes for phase in phases) != path.headway_vector
        or len(compilation.exact_departures) != state.total_trips
    ):
        raise AssertionError("decoded compilation differs from exact DAG path")
    return KBestDagCandidateV1(
        state=state,
        state_fingerprint=fingerprint,
        compilation=compilation,
        compilation_fingerprint=clean_compilation_fingerprint_v1(compilation),
        compiler_objective=objective,
        exact_scaled_quantization=path.q_scaled,
        path_score=path.key,
        phase_indices=path.phase_indices,
        headway_vector=path.headway_vector,
        departure_vector=path.departure_vector,
    )


def kbest_dag_candidate_payload_v1(
    candidate: KBestDagCandidateV1, *, state_index: int
) -> dict[str, Any]:
    """Serialize semantic evidence without observational timings."""
    return {
        "fingerprint": candidate.compilation_fingerprint,
        "departures_minutes": list(candidate.departure_vector),
        "state_fingerprint": candidate.state_fingerprint,
        "state_index": state_index,
        "phase_indices": list(candidate.phase_indices),
        "headway_shape": list(candidate.headway_vector),
        "objective": [str(value) for value in candidate.compiler_objective],
        "integer_objective": [
            candidate.exact_scaled_quantization,
            *candidate.compiler_objective[1:],
        ],
        "direction": candidate.state.direction,
        "endpoint_checks": {"first": True, "last": True},
    }


def compile_service_plan_family_kbest_v1(
    *,
    states: Sequence[ServicePlanStateV1],
    endpoint_authority: OperationalEndpointAuthorityV1,
    raw_limit: int = 256,
) -> KBestDagFrontierV1:
    """Compile a family in canonical state order under its fixed endpoint authority."""
    started = perf_counter()
    _validate_raw_limit_v1(raw_limit)
    ordered_states = tuple(sorted(states, key=service_plan_fingerprint_v1))
    if not ordered_states:
        raise ValueError("states must contain at least one ServicePlan")
    fingerprints = tuple(service_plan_fingerprint_v1(state) for state in ordered_states)
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("duplicate ServicePlan fingerprint")
    for state in ordered_states:
        if not service_plan_matches_endpoint_contract_v1(state, endpoint_authority):
            raise ValueError("ServicePlan does not match the endpoint authority contract")
        if state.total_trips != ordered_states[0].total_trips:
            raise ValueError("ServicePlan family trip totals must agree")

    graph_started = perf_counter()
    domains = []
    all_regimes = []
    for state_index, state in enumerate(ordered_states):
        regimes = _regimes_from_state(state)
        all_regimes.append(regimes)
        raw = tuple(
            _phase_candidates(
                regime,
                regime_index=index,
                regime_count=len(regimes),
                authority=endpoint_authority,
            )
            for index, regime in enumerate(regimes)
        )
        witness = _candidate_path(raw)
        layers = tuple(
            _bounded_phase_candidates(
                layer, witness=witness[index] if witness else None, limit=4096
            )
            for index, layer in enumerate(raw)
        )
        domains.append(_build_layered_domain_v1(layers, state_index=state_index))
    # This scale is confined to this family; terminal comparisons remain rational.
    scale = math.lcm(*(domain.quantization_scale for domain in domains))
    domains = tuple(replace(domain, quantization_scale=scale) for domain in domains)
    graph_seconds = perf_counter() - graph_started

    dp_started = perf_counter()
    enumerations = tuple(
        _enumerate_state_domain_v1(domain, raw_limit=raw_limit) for domain in domains
    )
    dp_seconds = perf_counter() - dp_started
    merge_started = perf_counter()
    merged = _merge_sorted_sources_v1(
        tuple(enumeration.paths for enumeration in enumerations),
        raw_limit=raw_limit,
        exact_order=True,
    )
    merge_seconds = perf_counter() - merge_started

    decode_started = perf_counter()
    candidates = tuple(
        _decode_path_v1(
            path,
            domain=domains[path.state_index],
            state=ordered_states[path.state_index],
            authority=endpoint_authority,
            regimes=all_regimes[path.state_index],
            rank=rank,
        )
        for rank, path in enumerate(merged.paths, start=1)
    )
    decode_seconds = perf_counter() - decode_started
    statistics = KBestDagGraphStatisticsV1(
        **{
            field.name: sum(getattr(item.graph_statistics, field.name) for item in enumerations)
            for field in fields(KBestDagGraphStatisticsV1)
        }
    )
    statistics = replace(
        statistics,
        duplicate_departure_path_count=(
            statistics.duplicate_departure_path_count + merged.duplicates_suppressed
        ),
    )
    return KBestDagFrontierV1(
        candidates=candidates,
        ordered_fingerprints=tuple(candidate.compilation_fingerprint for candidate in candidates),
        requested_raw_limit=raw_limit,
        natural_exhaustion=(
            all(item.natural_exhaustion for item in enumerations) and not merged.truncated
        ),
        graph_statistics=statistics,
        telemetry=KBestDagTelemetryV1(
            graph_construction_seconds=graph_seconds,
            dynamic_programming_seconds=dp_seconds,
            final_merge_seconds=merge_seconds,
            decoding_seconds=decode_seconds,
            total_seconds=perf_counter() - started,
        ),
    )

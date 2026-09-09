"""Hard eligibility and aggregate diversity for exact DAG shadow candidates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from time import perf_counter
from typing import Any

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
    service_plan_matches_endpoint_contract_v1,
)
from .local_rhythm_refinement import retain_strict_directional_canonicalizations_v1
from .service_plan_coordinator import (
    DirectionalCompilationCandidateV1,
    evaluate_actual_service_v1,
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
    progressing = (
        retain_strict_directional_canonicalizations_v1(source_directional, eligible)
        if eligible
        else ()
    )
    return KBestDagEligibilityResultV1(
        raw_candidates=raw_candidates,
        eligible_candidates=tuple(eligible),
        candidates=tuple(progressing),
        structural_rejects=rejects["structural"],
        protection_rejects=rejects["protection"],
        tail_rejects=rejects["tail"],
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

"""Bounded post-frontier local rhythm canonicalization for ServicePlan search."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .contracts_v1.clean_compile_frontier import compile_service_plan_frontier_v1
from .contracts_v1.closed_loop_service_protection import (
    validate_closed_loop_service_protection_v1,
)
from .contracts_v1.operational_selection_policy_v3 import (
    DEFAULT_OPERATIONAL_SELECTION_POLICY_V3,
    OperationalSelectionPolicyV3,
    select_operational_timetable_v3,
)
from .contracts_v1.service_plan_state import (
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    service_plan_fingerprint_v1,
    validate_service_plan_state_v1,
)
from .service_plan_coordinator import (
    DEFAULT_COORDINATOR_SEARCH_BUDGET_V1,
    CoordinatorSearchBudgetV1,
    DirectionalCompilationCandidateV1,
    evaluate_actual_service_v1,
    evaluate_operating_pair_v1,
    search_route_service_plans_v1,
    update_operating_pair_pareto_v1,
)

LOCAL_RHYTHM_REFINEMENT_PROFILE_V1 = "bounded_local_rhythm_refinement_v1"
LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID = "LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID"
LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING = "LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING"

MAX_BOUNDARY_STEP_RADIUS = 3
MAX_TRIP_TRANSFER_RADIUS = 3
LOCAL_COMPILE_FRONTIER_LIMIT = 256
LOCAL_RHYTHM_REFINEMENT_COMPLETE = "LOCAL_RHYTHM_REFINEMENT_COMPLETE"


class LocalRhythmFamilyPlanMappingError(ValueError):
    """Raised when actual ServiceRegimes cannot be mapped to one planning span."""


@dataclass(frozen=True, slots=True)
class LocalRhythmFamilyV1:
    start_index: int
    end_index: int
    service_regime_ids: tuple[str, ...]
    headways: tuple[int, ...]
    trip_counts: tuple[int, ...]
    internal_gap_counts: tuple[int, ...]
    canonical_representative: int
    micro_rhythm_boundary_count: int


@dataclass(frozen=True, slots=True)
class LocalRhythmStateGenerationStatisticsV1:
    merged_states: int
    structural_local_combinations: int
    invalid_local_states: int
    valid_unique_local_states: int


@dataclass(frozen=True, slots=True)
class LocalRhythmStateGenerationV1:
    states: tuple[ServicePlanStateV1, ...]
    statistics: LocalRhythmStateGenerationStatisticsV1


@dataclass(frozen=True, slots=True)
class LocalRhythmRefinementPolicyV1:
    boundary_step_radius: int = MAX_BOUNDARY_STEP_RADIUS
    trip_transfer_radius: int = MAX_TRIP_TRANSFER_RADIUS
    local_compile_frontier_limit: int = LOCAL_COMPILE_FRONTIER_LIMIT
    selection_policy: OperationalSelectionPolicyV3 = DEFAULT_OPERATIONAL_SELECTION_POLICY_V3

    def __post_init__(self) -> None:
        if (
            self.boundary_step_radius != MAX_BOUNDARY_STEP_RADIUS
            or self.trip_transfer_radius != MAX_TRIP_TRANSFER_RADIUS
            or self.local_compile_frontier_limit != LOCAL_COMPILE_FRONTIER_LIMIT
        ):
            raise ValueError("PR62-U local technical limits are frozen at 3/3/256")


DEFAULT_LOCAL_RHYTHM_REFINEMENT_POLICY_V1 = LocalRhythmRefinementPolicyV1()


@dataclass(frozen=True, slots=True)
class DirectionalLocalCompileResultV1:
    candidates: tuple[Any, ...]
    generated_directional_compile_fingerprints: tuple[str, ...]
    compiler_calls: int
    compile_variants: int
    compiler_cap_binding_count: int
    protection_rejects: int
    tail_rejects: int
    retained_directional_canonical_candidates: int
    classification: str


@dataclass(frozen=True, slots=True)
class PairCrossProductResultV1:
    frontier: tuple[Any, ...]
    generated_pair_fingerprints: tuple[str, ...]
    pair_cross_products_evaluated: int
    fleet_rejects: int
    strict_rhythm_rejects: int
    duplicate_pair_rejects: int
    pareto_admitted_generated_pairs: int


@dataclass(frozen=True, slots=True)
class SourcePairRefinementV1:
    frontier: tuple[Any, ...]
    source_has_target_family: bool
    target_family_count_by_direction: tuple[tuple[str, int], ...]
    family_headways: tuple[tuple[str, tuple[int, ...]], ...]
    canonical_representatives: tuple[tuple[str, int], ...]
    source_micro_boundary_count: int
    merged_states: int
    structural_local_combinations: int
    invalid_local_states: int
    valid_unique_local_states: int
    compiler_calls: int
    compile_variants: int
    compiler_cap_binding_count: int
    protection_rejects: int
    tail_rejects: int
    retained_directional_canonical_candidates: int
    pair_cross_products_evaluated: int
    fleet_rejects: int
    strict_rhythm_rejects: int
    duplicate_pair_rejects: int
    pareto_admitted_generated_pairs: int
    generated_pair_fingerprints: tuple[str, ...]
    generated_directional_compile_fingerprints: tuple[str, ...]
    classification: str

    @classmethod
    def empty(cls, frontier: Sequence[Any]) -> SourcePairRefinementV1:
        return cls(
            frontier=tuple(frontier),
            source_has_target_family=False,
            target_family_count_by_direction=(("outbound", 0), ("inbound", 0)),
            family_headways=(),
            canonical_representatives=(),
            source_micro_boundary_count=0,
            merged_states=0,
            structural_local_combinations=0,
            invalid_local_states=0,
            valid_unique_local_states=0,
            compiler_calls=0,
            compile_variants=0,
            compiler_cap_binding_count=0,
            protection_rejects=0,
            tail_rejects=0,
            retained_directional_canonical_candidates=0,
            pair_cross_products_evaluated=0,
            fleet_rejects=0,
            strict_rhythm_rejects=0,
            duplicate_pair_rejects=0,
            pareto_admitted_generated_pairs=0,
            generated_pair_fingerprints=(),
            generated_directional_compile_fingerprints=(),
            classification=LOCAL_RHYTHM_REFINEMENT_COMPLETE,
        )


@dataclass(frozen=True, slots=True)
class LocalRhythmRefinementStatisticsV1:
    global_coordinator_executions: int
    source_materiality_pair_count: int
    source_pairs_with_target_families: int
    target_family_count_by_direction: tuple[tuple[str, int], ...]
    family_headways: tuple[tuple[str, tuple[int, ...]], ...]
    canonical_representatives: tuple[tuple[str, int], ...]
    source_micro_boundary_count: int
    merged_states: int
    structural_local_combinations: int
    invalid_local_states: int
    valid_unique_local_states: int
    compiler_calls: int
    compile_variants: int
    compiler_cap_binding_count: int
    protection_rejects: int
    tail_rejects: int
    retained_directional_canonical_candidates: int
    pair_cross_products_evaluated: int
    fleet_rejects: int
    strict_rhythm_rejects: int
    duplicate_pair_rejects: int
    pareto_admitted_generated_pairs: int
    processed_source_count: int
    refinement_iterations: int
    base_frontier_count: int
    final_frontier_count: int
    selection_anchor_history: tuple[tuple[int, str | None, float | None], ...]


@dataclass(frozen=True, slots=True)
class LocalRhythmRefinementResultV1:
    base_coordinator_result: Any
    base_v3_selection: Any
    augmented_pareto_frontier: tuple[Any, ...]
    final_v3_selection: Any
    statistics: LocalRhythmRefinementStatisticsV1
    processed_source_pair_fingerprints: tuple[str, ...]
    generated_pair_fingerprints: tuple[str, ...]
    generated_directional_compile_fingerprints: tuple[str, ...]
    classification: str


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


def _canonical_representative_v1(headways: Sequence[int], trip_counts: Sequence[int]) -> int:
    lower = max(headways) - 1
    upper = min(headways) + 1
    if lower > upper:
        raise ValueError("local rhythm family has no valid integer representative")
    candidates = range(lower, upper + 1)
    return min(
        candidates,
        key=lambda candidate: (
            sum(
                (trip_count - 1) * abs(headway - candidate)
                for headway, trip_count in zip(headways, trip_counts, strict=True)
            ),
            candidate,
        ),
    )


def detect_local_rhythm_families_v1(
    service_regimes: Sequence[Any],
) -> tuple[LocalRhythmFamilyV1, ...]:
    """Detect deterministic non-overlapping maximal sustained near-rhythm families."""

    families: list[LocalRhythmFamilyV1] = []
    index = 0
    while index < len(service_regimes):
        if int(_field(service_regimes[index], "trip_count")) < 3:
            index += 1
            continue
        end = index + 1
        headways = [int(_field(service_regimes[index], "uniform_headway_minutes"))]
        while end < len(service_regimes):
            regime = service_regimes[end]
            if int(_field(regime, "trip_count")) < 3:
                break
            candidate_headway = int(_field(regime, "uniform_headway_minutes"))
            if max((*headways, candidate_headway)) - min((*headways, candidate_headway)) > 2:
                break
            headways.append(candidate_headway)
            end += 1
        if end - index < 2:
            index += 1
            continue
        members = service_regimes[index:end]
        trip_counts = tuple(int(_field(item, "trip_count")) for item in members)
        exact_headways = tuple(int(_field(item, "uniform_headway_minutes")) for item in members)
        families.append(
            LocalRhythmFamilyV1(
                start_index=index,
                end_index=end - 1,
                service_regime_ids=tuple(
                    str(_field(item, "service_regime_id")) for item in members
                ),
                headways=exact_headways,
                trip_counts=trip_counts,
                internal_gap_counts=tuple(item - 1 for item in trip_counts),
                canonical_representative=_canonical_representative_v1(exact_headways, trip_counts),
                micro_rhythm_boundary_count=sum(
                    left != right
                    for left, right in zip(exact_headways, exact_headways[1:], strict=False)
                ),
            )
        )
        index = end
    return tuple(families)


def map_actual_family_to_planning_indices_v1(
    *, state: ServicePlanStateV1, compilation: Any, family: LocalRhythmFamilyV1
) -> tuple[int, ...]:
    """Map a family through ordered demand-regime slices without parsing identifiers."""

    slices = tuple(compilation.demand_regime_slices)
    family_ids = set(family.service_regime_ids)
    indices = tuple(
        index for index, item in enumerate(slices) if str(item.service_regime_id) in family_ids
    )
    mapped_service_ids = {str(slices[index].service_regime_id) for index in indices}
    valid = (
        len(slices) == len(state.service_regimes)
        and bool(indices)
        and mapped_service_ids == family_ids
        and len(indices) == len(set(indices))
        and indices == tuple(range(indices[0], indices[-1] + 1))
    )
    if not valid:
        raise LocalRhythmFamilyPlanMappingError(LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID)
    return indices


def _merged_family_state_v1(
    source: ServicePlanStateV1, planning_indices: Sequence[int]
) -> ServicePlanStateV1:
    indices = tuple(planning_indices)
    valid = (
        bool(indices)
        and len(indices) == len(set(indices))
        and indices == tuple(sorted(indices))
        and indices == tuple(range(indices[0], indices[-1] + 1))
        and indices[-1] < len(source.service_regimes)
    )
    if not valid:
        raise LocalRhythmFamilyPlanMappingError(LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID)
    first, last = indices[0], indices[-1]
    merged = ServiceRegimeDecisionV1(
        start=source.service_regimes[first].start,
        end=source.service_regimes[last].end,
        trip_count=sum(item.trip_count for item in source.service_regimes[first : last + 1]),
    )
    return dataclasses.replace(
        source,
        service_regimes=(
            *source.service_regimes[:first],
            merged,
            *source.service_regimes[last + 1 :],
        ),
        parent_fingerprint=service_plan_fingerprint_v1(source),
        operation="LOCAL_RHYTHM_CANONICALIZE",
        operation_evidence="LOCAL_NEAR_EQUIVALENT_RHYTHM_FAMILY",
    )


def enumerate_local_rhythm_states_v1(
    *,
    source: ServicePlanStateV1,
    planning_indices: Sequence[int],
    planning_grid_seconds: int,
) -> LocalRhythmStateGenerationV1:
    """Enumerate radius-3 adjustments on one immediate external side at a time."""

    merged = _merged_family_state_v1(source, planning_indices)
    merged_index = tuple(planning_indices)[0]
    sides: list[tuple[int, int]] = []
    if merged_index > 0:
        sides.append((merged_index - 1, merged_index))
    if merged_index + 1 < len(merged.service_regimes):
        sides.append((merged_index, merged_index + 1))
    if not sides:
        return LocalRhythmStateGenerationV1(
            states=(),
            statistics=LocalRhythmStateGenerationStatisticsV1(1, 0, 0, 0),
        )

    unique: dict[str, ServicePlanStateV1] = {}
    invalid = 0
    attempted_fingerprints: set[str] = set()
    for left_index, right_index in sides:
        left = merged.service_regimes[left_index]
        right = merged.service_regimes[right_index]
        for boundary_step in range(-MAX_BOUNDARY_STEP_RADIUS, MAX_BOUNDARY_STEP_RADIUS + 1):
            boundary = left.end + boundary_step * planning_grid_seconds
            for transfer in range(-MAX_TRIP_TRANSFER_RADIUS, MAX_TRIP_TRANSFER_RADIUS + 1):
                left_count = left.trip_count + transfer
                right_count = right.trip_count - transfer
                if (
                    boundary <= left.start
                    or boundary >= right.end
                    or min(left_count, right_count) < 2
                ):
                    invalid += 1
                    continue
                regimes = list(merged.service_regimes)
                regimes[left_index] = ServiceRegimeDecisionV1(left.start, boundary, left_count)
                regimes[right_index] = ServiceRegimeDecisionV1(boundary, right.end, right_count)
                candidate = dataclasses.replace(merged, service_regimes=tuple(regimes))
                fingerprint = service_plan_fingerprint_v1(candidate)
                if fingerprint in attempted_fingerprints:
                    continue
                attempted_fingerprints.add(fingerprint)
                errors = validate_service_plan_state_v1(
                    candidate,
                    authoritative_total_trips=source.total_trips,
                    planning_grid_seconds=planning_grid_seconds,
                    floor_headway_minutes=None,
                )
                if errors:
                    invalid += 1
                    continue
                unique[fingerprint] = candidate
    structural = len(sides) * 49 - (len(sides) - 1)
    states = tuple(unique[key] for key in sorted(unique))
    return LocalRhythmStateGenerationV1(
        states=states,
        statistics=LocalRhythmStateGenerationStatisticsV1(
            merged_states=1,
            structural_local_combinations=structural,
            invalid_local_states=invalid,
            valid_unique_local_states=len(states),
        ),
    )


def actual_micro_rhythm_boundary_count_v1(compilation: Any) -> int:
    return sum(
        family.micro_rhythm_boundary_count
        for family in detect_local_rhythm_families_v1(compilation.service_regimes)
    )


def retain_strict_directional_canonicalizations_v1(
    source: Any, candidates: Sequence[Any]
) -> tuple[Any, ...]:
    source_count = actual_micro_rhythm_boundary_count_v1(source.compile_variant.compilation)
    return tuple(
        candidate
        for candidate in candidates
        if actual_micro_rhythm_boundary_count_v1(candidate.compile_variant.compilation)
        < source_count
    )


def pair_rhythm_tuple_v1(candidate: Any) -> tuple[int, int, int, int]:
    metrics = candidate.metrics
    return (
        metrics.total_directional_sustained_headway_level_count,
        metrics.actual_service_regime_count,
        metrics.total_directional_effective_palette_count,
        metrics.total_single_gap_regime_count,
    )


def strict_pair_rhythm_progress_v1(source: Any, generated: Any) -> bool:
    return pair_rhythm_tuple_v1(generated) < pair_rhythm_tuple_v1(source)


def compile_local_states_v1(
    *, source_directional: Any, states: Sequence[ServicePlanStateV1], context: Any
) -> DirectionalLocalCompileResultV1:
    """Compile and revalidate local states through the existing production authorities."""

    candidates: dict[str, DirectionalCompilationCandidateV1] = {}
    compiler_calls = 0
    compile_variants = 0
    cap_bindings = 0
    protection_rejects = 0
    tail_rejects = 0
    for state in states:
        compiler_calls += 1
        frontier = compile_service_plan_frontier_v1(
            state,
            endpoint_authority=context.endpoint_authority[state.direction],
            compile_frontier_limit=LOCAL_COMPILE_FRONTIER_LIMIT,
        )
        cap_bindings += int(frontier.variants_limit_pruned > 0)
        for variant in frontier.variants:
            compile_variants += 1
            protection = validate_closed_loop_service_protection_v1(
                authority=context.service_protection_authority,
                direction=state.direction,
                exact_departures=variant.compilation.exact_departures,
            )
            if not protection.passed:
                protection_rejects += 1
                continue
            metrics, feedback = evaluate_actual_service_v1(
                variant,
                demand_buckets=context.demand_buckets[state.direction],
                scenario_b_departures=context.scenario_b_departures[state.direction],
                demand_response_regimes=(
                    None
                    if context.demand_response_regimes is None
                    else context.demand_response_regimes[state.direction]
                ),
                protection_authority=context.service_protection_authority,
                protection_validation=protection,
            )
            if not metrics.tail_ordering.eligible:
                tail_rejects += 1
                continue
            record = DirectionalCompilationCandidateV1(
                state=state,
                state_fingerprint=service_plan_fingerprint_v1(state),
                compile_variant=variant,
                metrics=metrics,
                feedback=feedback,
                history=("LIVE_LOCAL_RHYTHM_REFINEMENT_GENERATED",),
            )
            candidates.setdefault(variant.compilation_fingerprint, record)
    retained = (
        retain_strict_directional_canonicalizations_v1(
            source_directional, tuple(candidates.values())
        )
        if candidates
        else ()
    )
    retained = tuple(
        sorted(retained, key=lambda item: item.compile_variant.compilation_fingerprint)
    )
    return DirectionalLocalCompileResultV1(
        candidates=retained,
        generated_directional_compile_fingerprints=tuple(
            item.compile_variant.compilation_fingerprint for item in retained
        ),
        compiler_calls=compiler_calls,
        compile_variants=compile_variants,
        compiler_cap_binding_count=cap_bindings,
        protection_rejects=protection_rejects,
        tail_rejects=tail_rejects,
        retained_directional_canonical_candidates=len(retained),
        classification=(
            LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING
            if cap_bindings
            else LOCAL_RHYTHM_REFINEMENT_COMPLETE
        ),
    )


def evaluate_directional_cross_product_v1(
    *,
    source_pair: Any,
    outbound_options: Sequence[Any],
    inbound_options: Sequence[Any],
    context: Any,
    frontier: Sequence[Any],
    pair_frontier_limit: int,
    already_generated: set[str],
) -> PairCrossProductResultV1:
    """Evaluate the complete directional cross-product through exact pair authority."""

    current = tuple(frontier)
    generated: list[str] = []
    evaluated = 0
    fleet_rejects = 0
    strict_rejects = 0
    duplicate_rejects = 0
    admitted = 0
    for outbound in outbound_options:
        for inbound in inbound_options:
            evaluated += 1
            pair, _feedback = evaluate_operating_pair_v1(outbound, inbound, context=context)
            if pair is None:
                fleet_rejects += 1
                continue
            fingerprint = pair.pair_fingerprint
            if fingerprint in already_generated:
                duplicate_rejects += 1
                continue
            already_generated.add(fingerprint)
            generated.append(fingerprint)
            if not strict_pair_rhythm_progress_v1(source_pair, pair):
                strict_rejects += 1
                continue
            before = {item.pair_fingerprint for item in current}
            updated = update_operating_pair_pareto_v1(current, pair, limit=pair_frontier_limit)
            after = {item.pair_fingerprint for item in updated}
            admitted += int(fingerprint in after and fingerprint not in before)
            current = updated
    return PairCrossProductResultV1(
        frontier=current,
        generated_pair_fingerprints=tuple(generated),
        pair_cross_products_evaluated=evaluated,
        fleet_rejects=fleet_rejects,
        strict_rhythm_rejects=strict_rejects,
        duplicate_pair_rejects=duplicate_rejects,
        pareto_admitted_generated_pairs=admitted,
    )


def _deduplicate_directional_options_v1(options: Sequence[Any]) -> tuple[Any, ...]:
    unique: dict[str, Any] = {}
    for option in options:
        unique.setdefault(option.compile_variant.compilation_fingerprint, option)
    return tuple(unique.values())


def refine_source_pair_v1(
    *,
    source_pair: Any,
    context: Any,
    frontier: Sequence[Any],
    pair_frontier_limit: int,
    already_generated: set[str],
) -> SourcePairRefinementV1:
    """Refine all target families of one V3-materiality source pair."""

    target_counts = {"outbound": 0, "inbound": 0}
    family_headways: list[tuple[str, tuple[int, ...]]] = []
    representatives: list[tuple[str, int]] = []
    directional_options: dict[str, list[Any]] = {
        "outbound": [source_pair.outbound],
        "inbound": [source_pair.inbound],
    }
    merged_states = structural = invalid = valid = 0
    compiler_calls = variants = cap_bindings = protection_rejects = tail_rejects = 0
    retained = 0
    directional_fingerprints: set[str] = set()
    source_micro = 0
    classification = LOCAL_RHYTHM_REFINEMENT_COMPLETE

    for direction in ("outbound", "inbound"):
        source_directional = getattr(source_pair, direction)
        compilation = source_directional.compile_variant.compilation
        source_micro += actual_micro_rhythm_boundary_count_v1(compilation)
        families = tuple(
            family
            for family in detect_local_rhythm_families_v1(compilation.service_regimes)
            if family.micro_rhythm_boundary_count > 0
        )
        target_counts[direction] = len(families)
        for family in families:
            family_headways.append((direction, family.headways))
            representatives.append((direction, family.canonical_representative))
            try:
                indices = map_actual_family_to_planning_indices_v1(
                    state=source_directional.state,
                    compilation=compilation,
                    family=family,
                )
            except LocalRhythmFamilyPlanMappingError:
                continue
            generation = enumerate_local_rhythm_states_v1(
                source=source_directional.state,
                planning_indices=indices,
                planning_grid_seconds=context.planning_grid_seconds,
            )
            merged_states += generation.statistics.merged_states
            structural += generation.statistics.structural_local_combinations
            invalid += generation.statistics.invalid_local_states
            valid += generation.statistics.valid_unique_local_states
            compiled = compile_local_states_v1(
                source_directional=source_directional,
                states=generation.states,
                context=context,
            )
            compiler_calls += compiled.compiler_calls
            variants += compiled.compile_variants
            cap_bindings += compiled.compiler_cap_binding_count
            protection_rejects += compiled.protection_rejects
            tail_rejects += compiled.tail_rejects
            retained += compiled.retained_directional_canonical_candidates
            directional_fingerprints.update(compiled.generated_directional_compile_fingerprints)
            directional_options[direction].extend(compiled.candidates)
            if compiled.classification == LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING:
                classification = LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING

    if not any(target_counts.values()):
        return SourcePairRefinementV1.empty(frontier)

    outbound_options = _deduplicate_directional_options_v1(directional_options["outbound"])
    inbound_options = _deduplicate_directional_options_v1(directional_options["inbound"])
    cross_product = evaluate_directional_cross_product_v1(
        source_pair=source_pair,
        outbound_options=outbound_options,
        inbound_options=inbound_options,
        context=context,
        frontier=frontier,
        pair_frontier_limit=pair_frontier_limit,
        already_generated=already_generated,
    )
    return SourcePairRefinementV1(
        frontier=cross_product.frontier,
        source_has_target_family=True,
        target_family_count_by_direction=tuple(target_counts.items()),
        family_headways=tuple(family_headways),
        canonical_representatives=tuple(representatives),
        source_micro_boundary_count=source_micro,
        merged_states=merged_states,
        structural_local_combinations=structural,
        invalid_local_states=invalid,
        valid_unique_local_states=valid,
        compiler_calls=compiler_calls,
        compile_variants=variants,
        compiler_cap_binding_count=cap_bindings,
        protection_rejects=protection_rejects,
        tail_rejects=tail_rejects,
        retained_directional_canonical_candidates=retained,
        pair_cross_products_evaluated=cross_product.pair_cross_products_evaluated,
        fleet_rejects=cross_product.fleet_rejects,
        strict_rhythm_rejects=cross_product.strict_rhythm_rejects,
        duplicate_pair_rejects=cross_product.duplicate_pair_rejects,
        pareto_admitted_generated_pairs=cross_product.pareto_admitted_generated_pairs,
        generated_pair_fingerprints=cross_product.generated_pair_fingerprints,
        generated_directional_compile_fingerprints=tuple(sorted(directional_fingerprints)),
        classification=classification,
    )


def search_route_service_plans_with_local_rhythm_refinement_v1(
    *,
    context: Any,
    seeds: Sequence[ServicePlanStateV1],
    coordinator_budget: CoordinatorSearchBudgetV1 = DEFAULT_COORDINATOR_SEARCH_BUDGET_V1,
    refinement_policy: LocalRhythmRefinementPolicyV1 = DEFAULT_LOCAL_RHYTHM_REFINEMENT_POLICY_V1,
) -> LocalRhythmRefinementResultV1:
    """Run one global search followed by finite strict-progress local refinement."""

    base = search_route_service_plans_v1(context=context, seeds=seeds, budget=coordinator_budget)
    frontier = tuple(base.pareto_frontier)
    base_selection = select_operational_timetable_v3(
        context=context,
        candidates=frontier,
        policy=refinement_policy.selection_policy,
    )
    selection = base_selection
    processed: set[str] = set()
    generated_pairs: set[str] = set()
    generated_directional: set[str] = set()
    counts: dict[str, int] = {
        "source_materiality_pair_count": 0,
        "source_pairs_with_target_families": 0,
        "source_micro_boundary_count": 0,
        "merged_states": 0,
        "structural_local_combinations": 0,
        "invalid_local_states": 0,
        "valid_unique_local_states": 0,
        "compiler_calls": 0,
        "compile_variants": 0,
        "compiler_cap_binding_count": 0,
        "protection_rejects": 0,
        "tail_rejects": 0,
        "retained_directional_canonical_candidates": 0,
        "pair_cross_products_evaluated": 0,
        "fleet_rejects": 0,
        "strict_rhythm_rejects": 0,
        "duplicate_pair_rejects": 0,
        "pareto_admitted_generated_pairs": 0,
    }
    target_counts = {"outbound": 0, "inbound": 0}
    family_headways: list[tuple[str, tuple[int, ...]]] = []
    representatives: list[tuple[str, int]] = []
    iterations = 0
    anchor_history: list[tuple[int, str | None, float | None]] = [
        (
            0,
            base_selection.common_anchor_fingerprint,
            base_selection.continuous_preservation_bound,
        )
    ]
    classification = LOCAL_RHYTHM_REFINEMENT_COMPLETE

    while True:
        unprocessed = tuple(
            fingerprint
            for fingerprint in selection.phase_robust_materiality_fingerprints
            if fingerprint not in processed
        )
        if not unprocessed:
            break
        iterations += 1
        by_fingerprint = {item.pair_fingerprint: item for item in frontier}
        for fingerprint in unprocessed:
            processed.add(fingerprint)
            counts["source_materiality_pair_count"] += 1
            source_pair = by_fingerprint.get(fingerprint)
            if source_pair is None:
                continue
            refined = refine_source_pair_v1(
                source_pair=source_pair,
                context=context,
                frontier=frontier,
                pair_frontier_limit=coordinator_budget.max_pair_frontier,
                already_generated=generated_pairs,
            )
            frontier = refined.frontier
            counts["source_pairs_with_target_families"] += int(refined.source_has_target_family)
            for direction, value in refined.target_family_count_by_direction:
                target_counts[direction] += value
            family_headways.extend(refined.family_headways)
            representatives.extend(refined.canonical_representatives)
            for name in (
                "source_micro_boundary_count",
                "merged_states",
                "structural_local_combinations",
                "invalid_local_states",
                "valid_unique_local_states",
                "compiler_calls",
                "compile_variants",
                "compiler_cap_binding_count",
                "protection_rejects",
                "tail_rejects",
                "retained_directional_canonical_candidates",
                "pair_cross_products_evaluated",
                "fleet_rejects",
                "strict_rhythm_rejects",
                "duplicate_pair_rejects",
                "pareto_admitted_generated_pairs",
            ):
                counts[name] += int(getattr(refined, name))
            generated_directional.update(refined.generated_directional_compile_fingerprints)
            if refined.classification == LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING:
                classification = LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING
        selection = select_operational_timetable_v3(
            context=context,
            candidates=frontier,
            policy=refinement_policy.selection_policy,
        )
        anchor_history.append(
            (
                iterations,
                selection.common_anchor_fingerprint,
                selection.continuous_preservation_bound,
            )
        )

    statistics = LocalRhythmRefinementStatisticsV1(
        global_coordinator_executions=1,
        source_materiality_pair_count=counts["source_materiality_pair_count"],
        source_pairs_with_target_families=counts["source_pairs_with_target_families"],
        target_family_count_by_direction=tuple(target_counts.items()),
        family_headways=tuple(family_headways),
        canonical_representatives=tuple(representatives),
        source_micro_boundary_count=counts["source_micro_boundary_count"],
        merged_states=counts["merged_states"],
        structural_local_combinations=counts["structural_local_combinations"],
        invalid_local_states=counts["invalid_local_states"],
        valid_unique_local_states=counts["valid_unique_local_states"],
        compiler_calls=counts["compiler_calls"],
        compile_variants=counts["compile_variants"],
        compiler_cap_binding_count=counts["compiler_cap_binding_count"],
        protection_rejects=counts["protection_rejects"],
        tail_rejects=counts["tail_rejects"],
        retained_directional_canonical_candidates=counts[
            "retained_directional_canonical_candidates"
        ],
        pair_cross_products_evaluated=counts["pair_cross_products_evaluated"],
        fleet_rejects=counts["fleet_rejects"],
        strict_rhythm_rejects=counts["strict_rhythm_rejects"],
        duplicate_pair_rejects=counts["duplicate_pair_rejects"],
        pareto_admitted_generated_pairs=counts["pareto_admitted_generated_pairs"],
        processed_source_count=len(processed),
        refinement_iterations=iterations,
        base_frontier_count=len(base.pareto_frontier),
        final_frontier_count=len(frontier),
        selection_anchor_history=tuple(anchor_history),
    )
    return LocalRhythmRefinementResultV1(
        base_coordinator_result=base,
        base_v3_selection=base_selection,
        augmented_pareto_frontier=frontier,
        final_v3_selection=selection,
        statistics=statistics,
        processed_source_pair_fingerprints=tuple(sorted(processed)),
        generated_pair_fingerprints=tuple(sorted(generated_pairs)),
        generated_directional_compile_fingerprints=tuple(sorted(generated_directional)),
        classification=classification,
    )

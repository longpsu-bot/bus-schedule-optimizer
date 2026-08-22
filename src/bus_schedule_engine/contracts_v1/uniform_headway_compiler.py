"""Deterministic whole-direction uniform-headway schedule compiler V1."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from .uniform_headway_compiler_models import (
    CompilationStatusV1,
    CompiledDepartureV1,
    CompiledScheduleCandidateV1,
    CompilerDemandRegimeInputV1,
    CompilerInputV1,
    DemandRegimeCompilationV1,
    FleetValidationStatusV1,
    ServiceRegimeV1,
)


@dataclass(frozen=True, slots=True)
class LocalScheduleCandidateV1:
    regime: CompilerDemandRegimeInputV1
    headway_minutes: int | None
    phase_offset_minutes: int
    departures: tuple[int, ...]
    nominal_headway: Fraction
    quantization_error: Fraction
    reference_headway: int
    leading_slack_minutes: int
    trailing_slack_minutes: int
    edge_balance_error: int

    @property
    def first_departure_minute(self) -> int:
        return self.departures[0]

    @property
    def last_departure_minute(self) -> int:
        return self.departures[-1]

    @property
    def local_reference_headway(self) -> int:
        return self.reference_headway

    @property
    def headway_tiebreak_value(self) -> int:
        return self.headway_minutes if self.headway_minutes is not None else 0


@dataclass(frozen=True, slots=True)
class _DpState:
    current: LocalScheduleCandidateV1
    choices: tuple[LocalScheduleCandidateV1, ...]
    worst_gap_excess: int
    total_gap_excess: int
    total_quantization_units: int
    service_regime_count: int
    transition_shape_error_twice: int
    edge_balance_error: int
    headway_vector: tuple[int, ...]
    phase_vector: tuple[int, ...]
    departure_vector: tuple[int, ...]

    @property
    def score(self) -> tuple[object, ...]:
        return (
            self.worst_gap_excess,
            self.total_gap_excess,
            self.total_quantization_units,
            self.service_regime_count,
            self.transition_shape_error_twice,
            self.edge_balance_error,
            self.headway_vector,
            self.phase_vector,
            self.departure_vector,
        )


def enumerate_local_schedule_candidates_v1(
    regime: CompilerDemandRegimeInputV1,
) -> tuple[LocalScheduleCandidateV1, ...]:
    """Enumerate every feasible integer ``(h, phase)`` schedule for one regime."""
    duration = regime.duration_minutes
    count = regime.allocated_trip_count
    nominal = Fraction(duration, count)
    candidates: list[LocalScheduleCandidateV1] = []
    if count == 1:
        headway_phase_pairs: tuple[tuple[int | None, int], ...] = tuple(
            (None, phase) for phase in range(duration)
        )
    else:
        maximum_headway = (duration - 1) // (count - 1)
        headway_phase_pairs = tuple(
            (headway, phase)
            for headway in range(1, maximum_headway + 1)
            for phase in range(duration - (count - 1) * headway)
        )
    for headway, phase in headway_phase_pairs:
        if headway is None:
            departures = (regime.start_minute + phase,)
            quantization_error = Fraction(0)
        else:
            departures = tuple(
                regime.start_minute + phase + index * headway for index in range(count)
            )
            quantization_error = Fraction(abs(duration - count * headway), duration)
        leading = departures[0] - regime.start_minute
        trailing = regime.end_minute - departures[-1]
        candidates.append(
            LocalScheduleCandidateV1(
                regime=regime,
                headway_minutes=headway,
                phase_offset_minutes=phase,
                departures=departures,
                nominal_headway=nominal,
                quantization_error=quantization_error,
                reference_headway=(headway if headway is not None else duration),
                leading_slack_minutes=leading,
                trailing_slack_minutes=trailing,
                edge_balance_error=abs(leading - trailing),
            )
        )
    return tuple(candidates)


def _gap_excess(gap: int, ceiling: int) -> int:
    return max(0, gap - ceiling)


@lru_cache(maxsize=4096)
def _transition_metrics(
    gap: int,
    left_reference: int,
    right_reference: int,
) -> tuple[int, int]:
    ceiling = max(left_reference, right_reference)
    excess = _gap_excess(gap, ceiling)
    error_twice = abs(2 * gap - left_reference - right_reference)
    return excess, error_twice


def _can_merge(
    left: LocalScheduleCandidateV1,
    right: LocalScheduleCandidateV1,
) -> bool:
    return (
        left.headway_minutes is not None
        and left.headway_minutes == right.headway_minutes
        and right.first_departure_minute - left.last_departure_minute == left.headway_minutes
    )


def _initial_states(
    compiler_input: CompilerInputV1,
    candidates: tuple[LocalScheduleCandidateV1, ...],
    quantization_scale: int,
) -> tuple[_DpState, ...]:
    states = []
    for candidate in candidates:
        start_gap = candidate.first_departure_minute - compiler_input.service_start_minute
        excess = _gap_excess(start_gap, candidate.local_reference_headway)
        states.append(
            _DpState(
                current=candidate,
                choices=(candidate,),
                worst_gap_excess=excess,
                total_gap_excess=excess,
                total_quantization_units=int(candidate.quantization_error * quantization_scale),
                service_regime_count=1,
                transition_shape_error_twice=0,
                edge_balance_error=candidate.edge_balance_error,
                headway_vector=(candidate.headway_tiebreak_value,),
                phase_vector=(candidate.phase_offset_minutes,),
                departure_vector=candidate.departures,
            )
        )
    return tuple(states)


def _advance_state(
    previous: _DpState,
    current: LocalScheduleCandidateV1,
    quantization_scale: int,
) -> _DpState:
    left = previous.current
    gap = current.first_departure_minute - left.last_departure_minute
    ceiling = max(left.local_reference_headway, current.local_reference_headway)
    excess = _gap_excess(gap, ceiling)
    _excess_check, transition_error_twice = _transition_metrics(
        gap, left.local_reference_headway, current.local_reference_headway
    )
    return _DpState(
        current=current,
        choices=(*previous.choices, current),
        worst_gap_excess=max(previous.worst_gap_excess, excess),
        total_gap_excess=previous.total_gap_excess + excess,
        total_quantization_units=(
            previous.total_quantization_units + int(current.quantization_error * quantization_scale)
        ),
        service_regime_count=previous.service_regime_count + (not _can_merge(left, current)),
        transition_shape_error_twice=(
            previous.transition_shape_error_twice + transition_error_twice
        ),
        edge_balance_error=previous.edge_balance_error + current.edge_balance_error,
        headway_vector=(*previous.headway_vector, current.headway_tiebreak_value),
        phase_vector=(*previous.phase_vector, current.phase_offset_minutes),
        departure_vector=(*previous.departure_vector, *current.departures),
    )


def _advance_layer(
    previous_states: tuple[_DpState, ...],
    current_candidates: tuple[LocalScheduleCandidateV1, ...],
    quantization_scale: int,
) -> tuple[_DpState, ...]:
    output: list[_DpState] = []
    for current in current_candidates:
        current_quantization_units = int(current.quantization_error * quantization_scale)
        best_previous: _DpState | None = None
        best_scalar_score: tuple[object, ...] | None = None
        best_vector_score: tuple[tuple[int, ...], tuple[int, ...]] | None = None
        for previous in previous_states:
            left = previous.current
            gap = current.first_departure_minute - left.last_departure_minute
            excess, transition_error_twice = _transition_metrics(
                gap,
                left.local_reference_headway,
                current.local_reference_headway,
            )
            # Once headway and phase vectors are equal, the frozen regime starts
            # and counts make the departure vector equal as well.  Therefore the
            # final requested departure-vector tie-break is mathematically
            # redundant here and need not be copied for every pair comparison.
            scalar_score = (
                max(previous.worst_gap_excess, excess),
                previous.total_gap_excess + excess,
                previous.total_quantization_units + current_quantization_units,
                previous.service_regime_count + (not _can_merge(left, current)),
                previous.transition_shape_error_twice + transition_error_twice,
                previous.edge_balance_error + current.edge_balance_error,
            )
            if best_scalar_score is None or scalar_score < best_scalar_score:
                best_previous = previous
                best_scalar_score = scalar_score
                best_vector_score = (
                    (*previous.headway_vector, current.headway_tiebreak_value),
                    (*previous.phase_vector, current.phase_offset_minutes),
                )
            elif scalar_score == best_scalar_score:
                vector_score = (
                    (*previous.headway_vector, current.headway_tiebreak_value),
                    (*previous.phase_vector, current.phase_offset_minutes),
                )
                if best_vector_score is None or vector_score < best_vector_score:
                    best_previous = previous
                    best_vector_score = vector_score
        assert best_previous is not None
        output.append(_advance_state(best_previous, current, quantization_scale))
    return tuple(output)


def _final_score(
    compiler_input: CompilerInputV1,
    state: _DpState,
) -> tuple[object, ...]:
    end_gap = compiler_input.service_end_minute - state.current.last_departure_minute
    end_excess = _gap_excess(end_gap, state.current.local_reference_headway)
    return (
        max(state.worst_gap_excess, end_excess),
        state.total_gap_excess + end_excess,
        state.total_quantization_units,
        state.service_regime_count,
        state.transition_shape_error_twice,
        state.edge_balance_error,
        state.headway_vector,
        state.phase_vector,
        state.departure_vector,
    )


def _service_groups(
    choices: tuple[LocalScheduleCandidateV1, ...],
) -> tuple[tuple[LocalScheduleCandidateV1, ...], ...]:
    groups: list[list[LocalScheduleCandidateV1]] = []
    for choice in choices:
        if groups and _can_merge(groups[-1][-1], choice):
            groups[-1].append(choice)
        else:
            groups.append([choice])
    return tuple(tuple(group) for group in groups)


def _median(values: tuple[int, ...]) -> Fraction | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Fraction(ordered[middle])
    return Fraction(ordered[middle - 1] + ordered[middle], 2)


def _compiled_result(
    compiler_input: CompilerInputV1,
    state: _DpState,
    quantization_scale: int,
) -> CompiledScheduleCandidateV1:
    choices = state.choices
    groups = _service_groups(choices)
    service_regime_id_by_demand_regime: dict[str, str] = {}
    service_regimes: list[ServiceRegimeV1] = []
    for index, group in enumerate(groups, start=1):
        service_regime_id = f"SR{index}"
        for choice in group:
            service_regime_id_by_demand_regime[choice.regime.regime_id] = service_regime_id
        group_departures = tuple(departure for choice in group for departure in choice.departures)
        service_regimes.append(
            ServiceRegimeV1(
                service_regime_id=service_regime_id,
                start_minute=group[0].regime.start_minute,
                end_minute=group[-1].regime.end_minute,
                headway_minutes=group[0].headway_minutes,
                departure_count=len(group_departures),
                first_departure_minute=group_departures[0],
                last_departure_minute=group_departures[-1],
                member_demand_regime_ids=tuple(choice.regime.regime_id for choice in group),
            )
        )

    demand_compilations: list[DemandRegimeCompilationV1] = []
    departure_rows: list[CompiledDepartureV1] = []
    for choice in choices:
        actual_count = sum(
            choice.regime.start_minute <= departure < choice.regime.end_minute
            for departure in state.departure_vector
        )
        demand_compilations.append(
            DemandRegimeCompilationV1(
                regime_id=choice.regime.regime_id,
                start_minute=choice.regime.start_minute,
                end_minute=choice.regime.end_minute,
                duration_minutes=choice.regime.duration_minutes,
                allocated_trip_count=choice.regime.allocated_trip_count,
                nominal_headway=choice.nominal_headway,
                selected_integer_headway=choice.headway_minutes,
                phase_offset_minutes=choice.phase_offset_minutes,
                first_departure_minute=choice.first_departure_minute,
                last_departure_minute=choice.last_departure_minute,
                leading_slack_minutes=choice.leading_slack_minutes,
                trailing_slack_minutes=choice.trailing_slack_minutes,
                internal_headway_count=len(choice.departures) - 1,
                quantization_error=choice.quantization_error,
                actual_trip_count=actual_count,
                count_verified=actual_count == choice.regime.allocated_trip_count,
            )
        )
        service_regime_id = service_regime_id_by_demand_regime[choice.regime.regime_id]
        for departure in choice.departures:
            departure_rows.append(
                CompiledDepartureV1(
                    trip_sequence=len(departure_rows) + 1,
                    departure_minute=departure,
                    source_demand_regime_id=choice.regime.regime_id,
                    service_regime_id=service_regime_id,
                )
            )

    start_gap = state.departure_vector[0] - compiler_input.service_start_minute
    end_gap = compiler_input.service_end_minute - state.departure_vector[-1]
    transition_gaps = tuple(
        right.first_departure_minute - left.last_departure_minute
        for left, right in zip(choices, choices[1:], strict=False)
    )
    reviewed_gaps = (start_gap, *transition_gaps, end_gap)
    actual_gaps = tuple(
        right - left
        for left, right in zip(state.departure_vector, state.departure_vector[1:], strict=False)
    )
    end_excess = _gap_excess(end_gap, state.current.local_reference_headway)
    return CompiledScheduleCandidateV1(
        route_id=compiler_input.route_id,
        direction=compiler_input.direction,
        source_allocation_candidate_id=compiler_input.allocation_candidate_id,
        source_provenance=compiler_input.source_provenance,
        source_compiler_input_fingerprint=compiler_input.input_fingerprint,
        demand_regime_fingerprint_assertion=(compiler_input.demand_regime_fingerprint_assertion),
        trip_allocation_fingerprint_assertion=(
            compiler_input.trip_allocation_fingerprint_assertion
        ),
        service_start_minute=compiler_input.service_start_minute,
        service_end_minute=compiler_input.service_end_minute,
        total_trip_count=compiler_input.total_trip_count,
        demand_regime_compilations=tuple(demand_compilations),
        service_regimes=tuple(service_regimes),
        exact_departures=tuple(departure_rows),
        worst_gap_excess=Fraction(max(state.worst_gap_excess, end_excess)),
        total_gap_excess=Fraction(state.total_gap_excess + end_excess),
        total_quantization_error=Fraction(state.total_quantization_units, quantization_scale),
        service_regime_count=len(service_regimes),
        transition_shape_error=Fraction(state.transition_shape_error_twice, 2),
        edge_balance_error=state.edge_balance_error,
        service_start_gap_minutes=start_gap,
        service_end_gap_minutes=end_gap,
        worst_transition_or_edge_gap_minutes=max(reviewed_gaps),
        minimum_actual_gap_minutes=min(actual_gaps) if actual_gaps else None,
        maximum_actual_gap_minutes=max(actual_gaps) if actual_gaps else None,
        median_actual_gap_minutes=_median(actual_gaps),
        status=CompilationStatusV1.COMPILED,
        fleet_validation_status=FleetValidationStatusV1.NOT_FLEET_VALIDATED,
    )


def _uncompilable_result(
    compiler_input: CompilerInputV1,
    evidence: tuple[str, ...],
) -> CompiledScheduleCandidateV1:
    return CompiledScheduleCandidateV1(
        route_id=compiler_input.route_id,
        direction=compiler_input.direction,
        source_allocation_candidate_id=compiler_input.allocation_candidate_id,
        source_provenance=compiler_input.source_provenance,
        source_compiler_input_fingerprint=compiler_input.input_fingerprint,
        demand_regime_fingerprint_assertion=(compiler_input.demand_regime_fingerprint_assertion),
        trip_allocation_fingerprint_assertion=(
            compiler_input.trip_allocation_fingerprint_assertion
        ),
        service_start_minute=compiler_input.service_start_minute,
        service_end_minute=compiler_input.service_end_minute,
        total_trip_count=compiler_input.total_trip_count,
        demand_regime_compilations=(),
        service_regimes=(),
        exact_departures=(),
        worst_gap_excess=None,
        total_gap_excess=None,
        total_quantization_error=None,
        service_regime_count=0,
        transition_shape_error=None,
        edge_balance_error=None,
        service_start_gap_minutes=None,
        service_end_gap_minutes=None,
        worst_transition_or_edge_gap_minutes=None,
        minimum_actual_gap_minutes=None,
        maximum_actual_gap_minutes=None,
        median_actual_gap_minutes=None,
        status=CompilationStatusV1.UNCOMPILABLE_ALLOCATION,
        fleet_validation_status=FleetValidationStatusV1.NOT_FLEET_VALIDATED,
        failure_evidence=evidence,
    )


@lru_cache(maxsize=128)
def _compile_uniform_headway_schedule_cached_v1(
    compiler_input: CompilerInputV1,
) -> CompiledScheduleCandidateV1:
    """Compile one allocation without changing its frozen regime trip counts."""
    input_fingerprint_before = compiler_input.input_fingerprint
    local_layers = tuple(
        enumerate_local_schedule_candidates_v1(regime) for regime in compiler_input.demand_regimes
    )
    empty_regimes = tuple(
        regime.regime_id
        for regime, candidates in zip(compiler_input.demand_regimes, local_layers, strict=True)
        if not candidates
    )
    if empty_regimes:
        return _uncompilable_result(
            compiler_input,
            tuple(
                f"{regime_id}: allocated count cannot fit on the minute grid"
                for regime_id in empty_regimes
            ),
        )
    quantization_scale = math.lcm(
        *(regime.duration_minutes for regime in compiler_input.demand_regimes)
    )
    states = _initial_states(compiler_input, local_layers[0], quantization_scale)
    for candidates in local_layers[1:]:
        states = _advance_layer(states, candidates, quantization_scale)
    best = min(states, key=lambda state: _final_score(compiler_input, state))
    result = _compiled_result(compiler_input, best, quantization_scale)
    if compiler_input.input_fingerprint != input_fingerprint_before:
        raise RuntimeError("compiler mutated its frozen CompilerInputV1 authority")
    issues = validate_compiled_schedule_v1(compiler_input, result)
    if issues:
        raise RuntimeError("compiled schedule invariant failure: " + "; ".join(issues))
    return result


def compile_uniform_headway_schedule_v1(
    compiler_input: CompilerInputV1,
) -> CompiledScheduleCandidateV1:
    """Compile one immutable input, with deterministic memoization by DTO value."""
    return _compile_uniform_headway_schedule_cached_v1(compiler_input)


def validate_compiled_schedule_v1(
    compiler_input: CompilerInputV1,
    candidate: CompiledScheduleCandidateV1,
) -> tuple[str, ...]:
    """Independently recompute compiler-only hard invariants (never fleet)."""
    issues: list[str] = []
    if candidate.status != CompilationStatusV1.COMPILED:
        return ()
    departures = tuple(item.departure_minute for item in candidate.exact_departures)
    if len(departures) != compiler_input.total_trip_count:
        issues.append("exact total does not equal authoritative allocation total")
    if departures != tuple(sorted(departures)) or len(set(departures)) != len(departures):
        issues.append("departures are not strictly increasing and unique")
    if any(
        departure < compiler_input.service_start_minute
        or departure >= compiler_input.service_end_minute
        for departure in departures
    ):
        issues.append("departure lies outside the half-open service window")
    compilations = {item.regime_id: item for item in candidate.demand_regime_compilations}
    for regime in compiler_input.demand_regimes:
        compilation = compilations.get(regime.regime_id)
        if compilation is None:
            issues.append(f"{regime.regime_id}: missing demand-regime compilation")
            continue
        local = tuple(
            departure
            for departure in departures
            if regime.start_minute <= departure < regime.end_minute
        )
        if len(local) != regime.allocated_trip_count:
            issues.append(f"{regime.regime_id}: authoritative trip count changed")
        if regime.allocated_trip_count >= 2:
            headway = compilation.selected_integer_headway
            if headway is None or headway < 1:
                issues.append(f"{regime.regime_id}: measurable headway is not positive")
            elif any(
                right - left != headway for left, right in zip(local, local[1:], strict=False)
            ):
                issues.append(f"{regime.regime_id}: internal headways are not uniform")
        elif compilation.selected_integer_headway is not None:
            issues.append(f"{regime.regime_id}: singleton fabricated a headway")
    departure_service_ids = {
        item.trip_sequence: item.service_regime_id for item in candidate.exact_departures
    }
    for service_regime in candidate.service_regimes:
        local_rows = tuple(
            item
            for item in candidate.exact_departures
            if item.service_regime_id == service_regime.service_regime_id
        )
        if len(local_rows) != service_regime.departure_count:
            issues.append(f"{service_regime.service_regime_id}: departure count mismatch")
        if service_regime.headway_minutes is not None and any(
            right.departure_minute - left.departure_minute != service_regime.headway_minutes
            for left, right in zip(local_rows, local_rows[1:], strict=False)
        ):
            issues.append(f"{service_regime.service_regime_id}: merged sequence is not uniform")
        for regime_id in service_regime.member_demand_regime_ids:
            member_rows = tuple(
                row
                for row in candidate.exact_departures
                if row.source_demand_regime_id == regime_id
            )
            if any(
                departure_service_ids[row.trip_sequence] != service_regime.service_regime_id
                for row in member_rows
            ):
                issues.append(f"{service_regime.service_regime_id}: member mapping is inconsistent")
    if candidate.source_compiler_input_fingerprint != compiler_input.input_fingerprint:
        issues.append("compiled output is not bound to the immutable compiler input")
    return tuple(issues)


__all__ = [
    "LocalScheduleCandidateV1",
    "compile_uniform_headway_schedule_v1",
    "enumerate_local_schedule_candidates_v1",
    "validate_compiled_schedule_v1",
]

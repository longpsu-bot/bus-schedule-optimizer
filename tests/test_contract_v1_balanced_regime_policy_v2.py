from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_contract_v1_exact_demand_uniform_headways import (  # noqa: E402
    _raw_candidate_for_seconds,
    _single_regime_fixture,
)
from test_contract_v1_ortools_demand_optimizer import _record  # noqa: E402
from test_contract_v1_ortools_quality_optimizer import _quality_request  # noqa: E402

from bus_schedule_engine.contracts_v1 import (  # noqa: E402
    ContractDirection,
    GenerationResultStatus,
    RawCandidateTripV1,
    run_schedule_solver_v1,
    solver_fingerprints,  # noqa: E402
)
from bus_schedule_engine.contracts_v1.regime_headway_policy import (  # noqa: E402
    SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE,
    _authoritative_candidate_payload,
    _balanced_headway_shape,
    _CandidateRegimeGroup,
    _merge_maximal_balanced_regimes,
    _repair_singletons,
    _SustainedServiceRegime,
)
from bus_schedule_engine.contracts_v1.solver_fingerprints import (  # noqa: E402
    candidate_fingerprint,
    solution_fingerprint_payload,
)
from bus_schedule_engine.contracts_v1.solver_models import DepartureTerminal  # noqa: E402
from bus_schedule_engine.models import Direction  # noqa: E402


def _trip(trip_id: str, minute: int) -> RawCandidateTripV1:
    departure = minute * 60
    return RawCandidateTripV1(
        c_trip_id=trip_id,
        source_b_trip_id=f"B-{trip_id}",
        direction=ContractDirection.OUTBOUND,
        departure_terminal=DepartureTerminal.TERMINAL_1,
        b_departure_time=departure,
        c_departure_time=departure,
        arrival_time=departure + 60,
        runtime_minutes=1,
        shift_minutes=0.0,
        previous_b_headway=None,
        previous_c_headway=None,
        headway_regime_id="REGIME_PENDING_AUTHORITY",
        change_reason="Synthetic balanced-regime V2 fixture.",
    )


def _phase(index: int, start: int, end: int) -> _SustainedServiceRegime:
    return _SustainedServiceRegime(
        regime_id=f"PHASE-{index}",
        direction=ContractDirection.OUTBOUND,
        block_ids=(f"BLOCK-{index}",),
        start_time=start * 60,
        end_time=end * 60,
        duration_minutes=end - start,
        required_trips_85=index + 1,
    )


def _group(index: int, trip_ids: tuple[str, ...]) -> _CandidateRegimeGroup:
    return _CandidateRegimeGroup(
        direction=ContractDirection.OUTBOUND,
        phase_start_index=index,
        phase_end_index=index,
        trip_ids=trip_ids,
    )


def _repair_case(
    *,
    trips: tuple[RawCandidateTripV1, ...],
    phases: tuple[_SustainedServiceRegime, ...],
    groups: list[_CandidateRegimeGroup],
) -> list[_CandidateRegimeGroup]:
    return _repair_singletons(
        groups,
        phases,
        {trip.c_trip_id: trip for trip in trips},
    )


def test_singleton_absorbs_preceding_when_only_preceding_is_balanced() -> None:
    trips = tuple(
        _trip(trip_id, minute)
        for trip_id, minute in (
            ("P1", 360),
            ("P2", 370),
            ("S", 380),
            ("F1", 400),
            ("F2", 410),
        )
    )
    phases = (_phase(0, 350, 375), _phase(1, 375, 390), _phase(2, 390, 420))
    repaired = _repair_case(
        trips=trips,
        phases=phases,
        groups=[_group(0, ("P1", "P2")), _group(1, ("S",)), _group(2, ("F1", "F2"))],
    )

    assert [group.trip_ids for group in repaired] == [
        ("P1", "P2", "S"),
        ("F1", "F2"),
    ]


def test_singleton_absorbs_following_when_only_following_is_balanced() -> None:
    trips = tuple(
        _trip(trip_id, minute)
        for trip_id, minute in (
            ("P1", 360),
            ("P2", 370),
            ("S", 390),
            ("F1", 400),
            ("F2", 410),
        )
    )
    phases = (_phase(0, 350, 375), _phase(1, 375, 395), _phase(2, 395, 420))
    repaired = _repair_case(
        trips=trips,
        phases=phases,
        groups=[_group(0, ("P1", "P2")), _group(1, ("S",)), _group(2, ("F1", "F2"))],
    )

    assert [group.trip_ids for group in repaired] == [
        ("P1", "P2"),
        ("S", "F1", "F2"),
    ]


def test_singleton_both_valid_uses_preceding_as_final_deterministic_tie_break() -> None:
    trips = tuple(
        _trip(trip_id, minute)
        for trip_id, minute in (
            ("P1", 360),
            ("P2", 370),
            ("S", 380),
            ("F1", 392),
            ("F2", 404),
        )
    )
    phases = (_phase(0, 350, 375), _phase(1, 375, 385), _phase(2, 385, 420))
    repaired = _repair_case(
        trips=trips,
        phases=phases,
        groups=[_group(0, ("P1", "P2")), _group(1, ("S",)), _group(2, ("F1", "F2"))],
    )

    assert [group.trip_ids for group in repaired] == [
        ("P1", "P2", "S"),
        ("F1", "F2"),
    ]


def test_singleton_remains_unrepresentable_when_neither_merge_is_balanced() -> None:
    trips = tuple(
        _trip(trip_id, minute)
        for trip_id, minute in (
            ("P1", 360),
            ("P2", 370),
            ("S", 385),
            ("F1", 400),
            ("F2", 410),
        )
    )
    phases = (_phase(0, 350, 375), _phase(1, 375, 395), _phase(2, 395, 420))
    repaired = _repair_case(
        trips=trips,
        phases=phases,
        groups=[_group(0, ("P1", "P2")), _group(1, ("S",)), _group(2, ("F1", "F2"))],
    )

    assert [group.trip_ids for group in repaired] == [
        ("P1", "P2"),
        ("S",),
        ("F1", "F2"),
    ]


@pytest.mark.parametrize(
    ("minutes", "expected_status", "expected_target", "expected_valid"),
    (
        ((360, 370, 380), "UNIFORM", 10.0, True),
        ((360, 370, 381), "BALANCED_ROUNDING", 10.5, True),
        ((360, 370, 383), "INVALID_NON_UNIFORM", 11.5, False),
    ),
)
def test_balanced_shape_contract(
    minutes: tuple[int, ...],
    expected_status: str,
    expected_target: float,
    expected_valid: bool,
) -> None:
    trips = tuple(_trip(f"T{index}", minute) for index, minute in enumerate(minutes, start=1))
    trip_by_id = {trip.c_trip_id: trip for trip in trips}
    shape = _balanced_headway_shape(tuple(trip_by_id), trip_by_id)

    assert shape.valid is expected_valid
    assert shape.status == expected_status
    assert shape.target_headway == expected_target
    if expected_status == "BALANCED_ROUNDING":
        assert set(shape.headways) == {10, 11}
        assert shape.maximum_internal_variation == 1


def test_adjacent_regimes_merge_to_maximal_balanced_sequence() -> None:
    trips = tuple(
        _trip(trip_id, minute)
        for trip_id, minute in (("A1", 360), ("A2", 370), ("B1", 380), ("B2", 390))
    )
    merged = _merge_maximal_balanced_regimes(
        [_group(0, ("A1", "A2")), _group(1, ("B1", "B2"))],
        {trip.c_trip_id: trip for trip in trips},
    )

    assert len(merged) == 1
    assert merged[0].trip_ids == ("A1", "A2", "B1", "B2")


def test_adjacent_regimes_remain_separate_when_cross_boundary_breaks_balance() -> None:
    trips = tuple(
        _trip(trip_id, minute)
        for trip_id, minute in (("A1", 360), ("A2", 370), ("B1", 390), ("B2", 400))
    )
    merged = _merge_maximal_balanced_regimes(
        [_group(0, ("A1", "A2")), _group(1, ("B1", "B2"))],
        {trip.c_trip_id: trip for trip in trips},
    )

    assert [group.trip_ids for group in merged] == [("A1", "A2"), ("B1", "B2")]


def _two_phase_context(outbound_minutes: tuple[int, ...], boundary: int):
    return _quality_request(
        outbound_minutes=outbound_minutes,
        inbound_minutes=(500, 510),
        outbound_runtimes=tuple(1 for _ in outbound_minutes),
        inbound_runtimes=(1, 1),
        fleet_limit=12,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, outbound_minutes[0], boundary, 10),
            _record(Direction.TERMINAL_1_TO_2, boundary, outbound_minutes[-1] + 1, 200),
            _record(Direction.TERMINAL_2_TO_1, 500, 511, 20),
        ),
        route_id="SYNTHETIC-BALANCED-REGIME-V2",
    )


def test_transition_headway_is_visible_but_not_internal() -> None:
    context, *_ = _two_phase_context((360, 370, 390, 400), boundary=380)
    _, policy = _raw_candidate_for_seconds(
        context.problem,
        outbound_seconds=tuple(minute * 60 for minute in (360, 370, 390, 400)),
        inbound_seconds=(500 * 60, 510 * 60),
    )
    outbound_analyses = [
        analysis
        for analysis in policy.analyses
        if analysis.regime.direction == ContractDirection.OUTBOUND
    ]

    assert len(outbound_analyses) == 2
    assert [analysis.internal_headways for analysis in outbound_analyses] == [(10,), (10,)]
    assert [
        pair.headway_minutes
        for pair in policy.transition_pairs
        if pair.direction == ContractDirection.OUTBOUND
    ] == [20]
    assert outbound_analyses[0].transition_headway_after == 20
    assert outbound_analyses[1].transition_headway_before == 20


def test_canonical_maximal_merge_crosses_demand_phase_boundary() -> None:
    context, *_ = _two_phase_context((360, 370, 380, 390), boundary=375)
    candidate, policy = _raw_candidate_for_seconds(
        context.problem,
        outbound_seconds=tuple(minute * 60 for minute in (360, 370, 380, 390)),
        inbound_seconds=(500 * 60, 510 * 60),
    )
    outbound = [
        analysis
        for analysis in policy.analyses
        if analysis.regime.direction == ContractDirection.OUTBOUND
    ]

    assert len(outbound) == 1
    assert outbound[0].internal_headways == (10, 10, 10)
    assert outbound[0].status == "UNIFORM"
    assert (
        len(
            [
                regime
                for regime in candidate.headway_regimes
                if regime.direction == ContractDirection.OUTBOUND
            ]
        )
        == 1
    )


def test_irregular_scenario_b_remains_reviewable_and_ortools_can_balance_scenario_c() -> None:
    context, solver = _single_regime_fixture(
        (360, 365, 381),
        inbound_minutes=(365, 377),
        fleet_limit=12,
        turnaround=(5, 5),
    )
    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    outbound = next(
        regime
        for regime in outcome.solution.c_headway_regimes
        if regime.direction == ContractDirection.OUTBOUND
    )
    assert outbound.regularity_status == "BALANCED_ROUNDING"
    assert set(outbound.actual_headway_sequence) == {10, 11}
    assert outbound.target_headway == 10.5


def test_canonical_assignment_is_solver_label_independent_for_same_timetable() -> None:
    context, *_ = _two_phase_context((360, 370, 390, 400), boundary=380)
    candidate, _ = _raw_candidate_for_seconds(
        context.problem,
        outbound_seconds=tuple(minute * 60 for minute in (360, 370, 390, 400)),
        inbound_seconds=(500 * 60, 510 * 60),
    )
    unlabeled = tuple(
        replace(trip, headway_regime_id="REGIME_PENDING_AUTHORITY")
        for trip in candidate.exact_timetable
    )
    heuristic_problem = replace(context.problem, solver_adapter="legacy_heuristic_v1")
    _, _, heuristic_policy = _authoritative_candidate_payload(heuristic_problem, unlabeled)
    _, _, ortools_policy = _authoritative_candidate_payload(context.problem, unlabeled)

    assert heuristic_policy.regime_by_trip_id == ortools_policy.regime_by_trip_id
    assert tuple(
        (analysis.regime.direction, analysis.trip_ids, analysis.internal_headways)
        for analysis in heuristic_policy.analyses
    ) == tuple(
        (analysis.regime.direction, analysis.trip_ids, analysis.internal_headways)
        for analysis in ortools_policy.analyses
    )


def test_candidate_and_solution_fingerprints_bind_v2_policy_profile(monkeypatch) -> None:
    context, solver = _single_regime_fixture(
        (360, 365, 372),
        inbound_minutes=(365, 377),
        fleet_limit=12,
        turnaround=(5, 5),
    )
    run = solver.solve(context.problem)
    assert run.candidate is not None
    candidate = run.candidate
    first = candidate_fingerprint(
        problem_fingerprint=context.problem.problem_fingerprint,
        solver_adapter=candidate.solver_adapter,
        exact_timetable=candidate.exact_timetable,
        headway_regimes=candidate.headway_regimes,
    )
    second = candidate_fingerprint(
        problem_fingerprint=context.problem.problem_fingerprint,
        solver_adapter=candidate.solver_adapter,
        exact_timetable=candidate.exact_timetable,
        headway_regimes=candidate.headway_regimes,
    )
    assert first == second == candidate.candidate_fingerprint

    monkeypatch.setattr(
        solver_fingerprints,
        "SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE",
        "synthetic-different-profile",
    )
    changed = candidate_fingerprint(
        problem_fingerprint=context.problem.problem_fingerprint,
        solver_adapter=candidate.solver_adapter,
        exact_timetable=candidate.exact_timetable,
        headway_regimes=candidate.headway_regimes,
    )
    assert changed != first

    monkeypatch.setattr(
        solver_fingerprints,
        "SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE",
        SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE,
    )
    outcome = run_schedule_solver_v1(context, solver)
    assert outcome.solution is not None
    payload = solution_fingerprint_payload(
        outcome.solution,
        problem_fingerprint=context.problem.problem_fingerprint,
    )
    assert payload["scenario_c_regime_policy_profile"] == SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE


def test_v2_fixture_contains_no_private_route_data() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    route_prefix = "61" + "-"
    private_source_marker = "current_repo" + "_engine_source"
    assert route_prefix not in source
    assert private_source_marker not in source

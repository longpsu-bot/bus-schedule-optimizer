from __future__ import annotations

import json
from pathlib import Path

from bus_schedule_engine.contracts_v1.uniform_headway_compiler import (
    _service_groups,
    compile_uniform_headway_schedule_v1,
    enumerate_local_schedule_candidates_v1,
    validate_compiled_schedule_v1,
)
from bus_schedule_engine.contracts_v1.uniform_headway_compiler_bridge import (
    TemporaryAuthoritativeAllocationFixtureAdapterV1,
)
from bus_schedule_engine.contracts_v1.uniform_headway_compiler_models import (
    TEMPORARY_AUTHORITATIVE_BRIDGE_V1,
    CompilationStatusV1,
    CompilerDemandRegimeInputV1,
    CompilerInputV1,
    FleetValidationStatusV1,
    compiler_input_payload,
)
from bus_schedule_engine.contracts_v1.uniform_headway_compiler_serialization import (
    compiled_schedule_to_contract_dict_v1,
)

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "compiler_bridge"
_ARTIFACT_ROOT = Path(__file__).parents[1] / "artifacts" / "uniform_headway_compiler_v1"
_ASSERTED_DEMAND_FINGERPRINT = "A" * 64
_ASSERTED_ALLOCATION_FINGERPRINT = "B" * 64


def _input(*regimes: tuple[str, int, int, int]) -> CompilerInputV1:
    demand_regimes = tuple(
        CompilerDemandRegimeInputV1(
            regime_id=regime_id,
            start_minute=start,
            end_minute=end,
            allocated_trip_count=count,
        )
        for regime_id, start, end, count in regimes
    )
    return CompilerInputV1(
        source_provenance="SYNTHETIC_COMPILER_CONTRACT_TEST",
        route_id="TEST",
        direction="OUTBOUND",
        allocation_candidate_id="C_TEST",
        service_start_minute=demand_regimes[0].start_minute,
        service_end_minute=demand_regimes[-1].end_minute,
        total_trip_count=sum(item.allocated_trip_count for item in demand_regimes),
        demand_regime_fingerprint_assertion=_ASSERTED_DEMAND_FINGERPRINT,
        trip_allocation_fingerprint_assertion=_ASSERTED_ALLOCATION_FINGERPRINT,
        demand_regimes=demand_regimes,
    )


def test_bridge_fixture_integrity_and_all_twelve_inputs() -> None:
    bundles = [
        TemporaryAuthoritativeAllocationFixtureAdapterV1(path).load_bundle()
        for path in sorted(_FIXTURE_ROOT.glob("authoritative_route_*_allocation_v1.json"))
    ]
    inputs = tuple(item for bundle in bundles for item in bundle.inputs)
    assert len(inputs) == 12
    assert {item.source_provenance for item in inputs} == {TEMPORARY_AUTHORITATIVE_BRIDGE_V1}
    assert {(item.route_id, item.total_trip_count) for item in inputs} == {
        ("6", 78),
        ("10", 51),
    }
    assert all(
        sum(regime.allocated_trip_count for regime in item.demand_regimes) == item.total_trip_count
        for item in inputs
    )
    assert all(bundle.scenario_b_comparison.status == "UNAVAILABLE" for bundle in bundles)
    selected = next(
        item
        for item in inputs
        if item.route_id == "6"
        and item.direction == "OUTBOUND"
        and item.allocation_candidate_id == "C1_DEMAND_FIT"
    )
    before = json.dumps(
        compiler_input_payload(selected),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    compile_uniform_headway_schedule_v1(selected)
    after = json.dumps(
        compiler_input_payload(selected),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert after == before


def test_exact_counts_total_uniformity_and_minute_grid() -> None:
    compiler_input = _input(("R1", 270, 360, 5), ("R2", 360, 450, 9))
    result = compile_uniform_headway_schedule_v1(compiler_input)
    assert result.status == CompilationStatusV1.COMPILED
    assert result.fleet_validation_status == FleetValidationStatusV1.NOT_FLEET_VALIDATED
    assert len(result.exact_departures) == compiler_input.total_trip_count
    assert not validate_compiled_schedule_v1(compiler_input, result)
    for regime, compilation in zip(
        compiler_input.demand_regimes,
        result.demand_regime_compilations,
        strict=True,
    ):
        departures = [
            item.departure_minute
            for item in result.exact_departures
            if regime.start_minute <= item.departure_minute < regime.end_minute
        ]
        assert len(departures) == regime.allocated_trip_count
        assert all(isinstance(item, int) for item in departures)
        assert all(
            right - left == compilation.selected_integer_headway
            for left, right in zip(departures, departures[1:], strict=False)
        )


def test_180_minute_ten_trip_case_is_exact_18_without_boundary_anchors() -> None:
    result = compile_uniform_headway_schedule_v1(_input(("R1", 420, 600, 10)))
    compilation = result.demand_regime_compilations[0]
    assert compilation.selected_integer_headway == 18
    assert compilation.phase_offset_minutes == 9
    assert compilation.first_departure_minute == 429
    assert compilation.last_departure_minute == 591


def test_global_phase_optimization_beats_independent_centering() -> None:
    result = compile_uniform_headway_schedule_v1(_input(("R1", 0, 10, 3), ("R2", 10, 20, 3)))
    assert [item.selected_integer_headway for item in result.demand_regime_compilations] == [
        3,
        3,
    ]
    assert [item.phase_offset_minutes for item in result.demand_regime_compilations] == [
        2,
        1,
    ]
    assert result.worst_gap_excess == 0
    independently_centered_transition_gap = (10 + 2) - (0 + 2 + 2 * 3)
    assert independently_centered_transition_gap == 4


def test_exact_valid_merge_and_member_counts_survive() -> None:
    compiler_input = _input(("R1", 0, 10, 2), ("R2", 10, 20, 2))
    result = compile_uniform_headway_schedule_v1(compiler_input)
    assert len(result.service_regimes) == 1
    assert result.service_regimes[0].member_demand_regime_ids == ("R1", "R2")
    assert result.service_regimes[0].headway_minutes == 5
    assert [item.actual_trip_count for item in result.demand_regime_compilations] == [2, 2]


def test_same_headway_with_nonuniform_transition_does_not_merge() -> None:
    left_regime, right_regime = _input(("R1", 0, 10, 2), ("R2", 10, 20, 2)).demand_regimes
    left = next(
        item
        for item in enumerate_local_schedule_candidates_v1(left_regime)
        if item.headway_minutes == 5 and item.phase_offset_minutes == 2
    )
    right = next(
        item
        for item in enumerate_local_schedule_candidates_v1(right_regime)
        if item.headway_minutes == 5 and item.phase_offset_minutes == 3
    )
    assert right.first_departure_minute - left.last_departure_minute == 6
    assert len(_service_groups((left, right))) == 2


def test_end_exclusive_boundary_belongs_only_to_next_regime() -> None:
    regimes = _input(("R1", 0, 10, 2), ("R2", 10, 20, 2)).demand_regimes
    right = next(
        item
        for item in enumerate_local_schedule_candidates_v1(regimes[1])
        if item.phase_offset_minutes == 0 and item.headway_minutes == 5
    )
    assert right.departures[0] == 10
    assert not (regimes[0].start_minute <= 10 < regimes[0].end_minute)
    assert regimes[1].start_minute <= 10 < regimes[1].end_minute


def test_closing_edge_quality_breaks_otherwise_equal_phases() -> None:
    result = compile_uniform_headway_schedule_v1(_input(("R1", 0, 10, 2)))
    compilation = result.demand_regime_compilations[0]
    assert compilation.selected_integer_headway == 5
    assert compilation.phase_offset_minutes == 2
    assert result.service_start_gap_minutes == 2
    assert result.service_end_gap_minutes == 3


def test_uncompilable_allocation_is_structured_and_not_mutated() -> None:
    compiler_input = _input(("R1", 0, 3, 4))
    before = compiler_input.input_fingerprint
    result = compile_uniform_headway_schedule_v1(compiler_input)
    assert result.status == CompilationStatusV1.UNCOMPILABLE_ALLOCATION
    assert result.failure_evidence
    assert compiler_input.input_fingerprint == before
    assert compiler_input.demand_regimes[0].allocated_trip_count == 4


def test_one_hundred_serializations_are_byte_identical() -> None:
    compiler_input = _input(("R1", 0, 10, 3), ("R2", 10, 20, 3))
    serialized = {
        json.dumps(
            compiled_schedule_to_contract_dict_v1(
                compile_uniform_headway_schedule_v1(compiler_input)
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        for _ in range(100)
    }
    assert len(serialized) == 1


def test_singleton_has_no_fabricated_headway() -> None:
    result = compile_uniform_headway_schedule_v1(_input(("R1", 0, 5, 1)))
    assert result.demand_regime_compilations[0].selected_integer_headway is None
    assert result.service_regimes[0].headway_minutes is None


def test_real_bridge_artifacts_cover_all_twelve_exact_schedules() -> None:
    artifacts = sorted(_ARTIFACT_ROOT.glob("route-*.json"))
    assert len(artifacts) == 12
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in artifacts]
    assert all(item["status"] == "COMPILED" for item in payloads)
    assert all(item["fleet_validation_status"] == "NOT_FLEET_VALIDATED" for item in payloads)
    assert all(len(item["exact_departures"]) == item["total_trip_count"] for item in payloads)
    assert all(
        regime["count_verified"]
        for item in payloads
        for regime in item["demand_regime_compilations"]
    )
    review = json.loads((_ARTIFACT_ROOT / "review.json").read_text(encoding="utf-8"))
    assert review["compiled_count"] == 12
    assert review["uncompilable_count"] == 0

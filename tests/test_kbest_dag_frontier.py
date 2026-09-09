"""RED contract for the exact U6 port; expectations never import U5 experiments.

The private graph builder and enumerator are production seams: the public compiler
must use them. A domain exposes layers, edges, and graph_statistics; enumeration
exposes paths (with key/phase_indices/departure_vector), graph_statistics, and
natural_exhaustion. Synthetic phases test graph arithmetic without fake decoding.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import itertools
import json
import math
import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (
    OperationalEndpointAuthorityV1,
    _phase_candidates,
    _PhaseCandidate,
    validate_clean_boundary_compilation_v1,
)
from bus_schedule_engine.contracts_v1.clean_compile_frontier import (
    _regimes_from_state,
    clean_compilation_fingerprint_v1,
)
from bus_schedule_engine.contracts_v1.kbest_dag_frontier import (
    KBestDagCandidateV1,
    KBestDagFrontierV1,
    KBestDagGraphStatisticsV1,
    KBestDagTelemetryV1,
    _build_layered_domain_v1,
    _enumerate_state_domain_v1,
    compile_service_plan_family_kbest_v1,
    kbest_dag_candidate_payload_v1,
    service_plan_matches_endpoint_contract_v1,
)
from bus_schedule_engine.contracts_v1.service_plan_state import (
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    service_plan_fingerprint_v1,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/pr62_u6/u5_frozen_family.json"
MODULE = "bus_schedule_engine.contracts_v1.kbest_dag_frontier"
FAMILY_SHA = "465c0800be66ce991af017ecea6dc87cdd4db7342d8ac9adb30ba1b5678fa905"
TOP1_SHA = "8e06dbcafc0194e5d338bc96b28569825bff30a79f96eaec8b5eda3c778ca7f6"
RAW_SHA = "71092c883923e6d5460980a8c528f263a275255986e887bb03c3c1ef16c17601"


def _canonical_bytes(value):
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _state(boundaries=(0, 12, 24), counts=(3, 3), first=0, last=22):
    return ServicePlanStateV1(
        route_id="test-route",
        direction="outbound",
        fixed_first_departure=first * 60,
        fixed_last_departure=last * 60,
        service_regimes=tuple(
            ServiceRegimeDecisionV1(a * 60, b * 60, n)
            for a, b, n in zip(boundaries, boundaries[1:], counts, strict=False)
        ),
        seed_id="exact-dag-test",
    )


def _authority(state):
    return OperationalEndpointAuthorityV1(
        state.route_id,
        state.direction,
        state.service_regimes[0].start,
        state.service_regimes[-1].end,
        state.fixed_first_departure,
        state.fixed_last_departure,
        "test-fixed-endpoint-authority",
    )


def _phase(first, headway, *, count=2, q=Fraction(0), imbalance=0):
    departures = tuple(first + i * headway for i in range(count))
    return _PhaseCandidate(first, headway, departures[-1], departures, q, imbalance)


def _oracle(layers):
    """Exhaust all paths independently of production graph/merge/score helpers."""
    if not layers or any(not layer for layer in layers):
        return []
    result = []
    for path in itertools.product(*layers):
        if any(
            right.first_minute - left.last_minute
            not in (left.headway_minutes, right.headway_minutes)
            for left, right in zip(path, path[1:], strict=False)
        ):
            continue
        departures = tuple(itertools.chain.from_iterable(p.departures_minutes for p in path))
        result.append(
            (
                sum((p.quantization_error for p in path), Fraction(0)),
                1
                + sum(
                    a.headway_minutes != b.headway_minutes
                    for a, b in zip(path, path[1:], strict=False)
                ),
                sum(p.phase_imbalance_minutes for p in path),
                tuple(p.headway_minutes for p in path),
                departures,
            )
        )
    unique = {}
    for key in sorted(result):
        unique.setdefault(key[-1], key)
    return list(unique.values())


def _graph_result(layers, limit=256):
    domain = _build_layered_domain_v1(layers, state_index=0)
    return domain, _enumerate_state_domain_v1(domain, raw_limit=limit)


def _assert_graph_matches_oracle(layers, limit=256):
    domain, result = _graph_result(layers, limit)
    scale = math.lcm(*(p.quantization_error.denominator for layer in domain.layers for p in layer))
    expected = _oracle(layers)[:limit]
    assert [p.key for p in result.paths] == [
        (int(q * scale), regimes, imbalance, headways, departures)
        for q, regimes, imbalance, headways, departures in expected
    ]
    assert len({p.departure_vector for p in result.paths}) == len(result.paths)
    return domain, result


def _family_oracle(states, authority):
    records = []
    for state in sorted(states, key=service_plan_fingerprint_v1):
        regimes = _regimes_from_state(state)
        layers = tuple(
            _phase_candidates(
                regime, regime_index=i, regime_count=len(regimes), authority=authority
            )
            for i, regime in enumerate(regimes)
        )
        records.extend((key, service_plan_fingerprint_v1(state)) for key in _oracle(layers))
    unique = {}
    for key, fingerprint in sorted(records):
        unique.setdefault(key[-1], (key, fingerprint))
    return list(unique.values())


def _payloads(frontier, states):
    indices = {
        service_plan_fingerprint_v1(s): i
        for i, s in enumerate(sorted(states, key=service_plan_fingerprint_v1))
    }
    return [
        kbest_dag_candidate_payload_v1(c, state_index=indices[c.state_fingerprint])
        for c in frontier.candidates
    ]


def _read_frozen_family():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
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
    return payload, states, OperationalEndpointAuthorityV1(**payload["endpoint_authority"])


def test_empty_family_is_rejected():
    with pytest.raises(ValueError):
        compile_service_plan_family_kbest_v1(states=(), endpoint_authority=_authority(_state()))


@pytest.mark.parametrize("limit", [True, False, 1.0, "2", None, Fraction(2), 0, -1, 257])
def test_raw_limit_rejects_bool_non_integer_and_out_of_range(limit):
    state = _state()
    with pytest.raises(ValueError):
        compile_service_plan_family_kbest_v1(
            states=(state,), endpoint_authority=_authority(state), raw_limit=limit
        )


@pytest.mark.parametrize("limit", [1, 256])
def test_raw_limit_accepts_inclusive_endpoints(limit):
    state = _state()
    result = compile_service_plan_family_kbest_v1(
        states=(state,), endpoint_authority=_authority(state), raw_limit=limit
    )
    assert result.requested_raw_limit == limit
    assert 0 < len(result.candidates) <= limit


@pytest.mark.parametrize(
    "change",
    [
        {"route_id": "other-route"},
        {"direction": "inbound"},
        {"fixed_first_departure": 60},
        {"fixed_last_departure": 21 * 60},
        {
            "service_regimes": (
                ServiceRegimeDecisionV1(0, 720, 4),
                ServiceRegimeDecisionV1(720, 1440, 3),
            )
        },
    ],
)
def test_family_route_direction_endpoint_and_trip_total_mismatches_fail_closed(change):
    state = _state()
    with pytest.raises(ValueError):
        compile_service_plan_family_kbest_v1(
            states=(state, replace(state, **change)), endpoint_authority=_authority(state)
        )


@pytest.mark.parametrize(
    "change",
    [
        {"route_id": "other-route"},
        {"direction": "inbound"},
        {"fixed_first_departure": 60},
        {"fixed_last_departure": 21 * 60},
        {"analysis_window_start": -60},
        {"analysis_window_end": 25 * 60},
    ],
)
def test_endpoint_authority_mismatches_fail_closed(change):
    state = _state()
    authority = replace(_authority(state), **change)
    assert not service_plan_matches_endpoint_contract_v1(state, authority)
    with pytest.raises(ValueError):
        compile_service_plan_family_kbest_v1(states=(state,), endpoint_authority=authority)


def test_endpoint_preflight_uses_half_open_first_and_final_regimes():
    state = _state(first=11, last=23)
    assert service_plan_matches_endpoint_contract_v1(state, _authority(state))
    first_equal_end = replace(state, fixed_first_departure=12 * 60)
    assert not service_plan_matches_endpoint_contract_v1(
        first_equal_end, _authority(first_equal_end)
    )
    first_after_end = replace(state, fixed_first_departure=13 * 60)
    assert not service_plan_matches_endpoint_contract_v1(
        first_after_end, _authority(first_after_end)
    )
    last_before_final = replace(state, fixed_last_departure=11 * 60)
    assert not service_plan_matches_endpoint_contract_v1(
        last_before_final, _authority(last_before_final)
    )
    last_at_final_start = replace(state, fixed_last_departure=12 * 60)
    assert service_plan_matches_endpoint_contract_v1(
        last_at_final_start, _authority(last_at_final_start)
    )
    # Construction itself forbids the final half-open end; preflight must also
    # reject a malformed deserialized state rather than silently accepting it.
    with pytest.raises(ValueError):
        replace(state, fixed_last_departure=24 * 60)
    malformed = copy.copy(state)
    object.__setattr__(malformed, "fixed_last_departure", 24 * 60)
    wider_authority = replace(
        _authority(state), analysis_window_end=25 * 60, fixed_last_departure=24 * 60
    )
    assert not service_plan_matches_endpoint_contract_v1(malformed, wider_authority)


def test_caller_state_order_is_canonicalized_and_duplicate_fingerprints_rejected():
    state_a, state_b = _state(), _state(boundaries=(0, 13, 24))
    authority = _authority(state_a)
    forward = compile_service_plan_family_kbest_v1(
        states=(state_b, state_a), endpoint_authority=authority, raw_limit=2
    )
    reverse = compile_service_plan_family_kbest_v1(
        states=(state_a, state_b), endpoint_authority=authority, raw_limit=2
    )
    assert forward.ordered_fingerprints == reverse.ordered_fingerprints
    assert _canonical_bytes(_payloads(forward, (state_a, state_b))) == _canonical_bytes(
        _payloads(reverse, (state_b, state_a))
    )
    with pytest.raises(ValueError, match="duplicate ServicePlan fingerprint"):
        compile_service_plan_family_kbest_v1(
            states=(state_a, state_a), endpoint_authority=authority
        )
    with pytest.raises(ValueError, match="duplicate ServicePlan fingerprint"):
        compile_service_plan_family_kbest_v1(
            states=(state_a, replace(state_a, seed_id="history-only-change")),
            endpoint_authority=authority,
        )


def test_one_layer_exact_ordering_and_source_sink_counts():
    layers = (
        (
            _phase(2, 3, q=Fraction(1, 2)),
            _phase(0, 2, q=Fraction(1, 3)),
            _phase(1, 2, q=Fraction(1, 3)),
        ),
    )
    domain, result = _assert_graph_matches_oracle(layers)
    assert [p.departure_vector for p in result.paths] == [(0, 2), (1, 3), (2, 5)]
    assert domain.edges == ()
    stats = domain.graph_statistics
    assert (stats.state_count, stats.layer_count, stats.node_count) == (1, 1, 3)
    assert (stats.source_edge_count, stats.sink_edge_count, stats.legal_transition_edge_count) == (
        3,
        3,
        0,
    )
    assert stats.reachability_trimmed_node_count == 0
    assert result.natural_exhaustion


@pytest.mark.parametrize(
    "left,right,regime_count",
    [
        (_phase(0, 2), _phase(4, 3), 2),  # gap 2, left owns
        (_phase(0, 2), _phase(5, 3), 2),  # gap 3, right owns
        (_phase(0, 2), _phase(4, 2), 1),  # equal headway merges
    ],
    ids=["left_owned", "right_owned", "equal_headway_merged"],
)
def test_left_owned_right_owned_and_equal_headway_edges(left, right, regime_count):
    domain, result = _assert_graph_matches_oracle(((left,), (right,)))
    assert domain.edges == (((0, 0),),)
    assert result.paths[0].key[1] == regime_count
    assert domain.graph_statistics.legal_transition_edge_count == 1
    assert domain.graph_statistics.source_edge_count == domain.graph_statistics.sink_edge_count == 1


def test_illegal_boundary_is_excluded_and_empty_graph_exhausts():
    domain, result = _assert_graph_matches_oracle(((_phase(0, 2),), (_phase(6, 3),)))
    assert domain.layers == ((), ())
    assert domain.edges == ((),)
    assert domain.graph_statistics.reachability_trimmed_node_count == 2
    assert domain.graph_statistics.source_edge_count == domain.graph_statistics.sink_edge_count == 0
    assert result.paths == ()
    assert result.natural_exhaustion


def test_forward_and_backward_reachability_trim_only_incomplete_paths():
    # 20->24 is forward reachable but cannot finish. 40->44 can finish but
    # cannot be reached from the first layer. Only 0->4->8 survives both.
    layers = (
        (_phase(0, 2), _phase(20, 2)),
        (_phase(4, 2), _phase(24, 2), _phase(40, 2)),
        (_phase(8, 2), _phase(44, 2)),
    )
    domain, result = _assert_graph_matches_oracle(layers)
    assert domain.layers == ((layers[0][0],), (layers[1][0],), (layers[2][0],))
    assert domain.edges == (((0, 0),), ((0, 0),))
    assert domain.graph_statistics.reachability_trimmed_node_count == 4
    assert domain.graph_statistics.node_count == 3
    assert domain.graph_statistics.legal_transition_edge_count == 2
    assert result.paths[0].departure_vector == (0, 2, 4, 6, 8, 10)


def test_hand_checked_top1_top2_fractional_scale_and_node_truncation():
    layers = (
        (_phase(0, 2, q=Fraction(1, 3)), _phase(1, 1, q=Fraction(1, 2))),
        (_phase(4, 2, q=Fraction(1, 7)),),
    )
    _, one = _assert_graph_matches_oracle(layers, 1)
    _, two = _assert_graph_matches_oracle(layers, 2)
    assert [p.key for p in two.paths] == [
        (20, 1, 0, (2, 2), (0, 2, 4, 6)),
        (27, 2, 0, (1, 2), (1, 2, 4, 6)),
    ]
    assert one.paths == two.paths[:1]
    assert one.graph_statistics.truncated_node_count == 1
    assert one.graph_statistics.retained_partial_path_count == 3
    assert not one.natural_exhaustion
    assert two.graph_statistics.truncated_node_count == 0
    assert two.graph_statistics.retained_partial_path_count == 4
    assert two.natural_exhaustion


def test_terminal_limit_alone_prevents_natural_exhaustion():
    layers = ((_phase(0, 2), _phase(1, 2)),)
    _, result = _assert_graph_matches_oracle(layers, 1)
    assert result.graph_statistics.truncated_node_count == 0
    assert not result.natural_exhaustion


def test_exact_departure_dedup_and_equal_keys_have_canonical_phase_ties():
    best = _phase(0, 2, q=Fraction(1, 3))
    layers = ((best, best, replace(best, quantization_error=Fraction(1, 2)), _phase(1, 2)),)
    _, result = _assert_graph_matches_oracle(layers)
    assert [p.departure_vector for p in result.paths] == [(1, 3), (0, 2)]
    assert result.paths[1].phase_indices == (0,)
    assert result.graph_statistics.duplicate_departure_path_count == 2
    assert result.natural_exhaustion


@pytest.mark.parametrize("seed", range(40))
def test_fixed_seed_small_dags_equal_independent_exhaustive_oracle(seed):
    rng = random.Random(620600 + seed)
    # Include a guaranteed complete chain, plus disconnected and alternative
    # phases. All legal paths (at most 4**4) are materialized by the oracle.
    layers = tuple(
        tuple(
            [
                _phase(
                    4 * index,
                    2,
                    q=Fraction(rng.randrange(5), rng.choice((2, 3, 7))),
                    imbalance=rng.randrange(4),
                ),
                *(
                    _phase(
                        4 * index + rng.randrange(-1, 3),
                        rng.randrange(1, 4),
                        q=Fraction(rng.randrange(5), rng.choice((2, 3, 7))),
                        imbalance=rng.randrange(4),
                    )
                    for _ in range(rng.randrange(1, 4))
                ),
            ]
        )
        for index in range(rng.randrange(1, 5))
    )
    _assert_graph_matches_oracle(layers, 1 + seed % 7)


def test_cross_state_terminal_merge_uses_exact_fraction_quality_and_deduplicates():
    states = (_state(), _state(boundaries=(0, 13, 24)), _state(boundaries=(0, 10, 24)))
    authority = _authority(states[0])
    expected = _family_oracle(states, authority)
    individual_counts = [len(_family_oracle((state,), authority)) for state in states]
    assert sum(individual_counts) > len(expected), "fixture must exercise cross-state duplicates"
    assert len({fingerprint for _, fingerprint in expected}) > 1, (
        "fixture must exercise multiple winning states"
    )
    result = compile_service_plan_family_kbest_v1(states=states[::-1], endpoint_authority=authority)
    actual = [
        ((*c.compiler_objective, c.headway_vector, c.departure_vector), c.state_fingerprint)
        for c in result.candidates
    ]
    assert actual == expected
    assert result.natural_exhaustion
    assert result.graph_statistics.duplicate_departure_path_count > 0
    for candidate in result.candidates:
        validate_clean_boundary_compilation_v1(
            candidate.compilation, _regimes_from_state(candidate.state)
        )
        assert candidate.compilation_fingerprint == clean_compilation_fingerprint_v1(
            candidate.compilation
        )
        assert candidate.departure_vector == tuple(
            t // 60 for t in candidate.compilation.exact_departures
        )
        assert isinstance(candidate.compiler_objective[0], Fraction)
        assert candidate.path_score == (
            candidate.exact_scaled_quantization,
            *candidate.compiler_objective[1:],
            candidate.headway_vector,
            candidate.departure_vector,
        )


def test_raw_default_256_and_repeated_semantic_payloads_are_byte_identical():
    _, states, authority = _read_frozen_family()
    first = compile_service_plan_family_kbest_v1(states=states, endpoint_authority=authority)
    second = compile_service_plan_family_kbest_v1(
        states=states[::-1], endpoint_authority=authority, raw_limit=256
    )
    assert first.requested_raw_limit == 256
    assert len(first.candidates) == 256
    assert not first.natural_exhaustion
    assert first.ordered_fingerprints == tuple(c.compilation_fingerprint for c in first.candidates)
    assert first.ordered_fingerprints == second.ordered_fingerprints
    assert _canonical_bytes(_payloads(first, states)) == _canonical_bytes(_payloads(second, states))
    assert asdict(first.graph_statistics) == asdict(second.graph_statistics)
    assert all(math.isfinite(value) and value >= 0 for value in asdict(first.telemetry).values())


def test_frozen_fixture_is_reconstructable_data_only_with_exact_locks():
    payload, states, authority = _read_frozen_family()
    assert set(payload) == {
        "profile",
        "family_manifest_sha256",
        "state_fingerprints",
        "states",
        "endpoint_authority",
        "expected",
    }
    assert payload["profile"] == "pr62_u6_u5_frozen_family_v1"
    assert len(states) == len(set(payload["state_fingerprints"])) == 49
    assert [service_plan_fingerprint_v1(s) for s in states] == payload["state_fingerprints"]
    assert payload["state_fingerprints"] == sorted(payload["state_fingerprints"])
    assert payload["family_manifest_sha256"] == FAMILY_SHA
    assert payload["expected"] == {
        "top1_fingerprint": TOP1_SHA,
        "top_objective": [8214, 7, 74],
        "first_distinct_objective_tiers": [[8214, 7, 74], [9264, 7, 51], [10734, 7, 58]],
        "raw_top256_sha256": RAW_SHA,
    }
    assert all(
        set(row) == {f.name for f in fields(ServicePlanStateV1)} for row in payload["states"]
    )
    assert all(
        set(regime) == {"start", "end", "trip_count"}
        for row in payload["states"]
        for regime in row["service_regimes"]
    )
    assert set(payload["endpoint_authority"]) == {
        f.name for f in fields(OperationalEndpointAuthorityV1)
    }
    assert {s.total_trips for s in states} == {states[0].total_trips}
    assert all(service_plan_matches_endpoint_contract_v1(s, authority) for s in states)
    encoded = json.dumps(payload).lower()
    for forbidden in (
        ".pickle",
        ".pkl",
        "checkpoint",
        "source_pair",
        '"context"',
        "experiments.",
        "ortools",
        "timings",
        "wall_seconds",
        "pr62_u2/",
        "pr62_u3/",
        "pr62_u4/",
    ):
        assert forbidden not in encoded


def test_u5_frozen_family_has_exact_production_port_parity():
    payload, states, authority = _read_frozen_family()
    result = compile_service_plan_family_kbest_v1(
        states=states, endpoint_authority=authority, raw_limit=256
    )
    records = _payloads(result, states)
    assert len(records) == 256
    assert records[0]["fingerprint"] == payload["expected"]["top1_fingerprint"] == TOP1_SHA
    assert records[0]["integer_objective"] == [8214, 7, 74]
    tiers = []
    for record in records:
        if record["integer_objective"] not in tiers:
            tiers.append(record["integer_objective"])
    assert tiers[:3] == [[8214, 7, 74], [9264, 7, 51], [10734, 7, 58]]
    # U5's worker added these derived evidence fields after core extraction.
    # The frozen raw.json hash covers that decorated encoding; the production
    # payload remains the exact core schema asserted independently below.
    u5_evidence_records = [
        {
            **record,
            "tier_index": tiers.index(record["integer_objective"]),
            "delta_from_tier0": [
                value - baseline
                for value, baseline in zip(
                    record["integer_objective"], records[0]["integer_objective"], strict=True
                )
            ],
            "unscaled_quantization": record["objective"][0],
        }
        for record in records
    ]
    assert (
        hashlib.sha256(_canonical_bytes(u5_evidence_records)).hexdigest()
        == payload["expected"]["raw_top256_sha256"]
        == RAW_SHA
    )
    for candidate, record in zip(result.candidates, records, strict=True):
        assert record == {
            "fingerprint": candidate.compilation_fingerprint,
            "departures_minutes": list(candidate.departure_vector),
            "state_fingerprint": candidate.state_fingerprint,
            "state_index": payload["state_fingerprints"].index(candidate.state_fingerprint),
            "phase_indices": list(candidate.phase_indices),
            "headway_shape": list(candidate.headway_vector),
            "objective": [str(v) for v in candidate.compiler_objective],
            "integer_objective": [
                candidate.exact_scaled_quantization,
                *candidate.compiler_objective[1:],
            ],
            "direction": candidate.state.direction,
            "endpoint_checks": {"first": True, "last": True},
        }
        assert candidate.exact_scaled_quantization == candidate.compiler_objective[0] * 75600


def test_return_contracts_are_frozen_slotted_semantic_objects():
    state = _state()
    result = compile_service_plan_family_kbest_v1(
        states=(state,), endpoint_authority=_authority(state), raw_limit=1
    )
    for value, kind in (
        (result, KBestDagFrontierV1),
        (result.candidates[0], KBestDagCandidateV1),
        (result.graph_statistics, KBestDagGraphStatisticsV1),
        (result.telemetry, KBestDagTelemetryV1),
    ):
        assert isinstance(value, kind)
        assert not hasattr(value, "__dict__")
        with pytest.raises(FrozenInstanceError):
            setattr(value, fields(value)[0].name, None)


def test_production_dag_has_no_experiments_or_ortools_imports():
    source = ROOT / "src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py"
    forbidden = []
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            forbidden.extend(
                alias.name
                for alias in node.names
                if alias.name.split(".")[0] in {"experiments", "ortools"}
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in {"experiments", "ortools"}
        ):
            forbidden.append(node.module)
    assert forbidden == []


def test_production_dag_imports_in_child_process_with_ortools_unavailable(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    # The unchanged package initializers eagerly export legacy OR-Tools solvers.
    # Seed only namespace paths so this process loads the real DAG and its real
    # dependency closure without executing unrelated application exports.
    probe = f"""
import importlib
import sys
import types
from pathlib import Path

source = Path({str(ROOT / "src")!r})
for name in ("bus_schedule_engine", "bus_schedule_engine.contracts_v1"):
    package = types.ModuleType(name)
    package.__path__ = [str(source.joinpath(*name.split(".")))]
    sys.modules[name] = package
sys.modules["ortools"] = None
importlib.import_module({MODULE!r})
assert sys.modules["ortools"] is None
assert not any(
    name == "experiments" or name.startswith(("experiments.", "ortools."))
    or (name.startswith("bus_schedule_engine.") and "solver" in name)
    for name in sys.modules
)
print("DAG_IMPORT_WITHOUT_ORTOOLS_OK")
"""
    child = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert child.returncode == 0, child.stdout + child.stderr
    assert child.stdout.strip() == "DAG_IMPORT_WITHOUT_ORTOOLS_OK"

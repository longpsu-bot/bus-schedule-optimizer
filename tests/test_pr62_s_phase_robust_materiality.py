from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

import scripts.run_pr62_s_phase_robust_materiality as s

REPO_ROOT = Path(__file__).resolve().parents[1]


def _candidate(
    fingerprint: str,
    delta: float,
    rhythm: tuple[int, int, int, int],
    fleet: tuple[int, int, int],
    *,
    production_te_delta: float = 0.0,
    micro: int = 1,
) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "production_TE": 10.0 + production_te_delta,
        "continuous_exposure_equivalent": 20.0 + delta,
        "bucket_exposure_equivalent": 30.0 + delta,
        "rhythm_tuple": list(rhythm),
        "fleet_tuple": list(fleet),
        "micro_rhythm_boundary_count": micro,
    }


def test_breakpoints_are_exact_candidate_deltas_without_intermediate_samples() -> None:
    """Catch arbitrary threshold sampling or loss of an observed candidate delta."""

    s = importlib.import_module("scripts.run_pr62_s_phase_robust_materiality")

    assert s.observed_breakpoints([0.0, 0.4, 1.6, 2.0]) == [0.0, 0.4, 1.6, 2.0]


def test_compact_path_collapses_consecutive_breakpoints_with_same_winner() -> None:
    """Catch redundant path states that obscure the actual selector transitions."""

    candidates = [
        _candidate("anchor", 0.0, (2, 2, 2, 0), (2, 0, 0)),
        _candidate("worse-a", 0.4, (3, 1, 1, 0), (1, 0, 0)),
        _candidate("worse-b", 0.8, (4, 1, 1, 0), (1, 0, 0)),
        _candidate("simpler", 1.6, (1, 9, 9, 0), (9, 0, 0)),
    ]

    result = s.breakpoint_experiment(
        candidates, metric="continuous_exposure_equivalent", anchor_fingerprint="anchor"
    )

    assert result["breakpoints"] == pytest.approx([0.0, 0.4, 0.8, 1.6])
    assert [row["breakpoint"] for row in result["compact_path"]] == pytest.approx([0.0, 1.6])
    assert [(row["selected"], row["admitted_count"]) for row in result["compact_path"]] == [
        ("anchor", 1),
        ("simpler", 4),
    ]


def test_only_compact_winner_records_carry_full_metrics_and_all_anchor_deltas() -> None:
    """Catch repeated heavy records or omission of old/new metric comparison fields."""

    candidates = [
        _candidate("anchor", 0.0, (2, 2, 2, 0), (2, 0, 0)),
        _candidate("simpler", 1.6, (1, 1, 1, 0), (3, 0, 0), production_te_delta=0.7),
    ]

    result = s.breakpoint_experiment(
        candidates, metric="continuous_exposure_equivalent", anchor_fingerprint="anchor"
    )

    assert "selected_record" not in result["breakpoint_audit"][0]
    selected = result["compact_path"][1]["selected_record"]
    assert selected["production_TE_delta_from_anchor"] == pytest.approx(0.7)
    assert selected["continuous_exposure_delta_from_anchor"] == pytest.approx(1.6)
    assert selected["bucket_exposure_delta_from_anchor"] == pytest.approx(1.6)


def test_rhythm_precedes_fleet_in_breakpoint_selection() -> None:
    """Catch a fleet-first ordering that would mutate the frozen selector hierarchy."""

    candidates = [
        _candidate("better-rhythm", 0.0, (1, 9, 9, 9), (9, 9, 9)),
        _candidate("better-fleet", 0.0, (2, 0, 0, 0), (1, 0, 0)),
    ]

    assert s.select_by_frozen_secondary_hierarchy(candidates)["fingerprint"] == "better-rhythm"


def test_fleet_breaks_only_an_exact_rhythm_tie() -> None:
    """Catch failure to use the frozen fleet tuple after an exact rhythm tie."""

    candidates = [
        _candidate("fleet-worse", 0.0, (1, 2, 3, 4), (2, 0, 0)),
        _candidate("fleet-better", 0.0, (1, 2, 3, 4), (1, 9, 9)),
    ]

    assert s.select_by_frozen_secondary_hierarchy(candidates)["fingerprint"] == "fleet-better"


def test_fingerprint_is_only_the_final_exact_tie_break() -> None:
    """Catch fingerprint being promoted ahead of rhythm or fleet quality."""

    tied = [
        _candidate("bbb", 0.0, (1, 2, 3, 4), (5, 6, 7)),
        _candidate("aaa", 0.0, (1, 2, 3, 4), (5, 6, 7)),
    ]

    assert s.select_by_frozen_secondary_hierarchy(tied)["fingerprint"] == "aaa"


def test_legacy_preservation_bound_is_descriptive_maximum_phase_delta() -> None:
    """Catch copying the numeric +1 band instead of mapping its admitted set."""

    candidates = [
        _candidate("anchor", 0.0, (1, 1, 1, 0), (1, 1, 1), production_te_delta=0.0),
        _candidate("legacy-a", 0.3, (1, 1, 1, 0), (1, 1, 1), production_te_delta=0.5),
        _candidate("legacy-b", 1.8, (1, 1, 1, 0), (1, 1, 1), production_te_delta=1.0),
        _candidate("outside", 0.2, (1, 1, 1, 0), (1, 1, 1), production_te_delta=1.1),
    ]

    result = s.legacy_eligibility_mapping(
        candidates, metric="continuous_exposure_equivalent", anchor_fingerprint="anchor"
    )

    assert result["admitted_fingerprints"] == ["anchor", "legacy-a", "legacy-b"]
    assert result["delta_range"] == [0.0, 1.8000000000000007]
    assert result["preservation_bound"] == 1.8000000000000007
    assert result["production_threshold_created"] is False


def test_q_admission_does_not_imply_q_selection() -> None:
    """Catch treating inclusion in the phase envelope as automatic selection."""

    candidates = [
        _candidate("anchor", 0.0, (3, 3, 3, 0), (2, 0, 0)),
        _candidate("better-than-q", 0.5, (1, 1, 1, 0), (3, 0, 0)),
        _candidate("q", 1.0, (2, 1, 1, 0), (1, 0, 0), micro=0),
    ]

    result = s.breakpoint_experiment(
        candidates, metric="continuous_exposure_equivalent", anchor_fingerprint="anchor"
    )
    q_row = next(row for row in result["breakpoint_audit"] if row["breakpoint"] == 1.0)

    assert "q" in q_row["admitted_fingerprints"]
    assert q_row["selected"] == "better-than-q"


def test_material_disagreement_uses_only_the_four_declared_path_conditions() -> None:
    """Catch inventing a percentage or treating numeric-only differences as material."""

    continuous = {
        "first_rhythm_improvement_winner": "x",
        "first_micro_rhythm_free_winner": "q",
        "q_selected": True,
        "q_selection_vs_legacy_bound": "LESS",
    }
    bucket = {**continuous, "numeric_breakpoint": 999.0}

    assert s.material_path_disagreement(continuous, bucket) is False
    bucket["first_rhythm_improvement_winner"] = "y"
    assert s.material_path_disagreement(continuous, bucket) is True


def test_preserved_report_hash_and_fingerprint_mismatches_fail_closed(tmp_path: Path) -> None:
    """Catch use of operational reconstruction data before both integrity gates pass."""

    payload = {"pareto_frontier": [{"pair_fingerprint": "a"}, {"pair_fingerprint": "b"}]}
    path = tmp_path / "report.json"
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()

    loaded = s.load_locked_preserved_report(
        path, expected_sha256=digest, expected_fingerprints=["a", "b"]
    )
    assert [row["pair_fingerprint"] for row in loaded["pareto_frontier"]] == ["a", "b"]
    with pytest.raises(RuntimeError, match="hash mismatch"):
        s.load_locked_preserved_report(
            path, expected_sha256="0" * 64, expected_fingerprints=["a", "b"]
        )
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        s.load_locked_preserved_report(path, expected_sha256=digest, expected_fingerprints=["a"])


def test_committed_authorities_build_exact_route_universes_without_replay() -> None:
    """Catch authority drift, missing Q labeling, or accidental coordinator execution."""

    payload = s.build_evidence(REPO_ROOT)

    assert payload["R_commit_SHA"] == "702e0fe494f340d27b862cd4ffbca64366f2df03"
    assert (
        payload["R_evidence_lock"]["json"]["sha256"]
        == "7f6b238981024ede96905072a6445f55df5fca09d41539088fdd1579b15840fd"
    )
    assert payload["routes"]["10"]["candidate_universe_count"] == 8
    assert payload["routes"]["10"]["Q_authority"] == "Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE"
    assert payload["routes"]["6"]["candidate_universe_count"] == 41
    assert (
        payload["routes"]["10"]["anchor_fingerprint"]
        == "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
    )
    assert (
        payload["routes"]["10"]["P_fingerprint"]
        == "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24"
    )
    assert (
        payload["routes"]["10"]["Q_fingerprint"]
        == "12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5"
    )
    assert (
        payload["routes"]["6"]["anchor_fingerprint"]
        == "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"
    )
    assert (
        payload["routes"]["10"]["Q_continuous_delta"]
        < payload["routes"]["10"]["P_continuous_delta"]
    )
    assert payload["input_provenance"]["coordinator_replays_executed_by_S"] == 0
    assert all(value is False for value in payload["production_guards"].values())


def test_route10_named_observations_and_cross_route_table_are_explicit() -> None:
    """Catch forcing reviewers to infer required A-E observations from raw path rows."""

    payload = s.build_evidence(REPO_ROOT)
    continuous = payload["routes"]["10"]["required_breakpoint_observations"][
        "continuous_exposure_equivalent"
    ]

    assert continuous["FIRST_RHYTHM_IMPROVEMENT_BREAKPOINT"]["breakpoint"] == pytest.approx(
        0.3918230056112346
    )
    assert continuous["FIRST_MICRO_RHYTHM_FREE_BREAKPOINT"]["breakpoint"] == pytest.approx(
        1.5562442641156515
    )
    assert continuous["FIRST_Q_CANONICAL_ADMISSION_BREAKPOINT"] == pytest.approx(1.5562442641156515)
    assert continuous["CURRENT_P_ADMISSION_BREAKPOINT"] == pytest.approx(1.9858806668778222)
    assert continuous["MINIMUM_BREAKPOINT_SELECTING_Q"] == pytest.approx(1.5562442641156515)
    assert payload["cross_route_breakpoint_comparison"]["10"]["continuous_exposure_equivalent"][
        "Q_selected"
    ] == pytest.approx(1.5562442641156515)
    assert payload["classification"] == "PHASE_ROBUST_MATERIALITY_PATH_SUPPORTS_CANONICAL_Q"
    assert payload["next_milestone_recommendation"] == (
        "PR62-T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE"
    )

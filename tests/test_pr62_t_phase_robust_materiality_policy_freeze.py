from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

ROUTE6_ANCHOR = "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"
ROUTE10_ANCHOR = "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
ROUTE10_CONTINUOUS_INTERIM = "6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16"
ROUTE10_BUCKET_INTERIM = "c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7"
ROUTE10_Q = "12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5"


def _runner():
    module = importlib.import_module("scripts.run_pr62_t_phase_robust_materiality_policy_freeze")
    assert hasattr(module, "build_evidence")
    return module


def test_committed_s_universes_derive_exact_v3_route_locks_without_replay() -> None:
    """Catch hardcoded winners, wrong universe slicing, or accidental coordinator replay."""

    payload = _runner().build_evidence(REPO_ROOT)
    route6 = payload["route_results"]["6_current_production"]
    route10 = payload["route_results"]["10_current_production"]
    augmented = payload["route_results"]["10_q_augmented_review"]

    assert route6["common_anchor_fingerprint"] == ROUTE6_ANCHOR
    assert route6["legacy_calibration_set_count"] == 5
    assert route6["continuous_preservation_bound"] == pytest.approx(1.2760765031007502)
    assert route6["phase_robust_materiality_set_count"] == 6
    assert route6["selected_pair_fingerprint"] == ROUTE6_ANCHOR
    assert route6["classification"] == "PHASE_ROBUST_MATERIALITY_SELECTS_ANCHOR"

    assert route10["common_anchor_fingerprint"] == ROUTE10_ANCHOR
    assert route10["legacy_calibration_set_count"] == 2
    assert route10["continuous_preservation_bound"] == pytest.approx(1.9858806668778222)
    assert route10["phase_robust_materiality_set_count"] == 6
    assert route10["selected_pair_fingerprint"] == ROUTE10_CONTINUOUS_INTERIM

    assert augmented["common_anchor_fingerprint"] == ROUTE10_ANCHOR
    assert augmented["legacy_calibration_set_count"] == 2
    assert augmented["continuous_preservation_bound"] == pytest.approx(1.9858806668778222)
    assert augmented["phase_robust_materiality_set_count"] == 7
    assert augmented["selected_pair_fingerprint"] == ROUTE10_Q
    assert augmented["selected_inside_legacy_te_calibration_set"] is False
    assert payload["input_provenance"]["coordinator_replays_executed_by_T"] == 0


def test_bucket_corroboration_reports_distinct_interim_and_q_convergence() -> None:
    """Catch false claims that both phase-robust paths have every intermediate winner equal."""

    payload = _runner().build_evidence(REPO_ROOT)
    bucket = payload["bucket_exposure_corroboration"]

    assert bucket["route_6"]["preservation_bound"] == pytest.approx(1.2119704346485456)
    assert bucket["route_6"]["selected"] == ROUTE6_ANCHOR
    assert bucket["route_10_production_only"]["preservation_bound"] == pytest.approx(
        2.2628191917926586
    )
    assert bucket["route_10_production_only"]["selected"] == ROUTE10_BUCKET_INTERIM
    assert bucket["route_10_q_augmented"]["selected"] == ROUTE10_Q
    assert payload["intermediate_winner_comparison"] == {
        "continuous_production_only_winner": ROUTE10_CONTINUOUS_INTERIM,
        "bucket_production_only_winner": ROUTE10_BUCKET_INTERIM,
        "intermediate_winners_identical": False,
        "q_augmented_winners_converge_on_q": True,
    }


def test_q_remains_external_and_readiness_stops_before_final_pilot_use() -> None:
    """Catch relabeling Q as production output or advancing readiness into U/V."""

    payload = _runner().build_evidence(REPO_ROOT)

    assert payload["q_production_boundary"]["authority"] == (
        "Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE"
    )
    assert payload["q_production_boundary"]["generated_by_current_production_search"] is False
    assert payload["classification"] == "PHASE_ROBUST_MATERIALITY_POLICY_V3_FROZEN"
    assert payload["next_milestone"] == ("PR62-U_LOCAL_RHYTHM_CANONICALIZATION_SEARCH_INTEGRATION")
    assert payload["readiness"] == {
        "READY_FOR_LOCAL_RHYTHM_SEARCH_INTEGRATION": True,
        "READY_FOR_FINAL_PILOT_USE": False,
        "READY_FOR_PR62_COMPLETION_REVIEW": False,
    }
    assert payload["READY_FOR_LOCAL_RHYTHM_SEARCH_INTEGRATION"] is True
    assert payload["READY_FOR_FINAL_PILOT_USE"] is False
    assert payload["READY_FOR_PR62_COMPLETION_REVIEW"] is False


def test_production_guards_record_only_the_two_deliberate_v3_additions() -> None:
    """Catch production mutation being hidden as part of the policy freeze."""

    guards = _runner().build_evidence(REPO_ROOT)["production_guards"]
    deliberate = {
        "V3_selector_added": "YES",
        "Continuous_exposure_metric_promoted_to_V3_materiality": "YES",
    }

    assert {key: guards[key] for key in deliberate} == deliberate
    assert all(value == "NO" for key, value in guards.items() if key not in deliberate)


def test_lock_verification_fails_closed_on_byte_drift(tmp_path: Path) -> None:
    """Catch reporting unchanged authorities without hashing their current bytes."""

    runner = _runner()
    locked = tmp_path / "locked.txt"
    locked.write_bytes(b"authority")
    digest = hashlib.sha256(b"authority").hexdigest()

    assert (
        runner.verify_file_locks(tmp_path, {"locked.txt": digest})["locked.txt"]["unchanged"]
        is True
    )
    locked.write_bytes(b"drift")
    with pytest.raises(RuntimeError, match="authority lock mismatch"):
        runner.verify_file_locks(tmp_path, {"locked.txt": digest})


def test_json_and_markdown_render_twice_byte_identically() -> None:
    """Catch timestamps, ordering leaks, or any nondeterministic evidence serialization."""

    runner = _runner()
    payload = runner.build_evidence(REPO_ROOT)

    assert runner.canonical_json_bytes(payload) == runner.canonical_json_bytes(payload)
    assert runner.render_markdown(payload).encode("utf-8") == runner.render_markdown(
        payload
    ).encode("utf-8")
    assert payload["deterministic_render"] is True


def test_committed_evidence_matches_fresh_deterministic_render() -> None:
    """Catch stale or manually edited evidence diverging from the certification runner."""

    runner = _runner()
    payload = runner.build_evidence(REPO_ROOT)

    assert (REPO_ROOT / runner.OUTPUT_JSON).read_bytes() == runner.canonical_json_bytes(payload)
    assert (REPO_ROOT / runner.OUTPUT_MARKDOWN).read_bytes() == runner.render_markdown(
        payload
    ).encode("utf-8")

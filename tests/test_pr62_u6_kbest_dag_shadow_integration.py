"""The explicit certification boundary must reject invalid evidence before acting."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import run_pr62_u6_kbest_dag_shadow_production_integration as runner

from bus_schedule_engine import service_plan_coordinator as coordinator

ROOT = Path(__file__).resolve().parents[1]
SAVED = Path(
    "E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u/"
    ".pr62-u-local/certification/route_10_complete_base.pickle"
)
FIXTURE = ROOT / "tests/fixtures/pr62_u6/u5_frozen_family.json"


def test_saved_route10_binds_exact_bytes_and_reconstructs_authorities(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("global coordinator called while reconstructing Route 10")

    monkeypatch.setattr(coordinator, "search_route_service_plans_v1", forbidden)
    loaded = runner.load_route10_saved_result(SAVED)
    assert loaded.input_authority["size"] == 70577
    assert loaded.input_authority["sha256"] == (
        "d2ba609ffd8fa4450e0a0662a0c9255dcdf1d8d2b759e63a8de6cf44fbfb114b"
    )
    assert len(loaded.base.pareto_frontier) == 11
    assert loaded.selection.passenger_access_safe_count == 7
    assert loaded.selection.selected_pair_fingerprint == (
        "6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16"
    )
    assert "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24" in (
        loaded.selection.phase_robust_materiality_fingerprints
    )
    assert loaded.global_coordinator_executions == 0


@pytest.mark.parametrize("mutation", ["size", "hash", "path"])
def test_saved_wrong_authority_is_rejected_before_unpickle(tmp_path, monkeypatch, mutation):
    path = SAVED if mutation != "path" else tmp_path / "untrusted.pickle"
    original = Path.read_bytes
    data = original(SAVED)
    assert len(data) == 70577
    assert hashlib.sha256(data).hexdigest() == runner.ROUTE10_SHA256
    if mutation == "size":
        data = data[:-1]
    elif mutation == "hash":
        data = bytes([data[0] ^ 1]) + data[1:]
    monkeypatch.setattr(Path, "read_bytes", lambda self: data)
    monkeypatch.setattr(
        runner.pickle, "loads", lambda _: pytest.fail("unpickled before byte authority check")
    )
    with pytest.raises(runner.CertificationError, match="U6_ROUTE10_SAVED_BASE_AUTHORITY_MISMATCH"):
        runner.load_route10_saved_result(path)


def test_route10_reconstruction_rejects_wrong_budget_and_selection():
    loaded = runner.load_route10_saved_result(SAVED)
    altered = dataclasses.replace(
        loaded.base,
        search_budget=dataclasses.replace(loaded.base.search_budget, max_pair_frontier=1),
    )
    with pytest.raises(runner.CertificationError, match="U6_ROUTE10_GLOBAL_BASE_MISMATCH"):
        runner.certify_route10_base(loaded.context, altered)
    altered = dataclasses.replace(loaded.base, pareto_frontier=loaded.base.pareto_frontier[:1])
    with pytest.raises(runner.CertificationError, match="U6_ROUTE10_GLOBAL_BASE_MISMATCH"):
        runner.certify_route10_base(loaded.context, altered)


@pytest.mark.parametrize(
    "entrypoint",
    [
        "bus_schedule_engine",
        "bus_schedule_engine.application_pipeline",
        "bus_schedule_engine.optimization_service",
        "bus_schedule_engine.local_rhythm_refinement",
        "run_pr62_t_phase_robust_materiality_policy_freeze",
    ],
)
def test_explicit_shadow_never_loaded_by_existing_production_entrypoints(entrypoint):
    program = """
import importlib, sys
importlib.import_module(sys.argv[1])
assert 'bus_schedule_engine.kbest_shadow_refinement' not in sys.modules
assert 'bus_schedule_engine.contracts_v1.kbest_dag_frontier' not in sys.modules
assert 'run_pr62_u6_kbest_dag_shadow_production_integration' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", program, entrypoint],
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT / "scripts"))),
        },
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_explicit_global_guard_blocks_coordinator_and_restores_authority():
    original = coordinator.search_route_service_plans_v1
    with runner.zero_global_calls() as observed:
        with pytest.raises(runner.CertificationError, match="U6_ROUTE10_GLOBAL_CALL_PROHIBITED"):
            coordinator.search_route_service_plans_v1()
        assert observed["global_coordinator_executions"] == 1
    assert coordinator.search_route_service_plans_v1 is original


def test_explicit_scratch_write_is_exclusive(tmp_path):
    output = tmp_path / "payload.json"
    runner.write_once(output, b"first\n")
    with pytest.raises(FileExistsError):
        runner.write_once(output, b"second\n")
    assert output.read_bytes() == b"first\n"


def test_parity_runner_reproduces_frozen_u5_without_accepting_fixture_rewrites(tmp_path):
    parity = runner.run_parity(FIXTURE)
    assert parity["classification"] == "U5_EXACT_PRODUCTION_PORT_PARITY"
    assert parity["raw_top256_sha256"] == (
        "71092c883923e6d5460980a8c528f263a275255986e887bb03c3c1ef16c17601"
    )
    assert parity["first_distinct_objective_tiers"] == [
        [8214, 7, 74],
        [9264, 7, 51],
        [10734, 7, 58],
    ]
    changed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    changed["expected"]["top1_fingerprint"] = "0" * 64
    other = tmp_path / "altered.json"
    other.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(runner.CertificationError, match="U6_PRODUCTION_PORT_DIVERGED_FROM_U5"):
        runner.run_parity(other)


def _frozen_run():
    semantic = {
        "processed_source_order": ["source"],
        "raw_hashes": ["raw"],
        "eligible_hashes": ["eligible"],
        "retained_hashes": ["retained"],
        "pair_fingerprints": ["pair"],
        "final_pareto_hash": "pareto",
        "final_v3_fingerprint": "selected",
        "source_once": True,
        "hard_valid": True,
        "exact_fleet_valid": True,
        "global_coordinator_executions": 0,
    }
    return {
        "semantic": semantic,
        "semantic_sha256": runner.semantic_hash(semantic),
        "timings": {"total_seconds": 1.0, "max_family_dag_seconds": 0.2},
    }


def test_route10_determinism_excludes_timings_but_checks_every_semantic_stage():
    frozen = _frozen_run()
    repeat = json.loads(json.dumps(frozen))
    repeat["timings"]["total_seconds"] = 10.0
    assert runner.compare_route10_repeat(frozen, repeat)["identical"]
    for key in frozen["semantic"]:
        changed = json.loads(json.dumps(repeat))
        changed["semantic"][key] = "different"
        changed["semantic_sha256"] = runner.semantic_hash(changed["semantic"])
        with pytest.raises(runner.CertificationError, match="U6_ROUTE10_SHADOW_NONDETERMINISTIC"):
            runner.compare_route10_repeat(frozen, changed)


@pytest.mark.parametrize(
    "field,value,label",
    [
        ("global_coordinator_executions", 1, "U6_ROUTE10_GLOBAL_CALL_PROHIBITED"),
        ("source_once", False, "U6_ROUTE10_SOURCE_ONCE_CONTRACT_MISMATCH"),
        ("hard_valid", False, "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH"),
        ("exact_fleet_valid", False, "U6_ROUTE10_EXACT_FLEET_CONTRACT_MISMATCH"),
        ("total_seconds", 300.01, "U6_ROUTE10_SHADOW_OPERATIONALLY_INTRACTABLE"),
        ("max_family_dag_seconds", 60.01, "U6_ROUTE10_FAMILY_DAG_OPERATIONALLY_INTRACTABLE"),
    ],
)
def test_route10_gates_fail_closed(field, value, label):
    frozen = _frozen_run()
    section = "timings" if field.endswith("seconds") else "semantic"
    frozen[section][field] = value
    frozen["semantic_sha256"] = runner.semantic_hash(frozen["semantic"])
    with pytest.raises(runner.CertificationError, match=label):
        runner.validate_route10_payload(frozen)


def test_deterministic_renderer_has_all_sections_and_false_readiness(tmp_path):
    frozen = _frozen_run()
    evidence = runner.build_evidence(
        parity={"classification": "U5_EXACT_PRODUCTION_PORT_PARITY"},
        canonical=frozen,
        repeat=frozen,
        sensitivity={
            "binding": False,
            "canonical_cap32_semantic_sha256": frozen["semantic_sha256"],
        },
        port={"protected_authority_unchanged": True},
    )
    first, second = tmp_path / "first", tmp_path / "second"
    runner.render_evidence(evidence, first)
    runner.render_evidence(evidence, second)
    for name in (runner.EVIDENCE_JSON, runner.EVIDENCE_MD):
        data = (first / name).read_bytes()
        assert data == (second / name).read_bytes()
        assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    assert set(evidence) == {"PORT", "ROUTE 10", "ROUTE 6", "Q", "READINESS"}
    assert evidence["ROUTE 10"]["classification"] == "ROUTE10_KBEST_DAG_SHADOW_VALIDATED"
    assert evidence["ROUTE 6"]["state"] == "NOT_RUN_ROUTE10_GATE_PENDING"
    assert not any(evidence["READINESS"].values())


def test_q_is_observed_only_on_frozen_outputs_and_never_changes_classification():
    frozen = _frozen_run()
    with pytest.raises(runner.CertificationError, match="U6_Q_OBSERVATION_REQUIRES_FROZEN_OUTPUT"):
        runner.observe_q_after_freeze({"semantic": frozen["semantic"]}, "pair")
    original = runner.canonical_bytes(frozen)
    present = runner.observe_q_after_freeze(frozen, "pair")
    absent = runner.observe_q_after_freeze(frozen, "absent")
    assert present["pair_present"] is True
    assert absent["pair_present"] is False
    assert present["policy"] == absent["policy"] == "HISTORICAL_REFERENCE_ONLY"
    assert runner.canonical_bytes(frozen) == original


def test_evidence_rejects_binding_and_sensitivity_from_different_canonical_run():
    frozen = _frozen_run()
    for sensitivity, label in [
        ({"binding": True}, "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING"),
        (
            {"binding": False, "canonical_cap32_semantic_sha256": "other"},
            "U6_ROUTE10_SHADOW_NONDETERMINISTIC",
        ),
    ]:
        with pytest.raises(runner.CertificationError, match=label):
            runner.build_evidence(
                parity={"classification": "U5_EXACT_PRODUCTION_PORT_PARITY"},
                canonical=frozen,
                repeat=frozen,
                sensitivity=sensitivity,
                port={"protected_authority_unchanged": True},
            )


def test_route6_stages_cannot_consume_any_action_in_task7(tmp_path):
    for stage in ("route6-global-once", "route6-canonical", "route6-repeat", "route6-sensitivity"):
        with pytest.raises(runner.CertificationError, match="U6_ROUTE6_NOT_AUTHORIZED_IN_TASK7"):
            runner.main([stage, "--output-dir", str(tmp_path / stage)])
        assert not (tmp_path / stage).exists()


def test_explicit_runner_projects_real_shadow_result_and_restores_instrumentation():
    from test_kbest_shadow_refinement import _completed, _real_pair_context

    from bus_schedule_engine import kbest_shadow_refinement as shadow

    source, context = _real_pair_context()
    completed = _completed((source,), runner.FROZEN_BUDGET)
    original = shadow.compile_service_plan_family_kbest_v1
    with runner.instrument_shadow_gates() as observed:
        result = shadow.run_kbest_dag_shadow_from_completed_result_v1(
            base_coordinator_result=completed,
            context=context,
            coordinator_budget=runner.FROZEN_BUDGET,
            directional_frontier_limit=32,
            semantic_cache={},
        )
    assert shadow.compile_service_plan_family_kbest_v1 is original
    payload = runner.project_shadow_result(result, context=context, observed=observed, cap=32)
    # This small equal-demand fixture has no unique final V3 anchor either.
    with pytest.raises(
        runner.CertificationError, match="U6_ROUTE10_FINAL_V3_SELECTION_UNAVAILABLE"
    ):
        runner.validate_route10_payload(payload)
    assert payload["semantic"]["processed_source_order"] == list(
        result.processed_source_pair_fingerprints
    )
    assert payload["semantic"]["pair_fingerprints"] == list(result.generated_pair_fingerprints)
    assert payload["semantic"]["families"]
    assert payload["timings"]["hard_eligibility_seconds"] > 0
    assert payload["semantic"]["exact_fleet_valid"]
    assert "seconds" not in json.dumps(payload["semantic"])


def test_explicit_runtime_gate_stops_structural_reject_before_retention(monkeypatch):
    from types import SimpleNamespace

    from bus_schedule_engine import kbest_shadow_refinement as shadow

    monkeypatch.setattr(
        shadow,
        "evaluate_kbest_dag_hard_eligibility_v1",
        lambda **kwargs: SimpleNamespace(structural_rejects=1),
    )
    with (
        runner.instrument_shadow_gates(),
        pytest.raises(
            runner.CertificationError, match="U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH"
        ),
    ):
        shadow.evaluate_kbest_dag_hard_eligibility_v1()


def test_exact_fleet_observation_records_success_and_excludes_rejected_pairs():
    from test_kbest_shadow_refinement import _real_pair_context

    from bus_schedule_engine import kbest_shadow_refinement as shadow

    source, context = _real_pair_context()
    with runner.instrument_shadow_gates() as observed:
        valid, _ = shadow.evaluate_operating_pair_v1(
            source.outbound, source.inbound, context=context
        )
        context.fleet_ceiling = 1
        rejected, _ = shadow.evaluate_operating_pair_v1(
            source.outbound, source.inbound, context=context
        )
    assert valid is not None and rejected is None
    assert list(observed["fleet_valid_pairs"]) == [source.pair_fingerprint]
    assert observed["fleet_valid_pairs"][source.pair_fingerprint]["metrics"]["fleet_required"] > 1


def test_final_v3_unavailable_cannot_pass_route10_certification():
    frozen = _frozen_run()
    frozen["semantic"]["final_v3_fingerprint"] = None
    frozen["semantic"]["final_selection"] = {"classification": "DEMAND_FIT_ANCHOR_CONFLICT"}
    frozen["semantic_sha256"] = runner.semantic_hash(frozen["semantic"])
    with pytest.raises(
        runner.CertificationError, match="U6_ROUTE10_FINAL_V3_SELECTION_UNAVAILABLE"
    ):
        runner.validate_route10_payload(frozen)
    runner.validate_route10_payload(frozen, diagnostic_final_selection=True)
    frozen["semantic"]["hard_valid"] = False
    frozen["semantic_sha256"] = runner.semantic_hash(frozen["semantic"])
    with pytest.raises(
        runner.CertificationError, match="U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH"
    ):
        runner.validate_route10_payload(frozen, diagnostic_final_selection=True)


def test_diagnostic_evidence_preserves_selection_blocker_and_false_readiness(tmp_path):
    frozen = _frozen_run()
    frozen["semantic"]["final_v3_fingerprint"] = None
    frozen["semantic"]["final_selection"] = {"classification": "DEMAND_FIT_ANCHOR_CONFLICT"}
    frozen["semantic_sha256"] = runner.semantic_hash(frozen["semantic"])
    kwargs = dict(
        parity={"classification": "U5_EXACT_PRODUCTION_PORT_PARITY"},
        canonical=frozen,
        repeat=frozen,
        sensitivity={
            "binding": False,
            "canonical_cap32_semantic_sha256": frozen["semantic_sha256"],
        },
        port={"protected_authority_unchanged": True},
    )
    evidence = runner.build_evidence(**kwargs, diagnostic_final_selection=True)
    assert evidence["ROUTE 10"]["classification"] == "U6_ROUTE10_FINAL_V3_SELECTION_UNAVAILABLE"
    assert evidence["ROUTE 6"]["state"] == "NOT_RUN_ROUTE10_GATE_FAILED"
    assert not any(evidence["READINESS"].values())
    runner.render_evidence(evidence, tmp_path / "blocked")
    markdown = (tmp_path / "blocked" / runner.EVIDENCE_MD).read_text(encoding="utf-8")
    assert "DEMAND_FIT_ANCHOR_CONFLICT" in markdown
    assert "no selected timetable" in markdown
    kwargs["sensitivity"]["binding"] = True
    evidence = runner.build_evidence(**kwargs, diagnostic_final_selection=True)
    assert evidence["ROUTE 10"]["classification"] == "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING"

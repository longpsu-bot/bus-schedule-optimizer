"""The explicit certification boundary must reject invalid evidence before acting."""

from __future__ import annotations

import copy
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


def _frozen_run(*, pid=11, cap=32, selected="selected"):
    pair = {"fingerprint": "selected", "pareto_vector": [1, 2]}
    semantic = {
        "directional_cap": cap,
        "processed_source_order": ["source"],
        "raw_hashes": ["raw"],
        "eligible_hashes": ["eligible"],
        "retained_hashes": ["retained"],
        "pair_fingerprints": ["pair"],
        "final_pareto": [pair],
        "base_pareto": [pair],
        "base_selection": {"selected_pair_fingerprint": "base"},
        "final_pareto_hash": runner.semantic_hash([pair]),
        "final_v3_fingerprint": selected,
        "final_selection": {
            "selected_pair_fingerprint": selected,
            "classification": "SELECTED" if selected else "DEMAND_FIT_ANCHOR_CONFLICT",
        },
        "statistics": dict.fromkeys(
            (
                "processed_source_count",
                "families_processed",
                "raw_paths_produced",
                "hard_eligible_paths",
                "retained_directional_candidates",
                "pair_cross_products_evaluated",
                "final_frontier_count",
            ),
            1,
        ),
        "source_once": True,
        "hard_valid": True,
        "exact_fleet_valid": True,
        "global_coordinator_executions": 0,
    }
    return {
        "semantic": semantic,
        "semantic_sha256": runner.semantic_hash(semantic),
        "timings": {"total_seconds": 1.0, "max_family_dag_seconds": 0.2},
        "execution": {"pid": pid, "initial_cache_entries": 0},
        "persisted_artifact": {"path": f"/frozen/{pid}/cap{cap}.json", "sha256": str(pid)},
        "input_authority": {"sha256": runner.ROUTE10_SHA256},
        "implementation_authority_sha256": "implementation",
    }


def _evidence_kwargs(*, selected="selected"):
    canonical = _frozen_run(selected=selected)
    runs = {str(cap): _frozen_run(pid=33, cap=cap, selected=selected) for cap in (16, 32, 64)}
    return dict(
        parity={"classification": "U5_EXACT_PRODUCTION_PORT_PARITY"},
        canonical=canonical,
        repeat=_frozen_run(pid=22, selected=selected),
        sensitivity={
            "binding": False,
            "classification": "U6_DIRECTIONAL_FRONTIER_32_CAP_NON_BINDING",
            "canonical_cap32_semantic_sha256": canonical["semantic_sha256"],
            "independent_runs": runs,
            "normalized_union": copy.deepcopy(canonical["semantic"]["final_pareto"]),
            "normalized_union_selection": copy.deepcopy(canonical["semantic"]["final_selection"]),
            "normalized_union_winner_cap32_present": selected is not None,
            "normalized_union_winner_cap64_only": False,
        },
        port={
            "protected_authority_unchanged": True,
            "implementation_authority_sha256": "implementation",
        },
    )


def test_route10_determinism_excludes_timings_but_checks_every_semantic_stage():
    frozen = _frozen_run()
    repeat = _frozen_run(pid=22)
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
    evidence = runner.build_evidence(**_evidence_kwargs())
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


def test_evidence_rejects_sensitivity_from_different_canonical_run():
    kwargs = _evidence_kwargs()
    kwargs["sensitivity"]["canonical_cap32_semantic_sha256"] = "other"
    with pytest.raises(runner.CertificationError, match="U6_ROUTE10_SHADOW_NONDETERMINISTIC"):
        runner.build_evidence(**kwargs)


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
    kwargs = _evidence_kwargs(selected=None)
    evidence = runner.build_evidence(**kwargs, diagnostic_final_selection=True)
    assert evidence["ROUTE 10"]["classification"] == "U6_ROUTE10_FINAL_V3_SELECTION_UNAVAILABLE"
    assert evidence["ROUTE 6"]["state"] == "NOT_RUN_ROUTE10_GATE_FAILED"
    assert not any(evidence["READINESS"].values())
    runner.render_evidence(evidence, tmp_path / "blocked")
    markdown = (tmp_path / "blocked" / runner.EVIDENCE_MD).read_text(encoding="utf-8")
    assert "DEMAND_FIT_ANCHOR_CONFLICT" in markdown
    assert "no selected timetable" in markdown


@pytest.mark.parametrize(
    "filename",
    [
        "clean_boundary_pilot.py",
        "contracts_v1/operational_selection_policy.py",
        "contracts_v1/operational_selection_policy_v2.py",
    ],
)
def test_protected_audit_hashes_actual_fleet_and_selector_dependencies(filename):
    path = "src/bus_schedule_engine/" + filename
    audit = runner.authority_audit(ROOT)
    assert (
        audit["production_file_sha256"].get(path)
        == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    )


@pytest.mark.parametrize(
    "filename",
    [
        "clean_boundary_pilot.py",
        "contracts_v1/operational_selection_policy.py",
        "contracts_v1/operational_selection_policy_v2.py",
    ],
)
def test_protected_audit_rejects_changes_to_actual_dependencies(monkeypatch, filename):
    from types import SimpleNamespace

    path = "src/bus_schedule_engine/" + filename
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda command, **kw: SimpleNamespace(returncode=int(path in command)),
    )
    with pytest.raises(
        runner.CertificationError, match="U6_UNEXPECTED_PRODUCTION_AUTHORITY_CHANGE"
    ):
        runner.authority_audit(ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        "same_object",
        "same_pid",
        "same_artifact_path",
        "same_artifact_hash",
        "canonical_warm_cache",
        "repeat_warm_cache",
        "missing_execution",
        "missing_artifact",
    ],
)
def test_repeat_requires_distinct_artifacts_fresh_process_and_cold_cache(mutation):
    canonical, repeat = _frozen_run(), _frozen_run(pid=22)
    if mutation == "same_object":
        repeat = canonical
    elif mutation == "same_pid":
        repeat["execution"]["pid"] = canonical["execution"]["pid"]
    elif mutation.startswith("same_artifact"):
        field = "path" if mutation.endswith("path") else "sha256"
        repeat["persisted_artifact"][field] = canonical["persisted_artifact"][field]
    elif mutation.endswith("warm_cache"):
        (canonical if mutation.startswith("canonical") else repeat)["execution"][
            "initial_cache_entries"
        ] = 1
    elif mutation == "missing_execution":
        del repeat["execution"]
    else:
        del repeat["persisted_artifact"]
    with pytest.raises(runner.CertificationError, match="U6_ROUTE10_REPEAT_PROVENANCE_INVALID"):
        runner.compare_route10_repeat(canonical, repeat)


def test_read_payload_binds_artifact_identity_and_does_not_trust_embedded_provenance(tmp_path):
    path = tmp_path / "run.json"
    data = runner.canonical_bytes(_frozen_run())
    path.write_bytes(data)
    payload = runner._read_payload(path)
    assert payload["persisted_artifact"] == {
        "path": path.resolve().as_posix(),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    with pytest.raises(runner.CertificationError, match="U6_ROUTE10_REPEAT_PROVENANCE_INVALID"):
        runner.compare_route10_repeat(payload, runner._read_payload(path))


@pytest.mark.parametrize("cap", [16, 32, 64])
@pytest.mark.parametrize(
    "field,value,label",
    [
        ("total_seconds", 301, "U6_ROUTE10_SHADOW_OPERATIONALLY_INTRACTABLE"),
        ("max_family_dag_seconds", 61, "U6_ROUTE10_FAMILY_DAG_OPERATIONALLY_INTRACTABLE"),
        ("global_coordinator_executions", 1, "U6_ROUTE10_GLOBAL_CALL_PROHIBITED"),
        ("source_once", False, "U6_ROUTE10_SOURCE_ONCE_CONTRACT_MISMATCH"),
        ("hard_valid", False, "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH"),
        ("exact_fleet_valid", False, "U6_ROUTE10_EXACT_FLEET_CONTRACT_MISMATCH"),
    ],
)
def test_build_revalidates_every_sensitivity_hard_gate_before_no_selection(
    cap, field, value, label
):
    kwargs = _evidence_kwargs(selected=None)
    case = kwargs["sensitivity"]["independent_runs"][str(cap)]
    case["timings" if field.endswith("seconds") else "semantic"][field] = value
    case["semantic_sha256"] = runner.semantic_hash(case["semantic"])
    for diagnostic in (False, True):
        with pytest.raises(runner.CertificationError, match=label):
            runner.build_evidence(**kwargs, diagnostic_final_selection=diagnostic)


@pytest.mark.parametrize(
    "field",
    [
        "normalized_union",
        "normalized_union_selection",
        "binding",
        "classification",
        "normalized_union_winner_cap32_present",
        "normalized_union_winner_cap64_only",
    ],
)
def test_build_rejects_tampered_sensitivity_summary_before_no_selection(field):
    kwargs = _evidence_kwargs(selected=None)
    summary = kwargs["sensitivity"]
    if field == "normalized_union":
        summary[field] = []
    elif field == "normalized_union_selection":
        summary[field]["selected_pair_fingerprint"] = "invented"
    elif field == "classification":
        summary[field] = "INVENTED"
    else:
        summary[field] = not summary[field]
    for diagnostic in (False, True):
        with pytest.raises(
            runner.CertificationError, match="U6_ROUTE10_SENSITIVITY_AUTHORITY_MISMATCH"
        ):
            runner.build_evidence(**kwargs, diagnostic_final_selection=diagnostic)


def test_nondeterministic_repeat_precedes_provisional_no_selection():
    kwargs = _evidence_kwargs(selected=None)
    kwargs["repeat"]["semantic"]["raw_hashes"] = ["different"]
    kwargs["repeat"]["semantic_sha256"] = runner.semantic_hash(kwargs["repeat"]["semantic"])
    with pytest.raises(runner.CertificationError, match="U6_ROUTE10_SHADOW_NONDETERMINISTIC"):
        runner.build_evidence(**kwargs)


def test_content_bound_cap_binding_precedes_no_selection():
    kwargs = _evidence_kwargs(selected=None)
    case64 = kwargs["sensitivity"]["independent_runs"]["64"]
    pair = {"fingerprint": "winner64", "pareto_vector": [0, 1]}
    case64["semantic"].update(
        final_pareto=[pair],
        final_pareto_hash=runner.semantic_hash([pair]),
        final_v3_fingerprint="winner64",
        final_selection={"selected_pair_fingerprint": "winner64", "classification": "SELECTED"},
    )
    case64["semantic_sha256"] = runner.semantic_hash(case64["semantic"])
    kwargs["sensitivity"].update(
        binding=True,
        classification="U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING",
        normalized_union=[pair],
        normalized_union_selection=case64["semantic"]["final_selection"],
        normalized_union_winner_cap64_only=True,
    )
    with pytest.raises(runner.CertificationError, match="U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING"):
        runner.build_evidence(**kwargs)
    evidence = runner.build_evidence(**kwargs, diagnostic_final_selection=True)
    assert evidence["ROUTE 10"]["classification"] == "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING"


def test_render_revalidates_payloads_instead_of_trusting_built_evidence(tmp_path):
    evidence = runner.build_evidence(
        **_evidence_kwargs(selected=None), diagnostic_final_selection=True
    )
    evidence["ROUTE 10"]["sensitivity"]["independent_runs"]["64"]["timings"]["total_seconds"] = 301
    with pytest.raises(
        runner.CertificationError, match="U6_ROUTE10_SHADOW_OPERATIONALLY_INTRACTABLE"
    ):
        runner.render_evidence(evidence, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize(
    "mutation,label",
    [
        ("repeat_input", "U6_ROUTE10_SAVED_BASE_AUTHORITY_MISMATCH"),
        ("repeat_implementation", "U6_UNEXPECTED_PRODUCTION_AUTHORITY_CHANGE"),
        ("canonical_implementation", "U6_UNEXPECTED_PRODUCTION_AUTHORITY_CHANGE"),
        ("hidden_family_ceiling", "U6_ROUTE10_FAMILY_DAG_OPERATIONALLY_INTRACTABLE"),
        ("hidden_global", "U6_ROUTE10_GLOBAL_CALL_PROHIBITED"),
        ("duplicate_source", "U6_ROUTE10_SOURCE_ONCE_CONTRACT_MISMATCH"),
        ("structural_reject", "U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH"),
    ],
)
def test_nested_authority_and_hard_gates_cannot_hide_behind_selection_blocker(mutation, label):
    kwargs = _evidence_kwargs(selected=None)
    cap64 = kwargs["sensitivity"]["independent_runs"]["64"]
    if mutation == "repeat_input":
        kwargs["repeat"]["input_authority"] = {"sha256": "other"}
    elif mutation.endswith("implementation"):
        kwargs[mutation.split("_")[0]]["implementation_authority_sha256"] = "other"
    elif mutation == "hidden_family_ceiling":
        cap64["timings"]["families"] = [{"dag": {"total_seconds": 61}}]
    elif mutation == "hidden_global":
        cap64["timings"]["global_coordinator_executions"] = 1
    elif mutation == "duplicate_source":
        cap64["semantic"]["processed_source_order"] *= 2
    else:
        cap64["semantic"]["statistics"]["structural_rejects"] = 1
    cap64["semantic_sha256"] = runner.semantic_hash(cap64["semantic"])
    with pytest.raises(runner.CertificationError, match=label):
        runner.build_evidence(**kwargs)


def test_saved_repeat_is_still_accepted_without_running_a_route_stage(monkeypatch):
    from bus_schedule_engine import kbest_shadow_refinement as shadow

    monkeypatch.setattr(
        shadow,
        "run_kbest_dag_shadow_from_completed_result_v1",
        lambda **kw: pytest.fail("route stage rerun"),
    )
    scratch = ROOT.parent / "pr62-u6-runs"
    canonical = runner._read_payload(scratch / "task7-route10-canonical-20260909-01/cap32.json")
    repeat = runner._read_payload(scratch / "task7-route10-repeat-20260909-01/cap32.json")
    result = runner.compare_route10_repeat(canonical, repeat)
    assert result["identical"] and result["fresh_process"] and result["cold_initial_caches"]
    assert result["canonical_pid"] == 10176 and result["repeat_pid"] == 29540


def test_novel_union_without_saved_selector_authority_fails_closed():
    kwargs = _evidence_kwargs()
    cap64 = kwargs["sensitivity"]["independent_runs"]["64"]
    pair = {"fingerprint": "other", "pareto_vector": [0, 3]}
    cap64["semantic"].update(
        final_pareto=[pair],
        final_pareto_hash=runner.semantic_hash([pair]),
        final_v3_fingerprint="other",
        final_selection={"selected_pair_fingerprint": "other", "classification": "SELECTED"},
    )
    cap64["semantic_sha256"] = runner.semantic_hash(cap64["semantic"])
    kwargs["sensitivity"]["normalized_union"] = [
        pair,
        kwargs["canonical"]["semantic"]["final_pareto"][0],
    ]
    with pytest.raises(
        runner.CertificationError, match="U6_ROUTE10_UNION_SELECTION_AUTHORITY_UNAVAILABLE"
    ):
        runner.build_evidence(**kwargs)

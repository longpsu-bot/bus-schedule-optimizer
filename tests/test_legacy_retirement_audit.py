from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bus_schedule_engine.legacy_retirement_evidence import (
    EVIDENCE_PROFILE_V1,
    verify_evidence_fingerprint_v1,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "45b49791b1be734b89271e5700e8eeeb64deb2d4"
EVIDENCE_PATH = (
    ROOT / "docs" / "engine" / "evidence" / "M5C2R_LEGACY_RUNTIME_RETIREMENT_EVIDENCE_45B49791.json"
)
EVIDENCE_FILE_SHA256 = "fe972418873dc8b141561b9fe0719b549efc087b977c61395bcb65570f475045"
REPORT_FINGERPRINT = "2ab6efe216bfd7c3e6341fb29a1b459d739ac72a9e84e42816887e86bcbd417b"
RELEASE_AUDIT_BASELINE_SOURCE_SHA256 = (
    "97304e3bdebfb9b255269c28dab0bdc396c06b80788da5c5bbd4e85fd790e283"
)


@pytest.fixture(scope="module")
def archived_payload() -> dict[str, object]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_archived_m5c2r_evidence_is_bound_to_the_merged_baseline(
    archived_payload: dict[str, object],
) -> None:
    assert archived_payload["evidence_profile"] == EVIDENCE_PROFILE_V1
    assert archived_payload["audited_head_commit"] == BASELINE_COMMIT
    assert archived_payload["audited_target_commit"] == BASELINE_COMMIT
    assert archived_payload["target_commit_matches_head"] is True
    assert archived_payload["implementation_conclusion"] == "READY_FOR_FORMAL_APPROVAL"
    assert archived_payload["blocker_codes"] == []


def test_archived_m5c2r_fingerprint_verifies_and_detects_tampering(
    archived_payload: dict[str, object],
) -> None:
    assert archived_payload["report_fingerprint"] == REPORT_FINGERPRINT
    assert verify_evidence_fingerprint_v1(archived_payload)

    tampered = {**archived_payload, "implementation_conclusion": "BLOCKED"}
    assert not verify_evidence_fingerprint_v1(tampered)


def test_archived_m5c2r_file_bytes_are_unchanged() -> None:
    assert hashlib.sha256(EVIDENCE_PATH.read_bytes()).hexdigest() == EVIDENCE_FILE_SHA256


def test_archived_m5c2r_preserves_historical_pending_approval_truth(
    archived_payload: dict[str, object],
) -> None:
    assert archived_payload["production_approval_status"] == "PENDING"
    signoffs = archived_payload["required_human_signoffs"]
    assert {item["role"] for item in signoffs} == {
        "Engineering Owner",
        "QA/Release Owner",
    }
    assert all(item["status"] == "PENDING" for item in signoffs)
    assert archived_payload["warning_codes"] == [
        "M5C2R_APPROVER_IDENTITIES_PENDING",
        "M5C2R_PRODUCTION_APPROVAL_PENDING",
        "M5C2R_ROLLBACK_REHEARSAL_CONFIRMATION_PENDING",
    ]


def test_archived_m5c2r_records_the_authorized_candidate_and_retained_boundaries(
    archived_payload: dict[str, object],
) -> None:
    candidates = set(archived_payload["proposed_5c3_deletion_candidates"])
    retained = set(archived_payload["required_shared_dependencies"])

    assert "src/bus_schedule_engine/diagram.py::<module>" in candidates
    assert "src/bus_schedule_engine/comparison_exporter.py::<module>" in candidates
    assert "src/bus_schedule_engine/service.py::run_analysis" not in candidates
    assert "src/bus_schedule_engine/c_generator.py::generate_scenario_c" in retained
    assert "src/bus_schedule_engine/demand.py::evaluate_scenario" in retained
    assert candidates.isdisjoint(retained)


def test_release_audit_source_remains_unchanged() -> None:
    source = (ROOT / "src" / "bus_schedule_engine" / "release_audit.py").read_text(encoding="utf-8")

    normalized = source.replace("\r\n", "\n").encode("utf-8")
    assert hashlib.sha256(normalized).hexdigest() == RELEASE_AUDIT_BASELINE_SOURCE_SHA256

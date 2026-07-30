"""Explicit offline legacy-versus-Contract-V1 release audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from .application_pipeline import (
    WORKBOOK_IMPORT_INVALID,
    WORKBOOK_OPTIMIZATION_NOT_READY,
    sanitize_import_error_message_v1,
)
from .importer import import_workbook
from .input_authority import (
    assess_workbook_input_readiness_v1,
    normalization_options_from_workbook_v1,
)
from .optimization_service import SolverChoice
from .side_by_side_validation import run_side_by_side_validation_v1

RELEASE_AUDIT_SCHEMA_V1 = "BUS_SCHEDULE_RELEASE_AUDIT_V1"
RELEASE_AUDIT_PASSED = "RELEASE_AUDIT_PASSED"
RELEASE_AUDIT_BLOCKED = "RELEASE_AUDIT_BLOCKED"
_DETERMINISTIC_IMPORTED_AT = datetime(2000, 1, 1, tzinfo=UTC)


def _write_report(output: Path, payload: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _base_payload(
    *,
    source_sha256: str,
    solver_choice: SolverChoice,
) -> dict[str, object]:
    return {
        "schema": RELEASE_AUDIT_SCHEMA_V1,
        "source_sha256": source_sha256,
        "source_id": f"release-audit-sha256:{source_sha256}",
        "solver_choice": solver_choice.value,
    }


def run_release_audit_v1(
    workbook: Path,
    *,
    solver_choice: SolverChoice,
    output: Path,
) -> int:
    """Run the offline oracle and write a bounded deterministic JSON report."""
    workbook_bytes = workbook.read_bytes()
    source_sha256 = hashlib.sha256(workbook_bytes).hexdigest()
    payload = _base_payload(
        source_sha256=source_sha256,
        solver_choice=solver_choice,
    )
    try:
        imported = import_workbook(workbook_bytes)
    except Exception as exc:
        payload.update(
            {
                "status": WORKBOOK_IMPORT_INVALID,
                "sanitized_message": sanitize_import_error_message_v1(exc),
            }
        )
        _write_report(output, payload)
        return 2

    readiness = assess_workbook_input_readiness_v1(imported)
    readiness_payload = {
        "import_ready": readiness.import_ready,
        "optimization_ready": readiness.optimization_ready,
        "blocking_import_codes": list(readiness.blocking_import_codes),
        "missing_optimization_authority_codes": list(
            readiness.missing_optimization_authority_codes
        ),
        "optional_limitations": list(readiness.optional_limitations),
    }
    payload["input_readiness"] = readiness_payload
    if not readiness.optimization_ready:
        payload["status"] = WORKBOOK_OPTIMIZATION_NOT_READY
        _write_report(output, payload)
        return 2

    source_id = str(payload["source_id"])
    options = normalization_options_from_workbook_v1(
        imported,
        source_id=source_id,
        imported_at=_DETERMINISTIC_IMPORTED_AT,
    )
    report = run_side_by_side_validation_v1(
        imported,
        options,
        solver_choice=solver_choice,
    )
    unified = report.unified_snapshot
    payload.update(
        {
            "status": (
                RELEASE_AUDIT_BLOCKED if report.has_blocking_discrepancies else RELEASE_AUDIT_PASSED
            ),
            "blocking_discrepancy_codes": list(report.blocking_discrepancy_codes),
            "expert_review_required_codes": list(report.expert_review_required_codes),
            "informational_codes": list(report.informational_codes),
            "normalized_scenario_b_fingerprint": (unified.normalized_scenario_b_fingerprint),
            "accepted_solution_fingerprint": unified.solution_fingerprint,
            "comparisons": [
                {
                    "fact_code": comparison.fact_code,
                    "category": comparison.category.value,
                    "comparison_rule": comparison.comparison_rule.value,
                    "comparison_status": comparison.comparison_status.value,
                    "disposition": comparison.disposition.value,
                    "reason_code": comparison.reason_code,
                }
                for comparison in report.comparisons
            ],
        }
    )
    _write_report(output, payload)
    return 1 if report.has_blocking_discrepancies else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the offline Contract V1 side-by-side release audit."
    )
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument(
        "--solver",
        default=SolverChoice.HEURISTIC.value,
        choices=tuple(choice.value for choice in SolverChoice),
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return run_release_audit_v1(
        args.workbook,
        solver_choice=SolverChoice(args.solver),
        output=args.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "RELEASE_AUDIT_BLOCKED",
    "RELEASE_AUDIT_PASSED",
    "RELEASE_AUDIT_SCHEMA_V1",
    "main",
    "run_release_audit_v1",
]

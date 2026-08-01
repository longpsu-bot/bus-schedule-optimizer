"""Command-line entry point for the Milestone 5C2R repository audit."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .legacy_retirement_evidence import (
    ImplementationConclusionV1,
    build_legacy_retirement_evidence_v1,
    evidence_to_json_v1,
)


def run_legacy_retirement_audit_v1(
    repo_root: Path,
    *,
    target_commit: str,
    output: Path,
) -> int:
    """Audit the checkout, write deterministic JSON, and return the gate status."""
    report = build_legacy_retirement_evidence_v1(
        repo_root,
        target_commit=target_commit,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        evidence_to_json_v1(report),
        encoding="utf-8",
        newline="\n",
    )
    return (
        0
        if report.implementation_conclusion == ImplementationConclusionV1.READY_FOR_FORMAL_APPROVAL
        else 1
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic Milestone 5C2R legacy-retirement approval evidence."
    )
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Checkout to inspect; defaults to the current working directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return run_legacy_retirement_audit_v1(
        args.repo_root,
        target_commit=args.target_commit,
        output=args.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_legacy_retirement_audit_v1"]

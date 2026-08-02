"""CLI for one-workbook Milestone 6A2E operational review."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .operational_review import (
    EXPERT_REVIEW_REQUIRED,
    create_operational_review_package_v1,
    write_operational_review_package_v1,
)
from .optimization_service import SolverChoice


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one external workbook through the unified Contract V1 pipeline and write a "
            "bounded expert-review package."
        )
    )
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--solver",
        required=True,
        choices=tuple(item.value for item in SolverChoice),
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        package = create_operational_review_package_v1(
            args.workbook,
            source_id=args.source_id,
            solver_choice=SolverChoice(args.solver),
        )
        written = write_operational_review_package_v1(
            package,
            args.output_dir,
            overwrite=args.overwrite,
        )
    except Exception:
        print("REVIEW_SERIALIZATION_OR_INTEGRITY_FAILURE")
        return 5
    print(EXPERT_REVIEW_REQUIRED)
    print(f"pipeline_status={package.review.pipeline_status.value}")
    print(f"review_disposition={package.review.review_disposition.value}")
    print(f"review_fingerprint={package.review.review_fingerprint}")
    print("files=" + ",".join(path.name for path in written))
    return package.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline CLI for Milestone 6A2F layered data-authority review."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .partial_timetable_review import (
    create_data_authority_review_package_v1,
    write_data_authority_review_package_v1,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Review one exact timetable and its layered data authority without calling a solver."
        )
    )
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        package = create_data_authority_review_package_v1(
            args.workbook,
            source_id=args.source_id,
        )
        written = write_data_authority_review_package_v1(
            package,
            args.output_dir,
            overwrite=args.overwrite,
        )
    except Exception:
        print("DATA_AUTHORITY_REVIEW_SERIALIZATION_OR_INTEGRITY_FAILURE")
        return 5
    print(f"review_status={package.review.review_status.value}")
    print(f"review_fingerprint={package.review.review_fingerprint}")
    print("files=" + ",".join(path.name for path in written))
    return package.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

"""Review frozen Route 10 chains; never run timetable optimization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bus_schedule_engine.mvp.route10_crew_review import run_review  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="SHA-verified private workbook")
    parser.add_argument(
        "--evidence", type=Path, required=True, help="Existing MVP-6A fleet_report.json"
    )
    parser.add_argument("--evidence-sha256", help="Optional expected digest of the frozen JSON")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--policies",
        type=Path,
        help="Named explicit profiles; absent uses illustrative sensitivities",
    )
    parser.add_argument(
        "--operating-date", help="Operator-supplied YYYY-MM-DD; absent remains unknown"
    )
    args = parser.parse_args(argv)
    try:
        profiles = json.loads(args.policies.read_text(encoding="utf-8")) if args.policies else None
        if args.policies and not isinstance(profiles, dict):
            raise ValueError("policy file must contain an object of named profiles")
        report = run_review(
            args.input,
            args.evidence,
            args.output_dir,
            policies=profiles,
            operating_date=args.operating_date,
            evidence_sha256=args.evidence_sha256,
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Crew review failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps({"status": report["status"], "output_dir": str(args.output_dir)}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

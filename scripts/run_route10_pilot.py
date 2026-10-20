"""Run the SHA-verified Route 10 common-runtime control and engine pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bus_schedule_engine.mvp.route10_pilot import run_pilot  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--joint", action="store_true", help="Run MVP-5B plus unchanged MVP-5A control"
    )
    parser.add_argument(
        "--pairs-per-plan",
        type=int,
        choices=(6, 16),
        help="Joint experiment pair allocation (default: 16; requires --joint)",
    )
    parser.add_argument(
        "--fleet-guided", action="store_true", help="Run MVP-6A against the frozen six-pair control"
    )
    args = parser.parse_args(argv)
    if args.fleet_guided and (not args.joint or args.pairs_per_plan != 6):
        parser.error("--fleet-guided requires --joint and --pairs-per-plan 6")
    if args.pairs_per_plan is not None and not args.joint:
        parser.error("--pairs-per-plan requires --joint")
    try:
        if args.fleet_guided:
            from bus_schedule_engine.mvp.route10_fleet_pilot import run_fleet_pilot

            report = run_fleet_pilot(args.input, args.output_dir)
        elif args.joint:
            from bus_schedule_engine.mvp.route10_joint_pilot import run_joint_pilot

            report = run_joint_pilot(
                args.input, args.output_dir, pairs_per_plan=args.pairs_per_plan or 16
            )
        else:
            report = run_pilot(args.input, args.output_dir)
    except (OSError, ValueError, KeyError) as error:
        print(f"Route 10 pilot failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "outcomes": {r["id"]: r["outcome"] for r in report["scenarios"]},
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

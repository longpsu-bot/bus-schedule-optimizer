"""Run only the approved Route 10 Phase 1/2 terminal-only deployment pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bus_schedule_engine.mvp.peak_offpeak_pilot import run_pilot  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        help="Explicit experimental policy JSON; defaults to approved pilot parameters",
    )
    args = parser.parse_args(argv)
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8")) if args.policy else None
        result = run_pilot(
            args.input, args.evidence, args.output_dir, policy=policy, policy_source=args.policy
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Peak/off-peak pilot failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            dict(
                status=result["status"],
                selection=result["selection"],
                output_dir=str(args.output_dir),
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

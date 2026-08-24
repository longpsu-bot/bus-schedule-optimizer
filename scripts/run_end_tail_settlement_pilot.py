"""Run the Route 6/10 tail-aware end-settlement pilot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bus_schedule_engine.end_tail_pilot import (  # noqa: E402
    compact_end_tail_summary_v2,
    run_end_tail_pilot_v2,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Allocate Route 6/10 core DemandRegimes, settle residual trips in a "
            "backward fixed-last tail, then rerun the unchanged fleet validator."
        )
    )
    parser.add_argument(
        "--route-6-workbook",
        type=Path,
        default=_REPO_ROOT.parent / "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    parser.add_argument(
        "--route-10-workbook",
        type=Path,
        default=_REPO_ROOT.parent / "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=_REPO_ROOT / "outputs" / "end_tail_settlement_v3",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = run_end_tail_pilot_v2(
        repo_root=_REPO_ROOT,
        route_workbooks={
            "6": args.route_6_workbook,
            "10": args.route_10_workbook,
        },
        output_directory=args.output_directory,
    )
    print(compact_end_tail_summary_v2(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

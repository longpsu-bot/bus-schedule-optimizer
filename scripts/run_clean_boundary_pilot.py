"""Recompile and validate the Route 6/10 clean-boundary Scenario C pilot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bus_schedule_engine.clean_boundary_pilot import (  # noqa: E402
    compact_pilot_summary_v1,
    run_clean_boundary_pilot_v1,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compile frozen Route 6/10 C1-C3 allocations with fixed endpoints and clean "
            "ServiceRegime boundaries, then rerun fleet validation and final selection."
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
        default=_REPO_ROOT / "outputs" / "final_scenario_c_clean_boundaries_v2",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = run_clean_boundary_pilot_v1(
        repo_root=_REPO_ROOT,
        route_workbooks={
            "6": args.route_6_workbook,
            "10": args.route_10_workbook,
        },
        output_directory=args.output_directory,
    )
    print(compact_pilot_summary_v1(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

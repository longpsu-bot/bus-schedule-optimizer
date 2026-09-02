"""Run the review-only closed-loop ServicePlan coordinator for Routes 6 and 10."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bus_schedule_engine.service_plan_coordinator import (  # noqa: E402
    CoordinatorSearchBudgetV1,
    run_service_plan_coordinator_pilot_v1,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search a bounded closed-loop ServicePlan Pareto frontier for Routes 6/10."
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
        default=_REPO_ROOT / "outputs" / "service_plan_coordinator_v1",
    )
    parser.add_argument("--max-service-plan-evaluations", type=int, default=24)
    parser.add_argument("--max-open-states", type=int, default=512)
    parser.add_argument("--max-compile-frontier-per-state", type=int, default=4)
    parser.add_argument("--max-directional-compilations", type=int, default=24)
    parser.add_argument("--max-pair-frontier", type=int, default=512)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    budget = CoordinatorSearchBudgetV1(
        max_service_plan_evaluations=args.max_service_plan_evaluations,
        max_open_states=args.max_open_states,
        max_compile_frontier_per_state=args.max_compile_frontier_per_state,
        max_directional_compilations=args.max_directional_compilations,
        max_pair_frontier=args.max_pair_frontier,
    )
    payload = run_service_plan_coordinator_pilot_v1(
        repo_root=_REPO_ROOT,
        route_workbooks={
            "6": args.route_6_workbook,
            "10": args.route_10_workbook,
        },
        output_directory=args.output_directory,
        budget=budget,
    )
    for route in payload["routes"]:
        stats = route["search_statistics"]
        print(
            f"route={route['route_id']} status={route['status']} "
            f"states={stats['states_evaluated']} compile={stats['compile_variants_evaluated']} "
            f"fleet={stats['fleet_validations_run']} pareto={len(route['pareto_frontier'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

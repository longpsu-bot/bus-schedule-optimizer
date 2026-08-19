"""Run the explicit V3 multi-period two-stage workflow from one local workbook."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bus_schedule_engine.contracts_v1.v3_global_regularity import (  # noqa: E402
    BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1,
    CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1,
    GLOBAL_REGULARITY_POLICY_PROFILE_V1,
    install_global_regularity_v1,
    uninstall_global_regularity_v1,
)
from bus_schedule_engine.v3_result_exporter import (  # noqa: E402
    build_profile_comparison_v1,
    export_profile_comparison_xlsx_v1,
    export_v3_result_xlsx_v1,
)
from bus_schedule_engine.v3_runner import (  # noqa: E402
    DEFAULT_V3_TOTAL_SOLVE_BUDGET_SECONDS,
    run_v3_profile_v1,
    write_deterministic_json,
)
from bus_schedule_engine.v3_workbook import (  # noqa: E402
    import_v3_multi_period_workbook_v1,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run B_ANCHORED_TWO_STAGE_REBALANCE_V1 with native multi-period demand.",
    )
    parser.add_argument("--input", required=True, type=Path, help="V3 input workbook")
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument("--profile", help="one explicit demand profile")
    profiles.add_argument("--profiles", help="comma-separated independent profile runs")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--solve-budget-seconds",
        type=float,
        default=DEFAULT_V3_TOTAL_SOLVE_BUDGET_SECONDS,
        help="per-profile total Stage 1 + Stage 2 budget; maximum 120 seconds",
    )
    parser.add_argument(
        "--shape-distance-threshold",
        type=float,
        default=0.15,
        help="bounded L1/2 period-shape warning threshold",
    )
    return parser


def _selected_profiles(args: argparse.Namespace) -> tuple[tuple[str, ...], bool]:
    if args.profiles:
        selected = tuple(item.strip() for item in args.profiles.split(",") if item.strip())
        if not selected:
            raise ValueError("--profiles must contain at least one profile_id")
        if len(set(selected)) != len(selected):
            raise ValueError("--profiles must not repeat a profile_id")
        return selected, True
    if args.profile:
        return (args.profile.strip(),), False
    imported = import_v3_multi_period_workbook_v1(args.input)
    default = imported.multi_period_demand.default_profile_id
    if default is None or not default.strip():
        raise ValueError(
            "--profile was omitted and THONG_TIN_DU_LIEU has no valid default_demand_profile"
        )
    return (default,), False


def _with_global_regularity_metadata(run):
    payload = dict(run.payload)
    payload["global_regularity_policy"] = {
        "profile": GLOBAL_REGULARITY_POLICY_PROFILE_V1,
        "block_phase_max_deviation_trips": BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1,
        "cumulative_phase_max_deviation_trips": CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1,
        "regime_count_semantics": "HARD_MAXIMUM_WITH_REPRESENTABLE_FIXED_POINT_COARSENING",
        "surplus_allocation": "PASSENGER_PROPORTIONAL_LARGEST_REMAINDER",
        "transition_authority": "NOT_WORSE_THAN_SCENARIO_B",
        "declining_tail_authority": "FINAL_HEADWAY_NOT_SHORTER_THAN_PREVIOUS",
    }
    return replace(run, payload=payload)


def _run(args: argparse.Namespace) -> None:
    input_path = args.input.expanduser().resolve()
    output_root = args.output_dir.expanduser().resolve()
    selected_profiles, batch_mode = _selected_profiles(args)
    runs = []
    for profile_id in selected_profiles:
        run = run_v3_profile_v1(
            input_path,
            profile_id,
            total_budget_seconds=args.solve_budget_seconds,
            shape_distance_threshold=args.shape_distance_threshold,
        )
        run = _with_global_regularity_metadata(run)
        profile_output = output_root / profile_id if batch_mode else output_root
        write_deterministic_json(profile_output / "result.json", run.payload)
        export_v3_result_xlsx_v1(run, profile_output / "result.xlsx")
        runs.append(run)
        print(
            f"{profile_id}: {run.payload['aggregate_native_status']} / "
            f"{run.payload['final_acceptance_state']} / "
            f"global_regularity={GLOBAL_REGULARITY_POLICY_PROFILE_V1} -> {profile_output}"
        )
    if batch_mode:
        comparison = build_profile_comparison_v1(runs)
        write_deterministic_json(output_root / "profile_comparison.json", comparison)
        export_profile_comparison_xlsx_v1(
            comparison,
            output_root / "profile_comparison.xlsx",
        )
        comparison_state = (
            comparison["stability_classification"]
            or comparison["review_code"]
            or comparison["comparison_eligibility"]
        )
        print(f"profile comparison: {comparison['comparison_eligibility']} / {comparison_state}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    install_global_regularity_v1()
    try:
        try:
            _run(args)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"V3 runner failed: {exc}", file=sys.stderr)
            return 2
        return 0
    finally:
        uninstall_global_regularity_v1()


if __name__ == "__main__":
    raise SystemExit(main())

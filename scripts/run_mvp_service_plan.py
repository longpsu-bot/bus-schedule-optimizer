"""Compile one independent route bundle or V3 workbook into operator-reviewable outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bus_schedule_engine.mvp.input import bundle_from_workbook  # noqa: E402
from bus_schedule_engine.mvp.runner import export_result, run_bundle  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="normalized JSON route bundle or V3 XLSX workbook"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--settings", type=Path, help="JSON settings overrides")
    parser.add_argument("--profile")
    parser.add_argument("--minimum-layover", type=int)
    parser.add_argument("--maximum-load-factor", type=float)
    parser.add_argument(
        "--capacity-policy", choices=("hard", "evaluation_only"), default="evaluation_only"
    )
    parser.add_argument(
        "--constraints",
        type=Path,
        help="explicit JSON protected_windows/initial_vehicles overrides for workbook inputs",
    )
    args = parser.parse_args(argv)
    started = monotonic()
    try:
        settings = json.loads(args.settings.read_text(encoding="utf-8")) if args.settings else None
        if args.input.suffix.lower() == ".json":
            if (
                args.constraints
                or args.minimum_layover is not None
                or args.maximum_load_factor is not None
                or args.profile
            ):
                raise ValueError(
                    "JSON bundles contain their own authorities; workbook-only overrides were supplied"
                )
            data = json.loads(args.input.read_text(encoding="utf-8"))
        else:
            data = bundle_from_workbook(
                args.input,
                profile=args.profile,
                minimum_layover=args.minimum_layover,
                maximum_load_factor=args.maximum_load_factor,
                capacity_policy=args.capacity_policy,
            )
            if args.constraints:
                constraints = json.loads(args.constraints.read_text(encoding="utf-8"))
                if set(constraints) - {"protected_windows", "initial_vehicles"}:
                    raise ValueError(
                        "constraints supports only protected_windows and initial_vehicles"
                    )
                if "initial_vehicles" in constraints:
                    data["initial_vehicles"] = constraints["initial_vehicles"]
                if "protected_windows" in constraints:
                    for d, windows in constraints["protected_windows"].items():
                        data["directions"][d]["protected_windows"] = windows
                data["provenance"]["protection_source"] = args.constraints.name
        result = run_bundle(data, settings)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {
            "status": "BLOCKED_INPUT",
            "recommended": None,
            "alternatives": [],
            "diagnostics": {"input_error": str(exc), "evaluations": 0},
        }
    export_result(result, args.output_dir)
    print(f"{result['status']} -> {args.output_dir}")
    print(
        f"source={result.get('selected_source')}, search={result.get('search_status')}, runtime_seconds={monotonic() - started:.3f}"
    )
    if result["recommended"]:
        q = result["recommended"]["quality"]
        print(
            f"fleet={q['required_fleet']}, modeled_wait={q['waiting_minutes']}, regimes={q['regime_count']}"
        )
    return 0 if result["recommended"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

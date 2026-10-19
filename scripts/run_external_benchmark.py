"""Appraise an eight-sheet external timetable report without KH/HT or optimization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bus_schedule_engine.mvp.external_benchmark import (  # noqa: E402
    build_external_benchmark,
    export_external_benchmark,
)
from bus_schedule_engine.mvp.external_import import import_external_workbook  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--minimum-layover-scenario",
        type=float,
        help="explicit assumption in minutes; no authoritative minimum is inferred",
    )
    parser.add_argument(
        "--comparison", type=Path, help="JSON actual C departures and explicit evaluation context"
    )
    parser.add_argument(
        "--benchmark-context",
        type=Path,
        help="JSON common-context declaration; required before three-way ranking",
    )
    args = parser.parse_args(argv)
    try:
        data = import_external_workbook(args.input)
        comparison = (
            json.loads(args.comparison.read_text(encoding="utf-8")) if args.comparison else None
        )
        context = (
            json.loads(args.benchmark_context.read_text(encoding="utf-8"))
            if args.benchmark_context
            else None
        )
        report = build_external_benchmark(
            data,
            minimum_layover=args.minimum_layover_scenario,
            comparison=comparison,
            context=context,
        )
        export_external_benchmark(data, report, args.output_dir)
    except (OSError, ValueError, KeyError) as error:
        print(f"External benchmark failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"status": report["readiness"], "output_dir": str(args.output_dir)}, ensure_ascii=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

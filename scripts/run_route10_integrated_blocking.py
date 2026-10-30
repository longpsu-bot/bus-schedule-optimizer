"""Four approved P0 experiments; no timetable compiler, PR operation or production feedback."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from bus_schedule_engine.mvp.integrated_blocking import solve_integrated
from bus_schedule_engine.mvp.integrated_blocking_report import export_reports
from bus_schedule_engine.mvp.route10_integrated_blocking import route10_requests


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    sources = {args.input.resolve(), args.evidence.resolve()}
    targets = {args.output_dir.resolve()} | {
        (args.output_dir / name).resolve()
        for name in (
            "integrated_vehicle_crew_v1.xlsx",
            "integrated_vehicle_crew_v1.json",
            "summary.json",
        )
    }
    checkpoints = {
        args.output_dir / f"{runtime}_{duty}.checkpoint.json"
        for runtime in ("p50", "p75")
        for duty in (480, 600)
    }
    targets |= {path.resolve() for path in checkpoints}
    targets |= {path.with_suffix(path.suffix + ".tmp").resolve() for path in checkpoints}
    if sources & targets or any(
        source.exists() and target.exists() and source.samefile(target)
        for source in sources
        for target in targets
    ):
        raise ValueError("output/source collision")
    began = perf_counter()
    requests = route10_requests(args.input, args.evidence)
    cases = []
    for r in requests:
        name = f"{r['runtime_scenario']['id']}_{r['crew_policy']['duty']['limit']}"
        result = solve_integrated(
            r,
            checkpoint=args.output_dir / (name + ".checkpoint.json"),
            cancelled=lambda: perf_counter() - began >= 300,
        )
        cases.append((r, result))
        print(
            json.dumps(
                dict(
                    case=name,
                    status=result["status"],
                    lower=result["lower_bound"],
                    upper=result["upper_bound"],
                    seconds=result["wall_seconds"],
                )
            ),
            flush=True,
        )
    paths = export_reports(cases, args.output_dir)
    status = (
        "INTEGRATED_BLOCKING_VALIDATED"
        if all(res["status"] == "OPTIMAL_PROVEN" for _, res in cases)
        else "FEASIBLE_BUT_UNPROVED"
        if all(res["validator_pass"] for _, res in cases)
        else "IMPLEMENTATION_PARTIAL"
    )
    summary = dict(
        status=status,
        wall_seconds=perf_counter() - began,
        outputs=paths,
        cases=[
            dict(
                case=f"{r['runtime_scenario']['id']}_{r['crew_policy']['duty']['limit']}",
                status=res["status"],
                lower_bound=res["lower_bound"],
                upper_bound=res["upper_bound"],
                wall_seconds=res["wall_seconds"],
                initial_vehicles_required=res["validation"]["initial_vehicles_required"]
                if res["validation"]
                else None,
            )
            for r, res in cases
        ],
    )
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded V1.1 experiment on saved, independently validated P0 requests.

No production entrypoint imports this observer. Relaxations are diagnostic only.
Full requests, witnesses and traces stay in the ignored output directory.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ortools.sat.python import cp_model

from bus_schedule_engine.mvp import integrated_blocking
from bus_schedule_engine.mvp.input import runtime_at
from bus_schedule_engine.mvp.integrated_blocking_validation import digest, validate_assignment
from bus_schedule_engine.mvp.route10_integrated_blocking import DEPARTURE_SHA256

BASE_SHA = "98427b194d63a077f3e3ca7ac6e3d73cf98cf93f"
OFF = "DISABLED_EXPERIMENTAL"


def reset_workload_certificate(request):
    """Analytical necessary bound only; never supplied to the CP-SAT model.

    A driving segment holds at most floor(C/min_runtime) trips. If S segments
    are necessary, K duties need at least S-K distinct protected resets.
    Sum elapsed duties >= W+n(q+h+p)-qK+reset*(S-K).
    """
    crew = request["crew_policy"]
    if any(crew[key]["mode"] != "ENFORCED" for key in ("duty", "driving")):
        return None
    runtimes = [
        runtime_at(
            {"runtime_periods": request["runtime_scenario"]["directions"][t["direction"]]},
            t["departure"],
        )
        for t in request["timetable"]["trips"]
    ]
    per_segment = crew["driving"]["limit"] // min(runtimes)
    if per_segment == 0:
        return None
    n, workload = len(runtimes), sum(runtimes)
    segments = (n + per_segment - 1) // per_segment
    reset = crew["driving"]["reset_minutes"]
    tasks = request["terminal_policy"]
    numerator = workload + n * sum(tasks.values()) + reset * segments
    denominator = crew["duty"]["limit"] + tasks["technical"] + reset
    return dict(
        trip_count=n,
        driving_workload=workload,
        minimum_trip_runtime=min(runtimes),
        maximum_trips_per_driving_segment=per_segment,
        minimum_driving_segments=segments,
        reset_minutes=reset,
        numerator=numerator,
        denominator=denominator,
        lower_bound=(numerator + denominator - 1) // denominator,
        scope="analytical necessary bound under this request; not a solver bound",
    )


def metrics(result):
    checked = result["validation"]
    duties = checked["blocks"] if checked else []
    coverage = {}
    for name in ("lunch", "dinner", "general_rest"):
        records = [
            b["general_rest"] if name == "general_rest" else b["meals"][name] for b in duties
        ]
        coverage[name] = dict(
            required=sum(x["required"] for x in records),
            covered_required=sum(x["required"] and x["covered"] for x in records),
        )
    return dict(
        lower=result["lower_bound"],
        upper=result["upper_bound"],
        absolute_gap=result["absolute_gap"],
        duties=len(duties),
        coverage=coverage,
        max_continuous_driving=max((b["max_continuous_driving"] for b in duties), default=None),
        initial_AB=checked["initial_vehicles_required"] if checked else None,
        deterministic_seconds=result["deterministic_seconds"],
        wall_seconds=result["wall_seconds"],
        native_status=result["native_status"],
        status=result["status"],
    )


def observe(solver, request):
    """Spy on already validated retain() calls; never alter search or candidates."""
    events, fingerprints = [], []
    best_rank = None
    seed_calls = 0
    first_native = False
    original_validate = solver.validate_assignment
    original_solve = cp_model.CpSolver.solve

    def checked(r, blocks):
        nonlocal best_rank, seed_calls, first_native
        validation = original_validate(r, blocks)
        if sys._getframe(1).f_code.co_name != "retain":
            return validation
        caller = sys._getframe(2)
        native = caller.f_code.co_name == "on_solution_callback"
        if native:
            source = "cp_sat"
            callback = caller.f_locals["self"]
            work, bound = callback.deterministic_time, callback.best_objective_bound
        elif "native" in caller.f_locals:
            source, work, bound = "cp_sat_final", None, None
        else:
            source = "legacy_greedy" if seed_calls == 0 else "rest_aware_seed"
            seed_calls += 1
            work, bound = 0, None
        rank = (
            len(blocks),
            sum(b["duty_span"] for b in validation["blocks"]),
            tuple(tuple(b["trip_ids"]) for b in blocks),
        )
        improved = best_rank is None or rank < best_rank
        first = native and not first_native
        if improved or first:
            events.append(
                dict(
                    source=source,
                    first_cp_sat=first,
                    rank_improved=improved,
                    fleet_improved=best_rank is None or rank[0] < best_rank[0],
                    fleet=len(blocks),
                    total_duty=rank[1],
                    deterministic_seconds=work,
                    solver_lower_bound=bound,
                    witness_sha256=digest(blocks),
                    blocks=deepcopy(blocks),
                )
            )
        if improved:
            best_rank = rank
        first_native |= native
        return validation

    def solve(engine, model, *args, **kwargs):
        copy = model.clone()
        copy.clear_hints()
        fingerprints.append(sha256(str(copy.proto).encode()).hexdigest())
        return original_solve(engine, model, *args, **kwargs)

    with (
        patch.object(solver, "validate_assignment", checked),
        patch.object(cp_model.CpSolver, "solve", solve),
    ):
        result = solver.solve_integrated(request)
    # Recheck retained and intermediate witnesses without the observer/model helpers.
    for event in events:
        validate_assignment(request, event["blocks"])
    if result["blocks"]:
        assert validate_assignment(request, result["blocks"]) == result["validation"]
    return dict(
        request=request,
        result=result,
        metrics=metrics(result),
        events=events,
        constraint_sha256=fingerprints,
    )


def relaxations(request):
    """Each named request changes only the stated diagnostic policy groups."""
    for stage in range(7):
        r = deepcopy(request)
        crew = r["crew_policy"]
        if stage == 0:
            r["terminal_policy"].update(post=0, pre=0)
        for key in ("duty", "total_driving"):
            if stage < 2:
                crew[key]["mode"] = OFF
        if stage < 3:
            crew["driving"]["mode"] = OFF
        if stage < 4:
            crew["general_rest"]["mode"] = OFF
        for i, meal in enumerate(crew["meals"]["windows"]):
            if stage < 5 + i:
                meal["mode"] = OFF
        name = (
            "technical_only",
            "terminal_tasks",
            "elapsed_duty",
            "continuous_driving",
            "general_rest",
            "lunch",
            "full",
        )[stage]
        yield name, r
    for name in ("driving", "general_rest", "lunch", "dinner"):
        r = deepcopy(request)
        if name in {"lunch", "dinner"}:
            next(m for m in r["crew_policy"]["meals"]["windows"] if m["name"] == name)["mode"] = OFF
        else:
            r["crew_policy"][name]["mode"] = OFF
        yield "without_" + name, r


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=("before600", "after600", "constraints600", "before480", "after480"),
        required=True,
    )
    parser.add_argument("--original-solver", type=Path)
    args = parser.parse_args(argv)
    solver = integrated_blocking
    if args.phase.startswith("before"):
        if args.original_solver is None:
            parser.error("before runs require --original-solver extracted from " + BASE_SHA)
        spec = importlib.util.spec_from_file_location(
            "bus_schedule_engine.mvp._gap_original", args.original_solver
        )
        solver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(solver)
    frozen_bytes = args.frozen_results.read_bytes()
    frozen = json.loads(frozen_bytes)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    duty = 480 if args.phase.endswith("480") else 600
    for case in frozen["cases"]:
        production = case["request"]
        assert production["timetable"]["departure_sha256"] == DEPARTURE_SHA256
        assert (
            validate_assignment(production, case["result"]["blocks"])
            == case["result"]["validation"]
        )
        if production["crew_policy"]["duty"]["limit"] != duty:
            continue
        runtime = production["runtime_scenario"]["id"]
        variants = (
            relaxations(production) if args.phase == "constraints600" else [("full", production)]
        )
        for label, request in variants:
            # The after600 full run is already the full staircase endpoint.
            if args.phase == "constraints600" and label == "full":
                continue
            path = args.output_dir / f"{args.phase}_{runtime}_{label}.json"
            if path.exists():
                raise FileExistsError(f"preserve completed experiment: {path}")
            record = observe(solver, request)
            record.update(
                label=label,
                relaxed=label != "full",
                frozen_results_sha256=sha256(frozen_bytes).hexdigest(),
                historical_metrics=metrics(case["result"]),
                source_code_sha256=sha256(Path(solver.__file__).read_bytes()).hexdigest(),
            )
            if record["relaxed"] and record["result"]["blocks"]:
                try:
                    validate_assignment(production, record["result"]["blocks"])
                    failure = None
                except ValueError as exc:
                    failure = str(exc)
                record["full_policy_witness_failure"] = failure
            path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            print(
                json.dumps(
                    dict(
                        phase=args.phase,
                        runtime=runtime,
                        label=label,
                        **record["metrics"],
                        fleet_trace=[
                            e["fleet"]
                            for e in record["events"]
                            if e["fleet_improved"] or e["first_cp_sat"]
                        ],
                    )
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""MVP-6A acceptance against the unchanged six-pair Route 10 control."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from time import perf_counter

from ortools.graph.python import max_flow

from .circulation import validate_chains
from .fleet_feedback import fleet_pressure
from .input import DIRECTIONS, runtime_at
from .joint import local_key
from .route10_joint_pilot import JOINT_SETTINGS, retained_trials, run_joint_pilot
from .route10_pilot import _statistics, compare_timetable, render_report
from .runner import export_result, run_bundle


def audit_fleet(data, departures, fleet):
    """Independently rebuild compatibility and solve unit-capacity flow, outside search."""
    trips = []
    for d in DIRECTIONS:
        destination = DIRECTIONS[1 - DIRECTIONS.index(d)]
        for t in departures[d]:
            trips.append(
                (
                    d,
                    t,
                    t + runtime_at(data["directions"][d], t) + data["layover_minutes"][destination],
                )
            )
    n = len(trips)
    source, sink = 2 * n, 2 * n + 1
    flow = max_flow.SimpleMaxFlow()
    for i, (d, _, ready) in enumerate(trips):
        flow.add_arc_with_capacity(source, i, 1)
        flow.add_arc_with_capacity(n + i, sink, 1)
        for j, (other, departure, _) in enumerate(trips):
            if d != other and ready <= departure:
                flow.add_arc_with_capacity(i, n + j, 1)
    if flow.solve(source, sink) != flow.OPTIMAL:
        raise ValueError("Independent maximum-flow fleet audit incomplete")
    required = n - flow.optimal_flow()
    if required != fleet["required_fleet"]:
        raise ValueError("Independent maximum-flow minimum fleet differs")
    validate_chains(data, departures, fleet)
    return required


def _audit(data, result):
    count, fleets = 0, Counter()
    for c in retained_trials(result):
        if c["vehicle_chains"]["status"] != "EXACT":
            continue
        required = audit_fleet(data, c["departures"], c["vehicle_chains"])
        rebuilt = compare_timetable(data, c["id"], c["departures"], c["regimes"])
        if rebuilt["quality"] != c["quality"]:
            raise ValueError("Independent quality audit differs from measured candidate")
        count += 1
        fleets[required] += 1
    return {
        "exact_fleets_verified": count,
        "fleet_distribution": dict(sorted(fleets.items())),
        "method": "Independent SimpleMaxFlow graph, fresh quality/review, chain validation",
        "inside_search_budget": False,
    }


def _best(result):
    return result["recommended"] or min(
        retained_trials(result),
        key=lambda c: (
            len(c["quality"]["proven_hard_failures"]),
            c["quality"]["required_fleet"]
            if c["quality"]["required_fleet"] is not None
            else float("inf"),
            local_key(c),
            c["quality"]["waiting_minutes"] or 0,
            c["id"],
        ),
        default=None,
    )


def run_fleet_pilot(path, output_dir):
    output_dir = Path(output_dir)
    control = run_joint_pilot(path, output_dir / "control", pairs_per_plan=6)
    report = {
        "schema_version": "route10_fleet_pilot_v1",
        "source": control["source"],
        "scenarios": [],
        "limitations": control["limitations"][:],
        "implementation_validation": "Covered by independently known synthetic regression",
    }
    settings = JOINT_SETTINGS | {"pairs_per_plan": 6, "fleet_guided": True}
    for old in control["scenarios"]:
        data = old["bundle"]
        incumbent = old["revalidated_incumbent"]
        seed = {k: incumbent[k] for k in ("departures", "regimes")}
        start = perf_counter()
        result = run_bundle(data, settings, incumbents=[seed])
        elapsed = perf_counter() - start
        trial = _best(result)
        c = (
            compare_timetable(data, trial["id"], trial["departures"], trial["regimes"])
            if trial
            else None
        )
        if old["id"] == "report_p50":
            assert result["recommended"] is not None
            assert result["recommended"]["quality"]["waiting_minutes"] <= 9.441296
        selected = result["recommended"]
        if selected:
            assert selected["quality"]["hard_constraints_pass"]
            for d in DIRECTIONS:
                assert len(selected["departures"][d]) == 51
                assert selected["departures"][d][0] == data["directions"][d]["first"]
                assert selected["departures"][d][-1] == data["directions"][d]["last"]
        diag = result["diagnostics"]
        statistics = _statistics(result, elapsed) | {
            k: diag[k]
            for k in (
                "exact_pair_evaluations",
                "unexamined_retained_pairs",
                "feasible_generated_candidates",
                "directional_compilation_cache_hits",
                "fleet_guided_plans_generated",
                "fleet_guided_evaluations",
                "fleet_guided_feasible_candidates",
                "fleet_guided_fleet_improvements",
            )
        }
        prior = old["comparison"]["C"]
        gain = bool(
            selected
            and (
                not old["joint"]["recommended"]
                or c["quality"]["required_fleet"] < prior["quality"]["required_fleet"]
                or c["quality"]["waiting_minutes"] < prior["quality"]["waiting_minutes"] - 1e-9
                or len(c["review_exceptions"]) < len(prior["review_exceptions"])
                or c["positive_deterioration_passenger_minutes"]
                < prior["positive_deterioration_passenger_minutes"] - 1e-9
            )
        )
        row = {
            "id": old["id"],
            "definition": old["definition"],
            "bundle": data,
            "control": old["joint"],
            "guided": result,
            "statistics": {"control": old["statistics"], "guided": statistics},
            "control_comparison": old["comparison"],
            "comparison": old["comparison"] | {"C": c},
            "revalidated_incumbent": compare_timetable(
                data, "MVP5A_incumbent", seed["departures"], seed["regimes"]
            ),
            "fleet_pressure": fleet_pressure(data, trial["vehicle_chains"]) if trial else None,
            "audit": {"control": _audit(data, old["joint"]), "guided": _audit(data, result)},
            "c_role": "VERIFIED_RECOMMENDATION" if selected else "NEAR_FEASIBLE_TRIAL_ONLY",
            "outcome": "REAL_ROUTE_IMPROVEMENT" if gain else "NO_MEASURED_REAL_ROUTE_GAIN",
            "infeasibility_proof": None,
            "remaining_candidate_families": [
                "Unevaluated queued regime plans and retained settlements",
                "Trip transfers beyond two gaps; wider or three-regime integer headway changes",
                "Splits away from observed readiness misses; more than four regimes",
                "Timing changes outside the 60-minute missed-connection diagnostic window",
            ],
        }
        report["scenarios"].append(row)
        export_result(result, output_dir / old["id"])
    report["classification"] = (
        "REAL_ROUTE_IMPROVEMENT"
        if any(
            r["outcome"] == "REAL_ROUTE_IMPROVEMENT"
            for r in report["scenarios"]
            if r["id"] in {"report_p50", "report_p75"}
        )
        else "NO_MEASURED_REAL_ROUTE_GAIN"
    )
    report["limitations"].append(
        "Residual and terminal-pressure evidence only ranks revisions. At most 32 readiness misses, 12 directional shortlists, four alternatives per direction and 12 proposals per witness are retained. Every third search turn preserves generic exploration. Fixed integer feedback plans may retain fewer than four settlements. Independent acceptance validations are outside search budgets."
    )
    (output_dir / "fleet_report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# MVP-6A fleet-guided Route 10 acceptance",
        "",
        report["classification"],
        "",
    ]
    for row in report["scenarios"]:
        before, after = row["control_comparison"]["C"], row["comparison"]["C"]
        lines += [
            f"## {row['id']} control / guided",
            "",
            f"Outcome: {row['outcome']}. C role: {row['c_role']}.",
            "",
            "| Metric | Six-pair control | Fleet-guided |",
            "|---|---:|---:|",
        ]
        for label, getter in (
            ("Exact fleet", lambda c: c["quality"]["required_fleet"]),
            ("Modeled wait", lambda c: f"{c['quality']['waiting_minutes']:.6f}"),
            ("Review exception intervals", lambda c: len(c["review_exceptions"])),
            (
                "Positive deterioration passenger-minutes",
                lambda c: f"{c['positive_deterioration_passenger_minutes']:.3f}",
            ),
        ):
            lines.append(
                f"| {label} | {getter(before) if before else 'unavailable'} | {getter(after) if after else 'unavailable'} |"
            )
        for key in (
            "evaluations",
            "exact_pair_evaluations",
            "feasible_generated_candidates",
            "fleet_guided_evaluations",
            "fleet_guided_fleet_improvements",
            "runtime_seconds",
            "pending_plans",
            "unexamined_retained_pairs",
        ):
            values = [
                row[side]["diagnostics"].get(key, row["statistics"][side].get(key, 0))
                for side in ("control", "guided")
            ]
            lines.append(f"| {key} | {values[0]} | {values[1]} |")
        lines += [
            "",
            "Exact fleet distributions and independent validation: `"
            + json.dumps(row["audit"], sort_keys=True)
            + "`",
            "",
        ]
    lines.append(render_report(report))
    for row in report["scenarios"]:
        c = row["comparison"]["C"]
        if c:
            lines += [f"## {row['id']} exact vehicle chains", ""]
            lines += [
                f"- V{i:03d}: " + " -> ".join(chain)
                for i, chain in enumerate(c["vehicle_chains"]["chains"], 1)
            ]
            pressure_path = output_dir / row["id"] / "fleet_pressure.json"
            pressure_path.write_text(
                json.dumps(row["fleet_pressure"], sort_keys=True, indent=2) + "\n", encoding="utf-8"
            )
            pressure = row["fleet_pressure"]
            lines += [
                "",
                f"Matching size {pressure['matching_size']}; fleet shortfall {pressure['fleet_deficit']}. "
                f"Detailed chain starts/ends, terminal stock pressure, residual reachability and "
                f"{pressure['missed_connections_total']} readiness misses ({len(pressure['missed_connections'])} retained) "
                f"are in {row['id']}/fleet_pressure.json. All parent witnesses and proposed regime changes "
                "are in run_diagnostics.json. Missing connections are diagnostic hints, not fleet-reduction certificates.",
                "",
            ]
    (output_dir / "comparison_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report

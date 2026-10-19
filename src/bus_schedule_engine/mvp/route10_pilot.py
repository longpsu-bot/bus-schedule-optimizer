"""Executable Route 10 experiment using the existing compiler, coordinator and validators."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from itertools import groupby
from math import ceil
from pathlib import Path
from time import perf_counter

from .circulation import assign_fleet, validate_chains
from .external_benchmark import build_external_benchmark
from .external_import import import_external_workbook
from .input import DIRECTIONS, validate_bundle
from .quality import evaluate
from .review import build_review
from .runner import export_result, run_bundle

WORKBOOK_SHA256 = "8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b"
# Declared windows follow the broad morning, daytime, evening-congestion and late patterns.
# They are an experimental partition of X's report, not estimated historical authority for B.
RUNTIME_BOUNDS = {
    "outbound": [285, 360, 540, 930, 1095, 1261],
    "inbound": [300, 390, 540, 960, 1110, 1261],
}


def runtime_scenarios(source):
    evidence = {}
    for direction in DIRECTIONS:
        trips = [t for t in source["vehicle_trips"] if t["direction"] == direction]
        expected = [t["departure"] for t in source["timetables"]["EXTERNAL_CANDIDATE"][direction]]
        actual = [t["departure"] for t in trips]
        if sorted(actual) != sorted(expected) or len(set(actual)) != len(actual):
            raise ValueError(f"{direction}: recorded X runtime coverage differs from X timetable")
        evidence[direction] = []
        bounds = RUNTIME_BOUNDS[direction]
        for start, end in zip(bounds, bounds[1:], strict=False):
            local = sorted(
                (t for t in trips if start <= t["departure"] < end),
                key=lambda t: (t["departure"], t["source_cells"]),
            )
            values = sorted(t["arrival"] - t["departure"] for t in local)
            if len(values) < 5:
                raise ValueError(f"{direction} {start}-{end}: fewer than five runtime observations")
            if any(value <= 0 for value in values):
                raise ValueError("runtime durations must be positive")
            evidence[direction].append(
                {
                    "start": start,
                    "end": end,
                    "n": len(values),
                    "minimum": min(values),
                    "maximum": max(values),
                    "p50": values[ceil(len(values) * 0.5) - 1],
                    "p75": values[ceil(len(values) * 0.75) - 1],
                    "sparse": len(values) < 8,
                    "observations": deepcopy(local),
                }
            )
    return [
        {
            "id": f"report_{quantile}",
            "authority": "REPORT_DERIVED_HYPOTHETICAL",
            "minimum_layover_minutes": 5,
            "runtime_periods": {
                d: [
                    {"start": p["start"], "end": p["end"], "minutes": ceil(p[quantile])}
                    for p in evidence[d]
                ]
                for d in DIRECTIONS
            },
            "period_evidence": deepcopy(evidence),
            "method": "Nearest-rank empirical quantile; ceiling to a whole minute; half-open departure-time windows, including final departure in last period.",
            "limitations": [
                "Report-derived hypothetical operating scenario, not observed B runtime authority.",
                "Source trip clocks have whole-minute precision; no sub-minute accuracy is claimed.",
                "Five to seven observations are sparse; p75 is descriptive sensitivity, not a reliability guarantee. No statistical independence or day-to-day representativeness is established.",
                "Windows were declared after inspecting broad X duration patterns; no change-point or population-quantile inference is claimed.",
                "X's selected departures and recorded durations may bias both summaries and their application to different B/C departure times.",
                "Five-minute layover is an explicit experimental assumption, not an operating requirement. Terminal stock, drivers and onboard capacity are unverified.",
            ],
        }
        for quantile in ("p50", "p75")
    ]


def planning_bundle(source, scenario, *, headway_guardrail=None):
    if source["demand_status"] != "SUPPORTED_BOARDING_PROXY":
        raise ValueError("report demand aggregation is unresolved")
    data = {
        "route_id": "10",
        "provenance": {
            "source": deepcopy(source["source"]),
            "route_identity": deepcopy(source["route_identity"]),
            "scenario_id": scenario["id"],
            "runtime_basis": "report-derived hypothetical operating scenario",
            "layover_basis": "explicit experimental 5-minute minimum at both destination terminals",
            "protection_basis": "experimental B-derived full-horizon headway guardrail; no regulatory authority"
            if headway_guardrail is not None
            else "No explicit protected-service requirements supplied",
        },
        "demand_basis": "historical_boardings",
        "fleet_ceiling": 14,
        "layover_minutes": dict.fromkeys(DIRECTIONS, scenario["minimum_layover_minutes"]),
        "directions": {},
    }
    for direction in DIRECTIONS:
        times = [t["departure"] for t in source["timetables"]["BASELINE"][direction]]
        data["directions"][direction] = {
            "first": times[0],
            "last": times[-1],
            "trip_count": len(times),
            "baseline": times,
            "runtime_periods": deepcopy(scenario["runtime_periods"][direction]),
            "demand": [
                {
                    "start": b["interval_start"],
                    "end": b["interval_end"],
                    "passengers": b["demand_passengers"],
                }
                for b in source["demand"]
                if b["direction"] == direction
            ],
            "protected_windows": [
                {"start": times[0], "end": times[-1], "max_gap": headway_guardrail}
            ]
            if headway_guardrail is not None
            else [],
        }
    return validate_bundle(data)


def compare_timetable(data, label, departures, regimes):
    """Always rebuild arrivals and minimum path cover; never reuse recorded X arrivals."""
    data = validate_bundle(data)
    fleet = assign_fleet(data, departures)
    if fleet["status"] != "EXACT":
        raise ValueError(f"independent {label} exact fleet evaluation incomplete")
    validate_chains(data, departures, fleet)
    quality = evaluate(data, departures, regimes, fleet)
    candidate = {
        "id": label,
        "source": "BASELINE"
        if label == "B"
        else "EXTERNAL_CANDIDATE"
        if label == "X"
        else "OPTIMIZED",
        "departures": departures,
        "regimes": regimes,
        "vehicle_chains": fleet,
        "quality": quality,
    }
    baseline_times = {d: data["directions"][d]["baseline"] for d in DIRECTIONS}
    baseline_fleet = assign_fleet(data, baseline_times)
    baseline = {
        "id": "B",
        "source": "BASELINE",
        "departures": baseline_times,
        "regimes": [],
        "vehicle_chains": baseline_fleet,
        "quality": evaluate(data, baseline_times, [], baseline_fleet),
    }
    review = build_review(
        data,
        {
            "status": "CONDITIONAL",
            "recommended": candidate,
            "baseline_evidence": baseline,
            "diagnostics": {},
        },
    )
    candidate.update(
        operational_status="CONDITIONAL"
        if quality["hard_constraints_pass"]
        else "CONSTRAINT_FAILURE",
        maximum_directional_headways={
            d: max(z - a for a, z in zip(times, times[1:], strict=False))
            for d, times in departures.items()
        },
        regime_quality={
            d: {
                "uniform_runs": len(runs),
                "singleton_runs": sum(n == 1 for _, n in runs),
                "headways": sorted({h for h, _ in runs}),
            }
            for d, times in departures.items()
            for runs in [
                [
                    (h, len(list(group)))
                    for h, group in groupby(z - a for a, z in zip(times, times[1:], strict=False))
                ]
            ]
        },
        positive_deterioration_passenger_minutes=sum(
            max(0, b["excess_waiting_passenger_minutes"]) for b in quality["demand_buckets"]
        ),
        protected_rule_violations=sum(not p["pass"] for p in quality["protected_windows"]),
        review_exceptions=review["exceptions"],
        high_demand_warnings=[b for b in review["exceptions"] if b["high_demand"]],
    )
    return candidate


def _strongest_trial(data, result):
    if result["recommended"] and result["recommended"]["source"] == "OPTIMIZED":
        return result["recommended"], "GENERATED_RECOMMENDATION"
    available = [f for f in result["diagnostics"]["feedback"] if f.get("quality")]
    if not available:
        return None, "NO_COMPILED_C"
    trial = min(
        available,
        key=lambda f: (
            len(f["quality"]["proven_hard_failures"]),
            f["quality"]["required_fleet"]
            if f["quality"]["required_fleet"] is not None
            else float("inf"),
            f["quality"]["waiting_minutes"] or 0,
            f["evaluation"],
        ),
    )
    candidate = compare_timetable(
        data, f"C_trial_{trial['evaluation']:03d}", trial["departures"], trial["regimes"]
    )
    if (
        candidate["quality"]["required_fleet"] != trial["quality"]["required_fleet"]
        or abs(candidate["quality"]["waiting_minutes"] - trial["quality"]["waiting_minutes"]) > 1e-9
    ):
        raise ValueError("independent trial evaluation differs from measured evidence")
    return candidate, "STRONGEST_TRIAL_NOT_RECOMMENDED"


def _statistics(result, elapsed):
    diagnostics = result["diagnostics"]
    return {
        key: diagnostics[key]
        for key in (
            "evaluations",
            "distinct_plans_generated",
            "total_plans_generated",
            "compiled_candidates",
            "duplicate_schedules",
            "feasible_candidates",
            "rejections_by_reason",
            "search_limit_reason",
        )
    } | {
        "runtime_seconds": elapsed,
        "settlement_previews": sum(
            c.get("settlement_previews", int(c["status"] == "COMPILED"))
            for f in diagnostics["feedback"]
            for c in f["compilation"].values()
        ),
        "incomplete_compilations": sum(
            c.get("settlement_lookahead_complete") is False
            for f in diagnostics["feedback"]
            for c in f["compilation"].values()
        ),
    }


def render_report(report):
    lines = [
        "# Route 10 engine optimization pilot",
        "",
        "All operating results are conditional report-derived hypothetical scenarios. No operating approval is issued.",
        "Source SHA-256: `" + report["source"]["sha256"] + "`.",
        "",
        "Original recorded X trips/chains and the unchanged MVP-4 benchmark are stored separately. Common evaluations recompute every arrival and vehicle chain.",
        "",
    ]
    for row in report["scenarios"]:
        lines.extend(
            [
                f"## {row['id']}",
                "",
                f"C role: {row['c_role']}. Outcome: {row['outcome']}.",
                "",
                "| Criterion | B | X | C |",
                "|---|---|---|---|",
            ]
        )
        comparison = row["comparison"]
        metrics = [
            (
                "Trips outbound/inbound",
                lambda c: "/".join(str(len(c["departures"][d])) for d in DIRECTIONS),
            ),
            ("Required fleet", lambda c: str(c["quality"]["required_fleet"])),
            ("Modeled wait (minutes)", lambda c: f"{c['quality']['waiting_minutes']:.6f}"),
            (
                "Max headway outbound/inbound (minutes)",
                lambda c: "/".join(str(c["maximum_directional_headways"][d]) for d in DIRECTIONS),
            ),
            (
                "Positive deterioration vs B (passenger-minutes)",
                lambda c: f"{c['positive_deterioration_passenger_minutes']:.3f}",
            ),
            ("Protected-rule violations", lambda c: str(c["protected_rule_violations"])),
            (
                "Uniform runs outbound/inbound",
                lambda c: "/".join(str(c["regime_quality"][d]["uniform_runs"]) for d in DIRECTIONS),
            ),
            (
                "Singleton runs outbound/inbound",
                lambda c: "/".join(
                    str(c["regime_quality"][d]["singleton_runs"]) for d in DIRECTIONS
                ),
            ),
            ("Operational feasibility", lambda c: c["operational_status"]),
        ]
        for title, value in metrics:
            lines.append(
                "| "
                + title
                + " | "
                + " | ".join(
                    value(comparison[k]) if comparison[k] else "unavailable"
                    for k in ("B", "X", "C")
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "Zero explicit-rule violations does not certify protected service when no rules were supplied.",
                "",
                "Before/after statistics: `" + json.dumps(row["statistics"], sort_keys=True) + "`.",
                "",
            ]
        )
        c = comparison["C"]
        if c:
            lines.extend(
                ["C interval review warnings (review policy, not hard service authority):", ""]
            )
            for warning in c["review_exceptions"]:
                lines.append(
                    f"- {warning['direction']} {clock(warning['interval_start'])}-{clock(warning['interval_end'])}: "
                    f"wait delta {warning['waiting_difference_minutes']:.3f} min; "
                    f"high-demand classification: {warning['high_demand']}; "
                    f"{', '.join(warning['warnings'])}. "
                    f"B/C intersecting gaps {warning['baseline']['maximum_intersecting_headway']}/"
                    f"{warning['candidate']['maximum_intersecting_headway']} min."
                )
            lines.extend(["", "Exact C departures:", ""])
            for d in DIRECTIONS:
                lines.append(f"- {d}: " + ", ".join(clock(t) for t in c["departures"][d]))
            lines.extend(["", "C ServiceRegimes (shared pivots, no transition gap):", ""])
            for regime in c["regimes"]:
                lines.append(
                    f"- {regime['direction']} {clock(regime['start_time'])}-{clock(regime['end_time'])}: "
                    f"{regime['headway_minutes']} min, {regime['gap_count']} gaps."
                )
        lines.append("")
    lines.extend(["## Limits and next step", "", *["- " + s for s in report["limitations"]], ""])
    return "\n".join(lines)


def clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def run_pilot(path, output_dir):
    path, output_dir = Path(path), Path(output_dir)
    digest = sha256(path.read_bytes()).hexdigest()
    if digest != WORKBOOK_SHA256:
        raise ValueError(
            f"SHA-256 mismatch for {path.name}: expected {WORKBOOK_SHA256}, got {digest}"
        )
    source = import_external_workbook(path)
    benchmark = build_external_benchmark(source)
    for key in ("BASELINE", "EXTERNAL_CANDIDATE"):
        for d in DIRECTIONS:
            times = [t["departure"] for t in source["timetables"][key][d]]
            if (
                len(times) != 51
                or times[0] != (285 if d == "outbound" else 300)
                or times[-1] != 1260
            ):
                raise ValueError("Route 10 trip counts/endpoints differ from pilot specification")
    scenarios = runtime_scenarios(source)
    report = {
        "schema_version": "route10_pilot_v1",
        "source": source["source"],
        "scenarios": [],
        "limitations": scenarios[0]["limitations"]
        + [
            "Boarding/chart demand is a proxy with uniform within-bucket arrivals. Outside-service passengers are disclosed and excluded equally for B/X/C; no V3 demand is used.",
            "Headway 25 minutes is a separate B-derived experiment, not a regulatory limit. No inferred peak becomes mandatory protection.",
            "High-demand frequency/gap warnings remain for human review even where average waiting improves; no claim of unqualified operator acceptance is made.",
            "The compiler ranks bounded directional settlements by explicit protection and demand wait, not joint fleet. Next improvement: rank a small number of joint integer settlements with exact circulation inside the existing 25-evaluation budget.",
            "A failed bounded search is SEARCH_INCOMPLETE, never proof of route infeasibility. Native exact-model certification does not establish real-world operational authority.",
        ],
    }
    primary_c = None
    jobs = [(s, None) for s in scenarios] + [(scenarios[0], 25)]
    for scenario, guardrail in jobs:
        scenario_id = scenario["id"] + ("_B25_guardrail" if guardrail else "")
        data = planning_bundle(source, scenario, headway_guardrail=guardrail)
        results, statistics = {}, {}
        for label, lookahead in (("control", 0), ("improved", 256)):
            start = perf_counter()
            result = run_bundle(data, {"compilation_lookahead": lookahead})
            statistics[label] = _statistics(result, perf_counter() - start)
            results[label] = result
        trial, role = _strongest_trial(data, results["improved"])
        comparison = {}
        for label, key in (("B", "BASELINE"), ("X", "EXTERNAL_CANDIDATE")):
            times = {d: [t["departure"] for t in source["timetables"][key][d]] for d in DIRECTIONS}
            comparison[label] = compare_timetable(data, label, times, [])
        comparison["C"] = (
            compare_timetable(data, trial["id"], trial["departures"], trial["regimes"])
            if trial
            else None
        )
        c = comparison["C"]
        if not report["scenarios"] and role == "GENERATED_RECOMMENDATION":
            primary_c = c
        row = {
            "id": scenario_id,
            "definition": scenario,
            "bundle": data,
            "control": results["control"],
            "improved": results["improved"],
            "statistics": statistics,
            "comparison": comparison,
            "c_role": role,
            "outcome": "CONDITIONAL_C_REQUIRES_SERVICE_REVIEW"
            if role == "GENERATED_RECOMMENDATION"
            else "SEARCH_INCOMPLETE",
        }
        if primary_c is not None:
            row["primary_C_sensitivity"] = compare_timetable(
                data, "C_primary", primary_c["departures"], primary_c["regimes"]
            )
        report["scenarios"].append(row)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in (
        ("source_evidence.json", source),
        (
            "recorded_X_chains.json",
            {
                "trips": source["vehicle_trips"],
                "summaries": source["vehicle_summaries"],
                "validation": benchmark["fleet"],
            },
        ),
        ("unchanged_external_benchmark.json", benchmark),
        ("pilot_report.json", report),
    ):
        (output_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    (output_dir / "comparison_report.md").write_text(render_report(report), encoding="utf-8")
    for row in report["scenarios"]:
        export_result(row["improved"], output_dir / row["id"])
    return report

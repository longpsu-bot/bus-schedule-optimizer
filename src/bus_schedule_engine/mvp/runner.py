"""Bounded feedback coordinator and operator-reviewable JSON/XLSX outputs."""

from __future__ import annotations

import json
from collections import deque
from copy import deepcopy
from pathlib import Path
from time import monotonic

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .circulation import assign_fleet
from .input import DIRECTIONS, integer, number, validate_bundle
from .planning import compile_plan, initial_plan, revise_plan
from .quality import evaluate, select_candidate

DEFAULTS = {
    "candidate_budget": 25,
    "max_revisions": 24,
    "solver_seconds": 2,
    "solver_work_limit": 0.2,
    "total_seconds": 120,
    "minimum_internal_gaps": 2,
    "minimum_regime_minutes": 30,
    "maximum_regimes": 4,
    "boundary_settlement_minutes": 60,
    "wait_absolute_tolerance": 0.10,
    "wait_relative_tolerance": 0.02,
}


def _settings(settings):
    if settings is not None and not isinstance(settings, dict):
        raise ValueError("settings must be an object")
    active = DEFAULTS | (settings or {})
    if set(active) - (set(DEFAULTS) | {"maximum_transition_jump"}):
        raise ValueError("unknown planning setting")
    for key in ("candidate_budget", "minimum_internal_gaps", "maximum_regimes"):
        integer(active[key], key, 1)
    if active["minimum_internal_gaps"] < 2:
        raise ValueError("minimum_internal_gaps must be >=2; one-gap regimes are forbidden")
    for key in ("max_revisions", "minimum_regime_minutes", "boundary_settlement_minutes"):
        integer(active[key], key)
    for key in ("solver_seconds", "solver_work_limit", "total_seconds"):
        number(active[key], key)
        if active[key] <= 0:
            raise ValueError(f"{key} must be positive")
    for key in ("wait_absolute_tolerance", "wait_relative_tolerance"):
        number(active[key], key)
    if active.get("maximum_transition_jump") is not None:
        integer(active["maximum_transition_jump"], "maximum_transition_jump")
    return active


def run_bundle(bundle, settings=None):
    result = {
        "status": "BLOCKED_INPUT",
        "recommended": None,
        "alternatives": [],
        "diagnostics": {"evaluations": 0, "feedback": []},
    }
    try:
        data, active = validate_bundle(bundle), _settings(settings)
    except ValueError as exc:
        result["diagnostics"]["input_error"] = str(exc)
        return result
    result.update(
        route_id=data["route_id"],
        provenance=data["provenance"],
        settings=active,
        demand_basis=data["demand_basis"],
    )
    for direction in DIRECTIONS:
        d = data["directions"][direction]
        if d["trip_count"] > d["last"] - d["first"] + 1:
            result["status"] = "PROVEN_INFEASIBLE"
            result["diagnostics"]["proof"] = (
                f"{direction}: {d['trip_count']} trips exceed {d['last'] - d['first'] + 1} distinct whole-minute slots between authoritative endpoints"
            )
            return result
    deadline = monotonic() + active["total_seconds"]
    initial = {d: initial_plan(data["directions"][d], active) for d in DIRECTIONS}
    queue = deque([("initial", initial)])
    seen = {json.dumps(initial, sort_keys=True)}
    schedules = set()
    candidates = []
    limited = False
    # Baseline is reference evidence, never a generation or selection authority.
    baseline_data = deepcopy(data)
    baseline_times = {d: data["directions"][d]["baseline"] for d in DIRECTIONS}
    for d in DIRECTIONS:
        baseline_data["directions"][d]["trip_count"] = len(baseline_times[d])
    result["baseline"] = {}
    if monotonic() < deadline:
        baseline_fleet = assign_fleet(
            baseline_data, baseline_times, settings=active, deadline=deadline
        )
        if monotonic() < deadline and baseline_fleet["status"] != "SOLVER_LIMIT":
            result["baseline"] = evaluate(baseline_data, baseline_times, [], baseline_fleet, active)
    result["diagnostics"]["baseline_status"] = "EVALUATED" if result["baseline"] else "TIME_LIMIT"
    max_evaluations = min(active["candidate_budget"], active["max_revisions"] + 1)
    while queue:
        if result["diagnostics"]["evaluations"] >= max_evaluations or monotonic() >= deadline:
            limited = True
            break
        operation, plans = queue.popleft()
        result["diagnostics"]["evaluations"] += 1
        index = result["diagnostics"]["evaluations"]
        feedback = {"evaluation": index, "operation": operation, "plans": plans, "compilation": {}}
        departures, regimes = {}, []
        for direction in DIRECTIONS:
            remaining = deadline - monotonic()
            if remaining <= 0:
                feedback["compilation"][direction] = {
                    "status": "SOLVER_LIMIT",
                    "reason": "total run seconds reached",
                }
                limited = True
                break
            bounded = active | {"solver_seconds": min(active["solver_seconds"], remaining)}
            compiled = compile_plan(data["directions"][direction], plans[direction], bounded)
            feedback["compilation"][direction] = {
                k: v for k, v in compiled.items() if k not in {"departures", "regimes"}
            }
            if compiled["status"] != "COMPILED":
                continue
            departures[direction] = compiled["departures"]
            average = (
                data["directions"][direction]["last"] - data["directions"][direction]["first"]
            ) / (data["directions"][direction]["trip_count"] - 1)
            for r in compiled["regimes"]:
                r["direction"] = direction
                if r["regime_type"] != "end_tail":
                    r["regime_type"] = "peak" if r["headway_minutes"] < average else "low-demand"
                regimes.append(r)
        reason = "COMPILATION"
        if len(departures) == 2:
            key = json.dumps(departures, sort_keys=True)
            if key in schedules:
                feedback["candidate_status"] = "DUPLICATE_TIMETABLE"
            else:
                schedules.add(key)
                remaining = deadline - monotonic()
                if remaining <= 0:
                    limited = True
                    feedback["candidate_status"] = "SOLVER_LIMIT"
                else:
                    bounded = active | {"solver_seconds": min(active["solver_seconds"], remaining)}
                    fleet = assign_fleet(data, departures, settings=bounded, deadline=deadline)
                    quality = evaluate(data, departures, regimes, fleet, bounded)
                    feedback["candidate_status"] = (
                        "FEASIBLE" if quality["hard_constraints_pass"] else "REJECTED"
                    )
                    feedback["fleet_status"] = fleet["status"]
                    feedback["failures"] = quality["failures"]
                    feedback["quality"] = quality
                    if quality["hard_constraints_pass"]:
                        candidate = {
                            "id": f"C{index:03d}",
                            "departures": departures,
                            "regimes": regimes,
                            "vehicle_chains": fleet,
                            "quality": quality,
                        }
                        candidates.append(candidate)
                        result["recommended"] = select_candidate(candidates, active)
                        reason = "QUALITY"
                    else:
                        reason = (
                            "FLEET" if any("FLEET" in x for x in quality["failures"]) else "SERVICE"
                        )
        result["diagnostics"]["feedback"].append(feedback)
        # Interleave direction neighborhoods so one direction cannot starve the other.
        neighbors = [
            revise_plan(data["directions"][d], plans[d], reason, active) for d in DIRECTIONS
        ]
        for i in range(max(map(len, neighbors), default=0)):
            for direction, choices in zip(DIRECTIONS, neighbors, strict=True):
                if i >= len(choices):
                    continue
                name, changed = choices[i]
                revised = plans | {direction: changed}
                key = json.dumps(revised, sort_keys=True)
                if key not in seen and len(seen) < max_evaluations and len(queue) < 4:
                    seen.add(key)
                    queue.append((f"{direction}:{name}", revised))
    limited = limited or result["diagnostics"]["evaluations"] >= max_evaluations
    if result["recommended"]:
        result["status"] = "FEASIBLE_BUDGET_LIMITED" if limited else "FEASIBLE_RECOMMENDATION"
        alternatives = [c for c in candidates if c["id"] != result["recommended"]["id"]]
        while alternatives and len(result["alternatives"]) < 2:
            selected = select_candidate(alternatives, active)
            result["alternatives"].append(selected)
            alternatives.remove(selected)
        sse_anchor = min(candidates, key=lambda c: (c["quality"]["sse"], c["id"]))["id"]
        te_anchor = min(candidates, key=lambda c: (c["quality"]["te"], c["id"]))["id"]
        result["diagnostics"]["metric_disagreement"] = {
            "sse_best": sse_anchor,
            "te_best": te_anchor,
            "disagree": sse_anchor != te_anchor,
            "selection_gate": False,
        }
    else:
        result["status"] = "SEARCH_INCOMPLETE_NO_FEASIBLE_CANDIDATE"
        result["diagnostics"]["action"] = (
            "Inspect structured family/compiler/stock/protection feedback; increase bounded budget or revise service-plan family. Route infeasibility is not proved."
        )
    result["diagnostics"].update(
        budget_limited=limited,
        feasible_candidates=len(candidates),
        distinct_plans_generated=len(seen),
        selection_policy="feasibility > worst protected gap > wait-equivalence band > fleet > regimes > transitions > terminal wait > tail > exact tuple",
        global_optimality_proved=False,
    )
    return result


def export_result(result, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    recommended = result["recommended"]
    report = {
        "status": result["status"],
        "route_id": result.get("route_id"),
        "quality": recommended["quality"] if recommended else None,
        "baseline": result.get("baseline"),
        "provenance": result.get("provenance"),
        "settings": result.get("settings"),
        "demand_basis": result.get("demand_basis"),
        "alternatives": [{"id": c["id"], "quality": c["quality"]} for c in result["alternatives"]],
    }
    outputs = {
        "recommended_timetable.json": {
            "status": result["status"],
            "departures": recommended["departures"] if recommended else None,
            "candidate_id": recommended["id"] if recommended else None,
        },
        "service_regimes.json": recommended["regimes"] if recommended else [],
        "vehicle_chains.json": recommended["vehicle_chains"] if recommended else None,
        "quality_report.json": report,
        "run_diagnostics.json": result["diagnostics"],
    }
    for name, payload in outputs.items():
        (directory / name).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
    workbook = Workbook()
    workbook.remove(workbook.active)
    for direction in DIRECTIONS:
        sheet = workbook.create_sheet(direction.title())
        sheet.append(["Trip", "Departure minute", "Departure HH:MM", "Arrival HH:MM", "Vehicle"])
        if recommended:
            rows = sorted(
                (t for t in recommended["vehicle_chains"]["trips"] if t["direction"] == direction),
                key=lambda t: t["departure"],
            )
            for t in rows:
                sheet.append(
                    [
                        t["trip_id"],
                        t["departure"],
                        _time(t["departure"]),
                        _time(t["arrival"]),
                        t["vehicle_id"],
                    ]
                )
    sheet = workbook.create_sheet("ServiceRegimes")
    sheet.append(
        [
            "Direction",
            "Start",
            "End",
            "Headway minutes",
            "Planned departures",
            "Internal gaps",
            "Type",
        ]
    )
    for r in recommended["regimes"] if recommended else []:
        sheet.append(
            [
                r["direction"],
                _time(r["start_time"]),
                _time(r["end_time"]),
                r["headway_minutes"],
                r["planned_departure_count"],
                r["gap_count"],
                r["regime_type"],
            ]
        )
    sheet = workbook.create_sheet("VehicleCirculation")
    sheet.append(["Vehicle", "Trip", "Direction", "Departure", "Arrival", "Ready after layover"])
    for t in recommended["vehicle_chains"]["trips"] if recommended else []:
        sheet.append(
            [
                t["vehicle_id"],
                t["trip_id"],
                t["direction"],
                _time(t["departure"]),
                _time(t["arrival"]),
                _time(t["ready"]),
            ]
        )
    sheet = workbook.create_sheet("QualityComparison")
    sheet.append(["Measure", "Existing B", "Recommendation"])
    sheet.append(["Run status", "reference", result["status"]])
    for metric in (
        "hard_constraints_pass",
        "waiting_minutes",
        "required_fleet",
        "maximum_protected_gap",
        "regime_count",
        "transition_jump",
        "terminal_wait",
        "tail_gap",
        "sse",
        "te",
        "continuous_exposure",
        "capacity",
        "directional_waiting_minutes",
        "outside_service_passengers",
    ):
        baseline = result.get("baseline", {}).get(metric)
        value = recommended["quality"].get(metric) if recommended else None
        sheet.append(
            [
                metric,
                json.dumps(baseline) if isinstance(baseline, dict) else baseline,
                json.dumps(value) if isinstance(value, dict) else value,
            ]
        )
    sheet.append(
        [
            "Waiting assumption",
            "Uniform bucket arrivals",
            "Modeled scheduled wait, not observed wait",
        ]
    )
    sheet.append(
        [
            "Demand basis",
            result.get("demand_basis"),
            "Historical boardings are an arrival proxy"
            if result.get("demand_basis") == "historical_boardings"
            else "Independent arrivals",
        ]
    )
    for sheet in workbook:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="183B56")
            cell.font = Font(color="FFFFFF", bold=True)
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(
                70, max(14, max(len(str(c.value or "")) for c in column) + 2)
            )
    workbook.save(directory / "recommended_timetable.xlsx")


def _time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"

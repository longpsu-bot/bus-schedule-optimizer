"""Service-plan neighborhoods and bounded exact integer rhythm compilation."""

from __future__ import annotations

from copy import deepcopy
from math import sqrt

from ortools.sat.python import cp_model


def solver(settings):
    instance = cp_model.CpSolver()
    instance.parameters.num_search_workers = 1
    instance.parameters.random_seed = 0
    instance.parameters.max_time_in_seconds = settings.get("solver_seconds", 2)
    instance.parameters.max_deterministic_time = settings.get("solver_work_limit", 0.2)
    return instance


def initial_plan(direction, settings):
    first, last = direction["first"], direction["last"]
    min_duration = settings.get("minimum_regime_minutes", 30)
    min_gaps = settings.get("minimum_internal_gaps", 2)
    limit = min(settings.get("maximum_regimes", 4), (direction["trip_count"] - 1) // min_gaps)
    # Sustained demand changes define candidate boundaries; buckets are not departure anchors.
    buckets = direction["demand"]
    changes = []
    for left, right in zip(buckets, buckets[1:], strict=False):
        a = left["passengers"] / (left["end"] - left["start"])
        b = right["passengers"] / (right["end"] - right["start"])
        boundary = right["start"]
        relative_change = abs(a - b) / max(a, b) if max(a, b) else 0
        if relative_change >= 0.15 and first + min_duration <= boundary <= last - min_duration:
            changes.append((abs(a - b), boundary))
    bounds = [first, last]
    for _, boundary in sorted(changes, key=lambda item: (-item[0], item[1])):
        if len(bounds) - 1 >= limit:
            break
        if min(abs(boundary - x) for x in bounds) >= min_duration:
            bounds.append(boundary)
    bounds.sort()
    weights = []
    for start, end in zip(bounds, bounds[1:], strict=False):
        passengers = sum(
            b["passengers"]
            * max(0, min(end, b["end"]) - max(start, b["start"]))
            / (b["end"] - b["start"])
            for b in buckets
        )
        weights.append(sqrt(passengers / (end - start)) * (end - start))
    if sum(weights) == 0:
        weights = [b - a for a, b in zip(bounds, bounds[1:], strict=False)]
    remaining = direction["trip_count"] - 1 - min_gaps * len(weights)
    shares = [remaining * w / sum(weights) for w in weights]
    counts = [min_gaps + int(x) for x in shares]
    for i in sorted(range(len(counts)), key=lambda i: (-(shares[i] % 1), i))[
        : remaining - sum(int(x) for x in shares)
    ]:
        counts[i] += 1
    return [{"end": end, "gaps": count} for end, count in zip(bounds[1:], counts, strict=True)]


def revise_plan(direction, plan, feedback, settings):
    minimum = settings.get("minimum_internal_gaps", 2)
    # Try simplification early after compiler/fleet failure, retaining meaningful blocks.
    output = []
    for i in range(len(plan) - 1):
        merged = deepcopy(plan)
        merged[i + 1]["gaps"] += merged[i]["gaps"]
        del merged[i]
        output.append(("merge", merged))
    for i in range(len(plan) - 1):
        for delta in (-1, 1):
            if plan[i]["gaps"] + delta >= minimum and plan[i + 1]["gaps"] - delta >= minimum:
                changed = deepcopy(plan)
                changed[i]["gaps"] += delta
                changed[i + 1]["gaps"] -= delta
                output.append(("reallocate_trip", changed))
        for delta in (-15, 15):
            changed = deepcopy(plan)
            changed[i]["end"] += delta
            start = direction["first"] if i == 0 else plan[i - 1]["end"]
            if start + 30 <= changed[i]["end"] <= changed[i + 1]["end"] - 30:
                output.append(("shift_boundary", changed))
    if len(plan) < settings.get("maximum_regimes", 4):
        start = direction["first"]
        for i, block in enumerate(plan):
            if block["gaps"] >= 2 * minimum and block["end"] - start >= 2 * settings.get(
                "minimum_regime_minutes", 30
            ):
                split = deepcopy(plan)
                left_count = block["gaps"] // 2
                split[i : i + 1] = [
                    {"end": (start + block["end"]) // 2, "gaps": left_count},
                    {"end": block["end"], "gaps": block["gaps"] - left_count},
                ]
                output.append(("split_tail" if i == len(plan) - 1 else "split", split))
            start = block["end"]
    order = (
        ["reallocate_trip", "shift_boundary", "merge", "split", "split_tail"]
        if feedback in {"COMPILATION", "QUALITY", "SERVICE"}
        else ["merge", "reallocate_trip", "shift_boundary", "split_tail", "split"]
    )
    output.sort(key=lambda item: order.index(item[0]))
    first_per_operation = []
    remaining = []
    used = set()
    for item in output:
        if item[0] not in used:
            first_per_operation.append(item)
            used.add(item[0])
        else:
            remaining.append(item)
    return first_per_operation + remaining


def compile_plan(direction, plan, settings):
    """Shared pivots assign every gap to one whole-minute regime, with no transition gap."""
    minimum = settings.get("minimum_internal_gaps", 2)
    duration = direction["last"] - direction["first"]
    if (
        not plan
        or sum(p["gaps"] for p in plan) != direction["trip_count"] - 1
        or any(p["gaps"] < minimum for p in plan)
    ):
        return {"status": "INVALID_PLAN", "reason": "gap totals/minimum internal rhythm contract"}
    model = cp_model.CpModel()
    headways = []
    ends = []
    costs = []
    cursor = direction["first"]
    target_start = cursor
    for i, p in enumerate(plan):
        h = model.new_int_var(1, duration, f"h{i}")
        end = model.new_int_var(direction["first"], direction["last"], f"end{i}")
        model.add(end == cursor + h * p["gaps"])
        model.add(h * p["gaps"] >= settings.get("minimum_regime_minutes", 30))
        if i < len(plan) - 1:
            shift = settings.get("boundary_settlement_minutes", 60)
            model.add(end >= p["end"] - shift)
            model.add(end <= p["end"] + shift)
        deviation = model.new_int_var(0, duration * 2, f"deviation{i}")
        model.add_abs_equality(deviation, h * p["gaps"] - (p["end"] - target_start))
        costs.append(deviation)
        if headways and settings.get("maximum_transition_jump") is not None:
            model.add(h - headways[-1] <= settings["maximum_transition_jump"])
            model.add(headways[-1] - h <= settings["maximum_transition_jump"])
        cursor = end
        target_start = p["end"]
        headways.append(h)
        ends.append(end)
    model.add(ends[-1] == direction["last"])
    # This is boundary settlement, not the production selection objective.
    model.minimize(sum(costs))
    engine = solver(settings)
    status = engine.solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return {
            "status": "FAMILY_INFEASIBLE" if status == cp_model.INFEASIBLE else "SOLVER_LIMIT",
            "reason": "No settled integer rhythm found in this bounded plan family; revise allocation/boundary/count.",
        }
    departures = [direction["first"]]
    regimes = []
    for p, h in zip(plan, headways, strict=True):
        headway = engine.value(h)
        start = departures[-1]
        for _ in range(p["gaps"]):
            departures.append(departures[-1] + headway)
        if regimes and regimes[-1]["headway_minutes"] == headway:
            regimes[-1]["end_time"] = departures[-1]
            regimes[-1]["gap_count"] += p["gaps"]
        else:
            regimes.append(
                {
                    "start_time": start,
                    "end_time": departures[-1],
                    "headway_minutes": headway,
                    "gap_count": p["gaps"],
                }
            )
    for i, r in enumerate(regimes):
        r["planned_departure_count"] = r["gap_count"] + (i == len(regimes) - 1)
        r["regime_type"] = "end_tail" if i == len(regimes) - 1 else "normal"
    return {
        "status": "COMPILED",
        "departures": departures,
        "regimes": regimes,
        "boundary_settlement": [
            engine.value(e) - p["end"] for e, p in zip(ends, plan, strict=True)
        ],
        "solver_optimal_settlement": status == cp_model.OPTIMAL,
    }

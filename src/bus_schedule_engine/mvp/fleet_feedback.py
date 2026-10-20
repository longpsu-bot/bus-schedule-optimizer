"""Bounded matching diagnostics and integer ServiceRegime revision hints.

Hints do not certify fleet feasibility: changing times may remove existing links.
The normal compiler, service evaluator and exact assignment remain authoritative.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from itertools import combinations, product
from math import ceil
from time import perf_counter as monotonic

from .input import DIRECTIONS, runtime_at
from .joint import directional_quality


def _reachable(graph, starts):
    found = set(starts)
    queue = deque(starts)
    while queue:
        for node in graph[queue.popleft()]:
            if node not in found:
                found.add(node)
                queue.append(node)
    return found


def fleet_pressure(data, fleet, *, window=60, deadline=None):
    if fleet.get("status") != "EXACT":
        return {"status": "UNAVAILABLE", "reason": "Exact vehicle assignment required"}
    trips = fleet["trips"]
    by_id = {t["trip_id"]: i for i, t in enumerate(trips)}
    links = [(by_id[a], by_id[b]) for c in fleet["chains"] for a, b in zip(c, c[1:], strict=False)]
    matched = set(links)
    n = len(trips)
    starts = [by_id[c[0]] for c in fleet["chains"]]
    ends = [by_id[c[-1]] for c in fleet["chains"]]
    graph, reverse = defaultdict(list), defaultdict(list)
    for i, t in enumerate(trips):
        if deadline is not None and monotonic() >= deadline:
            return {"status": "UNAVAILABLE", "reason": "Feedback deadline reached"}
        for j, u in enumerate(trips):
            if t["direction"] != u["direction"] and t["ready"] <= u["departure"]:
                a, b = (n + j, i) if (i, j) in matched else (i, n + j)
                graph[a].append(b)
                reverse[b].append(a)
    reachable = _reachable(graph, ends)
    coreachable = _reachable(reverse, [n + i for i in starts])
    unconstrained = "initial_vehicles" not in data
    misses = []
    for i, t in enumerate(trips):
        for j, u in enumerate(trips):
            late = t["ready"] - u["departure"]
            if (
                t["direction"] != u["direction"]
                and t["departure"] < u["departure"]
                and 0 < late <= window
            ):
                misses.append(
                    {
                        "from_trip": t["trip_id"],
                        "to_trip": u["trip_id"],
                        "terminal": u["direction"],
                        "ready": t["ready"],
                        "departure": u["departure"],
                        "minutes_late": late,
                        "augmenting_bridge": unconstrained
                        and i in reachable
                        and n + j in coreachable,
                        "unmatched_start": j in starts,
                    }
                )
    misses.sort(
        key=lambda e: (
            not e["augmenting_bridge"],
            e["minutes_late"],
            e["departure"],
            e["from_trip"],
            e["to_trip"],
        )
    )
    terminals = {}
    for d in DIRECTIONS:
        events = defaultdict(int)
        for t in trips:
            events[t["departure"] if t["direction"] == d else t["ready"]] += (
                1 if t["direction"] == d else -1
            )
        balance, peak, intervals = 0, 0, []
        times = sorted(events)
        for i, minute in enumerate(times):
            balance += events[minute]
            peak = max(peak, balance)
            if balance > 0 and i + 1 < len(times):
                intervals.append(
                    {"start": minute, "end": times[i + 1], "initial_stock_pressure": balance}
                )
        terminals[d] = {"initial_stock_lower_bound": peak, "intervals": intervals}
    return {
        "status": "EXACT_ASSIGNMENT_DIAGNOSTIC",
        "matching_size": len(links),
        "required_fleet": fleet["required_fleet"],
        "fleet_deficit": max(0, fleet["required_fleet"] - data["fleet_ceiling"]),
        "chain_starts": [dict(trips[i]) for i in starts],
        "chain_ends": [dict(trips[i]) for i in ends],
        "terminal_pressure": terminals,
        "residual_basis": "MAXIMUM_BIPARTITE_MATCHING"
        if unconstrained
        else "UNCONSTRAINED_MATCHING_ONLY",
        "reachable_left": [t["trip_id"] for i, t in enumerate(trips) if i in reachable],
        "coreachable_right": [t["trip_id"] for i, t in enumerate(trips) if n + i in coreachable],
        "missed_connections": misses[:32],
        "missed_connections_total": len(misses),
        "missed_connection_window_minutes": window,
        "feasibility_prediction": False,
        "interpretation": "A residual bridge would augment the frozen compatibility graph. Time changes can remove links; only fresh exact assignment establishes a fleet improvement.",
    }


def _vector(direction, blocks):
    times = [direction["first"]]
    plan = []
    for count, headway in blocks:
        start = times[-1]
        times.extend(start + headway * j for j in range(1, count + 1))
        if plan and plan[-1]["headway_minutes"] == headway:
            plan[-1]["gaps"] += count
            plan[-1]["end"] = times[-1]
        else:
            plan.append({"end": times[-1], "gaps": count, "headway_minutes": headway})
    return plan, times


def fleet_revisions(data, candidate, settings, *, deadline=None):
    """At most 12 ranked plans per witness; no additional exact pair evaluations."""
    evidence = fleet_pressure(data, candidate["vehicle_chains"], deadline=deadline)
    if evidence["status"] == "UNAVAILABLE" or not evidence["missed_connections"]:
        return evidence, []
    trips = {t["trip_id"]: t for t in candidate["vehicle_chains"]["trips"]}
    links = [
        (a, b)
        for c in candidate["vehicle_chains"]["chains"]
        for a, b in zip(c, c[1:], strict=False)
    ]
    misses = evidence["missed_connections"]
    minimum = settings["minimum_internal_gaps"]
    move = min(2, max(1, evidence["fleet_deficit"]))
    originals, choices = {}, {}

    def expired():
        return deadline is not None and monotonic() >= deadline

    def timing(times):
        updated = {}
        for d in DIRECTIONS:
            for i, departure in enumerate(times[d]):
                tid = f"{d}-{i + 1:03d}"
                destination = DIRECTIONS[1 - DIRECTIONS.index(d)]
                updated[tid] = (
                    departure,
                    departure
                    + runtime_at(data["directions"][d], departure)
                    + data["layover_minutes"][destination],
                )
        closed = [e for e in misses if updated[e["from_trip"]][1] <= updated[e["to_trip"]][0]]
        lost = sum(updated[a][1] > updated[b][0] for a, b in links)
        gain = sum(
            max(
                -1,
                min(
                    1,
                    (e["minutes_late"] - (updated[e["from_trip"]][1] - updated[e["to_trip"]][0]))
                    / e["minutes_late"],
                ),
            )
            for e in misses
        )
        return (
            lost,
            sum(e["augmenting_bridge"] for e in closed),
            len(closed),
            gain,
            len({e["to_trip"] for e in closed if e["unmatched_start"]}),
        )

    for d in DIRECTIONS:
        direction = data["directions"][d]
        blocks = [
            (r["gap_count"], r["headway_minutes"])
            for r in candidate["regimes"]
            if r["direction"] == d
        ]
        if not blocks:
            return evidence, []
        original, _ = _vector(direction, blocks)
        originals[d] = original
        variants = {}

        def headway_steps(index, blocks=blocks, d=d):
            offset = sum(g for g, _ in blocks[:index])
            count = blocks[index][0]
            steps = {-1, 0, 1}
            for e in misses:
                for tid, sign in ((e["from_trip"], -1), (e["to_trip"], 1)):
                    position = int(tid.rsplit("-", 1)[1]) - 1 - offset
                    if trips[tid]["direction"] == d and 0 < position <= count:
                        steps.add(sign * ceil(e["minutes_late"] / position))
            return sorted(steps)

        def keep(
            changed, operation, d=d, direction=direction, original=original, variants=variants
        ):
            if expired() or any(
                g < minimum or h < 1 or g * h < settings["minimum_regime_minutes"]
                for g, h in changed
            ):
                return
            plan, times = _vector(direction, changed)
            if times[-1] != direction["last"] or plan == original:
                return
            score = timing(candidate["departures"] | {d: times})
            if score[3] <= 0 and score[2] == 0:
                return
            variants[tuple(times)] = {
                "plan": plan,
                "times": times,
                "operation": operation,
                "timing": score,
            }

        for i, j in combinations(range(len(blocks)), 2):
            gi, hi = blocks[i]
            gj, hj = blocks[j]
            duration = gi * hi + gj * hj
            for transfer, delta in product(range(-move, move + 1), headway_steps(i)):
                if expired():
                    break
                a, b, h = gi + transfer, gj - transfer, hi + delta
                if min(a, b) < minimum or h < 1 or (duration - a * h) % b:
                    continue
                changed = list(blocks)
                changed[i], changed[j] = (a, h), (b, (duration - a * h) // b)
                keep(changed, "reallocate" if transfer else "headway_boundary")
        if len(blocks) < settings["maximum_regimes"]:
            offset = 0
            for i, (g, h) in enumerate(blocks):
                cuts = set()
                for e in misses:
                    for tid in (e["from_trip"], e["to_trip"]):
                        if trips[tid]["direction"] == d:
                            cuts.add(int(tid.rsplit("-", 1)[1]) - 1 - offset)
                for a, delta in product(sorted(cuts), (-2, -1, 1, 2)):
                    if expired():
                        break
                    b, left = g - a, h + delta
                    if min(a, b) < minimum or left < 1 or (g * h - a * left) % b:
                        continue
                    keep(
                        blocks[:i] + [(a, left), (b, (g * h - a * left) // b)] + blocks[i + 1 :],
                        "split",
                    )
                offset += g
        ranked = sorted(
            variants.values(),
            key=lambda v: (
                -v["timing"][4],
                v["timing"][0],
                -v["timing"][1],
                -v["timing"][2],
                -v["timing"][3],
                tuple(v["times"]),
            ),
        )[:12]
        for v in ranked:
            v["quality"] = directional_quality(direction, v["times"], settings)
        ranked = [v for v in ranked if not v["quality"]["protection_violations"]]
        ranked.sort(
            key=lambda v: (
                -v["timing"][4],
                v["timing"][0],
                -v["timing"][1],
                -v["timing"][2],
                v["quality"]["waiting_integral"],
                v["quality"]["positive_passenger_minutes"],
                len(v["plan"]),
                tuple(v["times"]),
            )
        )
        choices[d] = [
            {
                "plan": original,
                "times": candidate["departures"][d],
                "operation": "keep",
                "quality": directional_quality(direction, candidate["departures"][d], settings),
            }
        ] + ranked[:4]
    proposals = []
    for pair in product(*(choices[d] for d in DIRECTIONS)):
        if expired():
            break
        changed = sum(v["operation"] != "keep" for v in pair)
        if not changed:
            continue
        times = {d: v["times"] for d, v in zip(DIRECTIONS, pair, strict=True)}
        lost, bridges, closed, gain, starts_closed = timing(times)
        if gain <= 0:
            continue
        plans = {d: v["plan"] for d, v in zip(DIRECTIONS, pair, strict=True)}
        waiting = sum(v["quality"]["waiting_integral"] for v in pair)
        local = sum(v["quality"]["positive_passenger_minutes"] for v in pair)
        consistency = sum(len(v["plan"]) for v in pair)
        priority = (
            evidence["required_fleet"],
            -starts_closed,
            lost,
            -bridges,
            -closed,
            -gain,
            waiting,
            local,
            consistency,
        )
        proposals.append(
            {
                "plans": plans,
                "priority": priority,
                "operation": "fleet:"
                + (
                    "coordinated"
                    if changed == 2
                    else next(v["operation"] for v in pair if v["operation"] != "keep")
                ),
                "direction": "both",
                "guided": False,
                "fleet_guidance": {
                    "parent_id": candidate["id"],
                    "parent_required_fleet": candidate["quality"]["required_fleet"],
                    "directions_changed": changed,
                    "matched_links_lost": lost,
                    "residual_bridges_closed": bridges,
                    "missed_connections_closed": closed,
                    "unmatched_start_connections_closed": starts_closed,
                    "timing_gain": gain,
                    "operations": [v["operation"] for v in pair],
                    "feasibility_prediction": False,
                },
            }
        )
    proposals.sort(key=lambda p: (p["priority"], json.dumps(p["plans"], sort_keys=True)))
    evidence["revision_proposals"] = len(proposals)
    evidence["revision_generation_complete"] = not expired()
    return evidence, proposals[:12]

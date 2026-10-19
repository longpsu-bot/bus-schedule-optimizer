"""Bounded timetable diversity and explicit local-service comparisons for the MVP."""

from __future__ import annotations

import json
from time import perf_counter as monotonic

from .input import DIRECTIONS
from .quality import waiting


def pair_key(data, departures, settings, review_settings):
    # Include all authorities, demand and review policy; never share p50/p75 results.
    return json.dumps([data, departures, settings, review_settings], sort_keys=True)


def directional_quality(direction, times, settings, baseline=None):
    buckets = direction["demand"]
    local = [waiting(times, [b]) for b in buckets]
    baseline = baseline or [waiting(direction["baseline"], [b]) for b in buckets]
    deterioration = [
        (c["wait"] or 0) - (b["wait"] or 0) for c, b in zip(local, baseline, strict=True)
    ]
    material = [
        delta
        for delta, b in zip(deterioration, baseline, strict=True)
        if delta
        > max(
            settings.get("wait_materiality_minutes", 0.05),
            (b["wait"] or 0) * settings.get("wait_materiality_relative", 0.01),
        )
        + 1e-9
    ]
    violations = sum(
        max(
            (
                z - a
                for a, z in zip(times, times[1:], strict=False)
                if a < w["end"] and z > w["start"]
            ),
            default=0,
        )
        > w["max_gap"]
        or sum(w["start"] <= t < w["end"] for t in times) < w.get("minimum_departures", 0)
        for w in direction.get("protected_windows", [])
    )
    protected_gap = max(
        (
            z - a
            for w in direction.get("protected_windows", [])
            for a, z in zip(times, times[1:], strict=False)
            if a < w["end"] and z > w["start"]
        ),
        default=0,
    )
    return {
        "protection_violations": violations,
        "maximum_protected_gap": protected_gap,
        "waiting_integral": sum(c["integral"] for c in local),
        "maximum_material_deterioration": max(material, default=0),
        "positive_passenger_minutes": sum(
            max(0, c["integral"] - b["integral"]) for c, b in zip(local, baseline, strict=True)
        ),
    }


def retain_settlements(direction, candidates, boundary, settings, deadline=None):
    """Keep boundary, passenger, local-service and timing alternatives, without dominance pruning."""
    unique = {tuple(c["departures"]): c for c in candidates}
    baseline = [waiting(direction["baseline"], [b]) for b in direction["demand"]]
    for c in unique.values():
        if deadline is not None and monotonic() >= deadline:
            raise TimeoutError("Directional diversity scoring reached route deadline")
        c["directional_quality"] = directional_quality(
            direction, c["departures"], settings, baseline
        )
    if deadline is not None and monotonic() >= deadline:
        raise TimeoutError("Directional diversity scoring reached route deadline")
    legal = [c for c in unique.values() if not c["directional_quality"]["protection_violations"]]
    retained = []

    def keep(c):
        if c not in retained and len(retained) < settings["directional_settlements"]:
            retained.append(c)

    boundary_candidate = unique[tuple(boundary)]
    if boundary_candidate in legal:
        keep(boundary_candidate)
    if legal:
        keep(
            min(
                legal, key=lambda c: (c["directional_quality"]["waiting_integral"], c["departures"])
            )
        )
        keep(
            min(
                legal,
                key=lambda c: (
                    c["directional_quality"]["maximum_protected_gap"],
                    c["directional_quality"]["waiting_integral"],
                    c["departures"],
                ),
            )
        )
        keep(
            min(
                legal,
                key=lambda c: (
                    c["directional_quality"]["maximum_material_deterioration"],
                    c["directional_quality"]["positive_passenger_minutes"],
                    c["directional_quality"]["waiting_integral"],
                    c["departures"],
                ),
            )
        )
    while len(retained) < min(settings["directional_settlements"], len(legal)):
        remaining = [c for c in legal if c not in retained]
        keep(
            min(
                remaining,
                key=lambda c: (
                    -min(
                        sum(
                            abs(a - b)
                            for a, b in zip(c["departures"], r["departures"], strict=True)
                        )
                        for r in retained
                    ),
                    c["directional_quality"]["waiting_integral"],
                    c["departures"],
                ),
            )
        )
    return retained


def pair_priority(pair, fleet_feedback):
    """Ordering hints only: no directional fleet estimate can reject a pair."""
    quality = [c.get("directional_quality", {}) for c in pair]
    pressure = sum(
        sum(f["interval_start"] <= t < f["interval_end"] for t in c["departures"]) * f["severity"]
        for d, c in zip(DIRECTIONS, pair, strict=True)
        for f in fleet_feedback
        if f["direction"] == d and f["problem"] == "FLEET_PRESSURE"
    )
    return (
        pressure,
        max((q.get("maximum_material_deterioration", 0) for q in quality), default=0),
        sum(q.get("positive_passenger_minutes", 0) for q in quality),
        sum(q.get("waiting_integral", 0) for q in quality),
        tuple(pair[0]["departures"]),
        tuple(pair[1]["departures"]),
    )


def local_evidence(data, candidate, baseline, review_settings, settings):
    from .review import _buckets, warning_policy

    rows = _buckets(data, baseline, candidate, warning_policy(review_settings))
    material = [
        b["waiting_difference_minutes"]
        for b in candidate["quality"]["demand_buckets"]
        if b["waiting_difference_minutes"] is not None
        and b["waiting_difference_minutes"]
        > max(
            settings.get("wait_materiality_minutes", 0.05),
            (b["baseline_waiting_minutes"] or 0) * settings.get("wait_materiality_relative", 0.01),
        )
        + 1e-9
    ]
    summary = {
        "maximum_material_deterioration": max(material, default=0),
        "positive_passenger_minutes": sum(
            max(0, b["excess_waiting_passenger_minutes"])
            for b in candidate["quality"]["demand_buckets"]
        ),
        "review_warning_intervals": sum(bool(b["warnings"]) for b in rows),
        "review_warning_count": sum(len(b["warnings"]) for b in rows),
        "maximum_warning_wait_increase": max(
            (b["waiting_difference_minutes"] or 0 for b in rows if b["warnings"]), default=0
        ),
        "maximum_warning_gap": max(
            (b["candidate"]["maximum_intersecting_headway"] for b in rows if b["warnings"]),
            default=0,
        ),
        "directional_waiting_minutes": candidate["quality"]["directional_waiting_minutes"],
        "warnings_are_hard_constraints": False,
    }
    candidate["local_service"] = summary
    return summary


def local_key(candidate):
    q = candidate.get("local_service", {})
    return tuple(
        q.get(k, 0)
        for k in (
            "maximum_material_deterioration",
            "positive_passenger_minutes",
            "review_warning_intervals",
            "review_warning_count",
            "maximum_warning_wait_increase",
            "maximum_warning_gap",
        )
    )

"""Exact bucket-arrival integration and explicit hierarchical product selection."""

from __future__ import annotations

from bisect import bisect_left

from .circulation import assign_fleet
from .input import DIRECTIONS


def waiting(departures, buckets):
    integral, served, unserved = 0.0, 0.0, 0.0
    maximum_boardings = 0.0
    for b in buckets:
        rate = b["passengers"] / (b["end"] - b["start"])
        start, end = max(b["start"], departures[0]), min(b["end"], departures[-1])
        served += rate * max(0, end - start)
        unserved += rate * ((b["end"] - b["start"]) - max(0, end - start))
        for left, right in zip(departures, departures[1:], strict=False):
            a, z = max(start, left), min(end, right)
            if a < z:
                integral += rate * ((right - a) ** 2 - (right - z) ** 2) / 2
    for left, right in zip(departures, departures[1:], strict=False):
        boarding = sum(
            b["passengers"]
            * max(0, min(right, b["end"]) - max(left, b["start"]))
            / (b["end"] - b["start"])
            for b in buckets
        )
        maximum_boardings = max(maximum_boardings, boarding)
    return {
        "integral": integral,
        "passengers": served,
        "unserved": unserved,
        "wait": integral / served if served else None,
        "maximum_boardings": maximum_boardings,
    }


def demand_fit_diagnostics(departures, buckets):
    """Port U7 point SSE/TE and V3 continuous TV equivalence without selector gates."""
    total = sum(b["passengers"] for b in buckets)
    if not total:
        return {"sse": None, "te": None, "continuous_exposure": None}
    shares = [b["passengers"] / total for b in buckets]
    counts = [
        bisect_left(departures, b["end"]) - bisect_left(departures, b["start"]) for b in buckets
    ]
    # A supplied demand grid may end exactly at the protected final departure.
    if buckets[-1]["end"] == departures[-1]:
        counts[-1] += 1
    residuals = [
        count / len(departures) - share for count, share in zip(counts, shares, strict=True)
    ]
    breakpoints = sorted(
        {
            buckets[0]["start"],
            buckets[-1]["end"],
            *departures,
            *(b["start"] for b in buckets),
            *(b["end"] for b in buckets),
        }
    )
    integral = 0.0
    for left, right in zip(breakpoints, breakpoints[1:], strict=False):
        density = next(
            (
                share / (b["end"] - b["start"])
                for b, share in zip(buckets, shares, strict=True)
                if b["start"] <= left < b["end"]
            ),
            0,
        )
        service = next(
            (
                1 / (b - a) / (len(departures) - 1)
                for a, b in zip(departures, departures[1:], strict=False)
                if a <= left < b
            ),
            0,
        )
        integral += (right - left) * abs(service - density)
    return {
        "sse": sum(r * r for r in residuals),
        "te": len(departures) * 0.5 * sum(abs(r) for r in residuals),
        "continuous_exposure": len(departures) * 0.5 * integral,
    }


def evaluate(data, departures, regimes, fleet=None, settings=None):
    settings = settings or {}
    failures = []
    direction_wait, outside, totals, exposure = {}, {}, {}, {}
    protected = []
    sse = te = continuous = 0.0
    maximum_boardings = 0.0
    for direction in DIRECTIONS:
        d = data["directions"][direction]
        times = departures[direction]
        if (
            len(times) != d["trip_count"]
            or times != sorted(set(times))
            or any(type(t) is not int for t in times)
            or times[0] != d["first"]
            or times[-1] != d["last"]
            or any(not d["operating_start"] <= t <= d["operating_end"] for t in times)
        ):
            failures.append(f"{direction}: TIMETABLE_AUTHORITY")
        w = waiting(times, d["demand"])
        direction_wait[direction], outside[direction], totals[direction] = (
            w["wait"],
            w["unserved"],
            w["passengers"],
        )
        exposure[direction] = w["integral"]
        maximum_boardings = max(maximum_boardings, w["maximum_boardings"])
        for window in d["protected_windows"]:
            gaps = [
                b - a
                for a, b in zip(times, times[1:], strict=False)
                if a < window["end"] and b > window["start"]
            ]
            gap = max(gaps, default=0)
            count = sum(window["start"] <= t < window["end"] for t in times)
            protected.append(
                {
                    "direction": direction,
                    "start": window["start"],
                    "end": window["end"],
                    "maximum_gap": gap,
                    "departures": count,
                }
            )
            if gap > window["max_gap"] or count < window.get("minimum_departures", 0):
                failures.append(f"{direction}: PROTECTED_SERVICE")
        diagnostics = demand_fit_diagnostics(times, d["demand"])
        sse += diagnostics["sse"] or 0
        te += diagnostics["te"] or 0
        continuous += diagnostics["continuous_exposure"] or 0
    fleet = fleet or assign_fleet(data, departures, settings=settings)
    fleet_ok = fleet["status"] == "EXACT" and fleet["within_fleet_ceiling"]
    if not fleet_ok:
        failures.append("FLEET_CIRCULATION_OR_CEILING")
    for direction in DIRECTIONS:
        blocks = [r for r in regimes if r.get("direction") == direction]
        if regimes and not blocks:
            failures.append("REGIME_DIRECTION_MISSING")
        if blocks:
            gaps = []
            for r in blocks:
                if (
                    r["headway_minutes"] < 1
                    or type(r["headway_minutes"]) is not int
                    or r["gap_count"] < settings.get("minimum_internal_gaps", 2)
                    or r["end_time"] - r["start_time"] < settings.get("minimum_regime_minutes", 30)
                    or r["end_time"] - r["start_time"] != r["headway_minutes"] * r["gap_count"]
                ):
                    failures.append("REGIME_UNIFORMITY_OR_MEANINGFULNESS")
                gaps.extend([r["headway_minutes"]] * r["gap_count"])
            actual = [
                b - a
                for a, b in zip(departures[direction], departures[direction][1:], strict=False)
            ]
            if (
                gaps != actual
                or sum(r["planned_departure_count"] for r in blocks) != len(departures[direction])
                or blocks[0]["start_time"] != departures[direction][0]
                or blocks[-1]["end_time"] != departures[direction][-1]
                or any(
                    a["end_time"] != b["start_time"]
                    for a, b in zip(blocks, blocks[1:], strict=False)
                )
            ):
                failures.append("REGIME_BOUNDARY_COVERAGE")
    jumps = [
        abs(a["headway_minutes"] - b["headway_minutes"])
        for d in DIRECTIONS
        for a, b in zip(
            [r for r in regimes if r.get("direction") == d],
            [r for r in regimes if r.get("direction") == d][1:],
            strict=False,
        )
    ]
    if (
        settings.get("maximum_transition_jump") is not None
        and max(jumps, default=0) > settings["maximum_transition_jump"]
    ):
        failures.append("HARD_TRANSITION_JUMP")
    capacity = None
    if data.get("vehicle_capacity") is not None:
        limit = data["vehicle_capacity"] * data["maximum_load_factor"]
        capacity = {
            "maximum_modeled_boardings": maximum_boardings,
            "planning_limit": limit,
            "maximum_load_factor": data["maximum_load_factor"],
            "policy": data["capacity_policy"],
            "within_policy": maximum_boardings <= limit + 1e-9,
            "basis": "uniform-arrival boarding exposure; not observed onboard load",
        }
        if data["capacity_policy"] == "hard" and not capacity["within_policy"]:
            failures.append("CAPACITY_PLANNING_POLICY")
    by_id = {t["trip_id"]: t for t in fleet.get("trips", [])}
    terminal_wait = sum(
        by_id[b]["departure"] - by_id[a]["ready"]
        for chain in fleet.get("chains", [])
        for a, b in zip(chain, chain[1:], strict=False)
    )
    response = {}
    for direction in DIRECTIONS:
        evidence = []
        for r in [r for r in regimes if r.get("direction") == direction]:
            duration = r["end_time"] - r["start_time"]
            mass = sum(
                b["passengers"]
                * max(0, min(r["end_time"], b["end"]) - max(r["start_time"], b["start"]))
                / (b["end"] - b["start"])
                for b in data["directions"][direction]["demand"]
            )
            evidence.append(
                {
                    "start": r["start_time"],
                    "end": r["end_time"],
                    "passengers_per_minute": mass / duration,
                    "departures_per_hour": 60 / r["headway_minutes"],
                }
            )
        aligned = sum(
            (b["passengers_per_minute"] - a["passengers_per_minute"])
            * (b["departures_per_hour"] - a["departures_per_hour"])
            > 0
            for a, b in zip(evidence, evidence[1:], strict=False)
        )
        response[direction] = (
            {
                "regimes": evidence,
                "aligned_transitions": aligned,
                "transitions": max(0, len(evidence) - 1),
            }
            if evidence
            else None
        )
    passengers = sum(totals.values())
    return {
        "hard_constraints_pass": not failures,
        "failures": sorted(set(failures)),
        "maximum_protected_gap": max((p["maximum_gap"] for p in protected), default=0),
        "protected_windows": protected,
        "directional_waiting_minutes": direction_wait,
        "waiting_minutes": sum(exposure.values()) / passengers if passengers else None,
        "modeled_passengers": totals,
        "outside_service_passengers": outside,
        "required_fleet": fleet.get("required_fleet"),
        "regime_count": len(regimes),
        "transition_jump": sum(jumps),
        "terminal_wait": terminal_wait,
        "tail_gap": max(departures[d][-1] - departures[d][-2] for d in DIRECTIONS),
        "capacity": capacity,
        "demand_response": response,
        "sse": sse,
        "te": te,
        "continuous_exposure": continuous,
        "diagnostic_definition": "U7 point-share SSE; TE=N/2*L1 residual; V3 continuous=N/2*integral(abs(service density-demand density)), summed across directions; final grid endpoint belongs to last bucket",
        "waiting_model": "modeled scheduled wait, uniform bucket arrivals; outside first/last disclosed and excluded, no invented next-day service",
    }


def select_candidate(candidates, settings):
    feasible = [c for c in candidates if c["quality"]["hard_constraints_pass"]]
    if not feasible:
        return None
    protected = min(c["quality"]["maximum_protected_gap"] for c in feasible)
    feasible = [c for c in feasible if c["quality"]["maximum_protected_gap"] == protected]
    best_wait = min((c["quality"]["waiting_minutes"] or 0) for c in feasible)
    tolerance = max(
        settings.get("wait_absolute_tolerance", 0.10),
        best_wait * settings.get("wait_relative_tolerance", 0.02),
    )
    equivalent = [
        c
        for c in feasible
        if (c["quality"]["waiting_minutes"] or 0) <= best_wait + tolerance + 1e-9
    ]
    return min(
        equivalent,
        key=lambda c: (
            c["quality"]["required_fleet"],
            c["quality"]["regime_count"],
            c["quality"]["transition_jump"],
            c["quality"]["terminal_wait"],
            c["quality"]["tail_gap"],
            tuple(c["departures"]["outbound"]),
            tuple(c["departures"]["inbound"]),
            c["id"],
        ),
    )

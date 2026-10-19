"""Exact bucket-arrival integration and explicit hierarchical product selection."""

from __future__ import annotations

from bisect import bisect_left

from .circulation import assign_fleet
from .input import DIRECTIONS


def _coverage(times, start, end):
    return bisect_left(times, end) - bisect_left(times, start) + (times[-1] == end)


def _context(regimes, direction, start, end):
    relevant = [
        (i, r)
        for i, r in enumerate(regimes)
        if r["direction"] == direction and r["start_time"] < end and r["end_time"] > start
    ]
    return {
        "candidate_regime_indices": [i for i, _ in relevant],
        "nearby_regimes": [
            {
                "start": r["start_time"],
                "end": r["end_time"],
                "headway_minutes": r["headway_minutes"],
            }
            for _, r in relevant
        ],
    }


def feedback_key(item):
    return (
        item["priority"],
        -item["severity"],
        item["direction"],
        item["interval_start"],
        item["problem"],
    )


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
    bucket_rows, intervals, service_feedback = [], [], []
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
        for left, right in zip(times, times[1:], strict=False):
            boarding = sum(
                b["passengers"]
                * max(0, min(right, b["end"]) - max(left, b["start"]))
                / (b["end"] - b["start"])
                for b in d["demand"]
            )
            interval = {
                "direction": direction,
                "interval_start": left,
                "interval_end": right,
                "gap_minutes": right - left,
                "modeled_boardings": boarding,
                **_context(regimes, direction, left, right),
            }
            intervals.append(interval)
            if data.get("vehicle_capacity") is not None:
                limit = data["vehicle_capacity"] * data["maximum_load_factor"]
                interval.update(threshold=limit, excess_boardings=max(0, boarding - limit))
                if boarding > limit + 1e-9:
                    service_feedback.append(
                        interval
                        | {
                            "problem": "CAPACITY_PROXY",
                            "priority": 1,
                            "severity": boarding - limit,
                            "severity_units": "modeled_boardings",
                            "hard": data["capacity_policy"] == "hard",
                            "recommended_revision_types": [
                                "REALLOCATE_TRIP",
                                "SHIFT_BOUNDARY",
                                "SPLIT",
                            ],
                        }
                    )
        for b in d["demand"]:
            local = waiting(times, [b])
            baseline = waiting(d["baseline"], [b])
            delta = (
                local["wait"] - baseline["wait"]
                if local["wait"] is not None and baseline["wait"] is not None
                else None
            )
            row = {
                "direction": direction,
                "interval_start": b["start"],
                "interval_end": b["end"],
                "demand_passengers": b["passengers"],
                "served_modeled_passengers": local["passengers"],
                "outside_service_passengers": local["unserved"],
                "baseline_departures": _coverage(d["baseline"], b["start"], b["end"]),
                "candidate_departures": _coverage(times, b["start"], b["end"]),
                "waiting_integral": local["integral"],
                "waiting_minutes": local["wait"],
                "baseline_waiting_minutes": baseline["wait"],
                "waiting_difference_minutes": delta,
                "waiting_difference_percent": 100 * delta / baseline["wait"]
                if delta is not None and baseline["wait"]
                else None,
                "excess_waiting_passenger_minutes": local["integral"] - baseline["integral"],
                "maximum_intersecting_gap": max(
                    (
                        z - a
                        for a, z in zip(times, times[1:], strict=False)
                        if a < b["end"] and z > b["start"]
                    ),
                    default=0,
                ),
                **_context(regimes, direction, b["start"], b["end"]),
            }
            bucket_rows.append(row)
            materiality = max(
                settings.get("wait_materiality_minutes", 0.05),
                (baseline["wait"] or 0) * settings.get("wait_materiality_relative", 0.01),
            )
            excess = delta is not None and delta > materiality + 1e-9
            if local["integral"] > 0:
                service_feedback.append(
                    row
                    | {
                        "problem": "EXCESS_WAIT_VS_BASELINE" if excess else "WAIT_OPPORTUNITY",
                        "priority": 2 if excess else 3,
                        "severity": max(0, row["excess_waiting_passenger_minutes"])
                        if excess
                        else local["integral"],
                        "severity_units": "passenger_minutes",
                        "hard": False,
                        "recommended_revision_types": [
                            "REALLOCATE_TRIP",
                            "SHIFT_BOUNDARY",
                            "SPLIT",
                        ],
                    }
                )
        for window in d["protected_windows"]:
            gaps = [
                (a, b)
                for a, b in zip(times, times[1:], strict=False)
                if a < window["end"] and b > window["start"]
            ]
            gap = max((b - a for a, b in gaps), default=0)
            count = sum(window["start"] <= t < window["end"] for t in times)
            protected.append(
                {
                    "direction": direction,
                    "start": window["start"],
                    "end": window["end"],
                    "maximum_gap": gap,
                    "departures": count,
                    "maximum_allowed_gap": window["max_gap"],
                    "minimum_departures": window.get("minimum_departures", 0),
                    "responsible_gaps": [
                        {"start": a, "end": b, "gap_minutes": b - a}
                        for a, b in gaps
                        if b - a > window["max_gap"]
                    ],
                    "pass": gap <= window["max_gap"]
                    and count >= window.get("minimum_departures", 0),
                }
            )
            if gap > window["max_gap"] or count < window.get("minimum_departures", 0):
                failures.append(f"{direction}: PROTECTED_SERVICE")
                service_feedback.append(
                    {
                        "direction": direction,
                        "interval_start": window["start"],
                        "interval_end": window["end"],
                        "problem": "PROTECTED_SERVICE",
                        "priority": 0,
                        "hard": True,
                        "severity": gap - window["max_gap"]
                        if gap > window["max_gap"]
                        else window.get("minimum_departures", 0) - count,
                        "severity_units": "gap_minutes"
                        if gap > window["max_gap"]
                        else "missing_departures",
                        "responsible_gaps": protected[-1]["responsible_gaps"],
                        "missing_departures": max(0, window.get("minimum_departures", 0) - count),
                        **_context(regimes, direction, window["start"], window["end"]),
                        "recommended_revision_types": [
                            "REALLOCATE_TRIP",
                            "SHIFT_BOUNDARY",
                            "SPLIT",
                        ],
                    }
                )
        diagnostics = demand_fit_diagnostics(times, d["demand"])
        sse += diagnostics["sse"] or 0
        te += diagnostics["te"] or 0
        continuous += diagnostics["continuous_exposure"] or 0
    fleet = fleet or assign_fleet(data, departures, settings=settings)
    fleet_ok = fleet["status"] == "EXACT" and fleet["within_fleet_ceiling"]
    if not fleet_ok:
        failures.append("FLEET_CIRCULATION_OR_CEILING")
        if fleet["status"] == "EXACT":
            trips = fleet["trips"]
            peak = max(
                (t["departure"] for t in trips),
                key=lambda minute: sum(t["departure"] <= minute < t["ready"] for t in trips),
            )
            overlapping = [t["trip_id"] for t in trips if t["departure"] <= peak < t["ready"]]
            for direction in DIRECTIONS:
                start, end = (
                    max(data["directions"][direction]["first"], peak - 15),
                    min(data["directions"][direction]["last"], peak + 15),
                )
                if start < end:
                    service_feedback.append(
                        {
                            "direction": direction,
                            "interval_start": start,
                            "interval_end": end,
                            "problem": "FLEET_PRESSURE",
                            "priority": 0,
                            "hard": True,
                            "severity": fleet["required_fleet"] - data["fleet_ceiling"],
                            "severity_units": "vehicles",
                            "required_fleet": fleet["required_fleet"],
                            "fleet_ceiling": data["fleet_ceiling"],
                            "peak_minute": peak,
                            "overlapping_trip_ids": overlapping,
                            "basis": "Exact fleet excess; concurrent runtime/layover peak locates a revision opportunity, not a fleet prediction",
                            **_context(regimes, direction, start, end),
                            "recommended_revision_types": [
                                "SHIFT_BOUNDARY",
                                "MERGE",
                                "REALLOCATE_TRIP",
                            ],
                        }
                    )
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
    actual_jumps = [
        abs((c - b) - (b - a))
        for d in DIRECTIONS
        for a, b, c in zip(departures[d], departures[d][1:], departures[d][2:], strict=False)
    ]
    if (
        settings.get("maximum_transition_jump") is not None
        and max(actual_jumps, default=0) > settings["maximum_transition_jump"]
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
            "physical_capacity_passengers": data["vehicle_capacity"],
            "actual_load_factor_certified": False,
            "certification_limitation": "Stop-level boarding, alighting and onboard occupancy evidence unavailable",
            "violations": sorted(
                [i for i in intervals if i.get("excess_boardings", 0) > 1e-9],
                key=lambda i: (-i["excess_boardings"], i["direction"], i["interval_start"]),
            ),
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
    for row in bucket_rows:
        row["waiting_contribution_minutes"] = (
            row["waiting_integral"] / passengers if passengers else None
        )
        row["protected_service_violations"] = [
            p
            for p in protected
            if p["direction"] == row["direction"]
            and not p["pass"]
            and p["start"] < row["interval_end"]
            and p["end"] > row["interval_start"]
        ]
        row["maximum_modeled_boardings"] = max(
            (
                i["modeled_boardings"]
                for i in intervals
                if i["direction"] == row["direction"]
                and i["interval_start"] < row["interval_end"]
                and i["interval_end"] > row["interval_start"]
            ),
            default=0,
        )
        row["capacity_planning_threshold"] = capacity["planning_limit"] if capacity else None
    baseline_integral = sum(
        waiting(data["directions"][d]["baseline"], data["directions"][d]["demand"])["integral"]
        for d in DIRECTIONS
    )
    baseline_wait = baseline_integral / passengers if passengers else None
    combined_wait = sum(exposure.values()) / passengers if passengers else None
    return {
        "hard_constraints_pass": not failures,
        "operational_certification": "COMPLETE"
        if fleet["status"] in {"EXACT", "INITIAL_STOCK_INFEASIBLE"}
        else "INCOMPLETE",
        "proven_hard_failures": sorted(
            set(
                f
                for f in failures
                if f != "FLEET_CIRCULATION_OR_CEILING"
                or fleet["status"] in {"EXACT", "INITIAL_STOCK_INFEASIBLE"}
            )
        ),
        "failures": sorted(set(failures)),
        "maximum_protected_gap": max((p["maximum_gap"] for p in protected), default=0),
        "protected_windows": protected,
        "directional_waiting_minutes": direction_wait,
        "waiting_minutes": combined_wait,
        "waiting_difference_minutes": combined_wait - baseline_wait
        if combined_wait is not None
        else None,
        "waiting_difference_percent": 100 * (combined_wait - baseline_wait) / baseline_wait
        if baseline_wait
        else None,
        "modeled_passengers": totals,
        "outside_service_passengers": outside,
        "required_fleet": fleet.get("required_fleet"),
        "regime_count": len(regimes) if regimes else None,
        "transition_jump": sum(actual_jumps),
        "maximum_transition_jump": max(actual_jumps, default=0),
        "maximum_headway": max(
            (
                b - a
                for d in DIRECTIONS
                for a, b in zip(departures[d], departures[d][1:], strict=False)
            ),
            default=0,
        ),
        "directional_tail_gaps": {d: departures[d][-1] - departures[d][-2] for d in DIRECTIONS},
        "terminal_wait": terminal_wait,
        "tail_gap": max(departures[d][-1] - departures[d][-2] for d in DIRECTIONS),
        "capacity": capacity,
        "departure_intervals": intervals,
        "demand_buckets": bucket_rows,
        "service_feedback": sorted(service_feedback, key=feedback_key),
        "protected_service_certified": bool(protected) and all(p["pass"] for p in protected),
        "protection_basis": "Explicit configured windows"
        if protected
        else "No protected windows supplied; only exact endpoints checked",
        "demand_basis": data["demand_basis"],
        "total_bucket_demand_passengers": sum(
            b["passengers"] for d in DIRECTIONS for b in data["directions"][d]["demand"]
        ),
        "demand_response": response,
        "sse": sse,
        "te": te,
        "continuous_exposure": continuous,
        "diagnostic_definition": "U7 point-share SSE; TE=N/2*L1 residual; V3 continuous=N/2*integral(abs(service density-demand density)), summed across directions; final grid endpoint belongs to last bucket",
        "waiting_model": "modeled scheduled wait, uniform bucket arrivals; outside first/last disclosed and excluded, no invented next-day service",
    }


def change_justification(candidate, baseline, settings):
    """Explicit cases, no weighted composite and no secondary-only change rationale."""
    q, b = candidate["quality"], baseline["quality"]
    evidence = {"justified": False, "reason": "CANDIDATE_HARD_CONSTRAINT_FAILURE"}
    if not q["hard_constraints_pass"]:
        return evidence
    if not b["hard_constraints_pass"]:
        if b.get("operational_certification") == "INCOMPLETE" and not b.get("proven_hard_failures"):
            return {"justified": False, "reason": "BASELINE_CERTIFICATION_INCOMPLETE"}
        return {"justified": True, "reason": "REPLACE_NONCOMPLIANT_BASELINE"}
    bw, cw = b["waiting_minutes"], q["waiting_minutes"]
    band = max(
        settings.get("wait_absolute_tolerance", 0.10),
        (bw or 0) * settings.get("wait_relative_tolerance", 0.02),
    )
    materiality = max(
        settings.get("wait_materiality_minutes", 0.05),
        (bw or 0) * settings.get("wait_materiality_relative", 0.01),
    )
    evidence.update(
        reason="NO_MATERIAL_SERVICE_BENEFIT_OR_FLEET_SAVING",
        waiting_equivalence_minutes=band,
        waiting_materiality_minutes=materiality,
        waiting_difference_minutes=cw - bw if cw is not None and bw is not None else None,
        fleet_difference=q["required_fleet"] - b["required_fleet"],
    )
    protected_pairs = list(
        zip(q.get("protected_windows", []), b.get("protected_windows", []), strict=True)
    )
    protected_ok = all(c["maximum_gap"] <= old["maximum_gap"] for c, old in protected_pairs)
    protection_improved = any(
        old["maximum_gap"] - c["maximum_gap"] >= 1 for c, old in protected_pairs
    )
    if cw is None or bw is None:
        evidence["reason"] = "WAIT_COMPARISON_UNAVAILABLE"
        if (
            q.get("total_bucket_demand_passengers") == b.get("total_bucket_demand_passengers") == 0
            and protected_ok
            and protection_improved
            and q["required_fleet"] <= b["required_fleet"]
        ):
            evidence.update(justified=True, reason="MATERIAL_PROTECTED_SERVICE_IMPROVEMENT")
        return evidence
    directional_ok = all(
        q["directional_waiting_minutes"][d] is not None
        and q["directional_waiting_minutes"][d]
        <= b["directional_waiting_minutes"][d]
        + max(
            settings.get("wait_absolute_tolerance", 0.10),
            b["directional_waiting_minutes"][d] * settings.get("wait_relative_tolerance", 0.02),
        )
        + 1e-9
        for d in DIRECTIONS
        if b["directional_waiting_minutes"].get(d) is not None
    )
    if cw > bw + band + 1e-9 or not directional_ok or not protected_ok:
        evidence["reason"] = "SERVICE_DETERIORATION_EXCEEDS_EQUIVALENCE"
    elif q["required_fleet"] > b["required_fleet"]:
        evidence["reason"] = "FLEET_INCREASE_NOT_AUTHORIZED"
    elif bw - cw > materiality + 1e-9:
        evidence.update(justified=True, reason="MATERIAL_PASSENGER_WAIT_IMPROVEMENT")
    elif protection_improved:
        evidence.update(justified=True, reason="MATERIAL_PROTECTED_SERVICE_IMPROVEMENT")
    elif q["required_fleet"] < b["required_fleet"]:
        evidence.update(justified=True, reason="FLEET_SAVING_WITH_EQUIVALENT_WAIT")
    return evidence


def select_candidate(candidates, settings, baseline=None):
    feasible = [c for c in candidates if c["quality"]["hard_constraints_pass"]]
    if baseline is not None:
        feasible = [c for c in feasible if change_justification(c, baseline, settings)["justified"]]
    if not feasible:
        return (
            baseline
            if baseline is not None and baseline["quality"]["hard_constraints_pass"]
            else None
        )
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

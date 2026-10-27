"""Read-only vehicle recovery and conditional crew-break opportunities, never a roster."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import groupby
from statistics import median

from .input import DIRECTIONS, number, runtime_at


def validate_policies(policies):
    """Require explicit, separate role/task/reserve assumptions; missing is unknown."""
    if not isinstance(policies, dict):
        raise ValueError("policy must be an object; use {} for unknown policy")
    if not policies:
        return {}
    if set(policies) != {"authority", "short_turnaround_minutes", "roles"}:
        raise ValueError("policy requires authority, short_turnaround_minutes and roles")
    if not isinstance(policies["authority"], str) or policies["authority"] not in {
        "ILLUSTRATIVE",
        "OPERATOR_SUPPLIED_UNVERIFIED",
    }:
        raise ValueError("unsupported policy authority; this review cannot certify policy")
    number(policies["short_turnaround_minutes"], "short_turnaround_minutes", 0.01)
    if (
        not isinstance(policies["roles"], dict)
        or not policies["roles"]
        or set(policies["roles"]) - {"driver", "attendant"}
    ):
        raise ValueError("roles must explicitly name driver and/or attendant")
    for role, windows in policies["roles"].items():
        names = set()
        if not isinstance(windows, list) or not windows:
            raise ValueError(f"{role}: break policies missing")
        for w in windows:
            if not isinstance(w, dict) or set(w) != {
                "name",
                "start",
                "end",
                "minutes",
                "tasks_after",
                "tasks_before",
                "reserve",
                "handover",
            }:
                raise ValueError("every break policy requires all time and task assumptions")
            if not isinstance(w["name"], str) or not w["name"] or w["name"] in names:
                raise ValueError("break policy name must be nonempty and unique per role")
            names.add(w["name"])
            for key in set(w) - {"name"}:
                number(w[key], f"{role}.{w['name']}.{key}")
            if w["minutes"] <= 0 or w["end"] - w["start"] < w["minutes"]:
                raise ValueError("continuous break must be positive and fit its window")
        previous_end = None
        for w in sorted(windows, key=lambda w: w["start"]):
            if previous_end is not None and w["start"] < previous_end:
                raise ValueError("overlapping break windows unsupported: avoid double coverage")
            previous_end = w["end"]
    return deepcopy(policies)


def illustrative_policies():
    """Sensitivity points only: no operator policy or legal clock windows supplied."""
    result = {}
    for label, task, reserve, meal, afternoon, meal_window, afternoon_window in (
        ("optimistic", 0, 0, 30, 15, (630, 870), (840, 1050)),
        ("illustrative", 5, 5, 30, 20, (660, 840), (840, 1020)),
        ("conservative", 10, 10, 45, 30, (690, 810), (870, 990)),
    ):
        # Windows do not overlap, so one interval cannot discharge two declared breaks.
        meal_window = (meal_window[0], min(meal_window[1], afternoon_window[0]))
        roles = {}
        for role in ("driver", "attendant"):
            roles[role] = [
                {
                    "name": name,
                    "start": window[0],
                    "end": window[1],
                    "minutes": minutes + (10 if role == "attendant" and name == "afternoon" else 0),
                    "tasks_after": task,
                    "tasks_before": task,
                    "reserve": reserve,
                    "handover": 5,
                }
                for name, minutes, window in (
                    ("meal", meal, meal_window),
                    ("afternoon", afternoon, afternoon_window),
                )
            ]
        result[label] = validate_policies(
            {"authority": "ILLUSTRATIVE", "short_turnaround_minutes": 10, "roles": roles}
        )
    return result


def _crew_opportunities(trips, intervals, windows, compatible):
    rows = []
    for w in windows:
        active = trips[0]["departure"] < w["end"] and trips[-1]["arrival"] > w["start"]
        fixed, relief = [], []
        for interval in intervals:
            # Technical time, tasks and reserved recovery are unavailable for modeled rest.
            start = max(
                w["start"],
                interval["arrival"]
                + interval["technical_turnaround"]
                + w["tasks_after"]
                + w["reserve"],
            )
            end = min(w["end"], interval["next_departure"] - w["tasks_before"])
            if compatible and end - start >= w["minutes"]:
                fixed.append(
                    {
                        "after_trip_id": interval["from_trip_id"],
                        "terminal": interval["terminal"],
                        "free_start": start,
                        "free_end": end,
                        "continuous_minutes": end - start,
                        "break_end_if_started_at_free_start": start + w["minutes"],
                        "reserved_recovery_minutes": w["reserve"],
                        "status": "CONDITIONALLY_POSSIBLE",
                    }
                )
            release = max(w["start"], interval["arrival"] + w["handover"])
            finish = release + w["minutes"]
            # Off-bus relief frees the old crew; it does not replace the vehicle recovery.
            if compatible and release <= interval["next_departure"] and finish <= w["end"]:
                covered = [
                    t["trip_id"]
                    for t in trips
                    if t["departure"] >= interval["next_departure"] and t["departure"] < finish
                ]
                if covered:
                    relief.append(
                        {
                            "after_trip_id": interval["from_trip_id"],
                            "terminal": interval["terminal"],
                            "handover_start": release - w["handover"],
                            "release": release,
                            "break_end": finish,
                            "substitute_trip_ids": covered,
                            "relief_staff_available": None,
                            "return_assignment": None,
                            "status": "CONDITIONALLY_POSSIBLE",
                        }
                    )
        rows.append(
            {
                "policy": deepcopy(w),
                "overlaps_vehicle_span": active,
                "fixed_vehicle_opportunities": fixed,
                "fixed_vehicle_status": "NOT_APPLICABLE_PROXY"
                if not active
                else "CONDITIONALLY_POSSIBLE"
                if fixed
                else "POTENTIAL_RISK",
                "relief_opportunities": relief,
                "relief_status": "NOT_APPLICABLE_PROXY"
                if not active
                else "CONDITIONALLY_POSSIBLE"
                if relief
                else "INSUFFICIENT_CREW_EVIDENCE",
                "relief_dependency": active and not fixed and bool(relief),
                "crew_assignment_status": "INSUFFICIENT_CREW_EVIDENCE",
            }
        )
    return rows


def analyze_chains(fleet, technical_turnaround, policies, *, runtime_data=None):
    """Keep vehicle assignment fixed; optionally recompute only arrivals under runtime stress."""
    policies = validate_policies(policies)
    if set(technical_turnaround) != set(DIRECTIONS):
        raise ValueError("technical turnaround must name both terminals")
    for value in technical_turnaround.values():
        number(value, "technical_turnaround")
    by_id = {t["trip_id"]: deepcopy(t) for t in fleet["trips"]}
    ids = [tid for chain in fleet["chains"] for tid in chain]
    if (
        len(by_id) != len(fleet["trips"])
        or len(ids) != len(set(ids))
        or set(ids) != set(by_id)
        or len(fleet["chains"]) != fleet["required_fleet"]
    ):
        raise ValueError("vehicle chain identity/coverage/count mismatch")
    for t in by_id.values():
        if t["direction"] not in DIRECTIONS:
            raise ValueError("unknown trip direction")
        for key in ("departure", "arrival"):
            number(t[key], key)
        if runtime_data is not None:
            t["source_arrival"] = t["arrival"]
            t["arrival"] = t["departure"] + runtime_at(
                runtime_data["directions"][t["direction"]], t["departure"]
            )
            destination = DIRECTIONS[1 - DIRECTIONS.index(t["direction"])]
            t["ready"] = t["arrival"] + technical_turnaround[destination]
        if t["arrival"] <= t["departure"]:
            raise ValueError("trip arrival must follow departure")
    chains, vehicles = [], set()
    threshold = policies.get("short_turnaround_minutes")
    for chain in fleet["chains"]:
        if not chain:
            raise ValueError("empty chain")
        trips = [by_id[tid] for tid in chain]
        vehicle = trips[0]["vehicle_id"]
        if vehicle in vehicles or any(t["vehicle_id"] != vehicle for t in trips):
            raise ValueError("vehicle identity differs within/between chains")
        vehicles.add(vehicle)
        intervals = []
        for previous, following in zip(trips, trips[1:], strict=False):
            if (
                previous["direction"] == following["direction"]
                or previous["departure"] >= following["departure"]
            ):
                raise ValueError("chain terminal/time continuity mismatch")
            terminal = following["direction"]
            dwell = following["departure"] - previous["arrival"]
            technical = technical_turnaround[terminal]
            intervals.append(
                {
                    "from_trip_id": previous["trip_id"],
                    "to_trip_id": following["trip_id"],
                    "terminal": terminal,
                    "arrival": previous["arrival"],
                    "next_departure": following["departure"],
                    "scheduled_dwell": dwell,
                    "technical_turnaround": technical,
                    "slack": dwell - technical,
                    "short": dwell < threshold if threshold is not None else None,
                }
            )
        short_run = max(
            (len(list(group)) for short, group in groupby(i["short"] for i in intervals) if short),
            default=0,
        )
        compatible = all(i["slack"] >= 0 for i in intervals)
        dwells = [i["scheduled_dwell"] for i in intervals]
        chains.append(
            {
                "vehicle_id": vehicle,
                "trip_count": len(trips),
                "trips": trips,
                "first_departure": trips[0]["departure"],
                "last_arrival": trips[-1]["arrival"],
                "span_minutes": trips[-1]["arrival"] - trips[0]["departure"],
                "driving_minutes": sum(t["arrival"] - t["departure"] for t in trips),
                "intervals": intervals,
                "minimum_dwell": min(dwells, default=None),
                "median_dwell": median(dwells) if dwells else None,
                "short_turnarounds": sum(bool(i["short"]) for i in intervals)
                if threshold is not None
                else None,
                "longest_short_run": short_run,
                "incompatible_connections": sum(i["slack"] < 0 for i in intervals),
                "minimum_slack": min((i["slack"] for i in intervals), default=None),
                "crew": {
                    role: _crew_opportunities(trips, intervals, windows, compatible)
                    for role, windows in policies.get("roles", {}).items()
                },
            }
        )
    intervals = [i for chain in chains for i in chain["intervals"]]
    dwells = sorted(i["scheduled_dwell"] for i in intervals)
    failures = sum(c["incompatible_connections"] for c in chains)
    summary = {
        "assigned_vehicles": len(chains),
        "connections": len(intervals),
        "minimum_dwell": min(dwells, default=None),
        "median_dwell": median(dwells) if dwells else None,
        "maximum_dwell": max(dwells, default=None),
        "total_dwell": sum(dwells),
        "dwell_distribution": [
            {"minutes": k, "count": v} for k, v in sorted(Counter(dwells).items())
        ],
        "minimum_slack": min((i["slack"] for i in intervals), default=None),
        "short_threshold_minutes": threshold,
        "short_turnarounds": sum(bool(i["short"]) for i in intervals)
        if threshold is not None
        else None,
        "longest_short_run": max((c["longest_short_run"] for c in chains), default=0),
        "incompatible_connections": failures,
        "chains_with_failures": sum(c["incompatible_connections"] > 0 for c in chains),
        "roles": {},
        "recovery_reserve_sensitivity": [
            {
                "reserve_minutes": reserve,
                "connections_below_reserve": sum(i["slack"] < reserve for i in intervals),
            }
            for reserve in sorted(
                {w["reserve"] for windows in policies.get("roles", {}).values() for w in windows}
            )
        ],
    }
    for role, windows in policies.get("roles", {}).items():
        summary["roles"][role] = [
            {
                "name": w["name"],
                "applicable_chains": sum(
                    c["crew"][role][j]["overlaps_vehicle_span"] for c in chains
                ),
                "fixed_possible_chains": sum(
                    bool(c["crew"][role][j]["fixed_vehicle_opportunities"]) for c in chains
                ),
                "relief_dependency_chains": sum(
                    c["crew"][role][j]["relief_dependency"] for c in chains
                ),
                "relief_possible_chains": sum(
                    bool(c["crew"][role][j]["relief_opportunities"]) for c in chains
                ),
            }
            for j, w in enumerate(windows)
        ]
    return {
        "vehicle_status": "VERIFIED_CONSTRAINT_FAILURE" if failures else "CONDITIONALLY_POSSIBLE",
        "crew_status": "INSUFFICIENT_CREW_EVIDENCE",
        "policy_status": policies.get("authority", "MISSING_OPERATOR_POLICY"),
        "summary": summary,
        "chains": chains,
    }

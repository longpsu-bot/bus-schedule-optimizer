"""Read-only, terminal-only reconstruction of fixed vehicle chains; never a solver."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import ceil, floor, isfinite

from .crew_review import analyze_chains
from .input import DIRECTIONS

TERMINALS = {"outbound": "A", "inbound": "B"}


def meal_policy():
    return {
        "authority": "PRODUCT_OWNER_APPROVED_EXPERIMENTAL_2026-10-28",
        "assignment": "ONE_CREW_PER_FULL_VEHICLE_CHAIN",
        "technical": 5,
        "tasks_after": 5,
        "tasks_before": 5,
        "minutes": 30,
        "windows": {"lunch": [660, 840], "dinner": [1020, 1200]},
        "requirement": "DUTY_INTERSECTS_WINDOW",
        "driving_reset": "MODELED_SELECTED_CONTINUOUS_MEAL_ONLY",
    }


def _policy(policy):
    p = deepcopy(meal_policy() if policy is None else policy)
    if (
        not isinstance(p, dict)
        or set(p) != set(meal_policy())
        or p["assignment"] != "ONE_CREW_PER_FULL_VEHICLE_CHAIN"
        or p["requirement"] != "DUTY_INTERSECTS_WINDOW"
        or p["driving_reset"] != "MODELED_SELECTED_CONTINUOUS_MEAL_ONLY"
        or not isinstance(p["authority"], str)
        or not p["authority"]
    ):
        raise ValueError("invalid experimental crew policy")
    for k in ("technical", "tasks_after", "tasks_before", "minutes"):
        if type(p[k]) not in (int, float) or not isfinite(p[k]) or p[k] < 0:
            raise ValueError("invalid policy duration")
    if (
        p["minutes"] <= 0
        or not isinstance(p["windows"], dict)
        or set(p["windows"]) != {"lunch", "dinner"}
    ):
        raise ValueError("invalid policy meal windows")
    end = -1
    for a, b in sorted(p["windows"].values()):
        if (
            any(type(t) not in (int, float) or not isfinite(t) for t in (a, b))
            or a < end
            or b - a < p["minutes"]
        ):
            raise ValueError("invalid policy meal window")
        end = b
    return p


def reconstruct(
    fleet,
    initial_stock,
    *,
    margins=None,
    runtime_basis="p50",
    policy=None,
    standdown=False,
    horizon=None,
):
    """Half-open intervals; all stock physically starts at its declared terminal.

    A departure can be physically feasible while failing tasks/recovery or meals.
    `standdown` explicitly authors a conditional terminal parking plan, not time off.
    """
    p = _policy(policy)
    if runtime_basis not in {"p50", "p75"}:
        raise ValueError("runtime basis must be p50 or p75")
    if (
        not isinstance(initial_stock, dict)
        or set(initial_stock) != set(DIRECTIONS)
        or any(type(v) is not int or v < 0 for v in initial_stock.values())
    ):
        raise ValueError("explicit nonnegative initial stock is required at both terminals")
    margins = {} if margins is None else margins
    if any(type(v) not in (int, float) or not isfinite(v) or v < 0 for v in margins.values()):
        raise ValueError("traffic margins must be nonnegative finite minutes")
    base = analyze_chains(fleet, dict.fromkeys(DIRECTIONS, p["technical"]), {})
    if base["summary"]["incompatible_connections"]:
        raise ValueError("physical/technical continuity failure in fixed chains")
    if not fleet["trips"]:
        raise ValueError("empty fleet")
    by_id = {t["trip_id"]: t for t in fleet["trips"]}
    required = Counter(by_id[c[0]]["direction"] for c in fleet["chains"])
    if any(initial_stock[d] < required[d] for d in DIRECTIONS):
        raise ValueError("initial stock cannot support the assigned chain origins")
    first = min(t["departure"] for t in fleet["trips"])
    last = max(t["arrival"] for t in fleet["trips"]) + p["technical"] + p["tasks_after"]
    start, end = horizon or (floor((first - p["tasks_before"]) / 15) * 15, ceil(last / 15) * 15)
    if start > first or end < last or start >= end:
        raise ValueError("report horizon must contain all trips and final terminal tasks")
    segments, ledger, crews, opportunities, deficits = [], [], [], [], []

    def add(vehicle, a, b, location, state, crew="ON_DUTY_OTHER", **extra):
        if b > a:
            segments.append(
                dict(
                    vehicle_id=vehicle,
                    start=a,
                    end=b,
                    location=location,
                    vehicle_state=state,
                    crew_activity=crew,
                    **extra,
                )
            )

    for chain in fleet["chains"]:
        trips = [by_id[tid] for tid in chain]
        vehicle = trips[0]["vehicle_id"]
        origin = TERMINALS[trips[0]["direction"]]
        preparation = max(start, trips[0]["departure"] - p["tasks_before"])
        add(vehicle, start, preparation, origin, "NOT_YET_DEPLOYED", "NOT_YET_ON_DUTY")
        add(
            vehicle,
            preparation,
            trips[0]["departure"],
            origin,
            "NOT_YET_DEPLOYED",
            "PRE_DEPARTURE_TASKS",
        )
        ledger.append(
            dict(
                time=start,
                order=0,
                event="INITIAL_STOCK",
                vehicle_id=vehicle,
                terminal=origin,
                stock_delta=1,
            )
        )
        free, connections = [], []
        for i, t in enumerate(trips):
            destination = "B" if t["direction"] == "outbound" else "A"
            ledger.extend(
                [
                    dict(
                        time=t["departure"],
                        order=3,
                        event="DEPARTURE",
                        vehicle_id=vehicle,
                        terminal=TERMINALS[t["direction"]],
                        stock_delta=-1,
                        trip_id=t["trip_id"],
                    ),
                    dict(
                        time=t["arrival"],
                        order=1,
                        event="ARRIVAL",
                        vehicle_id=vehicle,
                        terminal=destination,
                        stock_delta=1,
                        trip_id=t["trip_id"],
                    ),
                    dict(
                        time=t["arrival"] + p["technical"],
                        order=2,
                        event="TECHNICALLY_READY",
                        vehicle_id=vehicle,
                        terminal=destination,
                        stock_delta=0,
                        trip_id=t["trip_id"],
                    ),
                ]
            )
            add(
                vehicle,
                t["departure"],
                t["arrival"],
                t["direction"],
                "IN_PASSENGER_SERVICE",
                "DRIVING",
                trip_id=t["trip_id"],
            )
            following = trips[i + 1] if i + 1 < len(trips) else None
            departure = following["departure"] if following else end
            cursor = t["arrival"]
            add(
                vehicle,
                cursor,
                min(cursor + p["technical"], departure),
                destination,
                "TECHNICAL_TURNAROUND",
            )
            cursor += p["technical"]
            add(
                vehicle,
                cursor,
                min(cursor + p["tasks_after"], departure),
                destination,
                "TERMINAL_IDLE",
                "POST_ARRIVAL_TASKS",
            )
            cursor += p["tasks_after"]
            if not following:
                add(vehicle, cursor, end, destination, "FINISHED_SERVICE", "DUTY_FINISHED")
                continue
            reserve = margins.get(t["trip_id"], 0) if runtime_basis == "p50" else 0
            available_end = departure - p["tasks_before"]
            shortfall = max(0, cursor + reserve - available_end)
            connection = dict(
                vehicle_id=vehicle,
                from_trip_id=t["trip_id"],
                to_trip_id=following["trip_id"],
                terminal=destination,
                arrival=t["arrival"],
                next_departure=departure,
                traffic_margin=margins.get(t["trip_id"], 0),
                reserved_recovery=reserve,
                deficit_minutes=shortfall,
            )
            connections.append(connection)
            if shortfall:
                deficits.append(connection)
            add(
                vehicle,
                cursor,
                min(cursor + reserve, departure),
                destination,
                "RECOVERY_RESERVED",
                "RECOVERY_COMMITTED",
            )
            cursor += reserve
            if available_end > cursor:
                free.append(
                    dict(
                        start=cursor,
                        end=available_end,
                        terminal=destination,
                        after_trip_id=t["trip_id"],
                        next_trip_id=following["trip_id"],
                    )
                )
            add(
                vehicle,
                max(cursor, available_end),
                departure,
                destination,
                "TERMINAL_IDLE",
                "PRE_DEPARTURE_TASKS",
            )
        duty_start = first_duty = trips[0]["departure"] - p["tasks_before"]
        duty_end = trips[-1]["arrival"] + p["technical"] + p["tasks_after"]
        meals = {}
        for name, (a, b) in p["windows"].items():
            required_meal = duty_start < b and duty_end > a
            choices = [
                (max(a, f["start"]), min(b, f["end"]), f)
                for f in free
                if min(b, f["end"]) - max(a, f["start"]) >= p["minutes"]
            ]
            chosen = choices[0] if required_meal and choices else None
            meals[name] = dict(
                required=required_meal,
                opportunity=[chosen[0], chosen[0] + p["minutes"]] if chosen else None,
                terminal=chosen[2]["terminal"] if chosen else None,
                status="MODELED_OPPORTUNITY"
                if chosen
                else "MISSING"
                if required_meal
                else "NOT_REQUIRED",
            )
        for f in free:
            pieces = [(f["start"], f["end"], "TERMINAL_IDLE", "ON_DUTY_WAITING")]
            for meal in meals.values():
                if not meal["opportunity"]:
                    continue
                a, b = meal["opportunity"]
                if f["start"] <= a and b <= f["end"]:
                    pieces = (
                        [(x, min(y, a), s, c) for x, y, s, c in pieces if x < a]
                        + [(a, b, "CREW_MEAL_BREAK", "MODELED_MEAL_OPPORTUNITY")]
                        + [(max(x, b), y, s, c) for x, y, s, c in pieces if y > b]
                    )
            for a, b, state, activity in pieces:
                if standdown and state == "TERMINAL_IDLE" and b - a >= p["minutes"]:
                    state = "TEMPORARILY_STOOD_DOWN"
                    activity = "ON_DUTY_WAITING"
                add(vehicle, a, b, f["terminal"], state, activity)
            opportunities.append(
                dict(
                    vehicle_id=vehicle,
                    **f,
                    free_minutes=f["end"] - f["start"],
                    standdown_authored=standdown,
                    parking_feasibility="UNVERIFIED",
                    earliest_reactivation=max(
                        [f["start"]]
                        + [
                            m["opportunity"][1]
                            for m in meals.values()
                            if m["opportunity"]
                            and f["start"] <= m["opportunity"][0]
                            and m["opportunity"][1] <= f["end"]
                        ]
                    )
                    + p["tasks_before"],
                    planned_reactivation=f["end"] + p["tasks_before"],
                )
            )
        driving, maximum = 0, 0
        reset = sorted(m["opportunity"][1] for m in meals.values() if m["opportunity"])
        for t in trips:
            if any(first_duty < z <= t["departure"] for z in reset):
                driving = 0
            driving += t["arrival"] - t["departure"]
            maximum = max(maximum, driving)
            first_duty = t["departure"]
        crews.append(
            dict(
                vehicle_id=vehicle,
                duty_start=duty_start,
                duty_end=duty_end,
                duty_span_minutes=duty_end - duty_start,
                meals=meals,
                duty_span_screen_over_8h=duty_end - duty_start > 480,
                driving_minutes=sum(t["arrival"] - t["departure"] for t in trips),
                modeled_max_continuous_driving_minutes=maximum,
                connections=connections,
            )
        )
    unused = 0
    for d in DIRECTIONS:
        for _ in range(initial_stock[d] - required[d]):
            unused += 1
            vehicle = f"U{unused:03d}"
            add(vehicle, start, end, TERMINALS[d], "NOT_YET_DEPLOYED", "NO_CREW_ASSIGNED")
            ledger.append(
                dict(
                    time=start,
                    order=0,
                    event="INITIAL_STOCK",
                    vehicle_id=vehicle,
                    terminal=TERMINALS[d],
                    stock_delta=1,
                )
            )
    segments.sort(key=lambda s: (s["vehicle_id"], s["start"], s["end"]))
    for vehicle in sorted({s["vehicle_id"] for s in segments}):
        local = [s for s in segments if s["vehicle_id"] == vehicle]
        if (
            local[0]["start"] != start
            or local[-1]["end"] != end
            or any(a["end"] != b["start"] for a, b in zip(local, local[1:], strict=False))
        ):
            raise ValueError("state coverage/overlap error")
    for s in segments:
        ledger.append(
            dict(
                time=s["start"],
                order=2,
                event="STATE_CHANGE",
                vehicle_id=s["vehicle_id"],
                location=s["location"],
                state=s["vehicle_state"],
                stock_delta=0,
            )
        )
    ledger.sort(key=lambda e: (e["time"], e["order"], e["vehicle_id"], e["event"]))
    counts = dict(A=0, B=0)
    for event in ledger:
        if event["stock_delta"]:
            counts[event["terminal"]] += event["stock_delta"]
            if counts[event["terminal"]] < 0:
                raise ValueError("phantom vehicle activation: negative terminal inventory")
        event["terminal_A_after_event"] = counts["A"]
        event["terminal_B_after_event"] = counts["B"]
    boundaries = sorted(
        {start, end} | {s["start"] for s in segments} | {s["end"] for s in segments}
    )
    snapshots = []
    n = sum(initial_stock.values())
    for t in boundaries[:-1]:
        active = [s for s in segments if s["start"] <= t < s["end"]]
        locations = Counter(s["location"] for s in active)
        states = Counter(s["vehicle_state"] for s in active)
        row = dict(
            time=t,
            physical_vehicles=n,
            terminal_A=locations["A"],
            terminal_B=locations["B"],
            travelling_outbound=locations["outbound"],
            travelling_inbound=locations["inbound"],
            in_passenger_service=states["IN_PASSENGER_SERVICE"],
            terminal_ready=sum(
                s["location"] in {"A", "B"}
                and s["vehicle_state"] in {"TERMINAL_IDLE", "NOT_YET_DEPLOYED", "FINISHED_SERVICE"}
                and s["crew_activity"] not in {"POST_ARRIVAL_TASKS", "PRE_DEPARTURE_TASKS"}
                for s in active
            ),
            temporarily_stood_down=states["TEMPORARILY_STOOD_DOWN"],
            crew_meal_break=states["CREW_MEAL_BREAK"],
            technical_turnaround=states["TECHNICAL_TURNAROUND"],
            recovery_reserved=states["RECOVERY_RESERVED"],
            committed_to_circulation=n - states["NOT_YET_DEPLOYED"] - states["FINISHED_SERVICE"],
            parked_waiting=locations["A"] + locations["B"],
        )
        if len(active) != n or sum(locations.values()) != n:
            raise ValueError("physical vehicle conservation failure")
        snapshots.append(row)
    utilization = []
    keys = [k for k in snapshots[0] if k != "time"]
    for a in range(floor(start / 15) * 15, ceil(end / 15) * 15, 15):
        b = min(a + 15, end)
        a = max(a, start)
        spans = [
            (row, max(0, min(b, z) - max(a, row["time"])))
            for row, z in zip(snapshots, boundaries[1:], strict=True)
        ]
        spans = [(row, duration) for row, duration in spans if duration]
        row = dict(start=a, end=b)
        for key in keys:
            row[key + "_mean"] = round(sum(r[key] * duration for r, duration in spans) / (b - a), 6)
            row[key + "_max"] = max(r[key] for r, _ in spans)
        row["departures"] = sum(a <= e["time"] < b and e["event"] == "DEPARTURE" for e in ledger)
        row["arrivals"] = sum(a <= e["time"] < b and e["event"] == "ARRIVAL" for e in ledger)
        utilization.append(row)
    durations = Counter()
    for s in segments:
        durations[s["vehicle_state"]] += s["end"] - s["start"]
    crew = dict(
        policy=p,
        chains=crews,
        both_meals=sum(all(m["opportunity"] for m in c["meals"].values()) for c in crews),
        duty_span_concerns=sum(c["duty_span_screen_over_8h"] for c in crews),
        note="Opportunities only; parked crew remains on duty; no labor-law certification.",
    )
    for name in p["windows"]:
        crew[name + "_required"] = sum(c["meals"][name]["required"] for c in crews)
        crew[name + "_covered"] = sum(bool(c["meals"][name]["opportunity"]) for c in crews)
    return dict(
        ledger=ledger,
        segments=segments,
        snapshots=snapshots,
        utilization=utilization,
        crew=crew,
        opportunities=opportunities,
        metrics=dict(
            unique_vehicles_required=fleet["required_fleet"],
            physical_vehicles_in_scenario=n,
            max_concurrent_passenger_service=max(r["in_passenger_service"] for r in snapshots),
            passenger_vehicle_hours=durations["IN_PASSENGER_SERVICE"] / 60,
            state_vehicle_hours={k: v / 60 for k, v in sorted(durations.items())},
            terminal_vehicle_hours=(n * (end - start) - durations["IN_PASSENGER_SERVICE"]) / 60,
        ),
        audit=dict(
            physical_conservation_pass=True,
            terminal_continuity_pass=True,
            initial_stock=initial_stock,
            initial_required=dict(required),
            recovery_task_deficit_connections=len(deficits),
            deficits=deficits,
            parking_authority="UNKNOWN",
            operational_parking_feasibility="UNVERIFIED",
            depot_movements=0,
            runtime_basis=runtime_basis,
            horizon=[start, end],
        ),
    )

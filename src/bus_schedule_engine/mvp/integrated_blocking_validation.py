"""Independent request and executable fixed-team witness reconstruction.

No solver model/opportunity/state helpers are imported here. Times are half-open
whole-minute intervals. Experimental policy satisfaction is not legal approval.
"""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from datetime import date
from hashlib import sha256

from .circulation import validate_chains
from .input import DIRECTIONS, integer, number, runtime_at

AUTHORITY = {"EXPERIMENTAL_DECLARED", "OPERATOR_SUPPLIED_UNVERIFIED", "SOURCE_BACKED_OPERATOR"}
MODES = {"ENFORCED", "DISABLED_EXPERIMENTAL"}
ORIGIN = {"outbound": "A", "inbound": "B"}
DESTINATION = {"outbound": "B", "inbound": "A"}


def digest(value):
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _fields(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError(f"{name}: missing/unsupported fields; expected {keys}")


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must identify its source/value")


def _authority(value):
    if value not in AUTHORITY:
        raise ValueError("missing/unsupported policy authority")


def validate_request(request):
    """Reject unknown hard policies and missing values before constructing a model."""
    r = deepcopy(request)
    try:
        # A 32-bit input ceiling keeps every 102-trip sum and derived clock safely
        # within CP-SAT's 64-bit arithmetic, and matches its random-seed domain.
        pending = [r]
        while pending:
            value = pending.pop()
            if type(value) is int and value > 2**31 - 1:
                raise ValueError("integer input exceeds V1 solver-safe maximum 2147483647")
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        _fields(
            r,
            "schema_version route_id terminals source timetable runtime_scenario terminal_policy recovery_policy crew_policy stock resource_cap search operating_date operational_evidence",
            "request",
        )
        if r["schema_version"] != "integrated_blocking_v1" or r["terminals"] != ["A", "B"]:
            raise ValueError("unsupported version/terminals")
        _text(r["route_id"], "route_id")
        _fields(r["source"], "authority provenance", "source")
        _authority(r["source"]["authority"])
        _text(r["source"]["provenance"], "source.provenance")
        _fields(r["timetable"], "trips departure_sha256", "timetable")
        trips = r["timetable"]["trips"]
        if not isinstance(trips, list) or not 1 <= len(trips) <= 102:
            raise ValueError("V1 requires 1..102 trips")
        seen, counts, departures = set(), Counter(), {d: [] for d in DIRECTIONS}
        for t in trips:
            _fields(t, "trip_id direction departure source_pointer", "trip")
            if t["direction"] not in DIRECTIONS:
                raise ValueError("unknown direction")
            integer(t["departure"], "departure")
            _text(t["source_pointer"], "trip.source_pointer")
            d = t["direction"]
            counts[d] += 1
            if t["trip_id"] != f"{d}-{counts[d]:03d}" or t["trip_id"] in seen:
                raise ValueError("trip identity/ordinal mismatch")
            if departures[d] and departures[d][-1] >= t["departure"]:
                raise ValueError("departures must be ordered unique per direction")
            seen.add(t["trip_id"])
            departures[d].append(t["departure"])
        expected = r["timetable"]["departure_sha256"]
        if expected is not None and expected != digest(departures):
            raise ValueError("departure SHA-256 mismatch")
        _fields(r["runtime_scenario"], "id directions", "runtime_scenario")
        if r["runtime_scenario"]["id"] not in {"p50", "p75"}:
            raise ValueError("unsupported runtime scenario")
        profiles = r["runtime_scenario"]["directions"]
        _fields(profiles, "outbound inbound", "runtime directions")
        for d in DIRECTIONS:
            cursor = None
            if not isinstance(profiles[d], list) or (departures[d] and not profiles[d]):
                raise ValueError("missing runtime partition")
            for p in profiles[d]:
                _fields(p, "start end minutes", "runtime period")
                for key in p:
                    integer(p[key], key, 1 if key == "minutes" else 0)
                if p["end"] <= p["start"] or (cursor is not None and p["start"] != cursor):
                    raise ValueError("runtime partition must be contiguous and ordered")
                cursor = p["end"]
            for departure in departures[d]:
                runtime_at({"runtime_periods": profiles[d]}, departure)
        _fields(r["terminal_policy"], "technical post pre", "terminal_policy")
        for k, v in r["terminal_policy"].items():
            integer(v, f"terminal.{k}")
        recovery = r["recovery_policy"]
        _fields(recovery, "runtime_basis reserve_by_arriving_trip provenance", "recovery_policy")
        if recovery["runtime_basis"] != r["runtime_scenario"]["id"]:
            raise ValueError("recovery/runtime basis mismatch")
        _text(recovery["provenance"], "recovery provenance")
        if set(recovery["reserve_by_arriving_trip"]) != seen:
            raise ValueError("reserve map must explicitly cover every arriving trip")
        for v in recovery["reserve_by_arriving_trip"].values():
            integer(v, "reserve")
        crew = r["crew_policy"]
        _fields(crew, "assignment duty total_driving driving meals general_rest", "crew_policy")
        if crew["assignment"] != "FIXED_SYNCHRONIZED_DRIVER_ATTENDANT":
            raise ValueError("unsupported crew assignment")
        for key in ("duty", "total_driving", "driving", "general_rest"):
            rule = crew[key]
            keys = (
                "mode limit"
                if key in {"duty", "total_driving"}
                else (
                    "mode limit reset_minutes"
                    if key == "driving"
                    else "mode duty_threshold minutes"
                )
            )
            _fields(rule, keys, key)
            if rule["mode"] not in MODES:
                raise ValueError("explicit supported rule mode required")
            for k, v in rule.items():
                if k != "mode":
                    integer(v, f"{key}.{k}", 0 if k == "duty_threshold" else 1)
        meals = crew["meals"]
        _fields(meals, "eligibility duty_threshold overlap_threshold windows", "meals")
        if meals["eligibility"] not in {"SUSTAINED_WINDOW_DUTY", "DUTY_INTERSECTS_WINDOW"}:
            raise ValueError("unsupported meal eligibility")
        integer(meals["duty_threshold"], "meal duty threshold")
        integer(meals["overlap_threshold"], "meal overlap threshold")
        if not isinstance(meals["windows"], list) or len(meals["windows"]) != 2:
            raise ValueError("V1 requires explicit lunch and dinner rules")
        previous_end = None
        for m, name in zip(meals["windows"], ("lunch", "dinner"), strict=True):
            _fields(m, "name start end minutes mode", "meal window")
            if m["name"] != name or m["mode"] not in MODES:
                raise ValueError("meal name/mode mismatch")
            for key in ("start", "end", "minutes"):
                integer(m[key], f"meal.{key}", 1 if key == "minutes" else 0)
            if m["end"] - m["start"] < m["minutes"] or (
                previous_end is not None and m["start"] < previous_end
            ):
                raise ValueError("meal windows must be ordered, nonoverlapping and long enough")
            previous_end = m["end"]
        stock = r["stock"]
        _fields(stock, "mode initial_vehicles authority provenance", "stock")
        _authority(stock["authority"])
        _text(stock["provenance"], "stock provenance")
        if stock["mode"] == "RESOURCE_SIZING_UNCONFIRMED":
            if stock["initial_vehicles"] is not None:
                raise ValueError("resource sizing must not contain hidden stock caps")
        elif stock["mode"] in {"EXPERIMENTAL_CAPS", "CONFIRMED_CAPS"}:
            _fields(stock["initial_vehicles"], "A B", "initial stock")
            for v in stock["initial_vehicles"].values():
                integer(v, "initial stock")
            if stock["mode"] == "CONFIRMED_CAPS" and stock["authority"] != "SOURCE_BACKED_OPERATOR":
                raise ValueError("confirmed stock requires sourced authority")
        else:
            raise ValueError("unsupported stock mode")
        if r["resource_cap"] is not None:
            _fields(r["resource_cap"], "limit authority provenance", "resource_cap")
            integer(r["resource_cap"]["limit"], "resource cap", 1)
            _authority(r["resource_cap"]["authority"])
            _text(r["resource_cap"]["provenance"], "cap provenance")
        search = r["search"]
        _fields(
            search, "seed workers deterministic_seconds wall_seconds memory_mb max_edges", "search"
        )
        integer(search["seed"], "seed")
        if type(search["workers"]) is not int or search["workers"] != 1:
            raise ValueError("V1 requires one worker")
        for key in ("deterministic_seconds", "wall_seconds"):
            number(search[key], key)
            if search[key] <= 0:
                raise ValueError("search limits must be positive")
        for key in ("memory_mb", "max_edges"):
            integer(search[key], key, 1)
        if r["operating_date"] is not None:
            date.fromisoformat(r["operating_date"])
        if not isinstance(r["operational_evidence"], list) or any(
            not isinstance(s, str) for s in r["operational_evidence"]
        ):
            raise ValueError("operational_evidence must be a list of strings")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"missing/invalid essential input: {exc}") from exc
    return r


def _union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def validate_assignment(request, blocks):
    """Recompute every physical interval, role identity and rule from immutable inputs."""
    r = validate_request(request)
    crew, tasks = r["crew_policy"], r["terminal_policy"]
    q, h, p = (tasks[k] for k in ("technical", "post", "pre"))
    trips = {}
    for raw in r["timetable"]["trips"]:
        t = dict(raw)
        t["runtime"] = runtime_at(
            {"runtime_periods": r["runtime_scenario"]["directions"][t["direction"]]}, t["departure"]
        )
        t["arrival"] = t["departure"] + t["runtime"]
        trips[t["trip_id"]] = t
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("assignment must contain nonempty blocks")
    identities = {
        k: set() for k in ("block_id", "vehicle_id", "team_id", "driver_id", "attendant_id")
    }
    people, covered, metrics, events, legacy_trips = set(), [], [], [], []
    initial = dict(A=0, B=0)
    for b in blocks:
        _fields(
            b, "block_id vehicle_id team_id driver_id attendant_id trip_ids rests", "block witness"
        )
        for key, values in identities.items():
            _text(b[key], key)
            if b[key] in values:
                raise ValueError(f"reused {key} across blocks")
            values.add(b[key])
        if b["driver_id"] == b["attendant_id"] or people.intersection(
            (b["driver_id"], b["attendant_id"])
        ):
            raise ValueError("person reused between crew roles/blocks")
        people.update((b["driver_id"], b["attendant_id"]))
        if (
            not isinstance(b["trip_ids"], list)
            or not b["trip_ids"]
            or any(not isinstance(t, str) or t not in trips for t in b["trip_ids"])
        ):
            raise ValueError("unknown/empty trip chain")
        local = [trips[tid] for tid in b["trip_ids"]]
        covered.extend(b["trip_ids"])
        first, last = local[0], local[-1]
        start, end = first["departure"] - p, last["arrival"] + h
        span = end - start
        if crew["duty"]["mode"] == "ENFORCED" and span > crew["duty"]["limit"]:
            raise ValueError(f"{b['block_id']}: duty {span} exceeds limit")
        initial[ORIGIN[first["direction"]]] += 1
        connections, activities = [], []
        for i, t in enumerate(local):
            activities.extend(
                [
                    dict(
                        kind="pre",
                        start=t["departure"] - p,
                        end=t["departure"],
                        trip_id=t["trip_id"],
                    ),
                    dict(
                        kind="driving", start=t["departure"], end=t["arrival"], trip_id=t["trip_id"]
                    ),
                    dict(
                        kind="post", start=t["arrival"], end=t["arrival"] + h, trip_id=t["trip_id"]
                    ),
                ]
            )
            events.extend(
                [
                    (t["departure"], 1, ORIGIN[t["direction"]], -1),
                    (t["arrival"], 0, DESTINATION[t["direction"]], 1),
                ]
            )
            legacy_trips.append(
                dict(
                    trip_id=t["trip_id"],
                    direction=t["direction"],
                    departure=t["departure"],
                    arrival=t["arrival"],
                    ready=t["arrival"] + q + h + p,
                    vehicle_id=b["vehicle_id"],
                )
            )
            if i + 1 < len(local):
                nxt = local[i + 1]
                reserve = r["recovery_policy"]["reserve_by_arriving_trip"][t["trip_id"]]
                left, right = t["arrival"] + h + q + reserve, nxt["departure"] - p
                if (
                    t["direction"] == nxt["direction"]
                    or t["departure"] >= nxt["departure"]
                    or left > right
                ):
                    raise ValueError(f"invalid connection {t['trip_id']}->{nxt['trip_id']}")
                connections.append(
                    dict(
                        after_trip=t["trip_id"],
                        before_trip=nxt["trip_id"],
                        terminal=DESTINATION[t["direction"]],
                        arrival=t["arrival"],
                        departure=nxt["departure"],
                        dwell=nxt["departure"] - t["arrival"],
                        technical=q,
                        post=h,
                        pre=p,
                        reserve=reserve,
                        free_start=left,
                        free_end=right,
                    )
                )
                activities.extend(
                    [
                        dict(
                            kind="technical",
                            start=t["arrival"] + h,
                            end=t["arrival"] + h + q,
                            trip_id=t["trip_id"],
                        ),
                        dict(
                            kind="recovery",
                            start=t["arrival"] + h + q,
                            end=left,
                            trip_id=t["trip_id"],
                        ),
                    ]
                )
        if not isinstance(b["rests"], list):
            raise ValueError("rests must be explicit list")
        meals = {
            m["name"]: dict(required=False, covered=False, overlap=0, intervals=[])
            for m in crew["meals"]["windows"]
        }
        for rest in b["rests"]:
            _fields(rest, "after_trip before_trip start end terminal kind", "rest witness")
            for key in ("start", "end"):
                integer(rest[key], f"rest {key}")
            edge = next(
                (
                    c
                    for c in connections
                    if (c["after_trip"], c["before_trip"])
                    == (rest["after_trip"], rest["before_trip"])
                ),
                None,
            )
            if (
                edge is None
                or rest["terminal"] != edge["terminal"]
                or not edge["free_start"] <= rest["start"] < rest["end"] <= edge["free_end"]
            ):
                raise ValueError("protected rest outside free interval/terminal")
            if rest["kind"] != "protected":
                m = next((m for m in crew["meals"]["windows"] if m["name"] == rest["kind"]), None)
                if (
                    m is None
                    or rest["start"] < m["start"]
                    or rest["end"] > m["end"]
                    or rest["end"] - rest["start"] < m["minutes"]
                ):
                    raise ValueError("meal outside its own window or too short")
                if meals[m["name"]]["covered"]:
                    raise ValueError("multiple meals of same kind in block")
                meals[m["name"]].update(covered=True, intervals=[[rest["start"], rest["end"]]])
        for m in crew["meals"]["windows"]:
            overlap = max(0, min(end, m["end"]) - max(start, m["start"]))
            required = m["mode"] == "ENFORCED" and (
                overlap > 0
                if crew["meals"]["eligibility"] == "DUTY_INTERSECTS_WINDOW"
                else span >= crew["meals"]["duty_threshold"]
                and overlap >= crew["meals"]["overlap_threshold"]
            )
            meals[m["name"]].update(required=required, overlap=overlap)
            if required and not meals[m["name"]]["covered"]:
                raise ValueError(f"{b['block_id']}: required {m['name']} missing")
        union = _union((s["start"], s["end"]) for s in b["rests"])
        qualifying = [s for s in union if s[1] - s[0] >= crew["general_rest"]["minutes"]]
        general_required = (
            crew["general_rest"]["mode"] == "ENFORCED"
            and span >= crew["general_rest"]["duty_threshold"]
        )
        if general_required and not qualifying:
            raise ValueError(f"{b['block_id']}: required general rest missing")
        resets = [s for s in union if s[1] - s[0] >= crew["driving"]["reset_minutes"]]
        cumulative, max_drive = 0, 0
        for i, t in enumerate(local):
            if i and any(
                local[i - 1]["arrival"] <= s[0] and s[1] <= t["departure"] for s in resets
            ):
                cumulative = 0
            cumulative += t["runtime"]
            max_drive = max(max_drive, cumulative)
        total = sum(t["runtime"] for t in local)
        if crew["driving"]["mode"] == "ENFORCED" and max_drive > crew["driving"]["limit"]:
            raise ValueError("continuous driving limit exceeded")
        if crew["total_driving"]["mode"] == "ENFORCED" and total > crew["total_driving"]["limit"]:
            raise ValueError("total driving limit exceeded")
        cursor, exposure = start, 0
        for left, right in resets:
            exposure = max(exposure, left - cursor)
            cursor = right
        exposure = max(exposure, end - cursor)
        for c in connections:
            c["protected_intervals"] = [
                s for s in union if c["free_start"] <= s[0] and s[1] <= c["free_end"]
            ]
            c["protected_minutes"] = sum(u - lo for lo, u in c["protected_intervals"])
            c["other_wait"] = c["free_end"] - c["free_start"] - c["protected_minutes"]
        metrics.append(
            {k: b[k] for k in identities}
            | dict(
                trip_ids=b["trip_ids"],
                initial_terminal=ORIGIN[first["direction"]],
                final_terminal=DESTINATION[last["direction"]],
                duty_start=start,
                duty_end=end,
                duty_span=span,
                total_driving=total,
                max_continuous_driving=max_drive,
                continuous_work_exposure=exposure,
                protected_minutes=sum(u - lo for lo, u in union),
                rest_union=union,
                reset_intervals=resets,
                general_rest=dict(
                    required=general_required,
                    covered=bool(qualifying),
                    qualifying_intervals=qualifying,
                ),
                meals=meals,
                connections=connections,
                activities=activities,
            )
        )
    if Counter(covered) != Counter(trips.keys()):
        raise ValueError("trip coverage duplicate/omission")
    caps = r["stock"]["initial_vehicles"]
    if caps is not None and any(initial[t] > caps[t] for t in initial):
        raise ValueError("initial terminal stock exceeded")
    if r["resource_cap"] is not None and len(blocks) > r["resource_cap"]["limit"]:
        raise ValueError("resource cap exceeded")
    inventory, state, moving = [], initial.copy(), 0
    for minute, _, terminal, delta in sorted(events):
        state[terminal] += delta
        moving -= delta
        if min(*state.values(), moving) < 0 or sum(state.values()) + moving != len(blocks):
            raise ValueError("physical inventory conservation failed")
        inventory.append(dict(minute=minute, A=state["A"], B=state["B"], in_transit=moving))
    departures = {
        d: [t["departure"] for t in trips.values() if t["direction"] == d] for d in DIRECTIONS
    }
    data = dict(
        directions={
            d: dict(runtime_periods=r["runtime_scenario"]["directions"][d]) for d in DIRECTIONS
        },
        layover_minutes=dict.fromkeys(DIRECTIONS, q + h + p),
    )
    physical = dict(
        required_fleet=len(blocks),
        chains=[b["trip_ids"] for b in blocks],
        trips=legacy_trips,
        initial_vehicles_required={d: initial[ORIGIN[d]] for d in DIRECTIONS},
    )
    validate_chains(data, departures, physical)
    return dict(
        validator_pass=True,
        blocks=metrics,
        required_fleet=len(blocks),
        initial_vehicles_required=initial,
        inventory=inventory,
        physical_assignment=dict(departures=departures, **physical),
        crew_rules="ENFORCED"
        if all(
            crew[k]["mode"] == "ENFORCED"
            for k in ("duty", "driving", "general_rest", "total_driving")
        )
        and all(m["mode"] == "ENFORCED" for m in crew["meals"]["windows"])
        else "CREW_RULES_DISABLED",
    )

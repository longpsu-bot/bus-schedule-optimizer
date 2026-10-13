"""Validated minute-based operational inputs and the existing V3 workbook adapter."""

from __future__ import annotations

import math
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from ..contracts_v1.multi_period_demand import derive_demand_profile_v1
from ..v3_workbook import import_v3_multi_period_workbook_v1

DIRECTIONS = ("outbound", "inbound")


def integer(value, field, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def number(value, field, minimum=0):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
    ):
        raise ValueError(f"{field} must be finite and >= {minimum}")
    return value


def validate_bundle(bundle):
    if not isinstance(bundle, dict):
        raise ValueError("route bundle must be an object")
    data = deepcopy(bundle)
    allowed = {
        "route_id",
        "provenance",
        "demand_basis",
        "fleet_ceiling",
        "layover_minutes",
        "directions",
        "initial_vehicles",
        "vehicle_capacity",
        "maximum_load_factor",
        "capacity_policy",
    }
    if set(data) - allowed:
        raise ValueError(f"Unsupported route fields/constraints: {sorted(set(data) - allowed)}")
    try:
        if not isinstance(data["route_id"], str) or not data["route_id"].strip():
            raise ValueError("route_id must be a nonempty string")
        if not isinstance(data["provenance"], dict) or not data["provenance"]:
            raise ValueError("provenance must identify the authoritative source")
        if data["demand_basis"] not in {"independent_arrivals", "historical_boardings"}:
            raise ValueError("demand_basis must be independent_arrivals or historical_boardings")
        integer(data["fleet_ceiling"], "fleet_ceiling", 1)
        if set(data["directions"]) != set(DIRECTIONS):
            raise ValueError("directions must contain outbound and inbound")
        if set(data["layover_minutes"]) != set(DIRECTIONS):
            raise ValueError(
                "layover_minutes must contain only outbound and inbound terminal values"
            )
        for direction in DIRECTIONS:
            integer(data["layover_minutes"][direction], f"layover_minutes.{direction}")
            d = data["directions"][direction]
            allowed_direction = {
                "first",
                "last",
                "trip_count",
                "runtime_minutes",
                "runtime_periods",
                "baseline",
                "demand",
                "protected_windows",
                "operating_start",
                "operating_end",
            }
            if set(d) - allowed_direction:
                raise ValueError(
                    f"Unsupported {direction} constraints: {sorted(set(d) - allowed_direction)}"
                )
            for field in ("first", "last"):
                integer(d[field], f"{direction}.{field}")
            if d["first"] >= d["last"]:
                raise ValueError(f"{direction}.last must be after first")
            d.setdefault("operating_start", d["first"])
            d.setdefault("operating_end", d["last"])
            integer(d["operating_start"], f"{direction}.operating_start")
            integer(d["operating_end"], f"{direction}.operating_end")
            if not d["operating_start"] <= d["first"] < d["last"] <= d["operating_end"]:
                raise ValueError(f"{direction} endpoints outside operating window")
            integer(d["trip_count"], f"{direction}.trip_count", 2)
            if "runtime_periods" in d:
                periods = d["runtime_periods"]
                cursor = d["operating_start"]
                for p in periods:
                    if set(p) != {"start", "end", "minutes"}:
                        raise ValueError("runtime_periods must contain only start, end, minutes")
                    for field in ("start", "end", "minutes"):
                        integer(
                            p[field],
                            f"{direction}.runtime_periods.{field}",
                            1 if field == "minutes" else 0,
                        )
                    if p["start"] != cursor or p["end"] <= p["start"]:
                        raise ValueError(
                            f"{direction}.runtime_periods must be a contiguous partition"
                        )
                    cursor = p["end"]
                if cursor <= d["last"]:
                    raise ValueError(f"{direction}.runtime_periods must cover the last departure")
            else:
                integer(d["runtime_minutes"], f"{direction}.runtime_minutes", 1)
            baseline = d["baseline"]
            if len(baseline) < 2 or baseline != sorted(set(baseline)):
                raise ValueError(f"{direction}.baseline must have ordered unique departures")
            for t in baseline:
                integer(t, f"{direction}.baseline departure")
            if baseline[0] != d["first"] or baseline[-1] != d["last"]:
                raise ValueError(f"{direction}.baseline endpoints differ from authority")
            if not d["demand"]:
                raise ValueError(f"{direction}.demand is missing; missing is not zero")
            cursor = None
            for b in d["demand"]:
                if set(b) != {"start", "end", "passengers"}:
                    raise ValueError("demand buckets must contain only start, end, passengers")
                integer(b["start"], f"{direction}.demand.start")
                integer(b["end"], f"{direction}.demand.end")
                number(b["passengers"], f"{direction}.demand.passengers")
                if b["end"] <= b["start"] or (cursor is not None and b["start"] != cursor):
                    raise ValueError(
                        f"{direction}.demand must be contiguous; explicit zeros required"
                    )
                cursor = b["end"]
            if d["demand"][0]["start"] > d["first"] or cursor < d["last"]:
                raise ValueError(f"{direction}.demand must cover first through last departure")
            d.setdefault("protected_windows", [])
            for w in d["protected_windows"]:
                if set(w) - {"start", "end", "max_gap", "minimum_departures"}:
                    raise ValueError("unsupported protected_windows constraint")
                for field in ("start", "end", "max_gap"):
                    integer(
                        w[field],
                        f"{direction}.protected_windows.{field}",
                        1 if field == "max_gap" else 0,
                    )
                if not d["first"] <= w["start"] < w["end"] <= d["last"]:
                    raise ValueError(
                        f"{direction}.protected_windows must lie inside service endpoints"
                    )
                integer(w.get("minimum_departures", 0), "minimum_departures")
        if "initial_vehicles" in data:
            if set(data["initial_vehicles"]) != set(DIRECTIONS):
                raise ValueError("initial_vehicles must contain only outbound and inbound")
            for direction in DIRECTIONS:
                integer(data["initial_vehicles"][direction], f"initial_vehicles.{direction}")
        if data.get("capacity_policy") == "hard" and data.get("vehicle_capacity") is None:
            raise ValueError("vehicle_capacity is required to enforce hard capacity_policy")
        if "capacity_policy" in data and data["capacity_policy"] not in {"hard", "evaluation_only"}:
            raise ValueError("capacity_policy must be hard or evaluation_only")
        if data.get("vehicle_capacity") is not None:
            integer(data["vehicle_capacity"], "vehicle_capacity", 1)
            number(data["maximum_load_factor"], "maximum_load_factor")
            if not 0 < data["maximum_load_factor"] <= 1:
                raise ValueError("maximum_load_factor must be in (0,1]")
            if data["capacity_policy"] not in {"hard", "evaluation_only"}:
                raise ValueError("capacity_policy must be hard or evaluation_only")
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Missing/invalid essential field: {exc}") from exc
    return data


def runtime_at(direction, departure):
    if "runtime_periods" in direction:
        for period in direction["runtime_periods"]:
            if period["start"] <= departure < period["end"]:
                return period["minutes"]
        raise ValueError("runtime model does not cover departure")
    return direction["runtime_minutes"]


def bundle_from_workbook(
    path,
    *,
    profile=None,
    minimum_layover=None,
    maximum_load_factor=None,
    capacity_policy="evaluation_only",
):
    path = Path(path)
    imported = import_v3_multi_period_workbook_v1(path)
    base = imported.base_workbook
    p = base.parameters_b
    if (
        p.terminal_1_max_occupancy_vehicles is not None
        or p.terminal_2_max_occupancy_vehicles is not None
    ):
        raise ValueError(
            "terminal occupancy constraint is unsupported in MVP; use existing contract solver"
        )
    layover = p.minimum_layover_minutes if minimum_layover is None else minimum_layover
    if layover is None:
        raise ValueError("minimum_layover_minutes is absent; provide explicit --minimum-layover")
    profile_id = profile or imported.multi_period_demand.default_profile_id
    if not profile_id:
        raise ValueError("default demand profile is absent; provide --profile")
    derived = derive_demand_profile_v1(imported.multi_period_demand, profile_id).profile
    metadata = base.authority_metadata
    data = {
        "route_id": p.route_id,
        "provenance": {
            "workbook_sha256": sha256(path.read_bytes()).hexdigest(),
            "source_name": path.name,
            "demand_profile": profile_id,
            "demand_profile_fingerprint": derived.profile_fingerprint,
            "demand_dataset_id": metadata.demand_dataset_id,
            "layover_source": "explicit operational CLI input"
            if minimum_layover is not None
            else "THAM_SO_B",
            "capacity_policy": capacity_policy,
            "protection_source": "none supplied; exact first/last protected",
            "source_time_basis": sorted(
                {
                    o.source_time_basis
                    for period in imported.multi_period_demand.periods
                    for o in period.observations
                }
            ),
        },
        "demand_basis": "historical_boardings"
        if str(metadata.demand_source_type) == "ticketing"
        else "independent_arrivals",
        "fleet_ceiling": p.available_fleet_limit,
        "layover_minutes": dict.fromkeys(DIRECTIONS, layover),
        "directions": {},
    }
    for direction, terminal, first, last in (
        ("outbound", p.terminal_1_name, p.terminal_1_first_departure, p.terminal_1_last_departure),
        ("inbound", p.terminal_2_name, p.terminal_2_first_departure, p.terminal_2_last_departure),
    ):
        trips = sorted(
            (t for t in base.trips_b if t.departure_terminal == terminal),
            key=lambda t: t.departure_seconds,
        )
        if first % 60 or last % 60 or any(t.departure_seconds % 60 for t in trips):
            raise ValueError(f"{direction} Scenario B has non-whole-minute authority")
        runtimes = {
            (
                (t.arrival_seconds - t.departure_seconds) // 60
                if t.arrival_seconds is not None
                else p.trip_runtime_minutes
            )
            for t in trips
        }
        if len(runtimes) != 1 or any(
            t.arrival_seconds is not None and (t.arrival_seconds - t.departure_seconds) % 60
            for t in trips
        ):
            raise ValueError(
                f"{direction} variable source-trip runtimes require explicit runtime_periods bundle"
            )
        observations = sorted(
            (o for o in derived.derived_observations if o.direction.value == direction),
            key=lambda o: o.interval_start,
        )
        if any(o.interval_start % 60 or o.interval_end % 60 for o in observations):
            raise ValueError("demand bucket boundaries must be whole minutes")
        data["directions"][direction] = {
            "first": first // 60,
            "last": last // 60,
            "trip_count": len(trips),
            "runtime_minutes": next(iter(runtimes)),
            "baseline": [t.departure_seconds // 60 for t in trips],
            "demand": [
                {
                    "start": o.interval_start // 60,
                    "end": o.interval_end // 60,
                    "passengers": o.average_daily_passengers,
                }
                for o in observations
            ],
            "protected_windows": [],
        }
    if sum(d["trip_count"] for d in data["directions"].values()) != p.total_daily_trips:
        raise ValueError("Scenario B trip total differs from THAM_SO_B authority")
    data["capacity_policy"] = capacity_policy
    if p.vehicle_capacity_passengers is not None:
        data.update(
            vehicle_capacity=p.vehicle_capacity_passengers,
            maximum_load_factor=p.maximum_load_factor
            if maximum_load_factor is None
            else maximum_load_factor,
            capacity_policy=capacity_policy,
        )
    return validate_bundle(data)

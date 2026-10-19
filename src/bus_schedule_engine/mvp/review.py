"""Deterministic operational evidence; review policy never becomes service authority."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from .circulation import assign_fleet, validate_chains
from .input import DIRECTIONS, number, validate_bundle
from .quality import evaluate, waiting

WARNING_DEFAULTS = {
    "waiting_increase_minutes": 1.0,
    "waiting_increase_relative": 0.20,
    "high_demand_fraction": 0.75,
    "departure_reduction_fraction": 0.25,
    "headway_increase_minutes": 3.0,
}
INSUFFICIENT = "CHƯA ĐỦ DỮ LIỆU ĐÁNH GIÁ"


def warning_policy(settings=None):
    if settings is not None and not isinstance(settings, dict):
        raise ValueError("review settings must be an object")
    policy = WARNING_DEFAULTS | (settings or {})
    if set(policy) != set(WARNING_DEFAULTS):
        raise ValueError("unknown review setting")
    for key, value in policy.items():
        number(value, key)
        if key.endswith("fraction") and not 0 < value <= 1:
            raise ValueError(f"{key} must be in (0,1]")
    return policy


def bucket_evidence(times, bucket):
    """Keep whole gaps and clipped overlap; integrate against the following departure."""
    start, end = bucket["start"], bucket["end"]
    rate = bucket["passengers"] / (end - start)
    gaps = []
    for left, right in zip(times, times[1:], strict=False):
        a, z = max(left, start), min(right, end)
        if a < z:
            gaps.append(
                {
                    "preceding_departure": left,
                    "following_departure": right,
                    "gap_minutes": right - left,
                    "overlap_start": a,
                    "overlap_end": z,
                    "overlap_minutes": z - a,
                    "waiting_integral": rate * ((right - a) ** 2 - (right - z) ** 2) / 2,
                }
            )
    departures = [t for t in times if start <= t < end or t == end == times[-1]]
    local = waiting(times, [bucket])
    return {
        "departures": departures,
        "departure_count": len(departures),
        "gaps": gaps,
        "maximum_intersecting_headway": max((g["gap_minutes"] for g in gaps), default=0),
        "waiting_minutes": local["wait"],
        "waiting_integral": local["integral"],
        "served_passengers": local["passengers"],
        "outside_service_passengers": local["unserved"],
    }


def _buckets(data, baseline, candidate, policy):
    if baseline is None or candidate is None:
        return []
    rows = []
    for direction in DIRECTIONS:
        d = data["directions"][direction]
        peak_rate = max(b["passengers"] / (b["end"] - b["start"]) for b in d["demand"])
        for bucket in d["demand"]:
            b = bucket_evidence(baseline["departures"][direction], bucket)
            c = bucket_evidence(candidate["departures"][direction], bucket)
            bw, cw = b["waiting_minutes"], c["waiting_minutes"]
            delta = cw - bw if bw is not None and cw is not None else None
            materiality = max(
                policy["waiting_increase_minutes"], (bw or 0) * policy["waiting_increase_relative"]
            )
            high = (
                peak_rate > 0
                and bucket["passengers"] / (bucket["end"] - bucket["start"])
                >= peak_rate * policy["high_demand_fraction"]
            )
            warnings = []
            if delta is not None and delta > materiality + 1e-9:
                warnings.append("MATERIAL_WAIT_DETERIORATION")
            if (
                high
                and b["departure_count"]
                and (b["departure_count"] - c["departure_count"]) / b["departure_count"]
                >= policy["departure_reduction_fraction"]
            ):
                warnings.append("HIGH_DEMAND_FREQUENCY_REDUCTION")
            if (
                high
                and c["maximum_intersecting_headway"] > b["maximum_intersecting_headway"]
                and c["maximum_intersecting_headway"] - b["maximum_intersecting_headway"]
                >= policy["headway_increase_minutes"]
            ):
                warnings.append("HIGH_DEMAND_LONGER_GAP")
            protection = [
                w
                for w in candidate["quality"]["protected_windows"]
                if w["direction"] == direction
                and w["start"] < bucket["end"]
                and w["end"] > bucket["start"]
            ]
            rows.append(
                {
                    "direction": direction,
                    "interval_start": bucket["start"],
                    "interval_end": bucket["end"],
                    "demand_passengers": bucket["passengers"],
                    "demand_rate_per_minute": bucket["passengers"]
                    / (bucket["end"] - bucket["start"]),
                    "high_demand": high,
                    "baseline": b,
                    "candidate": c,
                    "waiting_difference_minutes": delta,
                    "waiting_difference_percent": 100 * delta / bw
                    if delta is not None and bw
                    else None,
                    "demand_weighted_waiting_impact": c["waiting_integral"] - b["waiting_integral"],
                    "warning_materiality_minutes": materiality,
                    "warnings": warnings,
                    "protected_windows": protection,
                    "protection_authority": "EXPLICIT_SCOPED_WINDOWS"
                    if protection
                    else INSUFFICIENT,
                    "regimes": [
                        r
                        for r in candidate["regimes"]
                        if r["direction"] == direction
                        and r["start_time"] < bucket["end"]
                        and r["end_time"] > bucket["start"]
                    ],
                }
            )
    return rows


def circulation_evidence(data, candidate):
    if candidate is None:
        return None
    fleet = candidate["vehicle_chains"]
    if fleet["status"] != "EXACT":
        return {
            "status": fleet["status"],
            "required_fleet": None,
            "initial_vehicles_required": None,
            "vehicles": [],
            "terminal_flow": [],
        }
    validate_chains(data, candidate["departures"], fleet)
    by_id = {t["trip_id"]: t for t in fleet["trips"]}
    vehicles = []
    events = defaultdict(lambda: {d: {"physically_present": 0, "ready": 0} for d in DIRECTIONS})
    for chain in fleet["chains"]:
        trips = []
        for i, tid in enumerate(chain):
            trip = by_id[tid]
            following = by_id[chain[i + 1]] if i + 1 < len(chain) else None
            destination = "inbound" if trip["direction"] == "outbound" else "outbound"
            trips.append(
                trip
                | {
                    "destination": destination,
                    "turnaround_slack_minutes": following["departure"] - trip["ready"]
                    if following
                    else None,
                    "actual_turnaround_minutes": following["departure"] - trip["arrival"]
                    if following
                    else None,
                }
            )
            for metric in ("physically_present", "ready"):
                events[trip["departure"]][trip["direction"]][metric] -= 1
            events[trip["arrival"]][destination]["physically_present"] += 1
            events[trip["ready"]][destination]["ready"] += 1
        vehicles.append(
            {
                "vehicle_id": trips[0]["vehicle_id"],
                "starting_terminal": trips[0]["direction"],
                "trips": trips,
            }
        )
    initial = fleet["initial_vehicles_required"]
    state = {d: {"physically_present": initial[d], "ready": initial[d]} for d in DIRECTIONS}
    first = min(t["departure"] for t in fleet["trips"])
    flow = [{"minute": first - 1, **deepcopy(state), "running": 0, "unavailable": 0}]
    for minute, changes in sorted(events.items()):
        for d in DIRECTIONS:
            for metric, value in changes[d].items():
                state[d][metric] += value
            if not 0 <= state[d]["ready"] <= state[d]["physically_present"]:
                raise ValueError("terminal flow violates physical/ready conservation")
        running = fleet["required_fleet"] - sum(s["physically_present"] for s in state.values())
        unavailable = fleet["required_fleet"] - sum(s["ready"] for s in state.values())
        if not 0 <= running <= unavailable <= fleet["required_fleet"]:
            raise ValueError("terminal flow violates fleet conservation")
        flow.append(
            {"minute": minute, **deepcopy(state), "running": running, "unavailable": unavailable}
        )
    return {
        "status": fleet["status"],
        "required_fleet": fleet["required_fleet"],
        "fleet_ceiling": data["fleet_ceiling"],
        "initial_vehicles_required": initial,
        "vehicles": vehicles,
        "terminal_flow": flow,
        "maximum_running": max(e["running"] for e in flow),
        "maximum_runtime_plus_layover": max(e["unavailable"] for e in flow),
        "basis": "Modeled required fleet only; post-event states, simultaneous events netted; no depot movements or extra declared idle stock modeled",
    }


def _assessment(data, candidate, buckets):
    if candidate is None:
        return {
            "candidate_id": None,
            "readiness": "INSUFFICIENT_OPERATIONAL_EVIDENCE",
            "hard_rule_status": "UNRESOLVED",
            "approval_blocked": False,
            "missing_evidence": ["TIMETABLE_UNAVAILABLE"],
            "evidence_label": INSUFFICIENT,
            "stock_status": "UNVERIFIED",
            "stock_comparison": {},
            "protected_windows": [],
            "actual_onboard_load_certified": False,
            "capacity_proxy": None,
            "hard_failures": [],
        }
    q, fleet = candidate["quality"], candidate["vehicle_chains"]
    missing = []
    unprotected = [d for d in DIRECTIONS if not data["directions"][d]["protected_windows"]]
    if unprotected:
        missing.append("PROTECTION_AUTHORITY_MISSING")
    stock_comparison = {}
    if "initial_vehicles" not in data:
        stock = "UNVERIFIED"
        missing.append("INITIAL_STOCK_UNCONFIRMED")
    elif fleet["status"] == "INITIAL_STOCK_INFEASIBLE":
        stock = "CONFIRMED_INFEASIBLE"
    elif fleet["status"] == "EXACT":
        for d in DIRECTIONS:
            required, declared = fleet["initial_vehicles_required"][d], data["initial_vehicles"][d]
            stock_comparison[d] = {
                "required": required,
                "declared": declared,
                "sufficient": required <= declared,
            }
        stock = (
            "VERIFIED_AGAINST_DECLARED_STOCK"
            if all(s["sufficient"] for s in stock_comparison.values())
            else "CONFIRMED_INFEASIBLE"
        )
    else:
        stock = "UNVERIFIED"
        missing.append("INITIAL_STOCK_COMPARISON_INCOMPLETE")
    for key in ("layover", "runtime"):
        if data["provenance"].get(f"{key}_verified") is not True:
            missing.append(f"{key.upper()}_UNVERIFIED")
    missing.append("ONBOARD_LOAD_UNCERTIFIED")
    if q["operational_certification"] != "COMPLETE":
        missing.append("EXACT_CIRCULATION_INCOMPLETE")
    if any(q["outside_service_passengers"].values()):
        missing.append("DEMAND_OUTSIDE_SERVICE")
    failures = q["proven_hard_failures"]
    if failures:
        readiness = "CONFIRMED_HARD_RULE_FAILURE"
    elif any(b["warnings"] for b in buckets):
        readiness = "HUMAN_REVIEW_REQUIRED"
    elif missing:
        readiness = "INSUFFICIENT_OPERATIONAL_EVIDENCE"
    else:
        readiness = "READY_FOR_HUMAN_APPROVAL_CONSIDERATION"
    # Onboard certification is disclosed separately and is not a universal service approval rule.
    required_missing = [m for m in missing if m != "ONBOARD_LOAD_UNCERTIFIED"]
    if readiness == "INSUFFICIENT_OPERATIONAL_EVIDENCE" and not required_missing:
        readiness = "READY_FOR_HUMAN_APPROVAL_CONSIDERATION"
    return {
        "candidate_id": candidate["id"],
        "readiness": readiness,
        "hard_rule_status": "CONFIRMED_FAILURE"
        if failures
        else "PASS_DECLARED_RULES"
        if q["hard_constraints_pass"]
        else "UNRESOLVED",
        "approval_blocked": bool(failures),
        "hard_failures": failures,
        "protected_windows": q["protected_windows"],
        "unprotected_directions": unprotected,
        "missing_evidence": missing,
        "evidence_label": INSUFFICIENT if missing else "ĐỦ BẰNG CHỨNG MÔ HÌNH ĐỂ TRÌNH XEM XÉT",
        "stock_status": stock,
        "stock_comparison": stock_comparison,
        "declared_stock": data.get("initial_vehicles"),
        "engine_operational_certification": q["operational_certification"],
        "actual_onboard_load_certified": False,
        "capacity_proxy": q["capacity"],
    }


def _validated_candidate(data, candidate, settings):
    if candidate is None:
        return None
    if candidate["vehicle_chains"]["status"] == "EXACT":
        validate_chains(data, candidate["departures"], candidate["vehicle_chains"])
    quality = evaluate(
        data, candidate["departures"], candidate["regimes"], candidate["vehicle_chains"], settings
    )
    if quality != candidate["quality"]:
        raise ValueError("operational review differs from validated engine quality")
    return candidate


def _scenarios(data, result, selected, scenarios, policy):
    if scenarios is None:
        return []
    if not isinstance(scenarios, list):
        raise ValueError("operating scenarios must be a list")
    output, names = [], set()
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) - {
            "name",
            "runtime_minutes",
            "layover_minutes",
        }:
            raise ValueError("scenario supports only name, runtime_minutes and layover_minutes")
        name = scenario.get("name")
        if not isinstance(name, str) or not name.strip() or name in names or len(scenario) < 2:
            raise ValueError("scenario requires a unique name and explicit operating changes")
        names.add(name)
        changed = deepcopy(data)
        if "layover_minutes" in scenario:
            changed["layover_minutes"] = scenario["layover_minutes"]
            changed["provenance"]["layover_verified"] = False
        if "runtime_minutes" in scenario:
            if not isinstance(scenario["runtime_minutes"], dict) or set(
                scenario["runtime_minutes"]
            ) != set(DIRECTIONS):
                raise ValueError("scenario runtime_minutes must contain both directions")
            for d, minutes in scenario["runtime_minutes"].items():
                changed["directions"][d].pop("runtime_periods", None)
                changed["directions"][d]["runtime_minutes"] = minutes
            changed["provenance"]["runtime_verified"] = False
        changed = validate_bundle(changed)
        if selected is None:
            output.append(
                {
                    "name": name,
                    "changes": scenario,
                    "independently_validated": False,
                    "assessment": _assessment(changed, None, []),
                    "circulation": None,
                }
            )
            continue
        fleet = assign_fleet(changed, selected["departures"], settings=result.get("settings"))
        quality = evaluate(
            changed, selected["departures"], selected["regimes"], fleet, result.get("settings")
        )
        candidate = selected | {"quality": quality, "vehicle_chains": fleet}
        baseline_times = {d: changed["directions"][d]["baseline"] for d in DIRECTIONS}
        baseline_fleet = assign_fleet(changed, baseline_times, settings=result.get("settings"))
        baseline = {"departures": baseline_times}
        buckets = _buckets(changed, baseline, candidate, policy)
        output.append(
            {
                "name": name,
                "changes": scenario,
                "departures_unchanged": True,
                "independently_validated": fleet["status"] == "EXACT",
                "quality": quality,
                "baseline_quality": evaluate(
                    changed, baseline_times, [], baseline_fleet, result.get("settings")
                ),
                "assessment": _assessment(changed, candidate, buckets),
                "circulation": circulation_evidence(changed, candidate),
            }
        )
    return output


def build_review(data, result, warning_settings=None, scenarios=None):
    data, policy = validate_bundle(data), warning_policy(warning_settings)
    settings = result.get("settings", {})
    baseline = _validated_candidate(data, result.get("baseline_evidence"), settings)
    selected = _validated_candidate(data, result.get("recommended"), settings)
    alternatives = [_validated_candidate(data, c, settings) for c in result.get("alternatives", [])]
    candidate = (
        selected
        if selected and selected["source"] == "OPTIMIZED"
        else alternatives[0]
        if alternatives
        else selected or baseline
    )
    buckets = _buckets(data, baseline, candidate, policy)
    selected_buckets = (
        buckets if candidate is selected else _buckets(data, baseline, selected, policy)
    )
    bq, sq, cq = (c["quality"] if c else {} for c in (baseline, selected, candidate))
    summary = {
        "baseline_fleet": bq.get("required_fleet"),
        "selected_fleet": sq.get("required_fleet"),
        "fleet_ceiling": data["fleet_ceiling"],
        "baseline_waiting_minutes": bq.get("waiting_minutes"),
        "selected_waiting_minutes": sq.get("waiting_minutes"),
        "waiting_difference_minutes": sq.get("waiting_difference_minutes"),
        "waiting_difference_percent": sq.get("waiting_difference_percent"),
        "baseline_maximum_headway": bq.get("maximum_headway"),
        "selected_maximum_headway": sq.get("maximum_headway"),
        "maximum_headway_difference": sq["maximum_headway"] - bq["maximum_headway"]
        if sq and bq
        else None,
        "comparison_fleet": cq.get("required_fleet"),
        "comparison_waiting_minutes": cq.get("waiting_minutes"),
        "comparison_waiting_difference_minutes": cq.get("waiting_difference_minutes"),
        "comparison_maximum_headway": cq.get("maximum_headway"),
    }
    maximum = cq.get("maximum_headway")
    longest = (
        [
            {
                "direction": d,
                "preceding_departure": a,
                "following_departure": z,
                "gap_minutes": z - a,
            }
            for d in DIRECTIONS
            for a, z in zip(
                candidate["departures"][d], candidate["departures"][d][1:], strict=False
            )
            if z - a == maximum
        ]
        if candidate
        else []
    )
    exceptions = sorted(
        [b for b in buckets if b["warnings"] or any(not w["pass"] for w in b["protected_windows"])],
        key=lambda b: (
            not any(not w["pass"] for w in b["protected_windows"]),
            -max(0, b["demand_weighted_waiting_impact"]),
            b["direction"],
            b["interval_start"],
        ),
    )
    return {
        "schema_version": "mvp3_operational_review_v1",
        "route_id": data["route_id"],
        "operator_decision": result.get("operator_decision", "UNRESOLVED"),
        "search_status": result.get("search_status", result["status"]),
        "decision": result.get("decision"),
        "selected_id": selected["id"] if selected else None,
        "selected_source": selected["source"] if selected else None,
        "comparison_id": candidate["id"] if candidate else None,
        "comparison_role": "BASELINE_REFERENCE"
        if selected is None and candidate is baseline
        else "GENERATED_ALTERNATIVE"
        if candidate is not selected
        else "SELECTED_TIMETABLE",
        "comparison_change_assessment": candidate.get("change_assessment", result.get("decision"))
        if candidate
        else None,
        "summary": summary,
        "warning_policy": policy,
        "selected_assessment": _assessment(data, selected, selected_buckets),
        "comparison_assessment": _assessment(data, candidate, buckets),
        "buckets": buckets,
        "exceptions": exceptions,
        "maximum_headway_gaps": longest,
        "circulation": circulation_evidence(data, selected),
        "comparison_circulation": circulation_evidence(data, candidate)
        if candidate is not selected
        else None,
        "sensitivities": _scenarios(data, result, selected, scenarios, policy),
        "provenance": data["provenance"],
        "demand_basis": data["demand_basis"],
        "assumptions": {
            "layover_minutes": data["layover_minutes"],
            "directions": {
                d: {
                    k: v
                    for k, v in data["directions"][d].items()
                    if k in {"first", "last", "trip_count", "runtime_minutes", "runtime_periods"}
                }
                for d in DIRECTIONS
            },
        },
        "regimes": candidate["regimes"] if candidate else [],
        "baseline_departures": baseline["departures"] if baseline else None,
        "comparison_departures": candidate["departures"] if candidate else None,
        "rejected_hard_failures": result["diagnostics"].get("best_rejected_failures", []),
        "rejected_service_violations": result["diagnostics"].get(
            "best_rejected_service_violations", []
        ),
    }

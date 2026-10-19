"""Independent appraisal of actual external departures and recorded vehicle trips."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .circulation import assign_fleet
from .input import DIRECTIONS, integer, number, runtime_at, validate_bundle
from .quality import evaluate, waiting
from .review import bucket_evidence, warning_policy


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _departures(times):
    if not isinstance(times, list) or len(times) < 2:
        raise ValueError("each direction requires at least two departures")
    for t in times:
        integer(t, "departure")
        if t >= 1440:
            raise ValueError("departure is outside the operating day")
    if times != sorted(set(times)):
        raise ValueError("departures must be sorted and unique")
    return times


def _buckets(data, direction):
    return [
        {
            "start": b["interval_start"],
            "end": b["interval_end"],
            "passengers": b["demand_passengers"],
        }
        for b in data["demand"]
        if b["direction"] == direction
    ]


def _alternative(source, departures, data):
    result = {"source": source, "directions": {}}
    integral = passengers = 0.0
    for d in DIRECTIONS:
        times = _departures(departures[d])
        headways = [b - a for a, b in zip(times, times[1:], strict=False)]
        buckets = _buckets(data, d)
        modeled = waiting(times, buckets) if buckets else None
        gaps = [
            {"preceding_departure": a, "following_departure": b, "gap_minutes": b - a}
            for a, b in zip(times, times[1:], strict=False)
        ]
        if modeled:
            integral += modeled["integral"]
            passengers += modeled["passengers"]
        result["directions"][d] = {
            "departures": times,
            "first_departure": times[0],
            "last_departure": times[-1],
            "trip_count": len(times),
            "headways": headways,
            "gaps": gaps,
            "minimum_headway": min(headways),
            "maximum_headway": max(headways),
            "headway_distribution": [
                {"headway_minutes": h, "count": count}
                for h, count in sorted(Counter(headways).items())
            ],
            "distinct_headway_values": len(set(headways)),
            "headway_change_count": sum(
                a != b for a, b in zip(headways, headways[1:], strict=False)
            ),
            "potential_regime_irregularity": len(set(headways)) > 1,
            "end_tail": {
                "last_departure": times[-1],
                "last_three_gaps": gaps[-3:],
                "final_hour_gaps": [g for g in gaps if g["following_departure"] > times[-1] - 60],
            },
            "modeled_waiting": modeled,
            "waiting_minutes": modeled["wait"] if modeled else None,
        }
    result.update(
        waiting_minutes=integral / passengers if passengers else None,
        waiting_integral=integral if data["demand"] else None,
        modeled_passengers=passengers if data["demand"] else None,
        outside_service_passengers=sum(
            v["modeled_waiting"]["unserved"] for v in result["directions"].values()
        )
        if data["demand"]
        else None,
    )
    return result


def _comparison_buckets(data, alternatives):
    policy, rows = warning_policy(), []
    for d in DIRECTIONS:
        demand = _buckets(data, d)
        peak_rate = max((b["passengers"] / (b["end"] - b["start"]) for b in demand), default=0)
        for bucket in demand:
            b, x = [
                bucket_evidence(alternatives[s]["directions"][d]["departures"], bucket)
                for s in ("BASELINE", "EXTERNAL_CANDIDATE")
            ]
            bw, xw = b["waiting_minutes"], x["waiting_minutes"]
            covered = [
                (
                    max(bucket["start"], alternatives[s]["directions"][d]["first_departure"]),
                    min(bucket["end"], alternatives[s]["directions"][d]["last_departure"]),
                )
                for s in ("BASELINE", "EXTERNAL_CANDIDATE")
            ]
            comparable = not bucket["passengers"] or covered[0] == covered[1]
            lost = x["outside_service_passengers"] - b["outside_service_passengers"]
            delta = xw - bw if comparable and bw is not None and xw is not None else None
            materiality = max(
                policy["waiting_increase_minutes"], (bw or 0) * policy["waiting_increase_relative"]
            )
            high = (
                peak_rate > 0
                and bucket["passengers"] / (bucket["end"] - bucket["start"])
                >= peak_rate * policy["high_demand_fraction"]
            )
            warnings = []
            if lost > 1e-9:
                warnings.append("SERVICE_COVERAGE_LOSS")
            if delta is not None and delta > materiality + 1e-9:
                warnings.append("MATERIAL_WAIT_DETERIORATION")
            if (
                high
                and b["departure_count"]
                and 1 - x["departure_count"] / b["departure_count"]
                >= policy["departure_reduction_fraction"]
            ):
                warnings.append("HIGH_DEMAND_FREQUENCY_REDUCTION")
            if (
                high
                and x["maximum_intersecting_headway"] - b["maximum_intersecting_headway"]
                >= policy["headway_increase_minutes"]
            ):
                warnings.append("HIGH_DEMAND_LONGER_GAP")
            rows.append(
                {
                    "direction": d,
                    "interval_start": bucket["start"],
                    "interval_end": bucket["end"],
                    "demand_passengers": bucket["passengers"],
                    "baseline": b,
                    "candidate": x,
                    "waiting_difference_minutes": delta,
                    "demand_weighted_waiting_impact": x["waiting_integral"] - b["waiting_integral"]
                    if comparable
                    else None,
                    "waiting_population_comparable": comparable,
                    "outside_service_passenger_change": lost,
                    "warnings": warnings,
                    "protection_status": "UNVERIFIED",
                    "confidence_limitation": "Historical boarding proxy with uniform within-bucket arrivals; protection policy not supplied; outside-service demand excluded from waiting.",
                }
            )
    return rows


def _fleet(data, minimum_layover):
    trips, issues, differences = data["vehicle_trips"], [], []
    expected = Counter(
        (d, t["departure"]) for d in DIRECTIONS for t in data["timetables"]["EXTERNAL_CANDIDATE"][d]
    )
    actual = Counter((t["direction"], t["departure"]) for t in trips)
    if actual != expected:
        issues.append(
            {
                "code": "TRIP_COVERAGE_MISMATCH",
                "missing": sorted((list(k) + [n] for k, n in (expected - actual).items())),
                "extra": sorted((list(k) + [n] for k, n in (actual - expected).items())),
            }
        )
    for d in DIRECTIONS:
        local = [t for t in trips if t["direction"] == d]
        if [t["trip_sequence"] for t in local] != list(range(1, len(local) + 1)) or [
            t["departure"] for t in local
        ] != sorted({t["departure"] for t in local}):
            issues.append({"code": "DIRECTIONAL_TRIP_SEQUENCE_MISMATCH", "direction": d})
    groups = defaultdict(list)
    for trip in trips:
        groups[trip["vehicle_id"]].append(trip)
    vehicles, initial, valid_count = [], dict.fromkeys(DIRECTIONS, 0), 0
    for vehicle, chain in sorted(groups.items()):
        chain = sorted(chain, key=lambda t: (t["departure"], t["direction"], t["trip_sequence"]))
        initial[chain[0]["direction"]] += 1
        local_issues, records = [], []
        for i, trip in enumerate(chain):
            following = chain[i + 1] if i + 1 < len(chain) else None
            implied = following["departure"] - trip["arrival"] if following else None
            record = trip | {
                "next_departure": following["departure"] if following else None,
                "implied_layover": implied,
                "turnaround_margin": implied - minimum_layover
                if implied is not None and minimum_layover is not None
                else None,
            }
            records.append(record)
            reference = {
                "vehicle_id": vehicle,
                "source_sheet": trip["source_sheet"],
                "source_cells": trip["source_cells"],
            }
            if trip["arrival"] <= trip["departure"]:
                local_issues.append(reference | {"code": "INVALID_TRIP_RUNTIME"})
            if following:
                if implied < 0:
                    local_issues.append(
                        reference | {"code": "OVERLAPPING_ASSIGNMENTS", "implied_layover": implied}
                    )
                if following["direction"] == trip["direction"]:
                    local_issues.append(reference | {"code": "TERMINAL_MISMATCH"})
                if minimum_layover is not None and implied < minimum_layover:
                    local_issues.append(
                        reference
                        | {"code": "INSUFFICIENT_SCENARIO_LAYOVER", "implied_layover": implied}
                    )
                if trip["recorded_layover"] is None:
                    differences.append(
                        reference | {"code": "RECORDED_LAYOVER_MISSING", "implied_layover": implied}
                    )
                elif abs(implied - trip["recorded_layover"]) > 1e-8:
                    differences.append(
                        reference
                        | {
                            "code": "RECORDED_LAYOVER_DIFFERS",
                            "recorded": trip["recorded_layover"],
                            "recomputed": implied,
                        }
                    )
            elif trip["recorded_layover"] is not None:
                differences.append(
                    reference
                    | {
                        "code": "LAYOVER_WITHOUT_FOLLOWING_TRIP",
                        "recorded": trip["recorded_layover"],
                    }
                )
        issues.extend(local_issues)
        valid_count += not local_issues
        vehicles.append(
            {
                "vehicle_id": vehicle,
                "starting_terminal": chain[0]["direction"],
                "trip_count": len(chain),
                "first_departure": chain[0]["departure"],
                "last_arrival": chain[-1]["arrival"],
                "running_duration": sum(t["arrival"] - t["departure"] for t in chain),
                "operating_span": chain[-1]["arrival"] - chain[0]["departure"],
                "trips": records,
                "chain_valid": not local_issues,
            }
        )
    summaries = data["vehicle_summaries"]
    if Counter(s["vehicle_id"] for s in summaries) != Counter({v: 1 for v in groups}):
        differences.append(
            {"code": "VEHICLE_SUMMARY_COVERAGE_MISMATCH", "source_sheet": "So chuyen cho tung xe"}
        )
    by_id = {v["vehicle_id"]: v for v in vehicles}
    for summary in summaries:
        v = by_id.get(summary["vehicle_id"])
        if not v:
            continue
        counts = Counter(t["direction"] for t in v["trips"])
        controls = {
            "trip_count": v["trip_count"],
            "inbound_count": counts["inbound"],
            "outbound_count": counts["outbound"],
            "first_departure": v["first_departure"],
            "last_arrival": v["last_arrival"],
        }
        for field, recomputed in controls.items():
            if summary[field] != recomputed:
                differences.append(
                    {
                        "code": "VEHICLE_SUMMARY_DIFFERS",
                        "vehicle_id": v["vehicle_id"],
                        "field": field,
                        "recorded": summary[field],
                        "recomputed": recomputed,
                        "source_sheet": summary["source_sheet"],
                        "source_cells": summary["source_cells"],
                    }
                )
        if summary["reported_operating_duration"] != v["running_duration"]:
            differences.append(
                {
                    "code": "OPERATING_DURATION_UNRESOLVED",
                    "vehicle_id": v["vehicle_id"],
                    "recorded": summary["reported_operating_duration"],
                    "recomputed_running_duration": v["running_duration"],
                    "recomputed_operating_span": v["operating_span"],
                    "source_sheet": summary["source_sheet"],
                    "source_cells": summary["source_cells"],
                }
            )
    output = {}
    for source in ("BASELINE", "EXTERNAL_CANDIDATE"):
        reported = {d: data["summary"][source][d]["reported_fleet"] for d in DIRECTIONS}
        agreed = reported["outbound"] if len(set(reported.values())) == 1 else None
        output[source] = {
            "reported_fleet": agreed,
            "reported_fleet_by_direction": reported,
            "reported_fleet_status": "REPORTED_FLEET"
            if agreed is not None
            else "CONFLICTING_REPORTED_FLEET",
            "minimum_fleet": None,
            "minimum_fleet_status": "MINIMUM_FLEET_UNVERIFIED",
            "runtime_status": "BASELINE_RUNTIME_UNAVAILABLE"
            if source == "BASELINE"
            else "PER_TRIP_RECORDED_ARRIVALS",
            "validated_assignment_fleet": None,
        }
    x = output["EXTERNAL_CANDIDATE"]
    if x["reported_fleet"] != len(groups):
        differences.append(
            {
                "code": "REPORTED_FLEET_DIFFERS_FROM_RECORDED_IDS",
                "reported": x["reported_fleet"],
                "recorded_identifiers": len(groups),
            }
        )
    incomplete = any(i["code"] == "INCOMPLETE_VEHICLE_ROW" for i in data["issues"])
    valid = not issues and not incomplete and actual == expected
    x.update(
        schedule_status="CHAIN_VALIDATED" if valid else "CHAIN_INVALID",
        validated_assignment_fleet=len(groups) if valid else None,
        recorded_vehicle_count=len(groups),
        validated_chain_count=valid_count,
        initial_terminal_requirements=initial,
        initial_stock_status="UNCONFIRMED_OPERATOR_STOCK",
        minimum_layover_assumption=minimum_layover,
        mandatory_minimum_layover="NOT_PROVIDED",
        chain_issues=issues,
        source_discrepancies=differences,
        vehicles=vehicles,
        validation_scope="Recorded departures, arrivals, opposite terminals, coverage and non-overlap only; no deadhead, driver-shift or labor certification; no authoritative minimum layover or minimum-fleet proof.",
    )
    return output


def demand_fingerprint(data):
    values = [
        {k: b[k] for k in ("direction", "interval_start", "interval_end", "demand_passengers")}
        for b in data["demand"]
    ]
    return hashlib.sha256(_json(values).encode("utf-8")).hexdigest()


def _three_way(data, alternatives, comparison, context):
    if comparison is None:
        return {
            "rankable": False,
            "reasons": ["OPTIMIZED_RESULT_NOT_SUPPLIED"],
            "separate_result": None,
        }
    if (
        not isinstance(comparison, dict)
        or not isinstance(comparison.get("departures"), dict)
        or set(comparison["departures"]) != set(DIRECTIONS)
    ):
        raise ValueError("comparison requires actual departures for both directions")
    separate = _alternative("OPTIMIZED", comparison["departures"], data)
    separate["id"] = comparison.get("id", "C")
    separate["evaluation_scope"] = (
        "Actual C departures recomputed on benchmark demand; original quality claims are not reused; comparability pending."
    )
    required = {
        "route_identity",
        "operating_day_profile",
        "direction_definitions",
        "demand_basis",
        "runtime_layover_assumptions",
        "trip_count_policy",
        "protected_service_policy",
        "fleet_assumptions",
    }
    reasons = []
    for label, candidate in [("BENCHMARK", context), ("OPTIMIZED", comparison.get("context"))]:
        if (
            not isinstance(candidate, dict)
            or set(candidate) != required
            or any(v is None or v == "" for v in candidate.values())
        ):
            reasons.append(f"{label}_EVALUATION_CONTEXT_INCOMPLETE")
        elif (
            not isinstance(candidate["operating_day_profile"], str)
            or not candidate["operating_day_profile"].strip()
            or candidate["operating_day_profile"].strip().upper()
            in {"UNVERIFIED", "UNKNOWN", "UNAVAILABLE"}
        ):
            reasons.append(f"{label}_OPERATING_DAY_PROFILE_UNVERIFIED")
    if not reasons:
        reasons.extend(
            f"CONTEXT_MISMATCH:{k}"
            for k in sorted(required)
            if context[k] != comparison["context"][k]
        )
        if (
            context["route_identity"] != data["route_identity"]
            or context["direction_definitions"] != data["route_identity"]
        ):
            reasons.append("ROUTE_OR_DIRECTION_EVIDENCE_MISMATCH")
        if not data["demand"] or context["demand_basis"] != demand_fingerprint(data):
            reasons.append("DEMAND_BASIS_MISMATCH_OR_UNRESOLVED")
    recomputed = {}
    if not reasons:
        try:
            model, policy, fleet = (
                context["runtime_layover_assumptions"],
                context["trip_count_policy"],
                context["fleet_assumptions"],
            )
            if (
                set(model) != {"runtime_minutes", "layover_minutes"}
                or set(model["runtime_minutes"]) != set(DIRECTIONS)
                or set(policy) != set(DIRECTIONS)
                or set(context["protected_service_policy"]) != set(DIRECTIONS)
                or set(fleet) - {"fleet_ceiling", "initial_vehicles"}
            ):
                raise ValueError("explicit common scenario has unsupported fields")
            bundle = {
                "route_id": "external-comparison-scenario",
                "provenance": {
                    "source": "explicit compatible evaluation contexts",
                    "runtime_verified": False,
                    "layover_verified": False,
                },
                "demand_basis": "historical_boardings",
                "fleet_ceiling": fleet["fleet_ceiling"],
                "layover_minutes": model["layover_minutes"],
                "directions": {},
            }
            if "initial_vehicles" in fleet:
                bundle["initial_vehicles"] = fleet["initial_vehicles"]
            for d in DIRECTIONS:
                b = alternatives["BASELINE"]["directions"][d]
                bundle["directions"][d] = {
                    "first": b["first_departure"],
                    "last": b["last_departure"],
                    "trip_count": policy[d],
                    "baseline": b["departures"],
                    "demand": _buckets(data, d),
                    "runtime_minutes": model["runtime_minutes"][d],
                    "protected_windows": context["protected_service_policy"][d],
                }
            bundle = validate_bundle(bundle)
            if any(
                t["arrival"] - t["departure"]
                != runtime_at(bundle["directions"][t["direction"]], t["departure"])
                for t in data["vehicle_trips"]
            ):
                raise ValueError("recorded external runtimes differ from the common scenario")
            for source, alternative in (alternatives | {"OPTIMIZED": separate}).items():
                departures = {d: alternative["directions"][d]["departures"] for d in DIRECTIONS}
                if any(
                    len(departures[d]) != policy[d]
                    or departures[d][0] != bundle["directions"][d]["first"]
                    or departures[d][-1] != bundle["directions"][d]["last"]
                    for d in DIRECTIONS
                ):
                    raise ValueError("trip-count or service-endpoint policy differs")
                assignment = assign_fleet(bundle, departures)
                quality = evaluate(bundle, departures, [], assignment)
                if assignment["status"] != "EXACT" or not quality["hard_constraints_pass"]:
                    raise ValueError(f"{source}: common operating scenario not validated")
                if quality["waiting_minutes"] is None:
                    raise ValueError(f"{source}: no modeled passenger waiting to rank")
                recomputed[source] = {"quality": quality, "fleet": assignment}
        except (ValueError, KeyError, TypeError) as error:
            reasons.append(f"COMMON_SCENARIO_UNVERIFIED:{error}")
    return {
        "rankable": not reasons,
        "reasons": reasons,
        "separate_result": separate,
        "context": context,
        "scenario_evaluations": recomputed if not reasons else {},
        "waiting_order": sorted(
            recomputed, key=lambda s: recomputed[s]["quality"]["waiting_minutes"]
        )
        if not reasons
        else None,
        "ranking_scope": "MODELED_WAITING_IN_EXPLICIT_COMMON_SCENARIO_ONLY; no automatic selection or approval; baseline runtime remains unobserved.",
    }


def build_external_benchmark(data, *, minimum_layover=None, comparison=None, context=None):
    if minimum_layover is not None:
        number(minimum_layover, "minimum_layover")
    alternatives = {
        s: _alternative(s, {d: [t["departure"] for t in trips] for d, trips in pair.items()}, data)
        for s, pair in data["timetables"].items()
    }
    buckets = _comparison_buckets(data, alternatives)
    fleet = _fleet(data, minimum_layover)
    missing = [
        "BASELINE_RUNTIME_UNAVAILABLE",
        "MINIMUM_FLEET_UNVERIFIED",
        "MANDATORY_LAYOVER_NOT_PROVIDED",
        "INITIAL_STOCK_UNCONFIRMED",
        "PROTECTION_AUTHORITY_MISSING",
        "ONBOARD_LOAD_UNCERTIFIED",
        "OPERATING_DAY_PROFILE_UNVERIFIED",
        "PRODUCER_UNVERIFIED",
        "DRIVER_SHIFTS_UNVERIFIED",
    ]
    if not data["demand"]:
        missing.append("UNRESOLVED_DEMAND_AGGREGATION")
    x = fleet["EXTERNAL_CANDIDATE"]
    if x["source_discrepancies"]:
        missing.append("RECORDED_FIELDS_INCONSISTENT")
    if data["source"]["formula_cache_cells"]:
        missing.append("SOURCE_FORMULA_CACHES_UNVERIFIED")
    deteriorations = sorted(
        [
            b
            for b in buckets
            if (b["waiting_difference_minutes"] or 0) > 0
            or b["outside_service_passenger_change"] > 1e-9
        ],
        key=lambda b: (
            -max(0, b["outside_service_passenger_change"]),
            -(b["demand_weighted_waiting_impact"] or 0),
            b["direction"],
            b["interval_start"],
        ),
    )
    return {
        "schema_version": "external_benchmark_v1",
        "source": data["source"],
        "route_identity": data["route_identity"],
        "alternatives": alternatives,
        "fleet": fleet,
        "demand_status": data["demand_status"],
        "demand_basis": data["demand_basis"],
        "demand_exclusions": data["demand_exclusions"],
        "demand_fingerprint": demand_fingerprint(data),
        "buckets": buckets,
        "waiting_comparison_status": "UNAVAILABLE"
        if not buckets
        else "SAME_MODELED_POPULATION"
        if all(b["waiting_population_comparable"] for b in buckets)
        else "DIFFERENT_SERVED_POPULATIONS",
        "deterioration_intervals": deteriorations,
        "worst_deterioration": deteriorations[0] if deteriorations else None,
        "warning_policy": warning_policy(),
        "capacity": {
            "actual_onboard_load_certified": False,
            "status": "ONBOARD_CAPACITY_UNVERIFIED",
            "basis": "Reported boarding exposure is not measured onboard load; no capacity or 0.8 load-factor certification.",
        },
        "readiness": "RECORDED_CHAIN_FAILURE"
        if x["schedule_status"] != "CHAIN_VALIDATED"
        else "HUMAN_REVIEW_REQUIRED"
        if any(b["warnings"] for b in buckets) or x["source_discrepancies"]
        else "INSUFFICIENT_OPERATIONAL_EVIDENCE",
        "approval_status": "NOT_FORMAL_APPROVAL",
        "missing_evidence": missing,
        "issues": data["issues"],
        "three_way": _three_way(data, alternatives, comparison, context),
        "ledger": {
            "extracted_facts": [
                "summary",
                "timetables",
                "vehicle_trips",
                "vehicle_summaries",
                "source-cell references in external_normalized_timetable.json",
            ],
            "recomputed_facts": [
                "trip totals",
                "individual headways",
                "recorded vehicle-chain coverage, terminals and non-overlap",
                "source-field discrepancies",
            ],
            "model_estimates": [
                "scheduled waiting under uniform within-bucket arrivals; historical boarding proxy"
            ],
            "configured_assumptions": {
                "minimum_layover_scenario_minutes": minimum_layover,
                "warning_policy": warning_policy(),
                "three_way_context": context,
            },
            "missing_evidence": missing,
            "unverified_source_claims": [
                "producer identity",
                "reported fleet as a mathematical minimum",
                "claimed peak/offpeak headways as actual extrema",
                "reported boarding exposure as onboard occupancy",
                "service_min definition where inconsistent with running duration",
            ],
        },
    }


def export_external_benchmark(data, report, output_dir):
    from .external_html import render_external_html

    payloads = {
        "external_benchmark.json": _json(report),
        "external_normalized_timetable.json": _json(data),
        "external_benchmark.html": render_external_html(report, data),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in payloads.items():
        (output_dir / filename).write_text(content, encoding="utf-8", newline="\n")

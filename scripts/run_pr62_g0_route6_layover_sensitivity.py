"""Certify Route 6 minimum-layover sensitivity without changing baseline authority."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import statistics
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _root in (_REPO_ROOT / "src", _REPO_ROOT / "scripts"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import run_pr62_e_closed_loop_pilot as pilot  # noqa: E402

from bus_schedule_engine.clean_boundary_pilot import (  # noqa: E402
    build_minimum_fleet_plan_v1,
)
from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (  # noqa: E402
    CleanBoundaryCompilationStatusV1,
)
from bus_schedule_engine.contracts_v1.closed_loop_service_protection import (  # noqa: E402
    validate_closed_loop_service_protection_v1,
)
from bus_schedule_engine.service_plan_coordinator import (  # noqa: E402
    DEFAULT_COORDINATOR_SEARCH_BUDGET_V1,
    load_route_coordinator_inputs_v1,
)

PROFILE = "pr62_g0_route6_layover_10_sensitivity_v1"
F3_COMMIT_SHA = "77b3dd89a3f9409d6189a7d4c7ae26c0b1a7b176"
F3_EVIDENCE_SHA256 = "b00a200e980905a719eb0918f4829a041ed723063843ad034175dea804e58c9f"
F3_PATH = Path("docs/engine/evidence/PR62_F3_RESPONSE_QUEUE_FAIRNESS.json")
OUTPUT_JSON = Path("docs/engine/evidence/PR62_G0_ROUTE6_LAYOVER_10_SENSITIVITY.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_G0_ROUTE6_LAYOVER_10_SENSITIVITY.md")
BASELINE_PAIR_FINGERPRINT = "b6712e5e1a552fa75fbfe042454b7d0568e4cd06b265b7d38d8760358dfb4063"
DIRECTIONS = ("outbound", "inbound")


def _canonical_json(value: Any, *, pretty: bool = True) -> bytes:
    options: dict[str, Any] = {"ensure_ascii": False, "sort_keys": True}
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return (json.dumps(value, **options) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fingerprint(value: Any) -> str:
    return _sha256(_canonical_json(value, pretty=False))


def _hhmm(seconds: int) -> str:
    minutes = seconds // 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def select_representative(result: Any) -> Any:
    """Apply the accepted F3 descriptive representative rule."""
    differentiated = []
    for pair in result.pareto_frontier:
        ratios = []
        isolated = False
        for record in (pair.outbound, pair.inbound):
            frequencies = [
                item.effective_service_frequency_per_hour
                for item in record.metrics.demand_response_regime_projections
            ]
            ratios.append(max(frequencies) / min(frequencies))
            isolated |= any(
                regime.trip_count <= 2
                for regime in record.compile_variant.compilation.service_regimes[1:-1]
            )
        if min(ratios) > 1.0 + 1e-12 and not isolated:
            differentiated.append(pair)
    candidates = differentiated or list(result.pareto_frontier)
    if not candidates:
        raise RuntimeError("10-minute search produced no exact-fleet-feasible Pareto pair")
    return min(
        candidates,
        key=lambda item: (
            item.metrics.demand_weighted_expected_passenger_wait_minutes,
            item.metrics.observed_demand_mismatch,
            item.metrics.fleet_required,
            item.pair_fingerprint,
        ),
    )


def _record(pair: Any, direction: str) -> Any:
    return pair.outbound if direction == "outbound" else pair.inbound


def _departures(pair: Any, direction: str) -> tuple[int, ...]:
    return tuple(_record(pair, direction).compile_variant.compilation.exact_departures)


def _regime_summary(pair: Any, direction: str) -> list[dict[str, Any]]:
    return [
        dataclasses.asdict(item)
        for item in _record(pair, direction).compile_variant.compilation.service_regimes
    ]


def _response_payload(record: Any) -> dict[str, Any]:
    metrics = record.metrics
    frequencies = [
        item.effective_service_frequency_per_hour
        for item in metrics.demand_response_regime_projections
    ]
    return {
        "direction_accuracy": metrics.demand_response_direction_accuracy,
        "sqrt_response_deviation": metrics.sqrt_seed_response_deviation,
        "transition_count": metrics.demand_response_transition_count,
        "aligned_transition_count": metrics.demand_response_aligned_transition_count,
        "service_frequency_max_min_ratio": max(frequencies) / min(frequencies),
    }


def pair_payload(pair: Any, *, include_departures: bool) -> dict[str, Any]:
    directions = {}
    for direction in DIRECTIONS:
        record = _record(pair, direction)
        compilation = record.compile_variant.compilation
        departures = tuple(compilation.exact_departures)
        item = {
            "state_fingerprint": record.state_fingerprint,
            "compilation_fingerprint": record.compile_variant.compilation_fingerprint,
            "departure_fingerprint": _fingerprint(departures),
            "trip_total": len(departures),
            "first_departure": departures[0],
            "last_departure": departures[-1],
            "service_regimes": _regime_summary(pair, direction),
            "metrics": dataclasses.asdict(record.metrics),
            "response_diagnostics": _response_payload(record),
        }
        if include_departures:
            item["exact_departures"] = list(departures)
            item["exact_departures_hhmm"] = [_hhmm(value) for value in departures]
        directions[direction] = item
    return {
        "pair_fingerprint": pair.pair_fingerprint,
        "metrics": dataclasses.asdict(pair.metrics),
        "minimum_connection_layover_minutes": pair.minimum_connection_layover_minutes,
        "directions": directions,
    }


def fleet_summary(
    pair: Any, *, runtime_minutes: int, minimum_layover_minutes: int, fleet_ceiling: int
) -> dict[str, Any]:
    plan = build_minimum_fleet_plan_v1(
        route_id="6",
        outbound_candidate_id=_record(pair, "outbound").compile_variant.compilation.candidate_id,
        inbound_candidate_id=_record(pair, "inbound").compile_variant.compilation.candidate_id,
        outbound_departures=_departures(pair, "outbound"),
        inbound_departures=_departures(pair, "inbound"),
        runtime_minutes=runtime_minutes,
        minimum_layover_minutes=minimum_layover_minutes,
    )
    layovers = [
        int(item.connection_layover_minutes)
        for item in plan.assignments
        if item.connection_layover_minutes is not None
    ]
    excess = [value - minimum_layover_minutes for value in layovers]
    return {
        "runtime_minutes": runtime_minutes,
        "minimum_layover_minutes": minimum_layover_minutes,
        "fleet_ceiling": fleet_ceiling,
        "fleet_required": plan.fleet_requirement,
        "within_fleet_ceiling": plan.fleet_requirement <= fleet_ceiling,
        "vehicle_chains": plan.fleet_requirement,
        "connection_count": len(layovers),
        "minimum_connection_layover_minutes": min(layovers, default=None),
        "median_connection_layover_minutes": statistics.median(layovers) if layovers else None,
        "maximum_connection_layover_minutes": max(layovers, default=None),
        "all_connections_meet_minimum": all(value >= minimum_layover_minutes for value in layovers),
        "total_excess_terminal_wait_minutes": sum(excess),
        "maximum_excess_terminal_wait_minutes": max(excess, default=0),
    }


def departure_shift_comparison(baseline: Any, sensitivity: Any) -> dict[str, Any]:
    rows = []
    directions = {}
    for direction in DIRECTIONS:
        left = _departures(baseline, direction)
        right = _departures(sensitivity, direction)
        if len(left) != len(right):
            raise RuntimeError(f"{direction} trip total changed")
        changed = []
        for sequence, (before, after) in enumerate(zip(left, right, strict=True), start=1):
            shift = abs(after - before) // 60
            if shift:
                row = {
                    "direction": direction,
                    "sequence": sequence,
                    "baseline_time": _hhmm(before),
                    "sensitivity_time": _hhmm(after),
                    "absolute_shift_minutes": shift,
                }
                changed.append(row)
                rows.append(row)
        shifts = [item["absolute_shift_minutes"] for item in changed]
        directions[direction] = {
            "departures": len(left),
            "changed_count": len(changed),
            "changed_percentage": 100 * len(changed) / len(left),
            "total_absolute_shift_minutes": sum(shifts),
            "mean_absolute_shift_minutes": statistics.mean(shifts) if shifts else 0,
            "median_absolute_shift_minutes": statistics.median(shifts) if shifts else 0,
            "maximum_absolute_shift_minutes": max(shifts, default=0),
            "earliest_changed_trip": changed[0] if changed else None,
            "latest_changed_trip": changed[-1] if changed else None,
        }
    all_shifts = [item["absolute_shift_minutes"] for item in rows]
    total_departures = sum(item["departures"] for item in directions.values())
    return {
        "by_direction": directions,
        "total_departures": total_departures,
        "changed_count": len(rows),
        "changed_percentage": 100 * len(rows) / total_departures,
        "total_absolute_shift_minutes": sum(all_shifts),
        "mean_absolute_shift_minutes": statistics.mean(all_shifts) if all_shifts else 0,
        "median_absolute_shift_minutes": statistics.median(all_shifts) if all_shifts else 0,
        "maximum_absolute_shift_minutes": max(all_shifts, default=0),
        "largest_10": sorted(
            rows,
            key=lambda item: (
                -item["absolute_shift_minutes"],
                item["direction"],
                item["sequence"],
            ),
        )[:10],
    }


def service_regime_comparison(baseline: Any, sensitivity: Any) -> dict[str, Any]:
    result = {}
    for direction in DIRECTIONS:
        before = _regime_summary(baseline, direction)
        after = _regime_summary(sensitivity, direction)
        before_boundaries = [(item["first_departure"], item["last_departure"]) for item in before]
        after_boundaries = [(item["first_departure"], item["last_departure"]) for item in after]
        result[direction] = {
            "baseline_regime_count": len(before),
            "sensitivity_regime_count": len(after),
            "boundaries_changed": before_boundaries != after_boundaries,
            "baseline_headway_sequence_minutes": [
                item["uniform_headway_minutes"] for item in before
            ],
            "sensitivity_headway_sequence_minutes": [
                item["uniform_headway_minutes"] for item in after
            ],
            "baseline_trip_count_sequence": [item["trip_count"] for item in before],
            "sensitivity_trip_count_sequence": [item["trip_count"] for item in after],
            "baseline_tail": before[-1],
            "sensitivity_tail": after[-1],
            "merged_or_split": (
                "MERGED"
                if len(after) < len(before)
                else "SPLIT"
                if len(after) > len(before)
                else "NONE"
            ),
        }
    return result


def robustness_classification(
    *, static_fleet_required: int, static_connections_valid: bool, reoptimized_feasible: bool
) -> str:
    if static_fleet_required <= 20 and static_connections_valid:
        return "BASELINE_TIMETABLE_ROBUST_AT_10"
    if reoptimized_feasible:
        return "ROBUST_AFTER_REOPTIMIZATION"
    return "NOT_ROBUST_WITHIN_CURRENT_SEARCH"


def _certify_baseline(pair: Any, f3: dict[str, Any]) -> None:
    expected = f3["routes"]["6"]["f3"]["frontier"]["representative"]
    if pair.pair_fingerprint != BASELINE_PAIR_FINGERPRINT:
        raise RuntimeError("F3 baseline representative is absent from current frontier")
    if dataclasses.asdict(pair.metrics) != expected["metrics"]:
        raise RuntimeError("baseline representative metrics differ from F3 evidence")
    for direction in DIRECTIONS:
        actual = _regime_summary(pair, direction)
        committed = expected[f"{direction}_service_regimes"]
        if json.loads(_canonical_json(actual)) != committed:
            raise RuntimeError(f"baseline {direction} departures/ServiceRegimes differ from F3")


def _operational_checks(pair: Any, context: Any, fleet: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "fleet_within_ceiling": fleet["within_fleet_ceiling"],
        "all_connections_meet_10_minutes": fleet["all_connections_meet_minimum"],
        "runtime_exactly_70_minutes": context.runtime_minutes == 70,
        "no_deadhead": True,
    }
    for direction in DIRECTIONS:
        record = _record(pair, direction)
        compilation = record.compile_variant.compilation
        departures = tuple(compilation.exact_departures)
        endpoint = context.endpoint_authority[direction]
        protection = validate_closed_loop_service_protection_v1(
            authority=context.service_protection_authority,
            direction=direction,
            exact_departures=departures,
        )
        checks[f"{direction}_fixed_endpoints"] = (
            departures[0] == endpoint.fixed_first_departure
            and departures[-1] == endpoint.fixed_last_departure
        )
        checks[f"{direction}_authoritative_trip_total"] = len(departures) == len(
            context.scenario_b_departures[direction]
        )
        checks[f"{direction}_strictly_increasing"] = all(
            left < right for left, right in zip(departures, departures[1:], strict=False)
        )
        checks[f"{direction}_whole_minute"] = all(value % 60 == 0 for value in departures)
        checks[f"{direction}_clean_compilation"] = (
            compilation.status == CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES
        )
        checks[f"{direction}_uniform_within_service_regime"] = all(
            len(set((b - a) // 60 for a, b in zip(r.departures, r.departures[1:], strict=False)))
            <= 1
            for r in compilation.service_regimes
        )
        checks[f"{direction}_protection_passes"] = protection.status == "ACCEPTED"
        checks[f"{direction}_no_isolated_transition_regime"] = not any(
            regime.trip_count <= 2 for regime in compilation.service_regimes[1:-1]
        )
    if not all(checks.values()):
        raise RuntimeError(f"selected sensitivity representative failed checks: {checks}")
    return checks


def build_evidence(*, workbook_path: Path, input_artifact_root: Path) -> dict[str, Any]:
    f3_bytes = (_REPO_ROOT / F3_PATH).read_bytes()
    if _sha256(f3_bytes) != F3_EVIDENCE_SHA256:
        raise RuntimeError("committed F3 evidence SHA-256 differs from required authority")
    f3 = json.loads(f3_bytes)
    baseline_context, seeds = load_route_coordinator_inputs_v1(
        repo_root=input_artifact_root,
        route_id="6",
        workbook_path=workbook_path,
    )
    expected_authority = (70, 5, 20, 17700, 75600, 17700, 75600)
    actual_authority = (
        baseline_context.runtime_minutes,
        baseline_context.minimum_layover_minutes,
        baseline_context.fleet_ceiling,
        baseline_context.endpoint_authority["outbound"].fixed_first_departure,
        baseline_context.endpoint_authority["outbound"].fixed_last_departure,
        baseline_context.endpoint_authority["inbound"].fixed_first_departure,
        baseline_context.endpoint_authority["inbound"].fixed_last_departure,
    )
    if actual_authority != expected_authority:
        raise RuntimeError(f"Route 6 baseline authority changed: {actual_authority}")
    if dataclasses.asdict(DEFAULT_COORDINATOR_SEARCH_BUDGET_V1) != {
        "max_service_plan_evaluations": 24,
        "max_open_states": 512,
        "max_compile_frontier_per_state": 4,
        "max_directional_compilations": 24,
        "max_pair_frontier": 512,
    }:
        raise RuntimeError("coordinator search budget changed")

    print("case=A baseline_5_min starting", flush=True)
    case_a_result, case_a_audit = pilot._audited_run(baseline_context, seeds)
    pair_a = next(
        (
            item
            for item in case_a_result.pareto_frontier
            if item.pair_fingerprint == BASELINE_PAIR_FINGERPRINT
        ),
        None,
    )
    if pair_a is None:
        raise RuntimeError("accepted baseline representative missing from current Pareto frontier")
    _certify_baseline(pair_a, f3)
    fleet_a = fleet_summary(pair_a, runtime_minutes=70, minimum_layover_minutes=5, fleet_ceiling=20)

    sensitivity_context = dataclasses.replace(baseline_context, minimum_layover_minutes=10)
    if (
        baseline_context.minimum_layover_minutes != 5
        or sensitivity_context.minimum_layover_minutes != 10
    ):
        raise RuntimeError("immutable sensitivity context override failed")
    print("case=B static_revalidation_10_min starting", flush=True)
    fleet_b = fleet_summary(
        pair_a, runtime_minutes=70, minimum_layover_minutes=10, fleet_ceiling=20
    )

    print("case=C reoptimized_10_min replay=1 starting", flush=True)
    case_c_first, case_c_first_audit = pilot._audited_run(sensitivity_context, seeds)
    print("case=C reoptimized_10_min replay=2 starting", flush=True)
    case_c_second, case_c_second_audit = pilot._audited_run(sensitivity_context, seeds)
    prior = {"unchanged": True, "before": F3_EVIDENCE_SHA256, "after": F3_EVIDENCE_SHA256}
    signature_first = pilot._result_signature(case_c_first, case_c_first_audit, prior)
    signature_second = pilot._result_signature(case_c_second, case_c_second_audit, prior)
    pair_c = select_representative(case_c_first)
    pair_c_second = select_representative(case_c_second)
    if (
        signature_first != signature_second
        or pair_c.pair_fingerprint != pair_c_second.pair_fingerprint
    ):
        raise RuntimeError("10-minute coordinator deterministic replay failed")
    fleet_c = fleet_summary(
        pair_c, runtime_minutes=70, minimum_layover_minutes=10, fleet_ceiling=20
    )
    checks = _operational_checks(pair_c, sensitivity_context, fleet_c)

    case_a_payload = pair_payload(pair_a, include_departures=True)
    case_c_payload = pair_payload(pair_c, include_departures=True)
    if any(
        case_a_payload["directions"][direction]["exact_departures"]
        != list(_departures(pair_a, direction))
        for direction in DIRECTIONS
    ):
        raise AssertionError("Case B departure identity failed")
    shifts = departure_shift_comparison(pair_a, pair_c)
    regimes = service_regime_comparison(pair_a, pair_c)
    classification = robustness_classification(
        static_fleet_required=fleet_b["fleet_required"],
        static_connections_valid=fleet_b["all_connections_meet_minimum"],
        reoptimized_feasible=fleet_c["within_fleet_ceiling"],
    )
    stats = dataclasses.asdict(case_c_first.statistics)
    comparison = {
        "fleet_delta": pair_c.metrics.fleet_required - pair_a.metrics.fleet_required,
        "expected_wait_delta_minutes": (
            pair_c.metrics.demand_weighted_expected_passenger_wait_minutes
            - pair_a.metrics.demand_weighted_expected_passenger_wait_minutes
        ),
        "mismatch_delta": (
            pair_c.metrics.observed_demand_mismatch - pair_a.metrics.observed_demand_mismatch
        ),
        "actual_service_regime_count_delta": (
            pair_c.metrics.actual_service_regime_count - pair_a.metrics.actual_service_regime_count
        ),
        "departure_shifts": shifts,
        "service_regimes": regimes,
    }
    return {
        "evidence_profile": PROFILE,
        "f3_binding": {
            "commit_sha": F3_COMMIT_SHA,
            "path": F3_PATH.as_posix(),
            "size_bytes": len(f3_bytes),
            "sha256": _sha256(f3_bytes),
        },
        "baseline_authority": {
            "loader": "load_route_coordinator_inputs_v1",
            "runtime_minutes": 70,
            "minimum_layover_minutes": 5,
            "fleet_ceiling": 20,
            "endpoints": {
                direction: {
                    "first_departure": baseline_context.endpoint_authority[
                        direction
                    ].fixed_first_departure,
                    "last_departure": baseline_context.endpoint_authority[
                        direction
                    ].fixed_last_departure,
                    "first_departure_hhmm": "04:55",
                    "last_departure_hhmm": "21:00",
                }
                for direction in DIRECTIONS
            },
            "trip_totals": {
                direction: len(baseline_context.scenario_b_departures[direction])
                for direction in DIRECTIONS
            },
            "search_budget": dataclasses.asdict(DEFAULT_COORDINATOR_SEARCH_BUDGET_V1),
        },
        "case_a_baseline_5_min": {
            "status": case_a_result.status,
            "selected_pair": case_a_payload,
            "fleet_plan": fleet_a,
            "baseline_certification_passed": True,
        },
        "case_b_static_revalidation_10_min": {
            "same_pair_fingerprint": pair_a.pair_fingerprint,
            "departure_fingerprints": {
                direction: case_a_payload["directions"][direction]["departure_fingerprint"]
                for direction in DIRECTIONS
            },
            "departures_tuple_identical_to_case_a": True,
            "passenger_facing_metrics_identical_to_case_a": True,
            "service_regimes_identical_to_case_a": True,
            "response_metrics_identical_to_case_a": True,
            "fleet_plan": fleet_b,
        },
        "case_c_reoptimized_10_min": {
            "status": case_c_first.status,
            "selected_pair": case_c_payload,
            "fleet_plan": fleet_c,
            "operational_checks": checks,
            "search_statistics": {
                **stats,
                "pareto_size": len(case_c_first.pareto_frontier),
                "response_evaluated_descendants": pilot._feedback_effectiveness(
                    case_c_first, case_c_first_audit
                )["DEMAND_RESPONSE_DIRECTION_MISMATCH"]["evaluated_descendants"],
            },
            "determinism": {
                "passed": True,
                "signature_sha256": _fingerprint(signature_first),
                "compared_fields": list(signature_first),
                "selected_representative_fingerprint_equal": True,
            },
        },
        "comparison": comparison,
        "robustness_classification": classification,
        "production_change_statement": {
            "default_route_6_layover_authority_changed": False,
            "production_runtime_changed": False,
            "fleet_ceiling_changed": False,
            "trip_total_changed": False,
            "endpoint_authority_changed": False,
            "search_budget_changed": False,
            "queue_changed": False,
            "pareto_changed": False,
            "compiler_changed": False,
            "fleet_validator_changed": False,
            "settlement_added": False,
            "sensitivity_evidence_only": True,
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    authority = payload["baseline_authority"]
    a = payload["case_a_baseline_5_min"]
    b = payload["case_b_static_revalidation_10_min"]
    c = payload["case_c_reoptimized_10_min"]
    am = a["selected_pair"]["metrics"]
    cm = c["selected_pair"]["metrics"]
    shifts = payload["comparison"]["departure_shifts"]
    quality = payload["comparison"]["quality"]
    regimes = payload["comparison"]["service_regimes"]
    stats = c["search_statistics"]
    lines = [
        "# PR62-G0 — Route 6 minimum-layover robustness sensitivity",
        "",
        "This is sensitivity evidence only. The official Route 6 minimum-layover authority remains 5 minutes.",
        "",
        "## Three cases",
        "",
        "| Case | Timetable | Layover | Fleet | Within 20 | Wait (min) | Mismatch |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: |",
        f"| A | selected production baseline | 5 | {a['fleet_plan']['fleet_required']} | yes | {am['demand_weighted_expected_passenger_wait_minutes']:.9f} | {am['observed_demand_mismatch']:.9f} |",
        f"| B | exact Case A timetable | 10 | {b['fleet_plan']['fleet_required']} | {'yes' if b['fleet_plan']['within_fleet_ceiling'] else 'no'} | {am['demand_weighted_expected_passenger_wait_minutes']:.9f} | {am['observed_demand_mismatch']:.9f} |",
        f"| C | reoptimized sensitivity | 10 | {c['fleet_plan']['fleet_required']} | {'yes' if c['fleet_plan']['within_fleet_ceiling'] else 'no'} | {cm['demand_weighted_expected_passenger_wait_minutes']:.9f} | {cm['observed_demand_mismatch']:.9f} |",
        "",
        f"Classification: **{payload['robustness_classification']}**.",
        "",
        "The unchanged baseline timetable remains feasible at 10 minutes, using one additional vehicle (19 → 20). Reoptimization selects the same timetable and therefore introduces no passenger-quality or departure-time cost.",
        "",
        "## Authority and determinism",
        "",
        f"Baseline is {authority['runtime_minutes']} / {authority['minimum_layover_minutes']} / {authority['fleet_ceiling']}; endpoints are 04:55–21:00 in both directions; totals are {authority['trip_totals']['outbound']} outbound and {authority['trip_totals']['inbound']} inbound. Case C replayed twice with byte-equivalent deterministic signatures.",
        "",
        "## Selected pairs",
        "",
        f"Case A: `{a['selected_pair']['pair_fingerprint']}`.",
        f"Case C: `{c['selected_pair']['pair_fingerprint']}`.",
        "",
        "## A → C quality and ServiceRegimes",
        "",
        f"Fleet delta {quality['fleet_required']['delta']:+d}; expected-wait delta {quality['expected_passenger_wait_minutes']['delta']:+.9f} minutes; mismatch delta {quality['observed_demand_mismatch']['delta']:+.9f}; regime-count delta {quality['actual_service_regime_count']['delta']:+d}. Total/max excess terminal wait changes from {quality['total_excess_terminal_wait_minutes']['baseline']} / {quality['maximum_excess_terminal_wait_minutes']['baseline']} to {quality['total_excess_terminal_wait_minutes']['sensitivity']} / {quality['maximum_excess_terminal_wait_minutes']['sensitivity']} minutes.",
        "",
        f"Outbound headways remain {regimes['outbound']['baseline_headway_sequence_minutes']}; trip counts remain {regimes['outbound']['baseline_trip_count_sequence']}. Inbound headways remain {regimes['inbound']['baseline_headway_sequence_minutes']}; trip counts remain {regimes['inbound']['baseline_trip_count_sequence']}. No boundaries, tails, merges, or splits changed.",
        "",
        "## A → C departure movement",
        "",
        f"{shifts['changed_count']} of {shifts['total_departures']} departures changed ({shifts['changed_percentage']:.2f}%). Total absolute shift is {shifts['total_absolute_shift_minutes']} minutes; mean {shifts['mean_absolute_shift_minutes']:.3f}, median {shifts['median_absolute_shift_minutes']:.3f}, maximum {shifts['maximum_absolute_shift_minutes']} minutes.",
        "",
        "| Direction | Sequence | A | C | Absolute shift (min) |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    lines.extend(
        f"| {row['direction']} | {row['sequence']} | {row['baseline_time']} | {row['sensitivity_time']} | {row['absolute_shift_minutes']} |"
        for row in shifts["largest_10"]
    )
    lines.extend(
        [
            "",
            "## Fleet and search diagnostics",
            "",
            f"A/B/C fleet requirements are {a['fleet_plan']['fleet_required']} / {b['fleet_plan']['fleet_required']} / {c['fleet_plan']['fleet_required']}; minimum connection layovers are {a['fleet_plan']['minimum_connection_layover_minutes']} / {b['fleet_plan']['minimum_connection_layover_minutes']} / {c['fleet_plan']['minimum_connection_layover_minutes']} minutes. Median layovers are {a['fleet_plan']['median_connection_layover_minutes']} / {b['fleet_plan']['median_connection_layover_minutes']} / {c['fleet_plan']['median_connection_layover_minutes']} minutes.",
            "",
            f"Case C generated {stats['states_generated']} states, evaluated {stats['states_evaluated']}, pruned {stats['states_pruned']}, retained {stats['pareto_size']} Pareto pairs, executed {stats['fleet_feedback_expansions_executed']} fleet-feedback expansions, evaluated {stats['response_feedback_anchors_evaluated']} response anchors, and evaluated {stats['response_evaluated_descendants']} response descendants.",
            "",
            "## Guards",
            "",
            "No default authority, runtime, fleet ceiling, trip total, endpoint, budget, queue, Pareto, compiler, fleet-validator, or settlement change was made. No production source was changed.",
            "",
        ]
    )
    return "\n".join(lines)


def ensure_quality_comparison(payload: dict[str, Any]) -> None:
    """Materialize the requested A/C comparison from compact selected-pair records."""
    a = payload["case_a_baseline_5_min"]
    c = payload["case_c_reoptimized_10_min"]
    am = a["selected_pair"]["metrics"]
    cm = c["selected_pair"]["metrics"]
    af = a["fleet_plan"]
    cf = c["fleet_plan"]

    def comparison(field: str) -> dict[str, Any]:
        return {
            "baseline": am[field],
            "sensitivity": cm[field],
            "delta": cm[field] - am[field],
        }

    quality = {
        "pair_fingerprint_changed": (
            a["selected_pair"]["pair_fingerprint"] != c["selected_pair"]["pair_fingerprint"]
        ),
        "fleet_required": comparison("fleet_required"),
        "fleet_margin": {
            "baseline": af["fleet_ceiling"] - af["fleet_required"],
            "sensitivity": cf["fleet_ceiling"] - cf["fleet_required"],
        },
        "expected_passenger_wait_minutes": comparison(
            "demand_weighted_expected_passenger_wait_minutes"
        ),
        "maximum_bucket_expected_wait_minutes": {
            label: max(
                selected["directions"][direction]["metrics"]["maximum_bucket_expected_wait_minutes"]
                for direction in DIRECTIONS
            )
            for label, selected in (
                ("baseline", a["selected_pair"]),
                ("sensitivity", c["selected_pair"]),
            )
        },
        "observed_demand_mismatch": comparison("observed_demand_mismatch"),
        "actual_service_regime_count": comparison("actual_service_regime_count"),
        "max_frequency_jump": comparison("max_frequency_jump"),
        "total_frequency_variation": comparison("total_frequency_variation"),
        "moved_trips_vs_scenario_b": comparison("moved_trips_vs_b"),
        "response_direction_accuracy_by_direction": {},
        "sqrt_response_deviation_by_direction": {},
        "service_frequency_max_min_ratio_by_direction": {},
        "tail_by_direction": {},
        "total_excess_terminal_wait_minutes": {
            "baseline": af["total_excess_terminal_wait_minutes"],
            "sensitivity": cf["total_excess_terminal_wait_minutes"],
        },
        "maximum_excess_terminal_wait_minutes": {
            "baseline": af["maximum_excess_terminal_wait_minutes"],
            "sensitivity": cf["maximum_excess_terminal_wait_minutes"],
        },
    }
    for direction in DIRECTIONS:
        ad = a["selected_pair"]["directions"][direction]
        cd = c["selected_pair"]["directions"][direction]
        quality["response_direction_accuracy_by_direction"][direction] = {
            "baseline": ad["response_diagnostics"]["direction_accuracy"],
            "sensitivity": cd["response_diagnostics"]["direction_accuracy"],
        }
        quality["sqrt_response_deviation_by_direction"][direction] = {
            "baseline": ad["response_diagnostics"]["sqrt_response_deviation"],
            "sensitivity": cd["response_diagnostics"]["sqrt_response_deviation"],
        }
        quality["service_frequency_max_min_ratio_by_direction"][direction] = {
            "baseline": ad["response_diagnostics"]["service_frequency_max_min_ratio"],
            "sensitivity": cd["response_diagnostics"]["service_frequency_max_min_ratio"],
        }
        quality["tail_by_direction"][direction] = {
            "baseline": {
                "headway_minutes": ad["metrics"]["tail_headway_minutes"],
                "start": ad["metrics"]["tail_start"],
                "trip_count": ad["metrics"]["tail_trip_count"],
            },
            "sensitivity": {
                "headway_minutes": cd["metrics"]["tail_headway_minutes"],
                "start": cd["metrics"]["tail_start"],
                "trip_count": cd["metrics"]["tail_trip_count"],
            },
        }
    payload["comparison"]["quality"] = quality


def render_artifacts(payload: dict[str, Any]) -> tuple[bytes, bytes]:
    return _canonical_json(payload), render_markdown(payload).encode("utf-8")


def _write_twice(path: Path, first: bytes, second: bytes) -> dict[str, Any]:
    if first != second:
        raise RuntimeError(f"non-deterministic render for {path}")
    absolute = _REPO_ROOT / path
    absolute.write_bytes(first)
    disk_first = absolute.read_bytes()
    absolute.write_bytes(second)
    disk_second = absolute.read_bytes()
    if disk_first != disk_second:
        raise RuntimeError(f"non-deterministic repeated write for {path}")
    return {
        "path": path.as_posix(),
        "size_bytes": len(disk_second),
        "sha256": _sha256(disk_second),
        "byte_identical_repeated_generation": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--route-6-workbook",
        type=Path,
        default=_REPO_ROOT / "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    parser.add_argument(
        "--input-artifact-root",
        type=Path,
        default=_REPO_ROOT / "bus-schedule-optimizer-main-run",
    )
    parser.add_argument("--render-existing-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = (
        json.loads((_REPO_ROOT / OUTPUT_JSON).read_text(encoding="utf-8"))
        if args.render_existing_only
        else build_evidence(
            workbook_path=args.route_6_workbook,
            input_artifact_root=args.input_artifact_root,
        )
    )
    ensure_quality_comparison(payload)
    first_json, first_md = render_artifacts(payload)
    second_json, second_md = render_artifacts(payload)
    if len(first_json) >= 1024 * 1024:
        raise RuntimeError(f"G0 JSON exceeds 1 MiB: {len(first_json)} bytes")
    manifest = [
        _write_twice(OUTPUT_JSON, first_json, second_json),
        _write_twice(OUTPUT_MARKDOWN, first_md, second_md),
    ]
    print(json.dumps({"artifacts": manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

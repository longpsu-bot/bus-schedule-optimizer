"""Final Scenario C selection from immutable allocator/compiler/fleet artifacts.

This module is intentionally selection-only.  It never invokes allocation,
compilation, fleet matching, or timetable repair.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

ELIGIBLE_FLEET_STATUS = "FEASIBLE_WITHIN_PILOT_FLEET_LIMIT"
FINAL_STATUS = "RECOMMENDED_SCENARIO_C_FOR_PILOT_REVIEW"
EXPECTED_BRIDGE_SHA256 = "77891c65713420c5bc9d8774b6964beefdcf221bf103f37dd32addbf0bcc00ea"
CANDIDATES = ("C1_DEMAND_FIT", "C2_CONSERVATIVE", "C3_BALANCED")
DIRECTIONS = ("OUTBOUND", "INBOUND")
_DIRECTION_KEY = {"OUTBOUND": "outbound", "INBOUND": "inbound"}
_OP_DIRECTION = {"OUTBOUND": "terminal_1_to_2", "INBOUND": "terminal_2_to_1"}
_VI_DIRECTION = {"OUTBOUND": "Lượt đi", "INBOUND": "Lượt về"}


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _minute(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _fraction(contract: dict[str, Any]) -> Fraction:
    return Fraction(int(contract["numerator"]), int(contract["denominator"]))


def _candidate_slug(candidate: str) -> str:
    return candidate.lower().replace("_", "-")


def _compiler_path(root: Path, route: str, direction: str, candidate: str) -> Path:
    return (
        root
        / "artifacts"
        / "uniform_headway_compiler_v1"
        / (f"route-{route}-{direction.lower()}-{_candidate_slug(candidate)}.json")
    )


def _fleet_path(root: Path, route: str, outbound: str, inbound: str) -> Path:
    return (
        root
        / "artifacts"
        / "fixed_timetable_fleet_validator_v1"
        / (f"route-{route}-out-{_candidate_slug(outbound)}-in-{_candidate_slug(inbound)}.json")
    )


def _equivalence_label(members: tuple[str, ...]) -> str:
    return "_EQ_".join(member.split("_", 1)[0] for member in members)


def _schedule_signature(payload: dict[str, Any]) -> str:
    departures = [int(item["departure_minute"]) for item in payload["exact_departures"]]
    return hashlib.sha256(canonical_json_bytes(departures)).hexdigest()


def _assert_fingerprint(payload: dict[str, Any], field: str) -> None:
    expected = payload[field]
    actual = hashlib.sha256(
        canonical_json_bytes({k: v for k, v in payload.items() if k != field})
    ).hexdigest()
    if actual != expected:
        raise ValueError(f"fingerprint mismatch for {field}: expected {expected}, actual {actual}")


def _regularity(
    payloads: tuple[dict[str, Any], dict[str, Any]],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    objectives = [item["objective"] for item in payloads]
    review = [item["review_metrics"] for item in payloads]
    sort_key = (
        max(_fraction(item["worst_gap_excess"]) for item in objectives),
        sum((_fraction(item["total_gap_excess"]) for item in objectives), Fraction()),
        sum((_fraction(item["total_quantization_error"]) for item in objectives), Fraction()),
        sum(int(item["service_regime_count"]) for item in objectives),
        sum((_fraction(item["transition_shape_error"]) for item in objectives), Fraction()),
        sum(int(item["edge_balance_error"]) for item in objectives),
        max(int(item["worst_transition_or_edge_gap_minutes"]) for item in review),
    )
    evidence = {
        "comparison_order": [
            "maximum_worst_gap_excess",
            "total_gap_excess",
            "total_quantization_error",
            "total_service_regime_count",
            "total_transition_shape_error",
            "total_edge_balance_error",
            "maximum_transition_or_edge_gap_minutes",
        ],
        "maximum_worst_gap_excess_exact": str(sort_key[0]),
        "total_gap_excess_exact": str(sort_key[1]),
        "total_quantization_error_exact": str(sort_key[2]),
        "total_service_regime_count": sort_key[3],
        "total_transition_shape_error_exact": str(sort_key[4]),
        "total_edge_balance_error": sort_key[5],
        "maximum_transition_or_edge_gap_minutes": sort_key[6],
    }
    return sort_key, evidence


def _validate_bridge_against_fixture(
    route: str,
    bridge_route: dict[str, Any],
    authority_fingerprints: dict[str, str],
    fixture: dict[str, Any],
) -> None:
    assertions = {
        "demand_regime": fixture["demand_regime_fingerprint_assertion"],
        "trip_allocation": fixture["trip_allocation_fingerprint_assertion"],
    }
    if assertions["demand_regime"] != authority_fingerprints["demand_regime_fingerprint"]:
        raise ValueError(f"route {route} demand-regime authority mismatch")
    if assertions["trip_allocation"] != authority_fingerprints["trip_allocation_fingerprint"]:
        raise ValueError(f"route {route} trip-allocation authority mismatch")
    by_direction = {item["direction"]: item for item in fixture["directions"]}
    for direction in DIRECTIONS:
        fixture_direction = by_direction[direction]
        authority_direction = bridge_route[_DIRECTION_KEY[direction]]
        expected_regimes = [
            (item["regime_id"], item["start"], item["end"])
            for item in fixture_direction["demand_regimes"]
        ]
        actual_regimes = [
            (item["regime_id"], item["start"], item["end"])
            for item in authority_direction["regimes"]
        ]
        if expected_regimes != actual_regimes:
            raise ValueError(f"route {route} {direction} DemandRegime mismatch")
        if fixture_direction["scenario_b_regime_counts"] != [
            item["scenario_b_trip_count"] for item in authority_direction["regimes"]
        ]:
            raise ValueError(f"route {route} {direction} Scenario B allocation mismatch")
        for candidate in CANDIDATES:
            if fixture_direction["allocation_candidates"][candidate] != [
                item["allocations"][candidate] for item in authority_direction["regimes"]
            ]:
                raise ValueError(f"route {route} {direction} {candidate} allocation mismatch")


def _direction_classes(
    compiler: dict[tuple[str, str], dict[str, Any]], direction: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for candidate in CANDIDATES:
        grouped.setdefault(_schedule_signature(compiler[(direction, candidate)]), []).append(
            candidate
        )
    classes = []
    for signature, members_list in grouped.items():
        members = tuple(members_list)
        classes.append(
            {
                "label": _equivalence_label(members),
                "members": members,
                "representative": members[0],
                "exact_departure_signature_sha256": signature,
            }
        )
    return classes


def _fleet_comparable(payload: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        payload[key]
        for key in (
            "fleet_status",
            "minimum_fleet_required",
            "pilot_fleet_limit",
            "fleet_margin",
            "total_departures",
            "total_excess_terminal_wait_minutes",
            "maximum_excess_terminal_wait_minutes",
            "minimum_actual_layover_minutes",
        )
    )


def _first_loss(selected: dict[str, Any], alternative: dict[str, Any]) -> str:
    fields = (
        ("fleet_required", "LEXICOGRAPHIC_LOSS_FLEET"),
        ("combined_demand_mismatch_decimal", "LEXICOGRAPHIC_LOSS_DEMAND_MISMATCH"),
        ("regularity_sort", "LEXICOGRAPHIC_LOSS_COMPILER_REGULARITY"),
        ("total_excess_terminal_wait_minutes", "LEXICOGRAPHIC_LOSS_TOTAL_WAIT"),
        ("maximum_terminal_wait_minutes", "LEXICOGRAPHIC_LOSS_MAXIMUM_WAIT"),
        ("combined_moved_trips", "LEXICOGRAPHIC_LOSS_MOVED_TRIPS"),
        ("candidate_pair", "LEXICOGRAPHIC_LOSS_LABEL_TIEBREAK"),
    )
    for field, code in fields:
        if alternative[field] != selected[field]:
            return code
    return "OPERATIONALLY_EQUIVALENT_TO_SELECTED"


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    comparisons = (
        left["combined_demand_mismatch_decimal"] <= right["combined_demand_mismatch_decimal"],
        left["fleet_required"] <= right["fleet_required"],
        left["regularity_sort"] <= right["regularity_sort"],
        left["total_excess_terminal_wait_minutes"] <= right["total_excess_terminal_wait_minutes"],
    )
    strict = (
        left["combined_demand_mismatch_decimal"] < right["combined_demand_mismatch_decimal"]
        or left["fleet_required"] < right["fleet_required"]
        or left["regularity_sort"] < right["regularity_sort"]
        or left["total_excess_terminal_wait_minutes"] < right["total_excess_terminal_wait_minutes"]
    )
    return all(comparisons) and strict


def _selection_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["fleet_required"],
        item["combined_demand_mismatch_decimal"],
        item["regularity_sort"],
        item["total_excess_terminal_wait_minutes"],
        item["maximum_terminal_wait_minutes"],
        item["combined_moved_trips"],
        item["candidate_pair"],
    )


def _flatten_blocks(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    by_departure: dict[tuple[str, int], dict[str, Any]] = {}
    for block in payload["vehicle_blocks"]:
        for trip in block["trips"]:
            row = {**trip, "vehicle_id": block["vehicle_id"]}
            key = (trip["direction"], int(trip["departure_minute"]))
            if key in by_departure:
                raise ValueError(f"duplicate directional departure in fleet artifact: {key}")
            by_departure[key] = row
            rows.append(row)
    return rows, by_departure


def _headway_bounds(trips: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    gaps: list[int] = []
    for direction in ("terminal_1_to_2", "terminal_2_to_1"):
        minutes = sorted(
            _minute(item["departure_time"]) for item in trips if item["direction"] == direction
        )
        gaps.extend(right - left for left, right in zip(minutes, minutes[1:], strict=False))
    return (min(gaps), max(gaps)) if gaps else (None, None)


def _route_product_data(
    route: str,
    authority_route: dict[str, Any],
    operational: dict[str, Any],
    scenario_b_source: dict[str, Any],
    baseline_fleet: dict[str, Any],
    selected: dict[str, Any],
    compiler: dict[tuple[str, str], dict[str, Any]],
    selected_fleet: dict[str, Any],
    decision_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    b_rows: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        op_direction = _OP_DIRECTION[direction]
        for sequence, item in enumerate(scenario_b_source[op_direction], 1):
            b_rows.append(
                {
                    "direction": direction,
                    "direction_vi": _VI_DIRECTION[direction],
                    "sequence": sequence,
                    **item,
                    "departure_minute": _minute(item["departure_time"]),
                    "arrival_minute": _minute(item["arrival_time"]),
                }
            )
    _, b_block_by_departure = _flatten_blocks(baseline_fleet)
    for item in b_rows:
        key = (
            item["direction"]
            .replace("OUTBOUND", "terminal_1_to_2")
            .replace("INBOUND", "terminal_2_to_1"),
            item["departure_minute"],
        )
        block = b_block_by_departure.get(key)
        if block is None or block["arrival_minute"] != item["arrival_minute"]:
            raise ValueError(f"route {route} Scenario B fleet/timetable mismatch at {key}")

    c_rows: list[dict[str, Any]] = []
    c_block_rows, c_block_by_departure = _flatten_blocks(selected_fleet)
    for direction in DIRECTIONS:
        candidate = selected[f"selected_{_DIRECTION_KEY[direction]}_representative"]
        compiled = compiler[(direction, candidate)]
        service_headway = {
            item["service_regime_id"]: item["headway_minutes"]
            for item in compiled["service_regimes"]
        }
        for departure in compiled["exact_departures"]:
            key = (_OP_DIRECTION[direction], int(departure["departure_minute"]))
            block = c_block_by_departure.get(key)
            if block is None:
                raise ValueError(
                    f"route {route} compiler departure absent from fleet blocks: {key}"
                )
            c_rows.append(
                {
                    "direction": direction,
                    "direction_vi": _VI_DIRECTION[direction],
                    "sequence": int(departure["trip_sequence"]),
                    "departure_time": departure["departure_time"],
                    "departure_minute": int(departure["departure_minute"]),
                    "arrival_time": block["arrival_time"],
                    "arrival_minute": int(block["arrival_minute"]),
                    "demand_regime_id": departure["source_demand_regime_id"],
                    "service_regime_id": departure["service_regime_id"],
                    "headway_minutes": service_headway[departure["service_regime_id"]],
                    "vehicle_id": block["vehicle_id"],
                    "fleet_trip_id": block["trip_id"],
                }
            )
    if len(c_rows) != len(c_block_rows) or len(c_rows) != len(
        {item["fleet_trip_id"] for item in c_rows}
    ):
        raise ValueError(f"route {route} selected trip/block reconciliation failed")

    service_rows: list[dict[str, Any]] = []
    demand_rows: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        direction_key = _DIRECTION_KEY[direction]
        candidate = selected[f"selected_{direction_key}_representative"]
        compiled = compiler[(direction, candidate)]
        service_by_demand_regime = {
            member: regime
            for regime in compiled["service_regimes"]
            for member in regime["member_demand_regime_ids"]
        }
        for regime in compiled["service_regimes"]:
            service_rows.append(
                {
                    "direction": direction,
                    "direction_vi": _VI_DIRECTION[direction],
                    **regime,
                }
            )
        total = int(authority_route["directional_total_trips"])
        for regime in authority_route[direction_key]["regimes"]:
            service_regime = service_by_demand_regime[regime["regime_id"]]
            demand_rows.append(
                {
                    "direction": direction,
                    "direction_vi": _VI_DIRECTION[direction],
                    "candidate": candidate,
                    "regime_id": regime["regime_id"],
                    "start": regime["start"],
                    "end": regime["end"],
                    "time_window": f"{regime['start']}–{regime['end']}",
                    "duration_minutes": regime["duration_minutes"],
                    "observed_demand_share": regime["observed_demand_share"],
                    "scenario_b_trip_count": regime["scenario_b_trip_count"],
                    "scenario_b_trip_share": regime["scenario_b_trip_count"] / total,
                    "scenario_c_trip_count": regime["allocations"][candidate],
                    "scenario_c_trip_share": regime["allocations"][candidate] / total,
                    "ideal_trip_count_float": regime["ideal_trip_count_float"],
                    "service_regime_id": service_regime["service_regime_id"],
                    "scenario_c_headway_minutes": service_regime["headway_minutes"],
                }
            )
    for direction in DIRECTIONS:
        candidate = selected[f"selected_{_DIRECTION_KEY[direction]}_representative"]
        expected = [
            item["allocations"][candidate]
            for item in authority_route[_DIRECTION_KEY[direction]]["regimes"]
        ]
        actual = [
            item["actual_trip_count"]
            for item in compiler[(direction, candidate)]["demand_regime_compilations"]
        ]
        if expected != actual:
            raise ValueError(f"route {route} demand allocation/compiler reconciliation failed")

    b_min, b_max = _headway_bounds(b_rows)
    c_headways = [item["headway_minutes"] for item in service_rows]
    baseline_mismatch = sum(
        (
            Decimal(
                authority_route[_DIRECTION_KEY[direction]]["candidate_scores"]["B_REFERENCE"][
                    "mismatch"
                ]
            )
            for direction in DIRECTIONS
        ),
        Decimal(),
    )
    comparison = [
        {"metric": "total_trips", "scenario_b": len(b_rows), "scenario_c": len(c_rows)},
        {
            "metric": "fleet_required",
            "scenario_b": baseline_fleet["minimum_fleet_required"],
            "scenario_c": selected_fleet["minimum_fleet_required"],
        },
        {
            "metric": "fleet_margin",
            "scenario_b": baseline_fleet["fleet_margin"],
            "scenario_c": selected_fleet["fleet_margin"],
        },
        {
            "metric": "observed_demand_mismatch",
            "scenario_b": str(baseline_mismatch),
            "scenario_c": selected["combined_demand_mismatch"],
        },
        {"metric": "moved_trips", "scenario_b": 0, "scenario_c": selected["combined_moved_trips"]},
        {
            "metric": "ServiceRegime_count",
            "scenario_b": "N/A — exact B timetable",
            "scenario_c": selected["service_regime_count"],
        },
        {"metric": "minimum_headway", "scenario_b": b_min, "scenario_c": min(c_headways)},
        {"metric": "maximum_headway", "scenario_b": b_max, "scenario_c": max(c_headways)},
        {
            "metric": "total_excess_wait",
            "scenario_b": baseline_fleet["total_excess_terminal_wait_minutes"],
            "scenario_c": selected_fleet["total_excess_terminal_wait_minutes"],
        },
        {
            "metric": "maximum_wait",
            "scenario_b": baseline_fleet["maximum_excess_terminal_wait_minutes"],
            "scenario_c": selected_fleet["maximum_excess_terminal_wait_minutes"],
        },
        {
            "metric": "first_departure",
            "scenario_b": min(item["departure_time"] for item in b_rows),
            "scenario_c": min(item["departure_time"] for item in c_rows),
        },
        {
            "metric": "last_departure",
            "scenario_b": max(item["departure_time"] for item in b_rows),
            "scenario_c": max(item["departure_time"] for item in c_rows),
        },
    ]
    return {
        "route": route,
        "route_name": operational["route_name"],
        "runtime_minutes": operational["runtime"]["terminal_1_to_2_minutes"],
        "minimum_layover_minutes": operational["turnaround"]["minimum_layover_minutes"],
        "service_window": f"{operational['compiler_analysis_window']['start']}–{operational['compiler_analysis_window']['end']}",
        "status": FINAL_STATUS,
        "selected": {
            k: v
            for k, v in selected.items()
            if k not in {"regularity_sort", "combined_demand_mismatch_decimal"}
        },
        "baseline": {
            "fleet_required": baseline_fleet["minimum_fleet_required"],
            "fleet_limit": baseline_fleet["pilot_fleet_limit"],
            "fleet_margin": baseline_fleet["fleet_margin"],
            "combined_demand_mismatch": str(baseline_mismatch),
        },
        "scenario_b_trips": b_rows,
        "scenario_c_trips": sorted(c_rows, key=lambda item: (item["direction"], item["sequence"])),
        "service_regimes": service_rows,
        "demand_allocation": demand_rows,
        "vehicle_blocks": sorted(
            c_block_rows, key=lambda item: (item["vehicle_id"], item["sequence_within_block"])
        ),
        "comparison": comparison,
        "decision_evidence": decision_rows,
    }


def build_final_selection_manifest(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    bridge_path = (
        root
        / "private_inputs"
        / "final_selection"
        / "final_selection_demand_authority_bridge_v1_20260821.json"
    )
    bridge_hash = sha256_file(bridge_path)
    if bridge_hash != EXPECTED_BRIDGE_SHA256:
        raise ValueError(f"demand authority bridge hash mismatch: {bridge_hash}")
    bridge = _load(bridge_path)
    if bridge["status"] != "TEMPORARY_AUTHORITATIVE_BRIDGE":
        raise ValueError("unexpected demand-authority bridge status")

    operational_path = (
        root / "private_inputs" / "operational" / "operational_inputs_mst_6_10_v1.json"
    )
    scenario_b_path = (
        root / "private_inputs" / "operational" / "scenario_b_exact_departures_mst_6_10_v1.json"
    )
    operational = _load(operational_path)
    scenario_b = _load(scenario_b_path)
    fleet_review_path = root / "artifacts" / "fixed_timetable_fleet_validator_v1" / "review.json"
    fleet_review = _load(fleet_review_path)
    _assert_fingerprint(fleet_review, "review_fingerprint")
    if fleet_review["input_hashes"] != {
        "operational_inputs": sha256_file(operational_path),
        "scenario_b_exact_departures": sha256_file(scenario_b_path),
    }:
        raise ValueError("operational input hashes no longer match fleet review")

    upstream = {
        "demand_authority_bridge": {
            "path": bridge_path.relative_to(root).as_posix(),
            "sha256": bridge_hash,
        },
        "operational_inputs": {
            "path": operational_path.relative_to(root).as_posix(),
            "sha256": sha256_file(operational_path),
        },
        "scenario_b_exact_departures": {
            "path": scenario_b_path.relative_to(root).as_posix(),
            "sha256": sha256_file(scenario_b_path),
        },
        "fleet_review": {
            "path": fleet_review_path.relative_to(root).as_posix(),
            "sha256": sha256_file(fleet_review_path),
            "review_fingerprint": fleet_review["review_fingerprint"],
        },
        "allocator_fixtures": {},
    }
    routes: dict[str, Any] = {}
    product_routes: dict[str, Any] = {}
    for route in ("6", "10"):
        fixture_path = (
            root
            / "tests"
            / "fixtures"
            / "compiler_bridge"
            / f"authoritative_route_{route}_allocation_v1.json"
        )
        fixture = _load(fixture_path)
        authority_route = bridge["routes"][route]
        authority_fingerprints = {
            "demand_regime_fingerprint": bridge["upstream_fingerprints"][
                f"route_{route}_demand_regime"
            ],
            "trip_allocation_fingerprint": bridge["upstream_fingerprints"][
                f"route_{route}_trip_allocation"
            ],
        }
        _validate_bridge_against_fixture(
            route,
            authority_route,
            authority_fingerprints,
            fixture,
        )
        upstream["allocator_fixtures"][route] = {
            "path": fixture_path.relative_to(root).as_posix(),
            "sha256": sha256_file(fixture_path),
            **authority_fingerprints,
        }

        compiler: dict[tuple[str, str], dict[str, Any]] = {}
        compiler_refs: dict[str, Any] = {}
        for direction in DIRECTIONS:
            for candidate in CANDIDATES:
                path = _compiler_path(root, route, direction, candidate)
                actual_hash = sha256_file(path)
                relative = path.relative_to(root).as_posix()
                if fleet_review["compiler_artifact_hashes"].get(relative) != actual_hash:
                    raise ValueError(f"compiler artifact hash mismatch: {relative}")
                payload = _load(path)
                _assert_fingerprint(payload, "compiled_schedule_fingerprint")
                assertions = payload["upstream_fingerprint_assertions"]
                if (
                    assertions["demand_regime"]
                    != authority_fingerprints["demand_regime_fingerprint"]
                    or assertions["trip_allocation"]
                    != authority_fingerprints["trip_allocation_fingerprint"]
                ):
                    raise ValueError(f"route {route} compiler upstream authority mismatch")
                expected_counts = [
                    item["allocations"][candidate]
                    for item in authority_route[_DIRECTION_KEY[direction]]["regimes"]
                ]
                actual_counts = [
                    item["allocated_trip_count"] for item in payload["demand_regime_compilations"]
                ]
                if expected_counts != actual_counts:
                    raise ValueError(
                        f"route {route} {direction} {candidate} compiler allocation mismatch"
                    )
                supplied_quality = Decimal(
                    authority_route[_DIRECTION_KEY[direction]]["candidate_scores"][candidate][
                        "compile_quality"
                    ]
                )
                compiler_quality = Decimal(
                    str(payload["objective"]["total_quantization_error"]["decimal"])
                ).quantize(Decimal("0.000000001"))
                if supplied_quality != compiler_quality:
                    raise ValueError(
                        f"route {route} {direction} {candidate} compile-quality mismatch"
                    )
                compiler[(direction, candidate)] = payload
                compiler_refs[f"{direction}:{candidate}"] = {
                    "path": relative,
                    "sha256": actual_hash,
                    "compiled_schedule_fingerprint": payload["compiled_schedule_fingerprint"],
                    "exact_departure_signature_sha256": _schedule_signature(payload),
                }

        classes = {direction: _direction_classes(compiler, direction) for direction in DIRECTIONS}
        expected_equivalence = bridge["operational_schedule_equivalences"].get(f"route_{route}", {})
        for direction in DIRECTIONS:
            expected = expected_equivalence.get(_DIRECTION_KEY[direction])
            if expected is not None and tuple(expected) not in {
                tuple(item["members"]) for item in classes[direction]
            }:
                raise ValueError(f"route {route} {direction} expected equivalence not verified")

        pairs: list[dict[str, Any]] = []
        for outbound_class in classes["OUTBOUND"]:
            for inbound_class in classes["INBOUND"]:
                representative_out = outbound_class["representative"]
                representative_in = inbound_class["representative"]
                fleet_path = _fleet_path(root, route, representative_out, representative_in)
                fleet_payload = _load(fleet_path)
                _assert_fingerprint(fleet_payload, "validation_fingerprint")
                comparable = _fleet_comparable(fleet_payload)
                for member_out in outbound_class["members"]:
                    for member_in in inbound_class["members"]:
                        member_payload = _load(_fleet_path(root, route, member_out, member_in))
                        if _fleet_comparable(member_payload) != comparable:
                            raise ValueError(
                                f"route {route} operational equivalence has unequal fleet metrics"
                            )
                mismatch = Decimal(
                    authority_route["combined_mismatch"][representative_out][representative_in]
                )
                recomputed = Decimal(
                    authority_route["outbound"]["candidate_scores"][representative_out]["mismatch"]
                ) + Decimal(
                    authority_route["inbound"]["candidate_scores"][representative_in]["mismatch"]
                )
                if mismatch != recomputed:
                    raise ValueError(
                        f"route {route} combined mismatch does not equal directional sum"
                    )
                moved = int(
                    authority_route["outbound"]["candidate_scores"][representative_out][
                        "moved_trips"
                    ]
                ) + int(
                    authority_route["inbound"]["candidate_scores"][representative_in]["moved_trips"]
                )
                regularity_sort, regularity = _regularity(
                    (
                        compiler[("OUTBOUND", representative_out)],
                        compiler[("INBOUND", representative_in)],
                    )
                )
                pair = {
                    "route": route,
                    "candidate_pair": f"{outbound_class['label']} + {inbound_class['label']}",
                    "operational_equivalence_class": {
                        "outbound": deepcopy(outbound_class),
                        "inbound": deepcopy(inbound_class),
                    },
                    "selected_outbound_provenance": list(outbound_class["members"]),
                    "selected_inbound_provenance": list(inbound_class["members"]),
                    "selected_outbound_representative": representative_out,
                    "selected_inbound_representative": representative_in,
                    "eligible": fleet_payload["fleet_status"] == ELIGIBLE_FLEET_STATUS,
                    "fleet_status": fleet_payload["fleet_status"],
                    "fleet_required": int(fleet_payload["minimum_fleet_required"]),
                    "fleet_limit": int(fleet_payload["pilot_fleet_limit"]),
                    "fleet_margin": int(fleet_payload["fleet_margin"]),
                    "combined_demand_mismatch": str(mismatch),
                    "combined_demand_mismatch_decimal": mismatch,
                    "combined_moved_trips": moved,
                    "demand_regime_count": sum(
                        len(authority_route[_DIRECTION_KEY[d]]["regimes"]) for d in DIRECTIONS
                    ),
                    "service_regime_count": regularity["total_service_regime_count"],
                    "compiler_regularity": regularity,
                    "regularity_sort": regularity_sort,
                    "minimum_actual_headway_minutes": min(
                        item["headway_minutes"]
                        for d in DIRECTIONS
                        for item in compiler[
                            (d, representative_out if d == "OUTBOUND" else representative_in)
                        ]["service_regimes"]
                    ),
                    "maximum_actual_headway_minutes": max(
                        item["headway_minutes"]
                        for d in DIRECTIONS
                        for item in compiler[
                            (d, representative_out if d == "OUTBOUND" else representative_in)
                        ]["service_regimes"]
                    ),
                    "total_excess_terminal_wait_minutes": int(
                        fleet_payload["total_excess_terminal_wait_minutes"]
                    ),
                    "maximum_terminal_wait_minutes": int(
                        fleet_payload["maximum_excess_terminal_wait_minutes"]
                    ),
                    "minimum_layover_minutes": int(fleet_payload["minimum_actual_layover_minutes"]),
                    "total_trips": int(fleet_payload["total_departures"]),
                    "first_departure": min(
                        compiler[(d, representative_out if d == "OUTBOUND" else representative_in)][
                            "exact_departures"
                        ][0]["departure_time"]
                        for d in DIRECTIONS
                    ),
                    "last_departure": max(
                        compiler[(d, representative_out if d == "OUTBOUND" else representative_in)][
                            "exact_departures"
                        ][-1]["departure_time"]
                        for d in DIRECTIONS
                    ),
                    "fleet_artifact_reference": fleet_path.relative_to(root).as_posix(),
                    "fleet_artifact_sha256": sha256_file(fleet_path),
                    "fleet_validation_fingerprint": fleet_payload["validation_fingerprint"],
                    "pareto_status": "INELIGIBLE"
                    if fleet_payload["fleet_status"] != ELIGIBLE_FLEET_STATUS
                    else "PENDING",
                    "selection_status": "INELIGIBLE"
                    if fleet_payload["fleet_status"] != ELIGIBLE_FLEET_STATUS
                    else "NOT_SELECTED",
                    "reason_codes": ["FLEET_STATUS_NOT_ELIGIBLE"]
                    if fleet_payload["fleet_status"] != ELIGIBLE_FLEET_STATUS
                    else ["FLEET_ELIGIBLE"],
                }
                pairs.append(pair)

        eligible = [item for item in pairs if item["eligible"]]
        nondominated = []
        for item in eligible:
            dominators = [
                other for other in eligible if other is not item and _dominates(other, item)
            ]
            if dominators:
                item["pareto_status"] = "PARETO_DOMINATED"
                item["reason_codes"].append("PARETO_DOMINATED")
                item["dominated_by"] = sorted(other["candidate_pair"] for other in dominators)
            else:
                item["pareto_status"] = "PARETO_NONDOMINATED"
                item["reason_codes"].append("PARETO_NONDOMINATED")
                nondominated.append(item)
        selected = min(nondominated, key=_selection_sort_key)
        selected["selection_status"] = "SELECTED"
        selected["reason_codes"].extend(
            [
                "MINIMUM_FLEET_AMONG_NONDOMINATED",
                "LOWEST_COMBINED_MISMATCH_AFTER_FLEET",
                "DETERMINISTIC_LEXICOGRAPHIC_SELECTION",
            ]
        )
        if (
            len(selected["selected_outbound_provenance"]) > 1
            or len(selected["selected_inbound_provenance"]) > 1
        ):
            selected["reason_codes"].append("OPERATIONAL_EQUIVALENCE_COLLAPSED")
        for item in nondominated:
            if item is not selected:
                item["reason_codes"].append(_first_loss(selected, item))
        nearest = min(
            (item for item in nondominated if item is not selected), key=_selection_sort_key
        )
        selected["nearest_competing_candidate"] = nearest["candidate_pair"]
        selected["nearest_competitor_loss_reason"] = _first_loss(selected, nearest)

        baseline_path = (
            root
            / "artifacts"
            / "fixed_timetable_fleet_validator_v1"
            / f"scenario-b-route-{route}.json"
        )
        baseline_fleet = _load(baseline_path)
        _assert_fingerprint(baseline_fleet, "validation_fingerprint")
        selected_fleet = _load(root / selected["fleet_artifact_reference"])
        decision_rows = []
        for item in sorted(
            pairs, key=lambda value: (not value["eligible"], _selection_sort_key(value))
        ):
            decision_rows.append(
                {
                    k: v
                    for k, v in item.items()
                    if k not in {"regularity_sort", "combined_demand_mismatch_decimal"}
                }
            )
        route_checkpoint = {
            "route": route,
            "status": FINAL_STATUS,
            "selected_outbound_provenance": selected["selected_outbound_provenance"],
            "selected_inbound_provenance": selected["selected_inbound_provenance"],
            "selected_outbound_representative": selected["selected_outbound_representative"],
            "selected_inbound_representative": selected["selected_inbound_representative"],
            "operational_equivalence_class": selected["operational_equivalence_class"],
            "combined_mismatch": selected["combined_demand_mismatch"],
            "combined_moved_trips": selected["combined_moved_trips"],
            "fleet_b": baseline_fleet["minimum_fleet_required"],
            "fleet_c": selected["fleet_required"],
            "fleet_limit": selected["fleet_limit"],
            "fleet_margin": selected["fleet_margin"],
            "compiler_metrics": selected["compiler_regularity"],
            "fleet_metrics": {
                "total_excess_terminal_wait_minutes": selected[
                    "total_excess_terminal_wait_minutes"
                ],
                "maximum_terminal_wait_minutes": selected["maximum_terminal_wait_minutes"],
                "minimum_actual_layover_minutes": selected["minimum_layover_minutes"],
            },
            "compiler_artifact_references": {
                "outbound": compiler_refs[
                    f"OUTBOUND:{selected['selected_outbound_representative']}"
                ],
                "inbound": compiler_refs[f"INBOUND:{selected['selected_inbound_representative']}"],
            },
            "fleet_artifact_reference": {
                "path": selected["fleet_artifact_reference"],
                "sha256": selected["fleet_artifact_sha256"],
                "validation_fingerprint": selected["fleet_validation_fingerprint"],
            },
            "scenario_b_fleet_artifact_reference": {
                "path": baseline_path.relative_to(root).as_posix(),
                "sha256": sha256_file(baseline_path),
                "validation_fingerprint": baseline_fleet["validation_fingerprint"],
            },
            "demand_authority_bridge_fingerprint": bridge_hash,
            "allocator_upstream_fingerprints": authority_fingerprints,
            "selection_reason_codes": selected["reason_codes"],
            "nearest_competing_candidate": nearest["candidate_pair"],
            "nearest_competitor_loss_reason": selected["nearest_competitor_loss_reason"],
            "product_xlsx": None,
            "chart_artifact": None,
            "decision_space": decision_rows,
        }
        routes[route] = route_checkpoint
        product_routes[route] = _route_product_data(
            route,
            authority_route,
            operational["routes"][route],
            scenario_b["routes"][route],
            baseline_fleet,
            selected,
            compiler,
            selected_fleet,
            decision_rows,
        )

    checkpoint = {
        "schema_version": "final_scenario_c_selection_v1",
        "status": FINAL_STATUS,
        "selection_method": {
            "pareto_dimensions": [
                "combined_observed_demand_mismatch",
                "fleet_required",
                "compiled_timetable_regularity",
                "total_excess_terminal_wait",
            ],
            "lexicographic_order": [
                "fleet_required",
                "combined_observed_demand_mismatch",
                "compiled_timetable_regularity",
                "total_excess_terminal_wait",
                "maximum_terminal_wait",
                "effective_moved_trips",
                "candidate_label",
            ],
            "combined_mismatch_rule": "SUM_DIRECTIONAL_MISMATCH_WHEN_DIRECTIONAL_TRIP_TOTALS_EQUAL",
            "comparison_epsilon": None,
            "equality_rule": "EXACT_REPORTED_DECIMAL_EQUALITY_OR_EXACT_DEPARTURE_EQUIVALENCE",
        },
        "demand_authority_bridge": upstream["demand_authority_bridge"],
        "upstream_artifacts": upstream,
        "routes": routes,
        "combined_product_xlsx": None,
        "checkpoint_fingerprint": None,
    }
    return {"checkpoint": checkpoint, "product_routes": product_routes}


def finalized_checkpoint(payload: dict[str, Any]) -> dict[str, Any]:
    checkpoint = deepcopy(payload)
    checkpoint["checkpoint_fingerprint"] = None
    fingerprint = hashlib.sha256(canonical_json_bytes(checkpoint)).hexdigest()
    checkpoint["checkpoint_fingerprint"] = fingerprint
    return checkpoint


__all__ = [
    "ELIGIBLE_FLEET_STATUS",
    "EXPECTED_BRIDGE_SHA256",
    "FINAL_STATUS",
    "build_final_selection_manifest",
    "canonical_json_bytes",
    "finalized_checkpoint",
    "sha256_file",
]

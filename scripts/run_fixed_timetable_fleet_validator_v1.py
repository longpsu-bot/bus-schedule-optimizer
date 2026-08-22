"""Validate Scenario B and all 18 immutable Scenario C operating combinations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bus_schedule_engine.contracts_v1.fixed_timetable_fleet_inputs import (  # noqa: E402
    ScheduleSourceV1,
    file_sha256,
    load_compiled_scenario_c_direction_v1,
    load_operational_authorities_v1,
    load_scenario_b_trips_v1,
    verify_operational_input_hashes_v1,
)
from bus_schedule_engine.contracts_v1.fixed_timetable_fleet_serialization import (  # noqa: E402
    fixed_timetable_fleet_result_to_contract_dict_v1,
)
from bus_schedule_engine.contracts_v1.fixed_timetable_fleet_validator import (  # noqa: E402
    FixedOperationalTripV1,
    FixedTimetableFleetResultV1,
    can_chain_trips_v1,
    validate_fixed_timetable_fleet_v1,
)
from bus_schedule_engine.contracts_v1.serialization import canonical_sha256  # noqa: E402

_DEFAULT_OPERATIONAL_ROOT = _REPO_ROOT / "private_inputs" / "operational"
_DEFAULT_COMPILER_ROOT = _REPO_ROOT / "artifacts" / "uniform_headway_compiler_v1"
_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "artifacts" / "fixed_timetable_fleet_validator_v1"

_CANDIDATE_ORDER = {
    "C1_DEMAND_FIT": 1,
    "C2_CONSERVATIVE": 2,
    "C3_BALANCED": 3,
}
_CANDIDATE_LABEL = {
    "C1_DEMAND_FIT": "C1",
    "C2_CONSERVATIVE": "C2",
    "C3_BALANCED": "C3",
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _assert_result_invariants(
    trips: tuple[FixedOperationalTripV1, ...],
    result: FixedTimetableFleetResultV1,
    minimum_layover_minutes: int,
) -> None:
    expected = {trip.trip_id: trip for trip in trips}
    flattened = [item.trip for block in result.blocks for item in block.trips]
    actual_ids = [trip.trip_id for trip in flattened]
    if len(actual_ids) != len(set(actual_ids)):
        raise RuntimeError("a trip appears in more than one vehicle block")
    if set(actual_ids) != set(expected):
        raise RuntimeError("vehicle blocks omit or invent fixed trips")
    for actual in flattened:
        if actual != expected[actual.trip_id]:
            raise RuntimeError("a fixed departure or runtime changed during validation")
    for block in result.blocks:
        for previous, successor in zip(block.trips, block.trips[1:], strict=False):
            if not can_chain_trips_v1(previous.trip, successor.trip, minimum_layover_minutes):
                raise RuntimeError("vehicle block contains an illegal successor")
            expected_layover = successor.trip.departure_minute - previous.trip.arrival_minute
            if previous.next_trip_layover_minutes != expected_layover:
                raise RuntimeError("serialized block layover is inconsistent")
    expected_direction_totals = {
        direction: sum(trip.direction == direction for trip in trips)
        for direction in ("terminal_1_to_2", "terminal_2_to_1")
    }
    if result.direction_totals != expected_direction_totals:
        raise RuntimeError("direction totals changed during fleet validation")
    if result.minimum_fleet_required != len(result.blocks):
        raise RuntimeError("minimum fleet does not equal reconstructed block count")


def _evaluate(
    trips: tuple[FixedOperationalTripV1, ...],
    authority,
) -> FixedTimetableFleetResultV1:
    result = validate_fixed_timetable_fleet_v1(
        trips,
        minimum_layover_minutes=authority.minimum_layover_minutes,
        pilot_fleet_limit=authority.pilot_fleet_limit,
        terminal_1_name=authority.terminal_1_name,
        terminal_2_name=authority.terminal_2_name,
    )
    _assert_result_invariants(trips, result, authority.minimum_layover_minutes)
    return result


def _add_baseline_delta(
    payload: dict[str, object],
    baseline: FixedTimetableFleetResultV1,
) -> dict[str, object]:
    payload.pop("validation_fingerprint")
    payload["scenario_b_comparison"] = {
        "fleet_required_delta": (
            int(payload["minimum_fleet_required"]) - baseline.minimum_fleet_required
        ),
        "terminal_wait_delta_minutes": (
            int(payload["total_excess_terminal_wait_minutes"])
            - baseline.layover_metrics.total_excess_terminal_wait_minutes
        ),
        "interpretation": (
            "Operational fleet/wait comparison only; lower fleet is not a service-quality claim."
        ),
    }
    payload["validation_fingerprint"] = canonical_sha256(payload)
    return payload


def _summary(payload: dict[str, object], artifact_path: Path) -> dict[str, object]:
    comparison = payload.get("scenario_b_comparison")
    return {
        key: payload[key]
        for key in (
            "scenario",
            "route",
            "outbound_candidate",
            "inbound_candidate",
            "total_departures",
            "minimum_fleet_required",
            "pilot_fleet_limit",
            "fleet_margin",
            "initial_fleet_terminal_1",
            "initial_fleet_terminal_2",
            "ending_fleet_terminal_1",
            "ending_fleet_terminal_2",
            "minimum_actual_layover_minutes",
            "median_actual_layover_minutes",
            "maximum_actual_layover_minutes",
            "total_excess_terminal_wait_minutes",
            "maximum_excess_terminal_wait_minutes",
            "number_of_vehicle_blocks",
            "compiler_status",
            "fleet_status",
            "terminal_capacity_status",
            "validation_fingerprint",
        )
    } | {
        "fleet_required_delta": (
            comparison["fleet_required_delta"] if isinstance(comparison, dict) else 0
        ),
        "terminal_wait_delta_minutes": (
            comparison["terminal_wait_delta_minutes"] if isinstance(comparison, dict) else 0
        ),
        "vehicle_block_artifact": artifact_path.relative_to(_REPO_ROOT).as_posix(),
    }


def _review_markdown(review: dict[str, object]) -> str:
    lines = [
        "# Fixed-Timetable Fleet Feasibility Validator V1 — MST 6 & 10",
        "",
        "> Fixed departures, trip allocations, runtimes, and layover authority are immutable. ",
        "> `available_fleet_limit` is a pilot hard upper bound; approved active fleet and ",
        "> terminal physical capacity remain unknown.",
        "",
        "## Input verification",
        "",
        f"- Operational inputs SHA-256: `{review['input_hashes']['operational_inputs']}` (verified)",
        f"- Scenario B departures SHA-256: `{review['input_hashes']['scenario_b_exact_departures']}` (verified)",
        f"- Compiler artifacts byte-identical after validation: `{str(review['compiler_artifacts_byte_identical']).lower()}`",
        "",
        "## Feasibility matrix",
        "",
        "| Route | Out | In | Fleet | Limit | Margin | Initial T1/T2 | End T1/T2 | Min/Median/Max layover | Total excess wait | Max excess wait | Δ fleet vs B | Δ wait vs B | Status |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in review["combination_summaries"]:
        lines.append(
            "| {route} | {out} | {inbound} | {minimum_fleet_required} | "
            "{pilot_fleet_limit} | {fleet_margin} | {initial_fleet_terminal_1}/"
            "{initial_fleet_terminal_2} | {ending_fleet_terminal_1}/"
            "{ending_fleet_terminal_2} | {minimum_actual_layover_minutes}/"
            "{median_actual_layover_minutes}/{maximum_actual_layover_minutes} | "
            "{total_excess_terminal_wait_minutes} | {maximum_excess_terminal_wait_minutes} | "
            "{fleet_required_delta} | {terminal_wait_delta_minutes} | {fleet_status} |".format(
                **item,
                out=_CANDIDATE_LABEL[item["outbound_candidate"]]
                if item["scenario"] == "C"
                else "B",
                inbound=_CANDIDATE_LABEL[item["inbound_candidate"]]
                if item["scenario"] == "C"
                else "B",
            )
        )
    lines.extend(
        [
            "",
            "Every combination has a detailed canonical vehicle-block JSON artifact referenced in "
            "`review.json`. No final Scenario C timetable is selected by this milestone.",
            "",
        ]
    )
    return "\n".join(lines)


def run(
    operational_root: Path,
    compiler_root: Path,
    output_root: Path,
) -> dict[str, object]:
    operational_path = operational_root / "operational_inputs_mst_6_10_v1.json"
    scenario_b_path = operational_root / "scenario_b_exact_departures_mst_6_10_v1.json"
    input_hashes = verify_operational_input_hashes_v1(operational_path, scenario_b_path)
    authorities = load_operational_authorities_v1(operational_path)
    compiler_paths = sorted(compiler_root.glob("route-*-*.json"))
    compiler_hashes_before = {path: file_sha256(path) for path in compiler_paths}

    compiled: dict[
        tuple[str, str, str], tuple[tuple[FixedOperationalTripV1, ...], ScheduleSourceV1]
    ] = {}
    for path in compiler_paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        route_id = str(raw["route_id"])
        trips, source = load_compiled_scenario_c_direction_v1(path, authorities[route_id])
        compiled[(route_id, source.direction or "", source.candidate_id)] = (trips, source)
    expected_keys = {
        (route_id, direction, candidate)
        for route_id in ("6", "10")
        for direction in ("OUTBOUND", "INBOUND")
        for candidate in _CANDIDATE_ORDER
    }
    if set(compiled) != expected_keys:
        raise ValueError("canonical compiler artifact set is not exactly 12 schedules")

    baseline_results: dict[str, FixedTimetableFleetResultV1] = {}
    summaries: list[dict[str, object]] = []
    for route_id in ("6", "10"):
        authority = authorities[route_id]
        trips, source = load_scenario_b_trips_v1(scenario_b_path, authority)
        result = _evaluate(trips, authority)
        baseline_results[route_id] = result
        payload = fixed_timetable_fleet_result_to_contract_dict_v1(
            result,
            scenario="B",
            outbound_candidate="SCENARIO_B",
            inbound_candidate="SCENARIO_B",
            sources=(source,),
            operational_input_sha256=input_hashes["operational_inputs"],
            minimum_layover_minutes=authority.minimum_layover_minutes,
        )
        artifact_path = output_root / f"scenario-b-route-{route_id}.json"
        _write_json(artifact_path, payload)
        summaries.append(_summary(payload, artifact_path))

    for route_id in ("6", "10"):
        authority = authorities[route_id]
        baseline = baseline_results[route_id]
        candidates = tuple(sorted(_CANDIDATE_ORDER, key=_CANDIDATE_ORDER.get))
        for outbound_candidate in candidates:
            outbound_trips, outbound_source = compiled[(route_id, "OUTBOUND", outbound_candidate)]
            for inbound_candidate in candidates:
                inbound_trips, inbound_source = compiled[(route_id, "INBOUND", inbound_candidate)]
                trips = outbound_trips + inbound_trips
                departure_snapshot = {trip.trip_id: trip.departure_minute for trip in trips}
                result = _evaluate(trips, authority)
                if departure_snapshot != {trip.trip_id: trip.departure_minute for trip in trips}:
                    raise RuntimeError("fixed departures changed during validation")
                payload = fixed_timetable_fleet_result_to_contract_dict_v1(
                    result,
                    scenario="C",
                    outbound_candidate=outbound_candidate,
                    inbound_candidate=inbound_candidate,
                    sources=(outbound_source, inbound_source),
                    operational_input_sha256=input_hashes["operational_inputs"],
                    minimum_layover_minutes=authority.minimum_layover_minutes,
                )
                payload = _add_baseline_delta(payload, baseline)
                out_slug = outbound_candidate.lower().replace("_", "-")
                in_slug = inbound_candidate.lower().replace("_", "-")
                artifact_path = output_root / (f"route-{route_id}-out-{out_slug}-in-{in_slug}.json")
                _write_json(artifact_path, payload)
                summaries.append(_summary(payload, artifact_path))

    compiler_hashes_after = {path: file_sha256(path) for path in compiler_paths}
    if compiler_hashes_after != compiler_hashes_before:
        raise RuntimeError("compiler artifacts changed during fleet validation")
    final_input_hashes = verify_operational_input_hashes_v1(operational_path, scenario_b_path)
    if final_input_hashes != input_hashes:
        raise RuntimeError("private operational inputs changed during validation")

    combination_summaries = sorted(
        summaries,
        key=lambda item: (
            item["route"],
            0 if item["scenario"] == "B" else 1,
            _CANDIDATE_ORDER.get(item["outbound_candidate"], 0),
            _CANDIDATE_ORDER.get(item["inbound_candidate"], 0),
        ),
    )
    review: dict[str, object] = {
        "review_profile": "fixed_timetable_fleet_feasibility_validator_v1_review",
        "input_hashes": input_hashes,
        "compiler_artifact_hashes": {
            path.relative_to(_REPO_ROOT).as_posix(): value
            for path, value in compiler_hashes_before.items()
        },
        "compiler_artifacts_byte_identical": True,
        "scenario_b_baseline_count": 2,
        "scenario_c_combination_count": 18,
        "combination_summaries": combination_summaries,
        "within_pilot_fleet_limit": [
            {
                "route": item["route"],
                "outbound_candidate": item["outbound_candidate"],
                "inbound_candidate": item["inbound_candidate"],
                "fleet_margin": item["fleet_margin"],
            }
            for item in combination_summaries
            if item["fleet_status"] == "FEASIBLE_WITHIN_PILOT_FLEET_LIMIT"
        ],
        "exceeds_pilot_fleet_limit": [
            {
                "route": item["route"],
                "outbound_candidate": item["outbound_candidate"],
                "inbound_candidate": item["inbound_candidate"],
                "fleet_margin": item["fleet_margin"],
            }
            for item in combination_summaries
            if item["fleet_status"] == "FEASIBLE_BUT_EXCEEDS_PILOT_FLEET_LIMIT"
        ],
        "approved_active_fleet": None,
        "terminal_capacity_status": "TERMINAL_CAPACITY_NOT_VALIDATED",
        "final_timetable_selection": "NOT_PERFORMED",
    }
    review["review_fingerprint"] = canonical_sha256(review)
    _write_json(output_root / "review.json", review)
    (output_root / "review.md").write_text(_review_markdown(review), encoding="utf-8")
    return review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operational-root", type=Path, default=_DEFAULT_OPERATIONAL_ROOT)
    parser.add_argument("--compiler-root", type=Path, default=_DEFAULT_COMPILER_ROOT)
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    review = run(args.operational_root, args.compiler_root, args.output_root)
    within = len(review["within_pilot_fleet_limit"])
    exceeds = len(review["exceeds_pilot_fleet_limit"])
    print(
        f"validated 2 Scenario B baselines and 18 Scenario C combinations: "
        f"{within} within pilot limit, {exceeds} exceeding -> {args.output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

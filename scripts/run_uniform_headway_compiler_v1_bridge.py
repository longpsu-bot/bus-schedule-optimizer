"""Compile the 12 temporary-authoritative bridge allocations into artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bus_schedule_engine.contracts_v1.serialization import canonical_sha256  # noqa: E402
from bus_schedule_engine.contracts_v1.uniform_headway_compiler import (  # noqa: E402
    compile_uniform_headway_schedule_v1,
)
from bus_schedule_engine.contracts_v1.uniform_headway_compiler_bridge import (  # noqa: E402
    TemporaryAuthoritativeAllocationFixtureAdapterV1,
)
from bus_schedule_engine.contracts_v1.uniform_headway_compiler_serialization import (  # noqa: E402
    compiled_schedule_to_contract_dict_v1,
    minute_hhmm,
)

_DEFAULT_FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures" / "compiler_bridge"
_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "artifacts" / "uniform_headway_compiler_v1"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _slug(value: str) -> str:
    return value.lower().replace("_", "-")


def _objective_review_vector(candidate) -> tuple[object, ...]:
    return (
        candidate.worst_gap_excess,
        candidate.total_gap_excess,
        candidate.total_quantization_error,
        candidate.service_regime_count,
        candidate.transition_shape_error,
        candidate.edge_balance_error,
        candidate.worst_transition_or_edge_gap_minutes,
    )


def _boundary_reviews(candidate) -> list[dict[str, object]]:
    compilations = candidate.demand_regime_compilations
    departure_by_regime = {
        item.source_demand_regime_id: item.service_regime_id for item in candidate.exact_departures
    }
    reviews = []
    for left, right in zip(compilations, compilations[1:], strict=False):
        gap = right.first_departure_minute - left.last_departure_minute
        merged = departure_by_regime[left.regime_id] == departure_by_regime[right.regime_id]
        equal_headway = (
            left.selected_integer_headway is not None
            and left.selected_integer_headway == right.selected_integer_headway
        )
        if merged:
            reason = "same actual integer headway and transition gap exactly equals headway"
        elif equal_headway:
            reason = f"transition gap {gap} != selected headway {left.selected_integer_headway}"
        else:
            reason = "selected actual integer headways differ"
        reviews.append(
            {
                "boundary_minute": left.end_minute,
                "boundary_time": minute_hhmm(left.end_minute),
                "left_demand_regime_id": left.regime_id,
                "right_demand_regime_id": right.regime_id,
                "left_headway_minutes": left.selected_integer_headway,
                "right_headway_minutes": right.selected_integer_headway,
                "transition_gap_minutes": gap,
                "status": ("MERGED_IN_SERVICE_PLAN" if merged else "RETAINED_IN_SERVICE_PLAN"),
                "reason": reason,
            }
        )
    return reviews


def _candidate_summary(candidate, artifact_path: Path) -> dict[str, object]:
    headways = tuple(
        item.selected_integer_headway
        for item in candidate.demand_regime_compilations
        if item.selected_integer_headway is not None
    )
    boundaries = _boundary_reviews(candidate)
    return {
        "route_id": candidate.route_id,
        "direction": candidate.direction,
        "candidate_id": candidate.source_allocation_candidate_id,
        "status": candidate.status.value,
        "fleet_validation_status": candidate.fleet_validation_status.value,
        "total_trip_count": candidate.total_trip_count,
        "service_regime_count": candidate.service_regime_count,
        "minimum_internal_headway_minutes": min(headways) if headways else None,
        "maximum_internal_headway_minutes": max(headways) if headways else None,
        "worst_transition_or_edge_gap_minutes": (candidate.worst_transition_or_edge_gap_minutes),
        "worst_gap_excess_exact": str(candidate.worst_gap_excess),
        "total_gap_excess_exact": str(candidate.total_gap_excess),
        "total_quantization_error_exact": str(candidate.total_quantization_error),
        "transition_shape_error_exact": str(candidate.transition_shape_error),
        "edge_balance_error": candidate.edge_balance_error,
        "service_start_gap_minutes": candidate.service_start_gap_minutes,
        "service_end_gap_minutes": candidate.service_end_gap_minutes,
        "final_departure": minute_hhmm(
            candidate.exact_departures[-1].departure_minute if candidate.exact_departures else None
        ),
        "service_regimes": [
            {
                "service_regime_id": item.service_regime_id,
                "start": minute_hhmm(item.start_minute),
                "end": minute_hhmm(item.end_minute),
                "headway_minutes": item.headway_minutes,
                "departure_count": item.departure_count,
                "first_departure": minute_hhmm(item.first_departure_minute),
                "last_departure": minute_hhmm(item.last_departure_minute),
                "member_demand_regime_ids": list(item.member_demand_regime_ids),
            }
            for item in candidate.service_regimes
        ],
        "boundary_reviews": boundaries,
        "successful_merges": [
            item for item in boundaries if item["status"] == "MERGED_IN_SERVICE_PLAN"
        ],
        "equal_headway_boundaries_not_merged": [
            item
            for item in boundaries
            if item["status"] == "RETAINED_IN_SERVICE_PLAN"
            and item["left_headway_minutes"] == item["right_headway_minutes"]
        ],
        "artifact_path": artifact_path.relative_to(_REPO_ROOT).as_posix(),
    }


def _review_markdown(review: dict[str, object], compiled_by_key) -> str:
    lines = [
        "# Uniform-Headway Schedule Compiler V1 — bridge review",
        "",
        "> Upstream hashes are provenance assertions from the unavailable source machine; ",
        "> they were not reproduced on this machine. All outputs are NOT_FLEET_VALIDATED.",
        "",
        "## Candidate summary",
        "",
        "| Route | Direction | Candidate | Status | Service regimes | Min HW | Max HW | Worst transition/edge gap | Gap excess | Quantization | Start gap | End gap | Final |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in review["candidate_summaries"]:
        lines.append(
            "| {route_id} | {direction} | {candidate_id} | {status} | "
            "{service_regime_count} | {minimum_internal_headway_minutes} | "
            "{maximum_internal_headway_minutes} | "
            "{worst_transition_or_edge_gap_minutes} | {worst_gap_excess_exact} | "
            "{total_quantization_error_exact} | {service_start_gap_minutes} | "
            "{service_end_gap_minutes} | {final_departure} |".format(**item)
        )
    lines.extend(["", "## Exact ServiceRegimePlans and departures", ""])
    for item in review["candidate_summaries"]:
        key = (item["route_id"], item["direction"], item["candidate_id"])
        candidate = compiled_by_key[key]
        lines.extend(
            [
                f"### Route {key[0]} · {key[1]} · {key[2]}",
                "",
                "| Service regime | Window | HW | Trips | First | Last | Demand members |",
                "| --- | --- | ---: | ---: | --- | --- | --- |",
            ]
        )
        for regime in item["service_regimes"]:
            lines.append(
                f"| {regime['service_regime_id']} | {regime['start']}–{regime['end']} | "
                f"{regime['headway_minutes']} | {regime['departure_count']} | "
                f"{regime['first_departure']} | {regime['last_departure']} | "
                f"{', '.join(regime['member_demand_regime_ids'])} |"
            )
        lines.extend(
            [
                "",
                "Departures: "
                + ", ".join(
                    minute_hhmm(row.departure_minute) for row in candidate.exact_departures
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Scenario B comparison",
            "",
            "Exact B-vs-C timetable metrics are unavailable because this branch has no "
            "canonical MST6/MST10 ScenarioBInput exact timetable. No B departures were fabricated.",
            "",
        ]
    )
    return "\n".join(lines)


def run(fixture_root: Path, output_root: Path) -> dict[str, object]:
    bundles = [
        TemporaryAuthoritativeAllocationFixtureAdapterV1(path).load_bundle()
        for path in sorted(fixture_root.glob("authoritative_route_*_allocation_v1.json"))
    ]
    input_fingerprints_before = {
        (item.route_id, item.direction, item.allocation_candidate_id): item.input_fingerprint
        for bundle in bundles
        for item in bundle.inputs
    }
    summaries = []
    compiled_by_key = {}
    for bundle in bundles:
        for compiler_input in bundle.inputs:
            candidate = compile_uniform_headway_schedule_v1(compiler_input)
            key = (
                candidate.route_id,
                candidate.direction,
                candidate.source_allocation_candidate_id,
            )
            compiled_by_key[key] = candidate
            artifact_path = output_root / (
                f"route-{_slug(candidate.route_id)}-{_slug(candidate.direction)}-"
                f"{_slug(candidate.source_allocation_candidate_id)}.json"
            )
            _write_json(artifact_path, compiled_schedule_to_contract_dict_v1(candidate))
            summaries.append(_candidate_summary(candidate, artifact_path))
    input_fingerprints_after = {
        (item.route_id, item.direction, item.allocation_candidate_id): item.input_fingerprint
        for bundle in bundles
        for item in bundle.inputs
    }
    if input_fingerprints_before != input_fingerprints_after:
        raise RuntimeError("compiler input fingerprints changed during bridge compilation")

    route_6_inbound = [
        candidate
        for key, candidate in compiled_by_key.items()
        if key[0] == "6" and key[1] == "INBOUND"
    ]
    least_clean_route_6_inbound = max(route_6_inbound, key=_objective_review_vector)
    route_10_c3 = compiled_by_key[("10", "OUTBOUND", "C3_BALANCED")]
    ten_boundary = next(
        item for item in _boundary_reviews(route_10_c3) if item["boundary_time"] == "10:00"
    )
    review: dict[str, object] = {
        "review_profile": "uniform_headway_compiler_v1_bridge_review",
        "compiler_input_authority": "CompilerInputV1",
        "bridge_profile": "TEMPORARY_AUTHORITATIVE_BRIDGE_V1",
        "upstream_fingerprint_semantics": ("PROVENANCE_ASSERTION_NOT_REPRODUCED_ON_THIS_MACHINE"),
        "objective_order": [
            "maximum_transition_or_edge_gap_excess",
            "total_gap_excess",
            "total_headway_quantization_error",
            "resulting_service_regime_count",
            "transition_shape_error",
            "phase_edge_imbalance",
            "lexicographic_integer_headway_vector",
            "lexicographic_phase_vector",
            "lexicographic_departure_vector_redundant_after_prior_vectors",
        ],
        "fixture_integrity": [
            {
                "route_id": bundle.scenario_b_comparison.route_id,
                "fixture_path": bundle.fixture_path.relative_to(_REPO_ROOT).as_posix(),
                "fixture_fingerprint": bundle.fixture_fingerprint,
                "compiler_input_count": len(bundle.inputs),
                "scenario_b_comparison_status": bundle.scenario_b_comparison.status,
                "scenario_b_comparison_reason": bundle.scenario_b_comparison.reason,
            }
            for bundle in bundles
        ],
        "compiler_input_fingerprints_preserved": (
            input_fingerprints_before == input_fingerprints_after
        ),
        "candidate_count": len(summaries),
        "compiled_count": sum(item["status"] == "COMPILED" for item in summaries),
        "uncompilable_count": sum(
            item["status"] == "UNCOMPILABLE_ALLOCATION" for item in summaries
        ),
        "candidate_summaries": sorted(
            summaries,
            key=lambda item: (
                item["route_id"],
                item["direction"],
                item["candidate_id"],
            ),
        ),
        "successful_merges": [
            {
                "route_id": item["route_id"],
                "direction": item["direction"],
                "candidate_id": item["candidate_id"],
                **merge,
            }
            for item in summaries
            for merge in item["successful_merges"]
        ],
        "equal_headway_boundaries_not_merged": [
            {
                "route_id": item["route_id"],
                "direction": item["direction"],
                "candidate_id": item["candidate_id"],
                **boundary,
            }
            for item in summaries
            for boundary in item["equal_headway_boundaries_not_merged"]
        ],
        "route_10_outbound_c3_10_00_boundary": ten_boundary,
        "route_6_inbound_least_clean_candidate": {
            "candidate_id": (least_clean_route_6_inbound.source_allocation_candidate_id),
            "review_vector": [
                str(value) for value in _objective_review_vector(least_clean_route_6_inbound)
            ],
        },
        "scenario_b_comparison": {
            "status": "UNAVAILABLE",
            "reason": (
                "No canonical MST6/MST10 ScenarioBInput exact timetable is tracked on "
                "this branch; exact B departures were not reconstructed from counts."
            ),
        },
    }
    review["review_fingerprint"] = canonical_sha256(review)
    _write_json(output_root / "review.json", review)
    (output_root / "review.md").write_text(
        _review_markdown(review, compiled_by_key) + "\n", encoding="utf-8"
    )
    return review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-root", type=Path, default=_DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    review = run(args.fixture_root.resolve(), args.output_root.resolve())
    print(
        f"compiled {review['compiled_count']}/{review['candidate_count']} schedules -> "
        f"{args.output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

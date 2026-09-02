"""Human-review artifacts for validated demand-regime trip allocation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .contracts_v1 import (
    DAILY_VALIDATED,
    DEFAULT_DETERMINISTIC_TRIP_ALLOCATOR_CONFIG_V1,
    DeterministicTripAllocatorConfigV1,
    RegimeModelSelectionStatusV1,
    TripAllocationCandidateSetV1,
    TripAllocationCandidateV1,
    TripAllocationSetStatusV1,
    allocate_validated_demand_regimes_v1,
    trip_allocation_candidate_set_to_dict_v1,
)
from .demand_regime_review import DemandRegimeReviewV1, build_v3_demand_regime_review_v1
from .time_utils import format_hhmm

DEMAND_REGIME_ALLOCATION_REVIEW_PROFILE_V1 = "demand_regime_allocation_review_v1"


@dataclass(frozen=True, slots=True)
class DemandRegimeAllocationReviewV1:
    input_path: Path
    route_id: str
    route_name: str
    demand_regime_review: DemandRegimeReviewV1
    candidate_sets: tuple[TripAllocationCandidateSetV1, ...]


def build_v3_demand_regime_allocation_review_v1(
    input_path: str | Path,
    *,
    raw_demand_path: str | Path,
    profile_id: str | None = None,
    allocator_config: DeterministicTripAllocatorConfigV1 = (
        DEFAULT_DETERMINISTIC_TRIP_ALLOCATOR_CONFIG_V1
    ),
) -> DemandRegimeAllocationReviewV1:
    """Build allocation candidates from authoritative daily-validated plans and Scenario B."""

    regime_review = build_v3_demand_regime_review_v1(
        input_path,
        profile_id=profile_id,
        raw_demand_path=raw_demand_path,
    )
    if regime_review.model_selection.status != RegimeModelSelectionStatusV1.SUCCESS:
        raise ValueError("trip allocation requires successful daily demand model selection")
    candidate_sets = []
    for selection in regime_review.model_selection.selections:
        if (
            selection.selection_status != RegimeModelSelectionStatusV1.SUCCESS
            or selection.final_plan is None
        ):
            raise ValueError(
                f"trip allocation requires a validated plan for {selection.direction.value}"
            )
        candidate_sets.append(
            allocate_validated_demand_regimes_v1(
                selection.final_plan,
                regime_review.scenario_b,
                evidence_status=DAILY_VALIDATED,
                config=allocator_config,
            )
        )
    return DemandRegimeAllocationReviewV1(
        input_path=Path(input_path).expanduser().resolve(),
        route_id=regime_review.route_id,
        route_name=regime_review.route_name,
        demand_regime_review=regime_review,
        candidate_sets=tuple(candidate_sets),
    )


def demand_regime_allocation_review_to_dict_v1(
    review: DemandRegimeAllocationReviewV1,
) -> dict[str, object]:
    return {
        "review_profile": DEMAND_REGIME_ALLOCATION_REVIEW_PROFILE_V1,
        "input_file": review.input_path.name,
        "route_id": review.route_id,
        "route_name": review.route_name,
        "architecture": {
            "demand_regime": "descriptive segmentation of observed realized demand",
            "service_regime": "future operational interval with one uniform headway",
            "generates_exact_departure_times": False,
        },
        "candidate_sets": [
            trip_allocation_candidate_set_to_dict_v1(item) for item in review.candidate_sets
        ],
    }


def _candidate_map(
    result: TripAllocationCandidateSetV1,
) -> dict[str, TripAllocationCandidateV1]:
    candidates = (
        result.b_reference,
        result.c1_demand_fit,
        result.c2_conservative,
        result.c3_balanced,
    )
    if any(item is None for item in candidates):
        return {}
    return {item.candidate_id: item for item in candidates if item is not None}


def _headway(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def render_demand_regime_allocation_review_markdown_v1(
    review: DemandRegimeAllocationReviewV1,
) -> str:
    lines = [
        f"# Validated demand-regime trip allocation: route {review.route_id}",
        "",
        f"- Route: {review.route_name}",
        f"- Input: `{review.input_path.name}`",
        "- Evidence: `DAILY_VALIDATED`",
        "- Output scope: integer trip-count candidates only; no departure timestamps or phases",
        "- Demand interpretation: observed-demand fit under realized Scenario B service, not a "
        "causal true-demand optimum",
        "- Interval membership: `[start,end)`",
        "- Nominal headway: `duration / trip_count` without endpoint anchoring",
        "- DemandRegime: descriptive segmentation of observed demand.",
        "- ServiceRegime: a future operational interval with one uniform headway.",
        "- Validated demand-regime count does not prescribe the final number of service regimes.",
    ]
    for result in review.candidate_sets:
        lines.extend(
            [
                "",
                f"## {result.direction.value}",
                "",
                f"- Status: `{result.status.value}`",
                f"- Canonical Scenario B direction total: **{result.total_trips}**",
                f"- Service floor: `{result.service_floor_provenance}`; slowest B nominal "
                f"headway = **{_headway(result.service_floor_headway_minutes)} min**",
                f"- Explicit minimum-headway authority: "
                f"**{result.minimum_headway_policy_minutes or 'none'}**",
                f"- DP states retained: **{result.feasible_dp_state_count}**",
                f"- Pareto frontier size: **{result.pareto_frontier_size}**",
            ]
        )
        if result.status != TripAllocationSetStatusV1.SUCCESS:
            lines.extend(
                [
                    "",
                    f"Failure: `{result.failure_code}` — {result.failure_message}",
                ]
            )
            continue
        candidates = _candidate_map(result)
        b = candidates["B_REFERENCE"]
        c1 = candidates["C1_DEMAND_FIT"]
        c2 = candidates["C2_CONSERVATIVE"]
        c3 = candidates["C3_BALANCED"]
        lines.extend(
            [
                "",
                "### Regime allocation comparison",
                "",
                "| Regime | Time | Demand share | B | Ideal | Floor | C1 | C2 | C3 | "
                "B HW | C1 HW | C2 HW | C3 HW |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for b_row, c1_row, c2_row, c3_row in zip(
            b.regime_allocations,
            c1.regime_allocations,
            c2.regime_allocations,
            c3.regime_allocations,
            strict=True,
        ):
            lines.append(
                f"| {b_row.regime_id} | {format_hhmm(b_row.start_time)}–"
                f"{format_hhmm(b_row.end_time)} | {b_row.demand_share:.2%} | "
                f"{b_row.b_trip_count} | {b_row.ideal_trip_count_float:.2f} | "
                f"{b_row.min_trip_count} | {c1_row.allocated_trip_count} | "
                f"{c2_row.allocated_trip_count} | {c3_row.allocated_trip_count} | "
                f"{_headway(b_row.b_nominal_headway)} | "
                f"{_headway(c1_row.nominal_headway)} | "
                f"{_headway(c2_row.nominal_headway)} | "
                f"{_headway(c3_row.nominal_headway)} |"
            )
        lines.extend(
            [
                "",
                "Each row additionally exposes demand sum, B service share, integer-headway "
                "proxy, quantization error, and observed demand per allocated trip in JSON.",
                "",
                "### Candidate scores",
                "",
                "| Candidate | Status | Demand mismatch | Improvement vs B | Moved trips | "
                "Compile quality | Min HW | Max HW | Duration-weighted HW | Changed regimes |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for candidate in (b, c1, c2, c3):
            lines.append(
                f"| {candidate.candidate_id} | `{candidate.status.value}` | "
                f"{candidate.demand_mismatch:.9f} | "
                f"{candidate.demand_mismatch_improvement_vs_b:.9f} | "
                f"{candidate.moved_trips} | {candidate.compile_quality_score:.9f} | "
                f"{candidate.minimum_nominal_headway:.2f} | "
                f"{candidate.maximum_nominal_headway:.2f} | "
                f"{candidate.duration_weighted_average_nominal_headway:.2f} | "
                f"{candidate.changed_regime_count} |"
            )
        lines.extend(
            [
                "",
                "### Candidate reconciliation and movement",
                "",
            ]
        )
        for candidate in (b, c1, c2, c3):
            increases = [
                f"{item.regime_id} +{item.allocated_trip_count - item.b_trip_count}"
                for item in candidate.regime_allocations
                if item.allocated_trip_count > item.b_trip_count
            ]
            decreases = [
                f"{item.regime_id} {item.allocated_trip_count - item.b_trip_count}"
                for item in candidate.regime_allocations
                if item.allocated_trip_count < item.b_trip_count
            ]
            lines.append(
                f"- `{candidate.candidate_id}`: sum={sum(candidate.allocation_vector)}; "
                f"moved={candidate.moved_trips}; increases="
                f"{', '.join(increases) or 'none'}; decreases={', '.join(decreases) or 'none'}."
            )
        lines.extend(
            [
                "",
                "### Binding service floors",
                "",
            ]
        )
        for candidate in (c1, c2, c3):
            binding = [
                item.regime_id
                for item in candidate.regime_allocations
                if item.service_floor_binding
            ]
            lines.append(f"- `{candidate.candidate_id}`: {', '.join(binding) or 'none'}.")
        lines.extend(
            [
                "",
                "### Potential downstream service-regime merge boundaries",
                "",
            ]
        )
        for candidate in (c1, c2, c3):
            mergeable = [
                format_hhmm(item.boundary_time)
                for item in candidate.merge_hints
                if item.service_rate_merge_candidate
            ]
            lines.append(f"- `{candidate.candidate_id}`: {', '.join(mergeable) or 'none'}.")
    lines.extend(
        [
            "",
            "> Merge hints are diagnostic only. The validated DemandRegimePlan is unchanged, "
            "and no exact Scenario C departures have been generated.",
        ]
    )
    return "\n".join(lines)


def write_demand_regime_allocation_review_v1(
    review: DemandRegimeAllocationReviewV1,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    target = Path(output_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    stem = f"route_{review.route_id}_demand_regime_trip_allocations"
    json_path = target / f"{stem}.json"
    markdown_path = target / f"{stem}.md"
    json_path.write_text(
        json.dumps(
            demand_regime_allocation_review_to_dict_v1(review),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(
        render_demand_regime_allocation_review_markdown_v1(review) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return json_path, markdown_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic trip allocations over validated demand regimes."
    )
    parser.add_argument("input", type=Path, nargs="+")
    parser.add_argument("--raw-demand", type=Path, required=True)
    parser.add_argument("--profile")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-headway-minutes", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = DeterministicTripAllocatorConfigV1(
        minimum_headway_minutes=args.minimum_headway_minutes
    )
    try:
        for input_path in args.input:
            review = build_v3_demand_regime_allocation_review_v1(
                input_path,
                raw_demand_path=args.raw_demand,
                profile_id=args.profile,
                allocator_config=config,
            )
            paths = write_demand_regime_allocation_review_v1(review, args.output_dir)
            statuses = ",".join(item.status.value for item in review.candidate_sets)
            print(f"route {review.route_id}: {statuses} -> {paths[1].name}")
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Demand-regime allocation review failed: {exc}", file=sys.stderr)
        return 2
    return 0


__all__ = [
    "DEMAND_REGIME_ALLOCATION_REVIEW_PROFILE_V1",
    "DemandRegimeAllocationReviewV1",
    "build_v3_demand_regime_allocation_review_v1",
    "demand_regime_allocation_review_to_dict_v1",
    "main",
    "render_demand_regime_allocation_review_markdown_v1",
    "write_demand_regime_allocation_review_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())

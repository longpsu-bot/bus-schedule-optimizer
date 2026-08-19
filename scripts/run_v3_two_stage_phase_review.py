"""Run V3 with an opt-in bounded 30-minute phase-membership review policy.

This runner exists to validate the real-route scheduling hypothesis before changing the
production V3 membership contract. It keeps all existing V3 hard operating constraints and
changes only two representation semantics for this local expert-review run:

1. a singleton regime uses one feasible departure domain instead of intersecting independent
   start/end boundary windows; and
2. a multi-block uniform regime may differ from a Stage 1 block target by at most one trip at
   each 30-minute boundary, with cumulative deviation also bounded to one trip.

The normal ``scripts/run_v3_two_stage.py`` path is intentionally unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bus_schedule_engine.contracts_v1 import two_stage_allocator as allocator  # noqa: E402
from bus_schedule_engine.contracts_v1 import two_stage_solver as stage2  # noqa: E402

# Exact private pilot identities prepared for the MST 6 / MST 10 review.
_EXPECTED_INPUT_SHA256 = {
    "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx": (
        "4a5030da74d809b8a8bb40364bdc54f625c12469850d1d6ba1385622ab8d8f11"
    ),
    "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx": (
        "876c5c709dfb6fee21ade63150302704f6c09589bf8a927bad279fbc88ff2b94"
    ),
}

_PHASE_DEVIATION_PER_BLOCK = 1
_PHASE_DEVIATION_CUMULATIVE = 1

_ORIGINAL_REPRESENTATION_CANDIDATES = allocator._representation_candidates_for_group


def _phase_membership_ok(
    representation: allocator.UniformRegimeRepresentationV1,
    group,
    allocation,
) -> bool:
    """Allow local phase movement without allowing cumulative allocation drift."""
    ordered_blocks = tuple(sorted(group.blocks, key=lambda item: (item.start_time, item.end_time)))
    cumulative_actual = 0
    cumulative_target = 0
    for block in ordered_blocks:
        target = allocation[(group.direction, block.block_id)]
        actual = sum(
            block.start_time // 60 <= minute < block.end_time // 60
            for minute in representation.departure_minutes
        )
        if abs(actual - target) > _PHASE_DEVIATION_PER_BLOCK:
            return False
        # A positive-demand block that Stage 1 explicitly serves may not become uncovered merely
        # because a uniform sequence crosses a statistical 30-minute boundary.
        if block.observed_passengers > 0 and target > 0 and actual == 0:
            return False
        cumulative_actual += actual
        cumulative_target += target
        if abs(cumulative_actual - cumulative_target) > _PHASE_DEVIATION_CUMULATIVE:
            return False
    # A merged regime still owns exactly the same number of trips. The bounded deviation only
    # changes which side of an internal statistical boundary one trip may fall on.
    return cumulative_actual == cumulative_target == group.trip_count


def _bounded_phase_membership_representation(candidates, group, allocation):
    return next(
        (
            representation
            for representation in candidates
            if _phase_membership_ok(representation, group, allocation)
        ),
        None,
    )


def _singleton_aware_representation_candidates(
    problem,
    group,
    policy,
    projection,
    *,
    absolute_max_shift_per_trip_minutes=None,
    enforce_final_tail=True,
    enforce_protected_floor=True,
):
    """Give a one-trip regime one feasible minute domain instead of two disjoint boundaries."""
    if group.trip_count != 1:
        return _ORIGINAL_REPRESENTATION_CANDIDATES(
            problem,
            group,
            policy,
            projection,
            absolute_max_shift_per_trip_minutes=absolute_max_shift_per_trip_minutes,
            enforce_final_tail=enforce_final_tail,
            enforce_protected_floor=enforce_protected_floor,
        )

    directional = allocator._ordered_directional_trips(problem)[group.direction]
    sources = directional[group.source_start_index : group.source_end_index + 1]
    if len(sources) != 1:
        return (), (0, -1), (0, -1)
    source = sources[0]
    source_minute = source.departure_time // 60
    first_service = directional[0].departure_time // 60
    last_service = directional[-1].departure_time // 60
    block_start = min(block.start_time // 60 for block in group.blocks)
    block_end = max(block.end_time // 60 for block in group.blocks)
    upper_membership = block_end if group.has_final_service_sentinel else block_end - 1
    shift_limit = (
        policy.absolute_max_shift_per_trip_minutes
        if absolute_max_shift_per_trip_minutes is None
        else absolute_max_shift_per_trip_minutes
    )
    lower = max(first_service, block_start, source_minute - shift_limit)
    upper = min(last_service, upper_membership, source_minute + shift_limit)

    # Preserve the authoritative first/last locks exactly. These are service locks, not demand
    # block preferences.
    if group.source_start_index == 0:
        lower = max(lower, first_service)
        upper = min(upper, first_service)
    if group.source_end_index == len(directional) - 1:
        lower = max(lower, last_service)
        upper = min(upper, last_service)
    if lower > upper:
        return (), (lower, upper), (lower, upper)

    candidates = tuple(
        allocator.UniformRegimeRepresentationV1(
            start_minute=minute,
            end_minute=minute,
            uniform_headway_minutes=None,
            departure_minutes=(minute,),
        )
        for minute in sorted(range(lower, upper + 1), key=lambda item: (abs(item - source_minute), item))
    )
    unified_window = (lower, upper)
    return candidates, unified_window, unified_window


def _add_bounded_phase_block_membership_constraints(
    model,
    problem,
    plan,
    departure_by_source_id,
):
    """Encode per-block and cumulative +/-1 phase deviation in Stage 2.

    The directional/day totals and regime trip totals remain exact through the existing V3 source
    slices. Only membership around internal demand-block boundaries is allowed to move locally.
    """
    directional = stage2._ordered_directional_trips(problem)
    by_direction_and_block = {}
    count_by_direction_and_block = {}
    target_by_direction_and_block = {}
    blocks_by_direction = defaultdict(list)

    for allocation_block in plan.allocation_blocks:
        targets = dict(allocation_block.directional_trip_counts)
        for direction, target in targets.items():
            memberships = []
            for source in directional[direction]:
                departure = departure_by_source_id[source.trip_id]
                at_or_after = stage2._reified_less_than_or_equal(
                    model,
                    allocation_block.start_minute,
                    departure,
                    name=f"v3_phase_after_{source.trip_id}_{allocation_block.block_id}",
                )
                before_end = stage2._reified_less_than_or_equal(
                    model,
                    departure,
                    allocation_block.end_minute - 1,
                    name=f"v3_phase_before_{source.trip_id}_{allocation_block.block_id}",
                )
                member = model.new_bool_var(
                    f"v3_phase_member_{source.trip_id}_{allocation_block.block_id}"
                )
                model.add(member <= at_or_after)
                model.add(member <= before_end)
                model.add(member >= at_or_after + before_end - 1)
                memberships.append(member)

            count = model.new_int_var(
                0,
                len(directional[direction]),
                f"v3_phase_count_{direction.value}_{allocation_block.block_id}",
            )
            model.add(count == sum(memberships))
            lower = max(0, target - _PHASE_DEVIATION_PER_BLOCK)
            upper = min(len(directional[direction]), target + _PHASE_DEVIATION_PER_BLOCK)
            if allocation_block.observed_passengers > 0 and target > 0:
                lower = max(lower, 1)
            model.add(count >= lower)
            model.add(count <= upper)

            key = (direction, allocation_block.block_id)
            by_direction_and_block[key] = tuple(memberships)
            count_by_direction_and_block[key] = count
            target_by_direction_and_block[key] = target
            blocks_by_direction[direction].append(allocation_block)

    for direction, blocks in blocks_by_direction.items():
        ordered = sorted(blocks, key=lambda item: (item.start_minute, item.end_minute, item.block_id))
        cumulative_counts = []
        cumulative_target = 0
        for block in ordered:
            key = (direction, block.block_id)
            cumulative_counts.append(count_by_direction_and_block[key])
            cumulative_target += target_by_direction_and_block[key]
            actual_prefix = sum(cumulative_counts)
            model.add(actual_prefix - cumulative_target <= _PHASE_DEVIATION_CUMULATIVE)
            model.add(cumulative_target - actual_prefix <= _PHASE_DEVIATION_CUMULATIVE)

        # At the complete analytical demand horizon there is no phase drift. A final-service
        # sentinel, when present, is intentionally outside the half-open final demand block and is
        # already excluded from the Stage 1 analytical total.
        if ordered:
            model.add(sum(cumulative_counts) == cumulative_target)

    return by_direction_and_block


def _install_review_policy() -> None:
    allocator._representation_candidates_for_group = _singleton_aware_representation_candidates
    allocator._exact_membership_representation = _bounded_phase_membership_representation
    stage2._add_exact_block_membership_constraints = _add_bounded_phase_block_membership_constraints


_install_review_policy()

from bus_schedule_engine.v3_result_exporter import (  # noqa: E402
    build_profile_comparison_v1,
    export_profile_comparison_xlsx_v1,
    export_v3_result_xlsx_v1,
)
from bus_schedule_engine.v3_runner import (  # noqa: E402
    DEFAULT_V3_TOTAL_SOLVE_BUDGET_SECONDS,
    run_v3_profile_v1,
    write_deterministic_json,
)
from bus_schedule_engine.v3_workbook import import_v3_multi_period_workbook_v1  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run V3 with opt-in bounded +/-1 block phase deviation for expert timetable review."
        )
    )
    parser.add_argument("--input", required=True, type=Path)
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument("--profile")
    profiles.add_argument("--profiles")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--solve-budget-seconds",
        type=float,
        default=DEFAULT_V3_TOTAL_SOLVE_BUDGET_SECONDS,
    )
    parser.add_argument("--shape-distance-threshold", type=float, default=0.15)
    return parser


def _selected_profiles(args: argparse.Namespace) -> tuple[tuple[str, ...], bool]:
    if args.profiles:
        selected = tuple(item.strip() for item in args.profiles.split(",") if item.strip())
        if not selected or len(set(selected)) != len(selected):
            raise ValueError("--profiles must contain unique profile ids")
        return selected, True
    if args.profile:
        return (args.profile.strip(),), False
    imported = import_v3_multi_period_workbook_v1(args.input)
    default = imported.multi_period_demand.default_profile_id
    if default is None or not default.strip():
        raise ValueError("no explicit or default demand profile is available")
    return (default,), False


def _input_identity(path: Path) -> tuple[str, str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = _EXPECTED_INPUT_SHA256.get(path.name)
    if expected is not None and digest != expected:
        raise ValueError(
            f"INPUT_FILE_IDENTITY_MISMATCH: {path.name} sha256={digest}, expected={expected}"
        )
    return digest, "MATCHED_EXPECTED_PILOT" if expected is not None else "UNREGISTERED_INPUT"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        input_path = args.input.expanduser().resolve()
        output_root = args.output_dir.expanduser().resolve()
        digest, identity_status = _input_identity(input_path)
        selected_profiles, batch_mode = _selected_profiles(args)
        print(
            f"input: {input_path.name} sha256={digest} identity={identity_status}; "
            f"phase_deviation=+/-{_PHASE_DEVIATION_PER_BLOCK}, "
            f"cumulative=+/-{_PHASE_DEVIATION_CUMULATIVE}"
        )
        runs = []
        for profile_id in selected_profiles:
            run = run_v3_profile_v1(
                input_path,
                profile_id,
                total_budget_seconds=args.solve_budget_seconds,
                shape_distance_threshold=args.shape_distance_threshold,
            )
            payload = dict(run.payload)
            payload["review_membership_policy"] = {
                "profile": "BLOCK_TARGET_BOUNDED_PHASE_DEVIATION_REVIEW_V1",
                "per_block_max_trip_deviation": _PHASE_DEVIATION_PER_BLOCK,
                "cumulative_max_trip_deviation": _PHASE_DEVIATION_CUMULATIVE,
                "input_sha256": digest,
                "input_identity_status": identity_status,
            }
            run = replace(run, payload=payload)
            profile_output = output_root / profile_id if batch_mode else output_root
            write_deterministic_json(profile_output / "result.json", run.payload)
            export_v3_result_xlsx_v1(run, profile_output / "result.xlsx")
            runs.append(run)
            print(
                f"{profile_id}: {run.payload['aggregate_native_status']} / "
                f"{run.payload['final_acceptance_state']} / "
                f"C={run.payload['scenario_c_available']} -> {profile_output}"
            )
        if batch_mode:
            comparison = build_profile_comparison_v1(runs)
            write_deterministic_json(output_root / "profile_comparison.json", comparison)
            export_profile_comparison_xlsx_v1(comparison, output_root / "profile_comparison.xlsx")
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"V3 phase-review runner failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

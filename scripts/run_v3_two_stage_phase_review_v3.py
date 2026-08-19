"""Run bounded-phase V3 review with matching independent-validator semantics.

This review-only wrapper extends phase-review v2 by aligning the final independent
validator with the same bounded 30-minute phase semantics already used by Stage 1,
its necessary-feasibility pre-check, and Stage 2.

Production ``scripts/run_v3_two_stage.py`` and the production validator contract are
unchanged. This wrapper only suppresses the legacy exact-block-membership rejection
when the candidate independently satisfies all bounded-phase conditions.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import run_v3_two_stage_phase_review_v2 as base  # noqa: E402

from bus_schedule_engine import v3_runner  # noqa: E402
from bus_schedule_engine.contracts_v1 import solver_validation  # noqa: E402

_BLOCK_REJECTION = "V3_STAGE_1_BLOCK_ALLOCATION_NOT_REPRODUCED"
_ORIGINAL_TWO_STAGE_CANDIDATE_ERRORS = solver_validation._two_stage_candidate_errors
_ORIGINAL_BUILD_PAYLOAD = v3_runner.build_v3_result_payload_v1


def _bounded_phase_candidate_membership_ok(candidate, allocation_plan) -> bool:
    """Independently verify the review policy before waiving exact block equality."""
    if allocation_plan is None:
        return False

    rows_by_direction = defaultdict(list)
    for block in allocation_plan.allocation_blocks:
        for direction, expected in block.directional_trip_counts:
            actual = sum(
                trip.direction == direction
                and block.start_minute * 60 <= trip.c_departure_time < block.end_minute * 60
                for trip in candidate.exact_timetable
            )
            if abs(actual - expected) > base.base._PHASE_DEVIATION_PER_BLOCK:
                return False
            if block.observed_passengers > 0 and expected > 0 and actual == 0:
                return False
            rows_by_direction[direction].append((block, expected, actual))

    for rows in rows_by_direction.values():
        cumulative_actual = 0
        cumulative_target = 0
        for block, expected, actual in sorted(
            rows,
            key=lambda item: (item[0].start_minute, item[0].end_minute, item[0].block_id),
        ):
            del block
            cumulative_actual += actual
            cumulative_target += expected
            if (
                abs(cumulative_actual - cumulative_target)
                > base.base._PHASE_DEVIATION_CUMULATIVE
            ):
                return False
        if cumulative_actual != cumulative_target:
            return False
    return True


def _review_two_stage_candidate_errors(problem, candidate, allocation_plan, policy):
    errors = _ORIGINAL_TWO_STAGE_CANDIDATE_ERRORS(
        problem,
        candidate,
        allocation_plan,
        policy,
    )
    if _BLOCK_REJECTION not in errors:
        return errors
    if not _bounded_phase_candidate_membership_ok(candidate, allocation_plan):
        return errors
    return [error for error in errors if error != _BLOCK_REJECTION]


def _review_build_payload(
    run_input_path,
    derivation,
    normalized,
    b_evaluation,
    result,
    stage_1_plans,
):
    payload = _ORIGINAL_BUILD_PAYLOAD(
        run_input_path,
        derivation,
        normalized,
        b_evaluation,
        result,
        stage_1_plans,
    )
    outcome = result.candidate_outcome
    diagnostic = outcome.diagnostic_candidate if outcome is not None else None
    payload["review_candidate_outcome"] = {
        "result_status": outcome.result_status.value if outcome is not None else None,
        "solver_status": outcome.solver_status.value if outcome is not None else None,
        "rejection_codes": list(diagnostic.rejection_codes) if diagnostic is not None else [],
        "rejection_summary": diagnostic.summary if diagnostic is not None else None,
    }
    policy_payload = dict(payload.get("review_membership_policy") or {})
    policy_payload["validator_semantics"] = "BOUNDED_PHASE_DEVIATION_REVIEW_V1"
    payload["review_membership_policy"] = policy_payload
    return payload


solver_validation._two_stage_candidate_errors = _review_two_stage_candidate_errors
v3_runner.build_v3_result_payload_v1 = _review_build_payload


if __name__ == "__main__":
    raise SystemExit(base.base.main())

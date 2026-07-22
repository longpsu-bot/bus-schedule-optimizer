from __future__ import annotations

from dataclasses import asdict

from .serialization import canonical_sha256
from .solver_models import (
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    ScheduleGenerationOutcomeV1,
    ScheduleSolutionV1,
)
from .solver_problem import jsonable


def candidate_fingerprint(
    *,
    source_b_fingerprint: str,
    solver_adapter: str,
    exact_timetable: tuple[RawCandidateTripV1, ...],
    headway_regimes: tuple[RawHeadwayRegimeV1, ...],
) -> str:
    return canonical_sha256(
        {
            "source_b_fingerprint": source_b_fingerprint,
            "solver_adapter": solver_adapter,
            "exact_timetable": jsonable(
                [asdict(item) for item in exact_timetable]
            ),
            "headway_regimes": jsonable(
                [asdict(item) for item in headway_regimes]
            ),
        }
    )


def solution_fingerprint_payload(
    solution: ScheduleSolutionV1,
) -> dict[str, object]:
    payload = jsonable(asdict(solution))
    payload.pop("solution_fingerprint", None)
    payload.pop("solve_duration_seconds", None)
    return payload


def outcome_fingerprint_payload(
    outcome: ScheduleGenerationOutcomeV1,
) -> dict[str, object]:
    payload = jsonable(asdict(outcome))
    payload.pop("outcome_fingerprint", None)
    payload.pop("solve_duration_seconds", None)
    solution = payload.get("solution")
    if isinstance(solution, dict):
        solution.pop("solve_duration_seconds", None)
    return payload

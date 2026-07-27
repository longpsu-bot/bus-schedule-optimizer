"""Characterize natural and proxy-sensitivity behavior for route corpus v1."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import ortools

from bus_schedule_engine import SolverChoice, analyze_and_optimize_schedule_v1
from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.contracts_v1 import (
    DemandConfidence,
    GenerationResultStatus,
    ScenarioBEvaluationPolicyV1,
    SolverPolicyV1,
    build_heuristic_schedule_request_v1,
    build_ortools_service_quality_request_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
    run_schedule_solver_v1,
)
from bus_schedule_engine.contracts_v1.exact_demand_authority import (
    _scale_exact_demand_authority,
)
from bus_schedule_engine.contracts_v1.regime_headway_policy import (
    _analyze_regime_headways,
    _derive_sustained_service_regimes,
)
from bus_schedule_engine.contracts_v1.service_quality_metrics import (
    _recompute_service_quality_objective_vector_with_authority_v1,
)
from bus_schedule_engine.optimization_comparison import compare_solver_outcomes_v1

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "tests"))

from route_corpus_support import (  # noqa: E402
    FIXTURE_FILES,
    imported_workbook_from_fixture,
    load_corpus_fixture,
    normalization_options_from_fixture,
)

OUTPUT_DIR = REPOSITORY / "outputs" / "route_corpus_v1"
RUN_MARKERS = ("COLD", "WARM_1", "WARM_2")
ORTOOLS_POLICY = SolverPolicyV1(
    time_limit_seconds=30,
    worker_count=1,
    random_seed=0,
)
SENSITIVITY_POLICY = ScenarioBEvaluationPolicyV1(
    minimum_authoritative_demand_confidence=DemandConfidence.LOW
)
OPERATIONAL_STATUS = "DRAFT_NOT_OPERATIONALLY_APPROVED"
SENSITIVITY_STATUS = "PROXY_SENSITIVITY_ONLY"
NOT_RUN = "NOT_RUN"
TERMINAL_OCCUPANCY_LIMITATION = "TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED"


class RecordingSolver:
    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.adapter_id = delegate.adapter_id
        self.last_run = None

    def solve(self, problem):
        self.last_run = self.delegate.solve(problem)
        return self.last_run


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _environment() -> dict[str, Any]:
    return {
        "commit_sha": _git("rev-parse", "HEAD"),
        "git_worktree_dirty": bool(_git("status", "--porcelain")),
        "ortools_version": ortools.__version__,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }


def _outcome_summary(outcome: Any | None) -> dict[str, Any] | None:
    if outcome is None:
        return None
    return {
        "accepted": outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED,
        "generation_result_status": outcome.result_status.value,
        "limitations": list(outcome.limitations),
        "native_status": (
            outcome.solver_status.value if outcome.solver_status is not None else None
        ),
        "outcome_fingerprint": outcome.outcome_fingerprint,
        "solve_duration_seconds": outcome.solve_duration_seconds,
        "solver_adapter": outcome.solver_adapter,
    }


def _natural_summary(result: Any) -> dict[str, Any]:
    return {
        "adjustment_decision": result.adjustment_assessment.primary_decision.value,
        "adjustment_reason_codes": list(result.adjustment_assessment.reason_codes),
        "b_evaluation_disposition": result.b_evaluation.evaluation.disposition.value,
        "comparison": (
            {
                "heuristic_vector": result.comparison.heuristic_vector,
                "objective_names": result.comparison.objective_names,
                "ortools_vector": result.comparison.ortools_vector,
                "reason_code": result.comparison.reason_code,
                "recommended_solver": (
                    result.comparison.recommended_solver.value
                    if result.comparison.recommended_solver is not None
                    else None
                ),
            }
            if result.comparison is not None
            else None
        ),
        "heuristic_outcome": _outcome_summary(result.heuristic_outcome),
        "limitations": list(result.limitations),
        "operational_status": OPERATIONAL_STATUS,
        "ortools_outcome": _outcome_summary(result.ortools_outcome),
        "recommended_outcome": _outcome_summary(result.recommended_outcome),
        "selected_action": result.selected_action.value,
        "solver_attempted": result.solver_attempted,
        "solver_choice": result.solver_choice.value,
    }


def _solution_summary(solution: Any | None) -> dict[str, Any] | None:
    if solution is None:
        return None
    return {
        "available_fleet_limit": solution.available_fleet_limit,
        "initial_terminal_split": {
            "terminal_1": solution.recommended_initial_fleet_terminal_1,
            "terminal_2": solution.recommended_initial_fleet_terminal_2,
        },
        "maximum_shift_minutes": solution.maximum_shift_minutes,
        "minimum_required_fleet": solution.minimum_required_fleet,
        "regime_count": len(solution.c_headway_regimes),
        "regime_sequences": [
            {
                "actual_headway_sequence": list(regime.actual_headway_sequence),
                "direction": regime.direction.value,
                "exceptional_headways": list(regime.exceptional_headways),
                "regime_id": regime.regime_id,
                "transition_headways": list(regime.transition_headways),
            }
            for regime in solution.c_headway_regimes
        ],
        "shifted_trip_count": solution.shifted_trip_count,
        "solution_fingerprint": solution.solution_fingerprint,
        "total_shift_minutes": solution.total_shift_minutes,
    }


def _regime_characterization(
    *,
    problem: Any,
    candidate: Any | None,
    exact_demand_authority: Any,
    scaled_demand: Any,
    solution: Any | None,
) -> dict[str, Any]:
    if candidate is None:
        exact_by_block = {block.block_id: block for block in exact_demand_authority.blocks}
        return {
            "different_measurable_headways_observed": None,
            "no_externally_fixed_headway_imposed": True,
            "regimes": [
                {
                    "demand_blocks": [
                        {
                            "block_id": block_id,
                            "denominator": exact_by_block[block_id].denominator,
                            "numerator": exact_by_block[block_id].numerator,
                            "scaled_integer_weight": (scaled_demand.weight_by_block_id[block_id]),
                        }
                        for block_id in regime.block_ids
                    ],
                    "direction": regime.direction.value,
                    "end_time": regime.end_time,
                    "endpoint_locks_binding": None,
                    "fleet_limit_binding": None,
                    "headway_measurable": None,
                    "internal_headway_sequence": None,
                    "maximum_internal_headway": None,
                    "minimum_internal_headway": None,
                    "regime_id": regime.regime_id,
                    "solver_derived_headway": None,
                    "start_time": regime.start_time,
                    "status": "NO_SOLVER_CANDIDATE",
                    "transition_headway_after": None,
                    "transition_headway_before": None,
                    "trip_count": None,
                    "turnaround_binding": None,
                }
                for regime in _derive_sustained_service_regimes(problem)
            ],
            "uniformity_error_codes": [],
        }

    policy = _analyze_regime_headways(
        problem,
        candidate.exact_timetable,
        enforce_candidate_labels=True,
    )
    exact_by_block = {block.block_id: block for block in exact_demand_authority.blocks}
    endpoint_ids: dict[str, str] = {}
    for direction in ("terminal_1_to_2", "terminal_2_to_1"):
        directional = sorted(
            (trip for trip in candidate.exact_timetable if trip.direction.value == direction),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        if directional:
            endpoint_ids[direction + ":first"] = directional[0].c_trip_id
            endpoint_ids[direction + ":last"] = directional[-1].c_trip_id

    turnaround_binding_trip_ids: set[str] = set()
    if solution is not None:
        assignments_by_vehicle: dict[str, list[Any]] = {}
        for assignment in solution.fleet_assignment:
            assignments_by_vehicle.setdefault(assignment.vehicle_id, []).append(assignment)
        for assignments in assignments_by_vehicle.values():
            ordered = sorted(
                assignments,
                key=lambda item: (item.departure_time, item.c_trip_id),
            )
            for earlier, later in zip(ordered, ordered[1:], strict=False):
                if earlier.ready_time == later.departure_time:
                    turnaround_binding_trip_ids.update((earlier.c_trip_id, later.c_trip_id))

    rows: list[dict[str, Any]] = []
    measurable_headways: list[int] = []
    for analysis in policy.analyses:
        endpoint_locks = []
        direction = analysis.regime.direction.value
        if endpoint_ids.get(direction + ":first") in analysis.trip_ids:
            endpoint_locks.append("FIRST_DEPARTURE")
        if endpoint_ids.get(direction + ":last") in analysis.trip_ids:
            endpoint_locks.append("LAST_DEPARTURE")
        if analysis.exact_headway is not None:
            measurable_headways.append(analysis.exact_headway)
        rows.append(
            {
                "demand_blocks": [
                    {
                        "block_id": block_id,
                        "denominator": exact_by_block[block_id].denominator,
                        "numerator": exact_by_block[block_id].numerator,
                        "scaled_integer_weight": (scaled_demand.weight_by_block_id[block_id]),
                    }
                    for block_id in analysis.regime.block_ids
                ],
                "direction": direction,
                "end_time": analysis.regime.end_time,
                "endpoint_locks_binding": endpoint_locks,
                "fleet_limit_binding": (
                    solution.minimum_required_fleet == solution.available_fleet_limit
                    if solution is not None
                    else None
                ),
                "headway_measurable": analysis.headway_measurable,
                "internal_headway_sequence": list(analysis.internal_headways),
                "maximum_internal_headway": analysis.maximum_internal_headway,
                "minimum_internal_headway": analysis.minimum_internal_headway,
                "regime_id": analysis.regime.regime_id,
                "solver_derived_headway": analysis.exact_headway,
                "start_time": analysis.regime.start_time,
                "status": analysis.status,
                "transition_headway_after": analysis.transition_headway_after,
                "transition_headway_before": analysis.transition_headway_before,
                "trip_count": len(analysis.trip_ids),
                "turnaround_binding": (
                    any(trip_id in turnaround_binding_trip_ids for trip_id in analysis.trip_ids)
                    if solution is not None
                    else None
                ),
            }
        )
    return {
        "different_measurable_headways_observed": (
            len(set(measurable_headways)) > 1 if measurable_headways else None
        ),
        "no_externally_fixed_headway_imposed": True,
        "regimes": rows,
        "uniformity_error_codes": list(policy.error_codes),
    }


def _benchmark_row(
    *,
    fixture_id: str,
    marker: str,
    solver_name: str,
    context: Any,
    recorder: RecordingSolver,
    outcome: Any,
    comparison: Any,
    common_quality_problem: Any,
    exact_demand_authority: Any,
    scaled_demand: Any,
) -> dict[str, Any]:
    run = recorder.last_run
    candidate = run.candidate if run is not None else None
    solution = outcome.solution
    objective_vector = (
        _recompute_service_quality_objective_vector_with_authority_v1(
            common_quality_problem,
            solution,
            exact_demand_authority,
        )
        if solution is not None
        and outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
        else None
    )
    scenario_b = common_quality_problem.scenario_b
    effective_controls = (
        {
            "random_seed": 0,
            "time_limit_seconds": 30,
            "worker_count": 1,
        }
        if solver_name == "OR_TOOLS"
        else {
            "random_seed": None,
            "time_limit_seconds": None,
            "worker_count": None,
        }
    )
    control_limitations = (
        []
        if solver_name == "OR_TOOLS"
        else [
            (
                "The canonical heuristic adapter is deterministic but does not implement "
                "generic time-limit, worker-count, or random-seed controls."
            )
        ]
    )
    fleet_assessment = context.b_evaluation.fleet_assessment
    minimum_required_fleet = (
        solution.minimum_required_fleet
        if solution is not None
        else fleet_assessment.minimum_required_fleet
    )
    initial_terminal_split = (
        {
            "terminal_1": solution.recommended_initial_fleet_terminal_1,
            "terminal_2": solution.recommended_initial_fleet_terminal_2,
        }
        if solution is not None
        else {
            "terminal_1": fleet_assessment.recommended_initial_fleet_terminal_1,
            "terminal_2": fleet_assessment.recommended_initial_fleet_terminal_2,
        }
    )
    return {
        "accepted": outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED,
        "available_fleet_limit": scenario_b.available_fleet_limit,
        "candidate_fingerprint": (
            candidate.candidate_fingerprint
            if candidate is not None
            else (
                outcome.diagnostic_candidate.candidate_fingerprint
                if outcome.diagnostic_candidate is not None
                else None
            )
        ),
        "directional_trips": {
            "inbound": scenario_b.trips_by_direction.inbound,
            "outbound": scenario_b.trips_by_direction.outbound,
        },
        "effective_controls": effective_controls,
        "fixture_id": fixture_id,
        "generation_result_status": outcome.result_status.value,
        "initial_terminal_split": initial_terminal_split,
        "limitations": [*outcome.limitations, *control_limitations],
        "marker": marker,
        "minimum_required_fleet": minimum_required_fleet,
        "native_status": (
            outcome.solver_status.value if outcome.solver_status is not None else None
        ),
        "objective_vector": objective_vector,
        "operational_status": OPERATIONAL_STATUS,
        "outcome_fingerprint": outcome.outcome_fingerprint,
        "problem_fingerprint": context.problem.problem_fingerprint,
        "pre_solve_b_fleet_feasible": fleet_assessment.feasible,
        "recommendation_reason": comparison.reason_code,
        "recommended_solver": (
            comparison.recommended_solver.value
            if comparison.recommended_solver is not None
            else None
        ),
        "requested_controls": {
            "random_seed": 0,
            "time_limit_seconds": 30,
            "worker_count": 1,
        },
        "sensitivity_status": SENSITIVITY_STATUS,
        "exact_demand_authority_fingerprint": (exact_demand_authority.authority_fingerprint),
        "regime_characterization": _regime_characterization(
            problem=common_quality_problem,
            candidate=candidate,
            exact_demand_authority=exact_demand_authority,
            scaled_demand=scaled_demand,
            solution=solution,
        ),
        "solution": _solution_summary(solution),
        "solution_fingerprint": (solution.solution_fingerprint if solution is not None else None),
        "solve_duration_seconds": outcome.solve_duration_seconds,
        "solver": solver_name,
        "solver_adapter": outcome.solver_adapter,
        "source_b_fingerprint": outcome.source_b_fingerprint,
        "total_trips": scenario_b.total_daily_trips,
    }


def _repeatability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "accepted",
        "candidate_fingerprint",
        "generation_result_status",
        "native_status",
        "objective_vector",
        "outcome_fingerprint",
        "problem_fingerprint",
        "solution_fingerprint",
    )
    by_solver: dict[str, Any] = {}
    for solver in ("HEURISTIC", "OR_TOOLS"):
        solver_rows = [row for row in rows if row["solver"] == solver]
        differing_fields = [
            field
            for field in fields
            if any(row[field] != solver_rows[0][field] for row in solver_rows[1:])
        ]
        by_solver[solver] = {
            "all_repetitions_identical": not differing_fields,
            "compared_fields": list(fields),
            "differences_by_marker": {
                field: {row["marker"]: row[field] for row in solver_rows}
                for field in differing_fields
            },
            "differing_fields": differing_fields,
            "run_count": len(solver_rows),
        }
    return by_solver


def _not_run_sensitivity(
    *,
    proxy: dict[str, Any],
    reason_code: str,
    limitations: list[str],
    quality_request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "benchmark_run_count": 0,
        "comparison": None,
        "comparison_runs": [],
        "coverage_issues": proxy["coverage_issues"],
        "coverage_status": proxy["coverage_status"],
        "demand_confidence": "LOW",
        "diagnostic_status": NOT_RUN,
        "heuristic_outcome": None,
        "heuristic_request": {
            "attempted": False,
            "constructed": False,
            "reason": "A common canonical quality problem was not available.",
        },
        "limitations": limitations,
        "minimum_accepted_confidence": "LOW",
        "operational_status": OPERATIONAL_STATUS,
        "ortools_outcome": None,
        "quality_request": quality_request,
        "reason_code": reason_code,
        "recommendation": None,
        "requested_controls": {
            "random_seed": 0,
            "time_limit_seconds": 30,
            "worker_count": 1,
        },
        "status": SENSITIVITY_STATUS,
    }


def characterize_fixture(
    filename: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixture = load_corpus_fixture(filename)
    imported = imported_workbook_from_fixture(fixture)
    options = normalization_options_from_fixture(fixture)

    natural = {}
    for solver_choice in SolverChoice:
        result = analyze_and_optimize_schedule_v1(
            imported,
            options,
            solver_choice=solver_choice,
        )
        natural[solver_choice.value] = _natural_summary(result)
        if result.solver_attempted:
            raise RuntimeError(
                f"{fixture['fixture_id']} default LOW-confidence path unexpectedly solved"
            )

    proxy = fixture["demand_observations"]["departure_hour_proxy_v1"]
    if proxy["coverage_status"] == "PROXY_COVERAGE_INCOMPLETE":
        characterization = {
            "fixture_id": fixture["fixture_id"],
            "limitations": [TERMINAL_OCCUPANCY_LIMITATION],
            "natural_unified_service": natural,
            "operational_status": OPERATIONAL_STATUS,
            "proxy_sensitivity_only": _not_run_sensitivity(
                proxy=proxy,
                reason_code="PROXY_COVERAGE_INCOMPLETE",
                limitations=[
                    (
                        "At least one interior Scenario B service-window hour has no Scenario A "
                        "departure observation."
                    ),
                    (
                        "No demand was fabricated, interpolated, or stretched across the "
                        "unobserved hour."
                    ),
                    "Neither canonical solver request was constructed or executed.",
                ],
                quality_request={
                    "attempted": False,
                    "builder_error_code": None,
                    "builder_error_codes": [],
                    "constructed": False,
                    "explanation": (
                        "Proxy coverage eligibility is false, so the canonical quality builder "
                        "was not invoked."
                    ),
                },
            ),
            "raw_trip_observation_policy": (
                "PRESERVED_AS_EVIDENCE_NEVER_SUPPLIED_AS_CONTRACT_V1_DEMAND_INTERVALS"
            ),
        }
        return characterization, []

    normalized = normalize_imported_workbook_v1(imported, options)
    evaluation = evaluate_scenario_b_v1(normalized, SENSITIVITY_POLICY)
    quality_context, quality_solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        evaluation_policy=SENSITIVITY_POLICY,
        solver_policy=ORTOOLS_POLICY,
    )

    heuristic_context, heuristic_solver = build_heuristic_schedule_request_v1(
        normalized,
        evaluation,
        imported.parameters_b,
        imported.trips_b,
        imported.demand,
        ScenarioCConfig.from_mapping(imported.configuration),
        evaluation_policy=SENSITIVITY_POLICY,
    )
    exact_demand_authority = quality_solver.exact_demand_authority
    if exact_demand_authority is None:
        raise RuntimeError("Canonical quality request omitted exact demand authority")
    scaled_demand = _scale_exact_demand_authority(
        exact_demand_authority,
        quality_context.problem,
    )

    benchmark_rows: list[dict[str, Any]] = []
    comparison_runs: list[dict[str, Any]] = []
    heuristic_outcome = None
    quality_outcome = None
    comparison = None
    for marker in RUN_MARKERS:
        heuristic_recorder = RecordingSolver(heuristic_solver)
        quality_recorder = RecordingSolver(quality_solver)
        heuristic_outcome = run_schedule_solver_v1(
            heuristic_context,
            heuristic_recorder,
        )
        quality_outcome = run_schedule_solver_v1(
            quality_context,
            quality_recorder,
        )
        comparison = compare_solver_outcomes_v1(
            quality_context.problem,
            heuristic_outcome,
            quality_outcome,
            exact_demand_authority=exact_demand_authority,
        )
        benchmark_rows.extend(
            (
                _benchmark_row(
                    fixture_id=fixture["fixture_id"],
                    marker=marker,
                    solver_name="HEURISTIC",
                    context=heuristic_context,
                    recorder=heuristic_recorder,
                    outcome=heuristic_outcome,
                    comparison=comparison,
                    common_quality_problem=quality_context.problem,
                    exact_demand_authority=exact_demand_authority,
                    scaled_demand=scaled_demand,
                ),
                _benchmark_row(
                    fixture_id=fixture["fixture_id"],
                    marker=marker,
                    solver_name="OR_TOOLS",
                    context=quality_context,
                    recorder=quality_recorder,
                    outcome=quality_outcome,
                    comparison=comparison,
                    common_quality_problem=quality_context.problem,
                    exact_demand_authority=exact_demand_authority,
                    scaled_demand=scaled_demand,
                ),
            )
        )
        comparison_runs.append(
            {
                "heuristic_vector": comparison.heuristic_vector,
                "marker": marker,
                "objective_names": comparison.objective_names,
                "operational_status": OPERATIONAL_STATUS,
                "ortools_vector": comparison.ortools_vector,
                "reason_code": comparison.reason_code,
                "recommended_solver": (
                    comparison.recommended_solver.value
                    if comparison.recommended_solver is not None
                    else None
                ),
                "sensitivity_status": SENSITIVITY_STATUS,
            }
        )

    characterization = {
        "fixture_id": fixture["fixture_id"],
        "limitations": [TERMINAL_OCCUPANCY_LIMITATION],
        "natural_unified_service": natural,
        "operational_status": OPERATIONAL_STATUS,
        "proxy_sensitivity_only": {
            "benchmark_run_count": len(benchmark_rows),
            "comparison_runs": comparison_runs,
            "coverage_issues": proxy["coverage_issues"],
            "coverage_status": proxy["coverage_status"],
            "demand_confidence": "LOW",
            "diagnostic_status": "RUN",
            "exact_demand_authority": {
                "blocks": [
                    [block.block_id, block.numerator, block.denominator]
                    for block in exact_demand_authority.blocks
                ],
                "fingerprint": exact_demand_authority.authority_fingerprint,
                "problem_adapter_context_fingerprint": (
                    quality_context.problem.adapter_context_fingerprint
                ),
                "scaling": {
                    "common_denominator": scaled_demand.common_denominator,
                    "global_reduction_gcd": scaled_demand.reduction_gcd,
                    "global_weight_by_block_id": dict(
                        sorted(scaled_demand.weight_by_block_id.items())
                    ),
                    "shared_across_both_directions": True,
                },
            },
            "heuristic_outcome": _outcome_summary(heuristic_outcome),
            "heuristic_request": {"attempted": True, "constructed": True},
            "limitations": [
                "DRAFT sensitivity evidence only; no timetable is operationally approved.",
                "No externally fixed headway was imposed.",
            ],
            "minimum_accepted_confidence": "LOW",
            "operational_status": OPERATIONAL_STATUS,
            "ortools_outcome": _outcome_summary(quality_outcome),
            "quality_request": {
                "attempted": True,
                "builder_error_code": None,
                "builder_error_codes": [],
                "constructed": True,
                "explanation": None,
            },
            "comparison": comparison_runs[-1],
            "reason_code": "COMPARISON_EXECUTED",
            "recommendation": {
                "reason_code": comparison.reason_code,
                "recommended_solver": (
                    comparison.recommended_solver.value
                    if comparison.recommended_solver is not None
                    else None
                ),
            },
            "repeatability": _repeatability(benchmark_rows),
            "status": SENSITIVITY_STATUS,
        },
        "raw_trip_observation_policy": (
            "PRESERVED_AS_EVIDENCE_NEVER_SUPPLIED_AS_CONTRACT_V1_DEMAND_INTERVALS"
        ),
    }
    return characterization, benchmark_rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    environment = _environment()
    fixtures: list[dict[str, Any]] = []
    benchmark_rows: list[dict[str, Any]] = []
    for filename in FIXTURE_FILES:
        characterization, rows = characterize_fixture(filename)
        fixtures.append(characterization)
        benchmark_rows.extend(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(
        OUTPUT_DIR / "characterization.json",
        {
            "environment": environment,
            "fixtures": fixtures,
            "operational_status": OPERATIONAL_STATUS,
        },
    )
    _write_json(
        OUTPUT_DIR / "benchmark_runs.json",
        {
            "environment": environment,
            "operational_status": OPERATIONAL_STATUS,
            "runs": benchmark_rows,
        },
    )
    print(f"Wrote characterization outputs to {OUTPUT_DIR.relative_to(REPOSITORY)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

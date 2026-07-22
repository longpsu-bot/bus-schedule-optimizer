from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "v1"
EXAMPLE_DIR = ROOT / "examples" / "contracts" / "v1"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


SCHEMAS = {path.name: _load(path) for path in SCHEMA_DIR.glob("*.schema.json")}
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in SCHEMAS.values()
)


def _validator(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        SCHEMAS[schema_name],
        registry=REGISTRY,
        format_checker=FormatChecker(),
    )


def _schema_errors(instance: dict[str, Any], schema_name: str) -> list[str]:
    return [error.message for error in _validator(schema_name).iter_errors(instance)]


def _solution_domain_errors(solution: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    minimum = solution["minimum_required_fleet"]
    available = solution["available_fleet_limit"]
    initial_1 = solution["recommended_initial_fleet_terminal_1"]
    initial_2 = solution["recommended_initial_fleet_terminal_2"]

    if minimum > available:
        errors.append("minimum_required_fleet exceeds available_fleet_limit")
    if initial_1 + initial_2 != minimum:
        errors.append("recommended initial fleet does not reconcile with minimum_required_fleet")
    if solution["fleet_margin"] != available - minimum:
        errors.append("fleet_margin is not available_fleet_limit - minimum_required_fleet")

    profiles = (
        ("vehicle_stock_profile_terminal_1", initial_1),
        ("vehicle_stock_profile_terminal_2", initial_2),
    )
    for profile_name, initial_stock in profiles:
        previous_after = initial_stock
        for event in solution[profile_name]:
            before = event["stock_before"]
            after = event["stock_after"]
            expected_after = (
                before + event["arriving_or_ready_vehicle_count"] - event["departure_count"]
            )
            if before != previous_after:
                errors.append(f"{profile_name} resets or breaks stock continuity")
            if after != expected_after:
                errors.append(f"{profile_name} has inconsistent event arithmetic")
            if before < 0 or after < 0:
                errors.append(f"{profile_name} has negative terminal stock")
            previous_after = after
    return errors


def _problem_domain_errors(problem: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if problem["initial_fleet_positioning_mode"] == "bounded":
        for terminal, bounds in problem["bounded_initial_fleet"].items():
            if bounds["minimum"] > bounds["maximum"]:
                errors.append(f"{terminal} minimum initial fleet exceeds maximum")
    return errors


def _accepted_outcome() -> dict[str, Any]:
    outcome = _load(EXAMPLE_DIR / "schedule_generation_outcome.example.json")
    outcome.update(
        {
            "result_status": "SOLUTION_ACCEPTED",
            "execution_status": "COMPLETED",
            "solver_status": "FEASIBLE",
            "solver_adapter": "ortools_cp_sat_target_example",
            "solve_duration_seconds": 0.42,
            "solution": _load(EXAMPLE_DIR / "schedule_solution.example.json"),
            "diagnostic_candidate": None,
            "explanations": ["An accepted candidate passed independent domain validation."],
        }
    )
    return outcome


@pytest.mark.parametrize(
    ("schema_name", "example_name"),
    [
        ("scenario_a_input.schema.json", "scenario_a_input.example.json"),
        ("scenario_b_input.schema.json", "scenario_b_input.example.json"),
        ("observed_demand_input.schema.json", "observed_demand_input.example.json"),
        ("demand_resolution.schema.json", "demand_resolution.example.json"),
        ("demand_analysis_block.schema.json", "demand_analysis_block.example.json"),
        ("block_supply_plan.schema.json", "block_supply_plan.example.json"),
        (
            "schedule_evaluation_result.schema.json",
            "schedule_evaluation_result.example.json",
        ),
        ("schedule_problem.schema.json", "schedule_problem.example.json"),
        ("schedule_solution.schema.json", "schedule_solution.example.json"),
        (
            "schedule_generation_outcome.schema.json",
            "schedule_generation_outcome.example.json",
        ),
    ],
)
def test_all_contract_examples_validate(schema_name: str, example_name: str) -> None:
    assert _schema_errors(_load(EXAMPLE_DIR / example_name), schema_name) == []


@pytest.mark.parametrize(
    "schema_name",
    ["scenario_a_input.schema.json", "scenario_b_input.schema.json"],
)
def test_available_fleet_limit_is_required_and_positive(schema_name: str) -> None:
    example_name = schema_name.replace(".schema", ".example")
    instance = _load(EXAMPLE_DIR / example_name)
    instance.pop("available_fleet_limit")
    assert _schema_errors(instance, schema_name)

    instance["available_fleet_limit"] = 0
    assert _schema_errors(instance, schema_name)


@pytest.mark.parametrize(
    ("schema_name", "example_name"),
    [
        ("scenario_a_input.schema.json", "scenario_a_input.example.json"),
        ("scenario_b_input.schema.json", "scenario_b_input.example.json"),
    ],
)
def test_approved_active_fleet_may_be_omitted_or_null(schema_name: str, example_name: str) -> None:
    scenario = _load(EXAMPLE_DIR / example_name)
    scenario.pop("approved_active_fleet", None)
    assert _schema_errors(scenario, schema_name) == []

    scenario["approved_active_fleet"] = None
    assert _schema_errors(scenario, schema_name) == []


def test_contract_defaults_are_upper_bound_and_solver_determined() -> None:
    properties = SCHEMAS["schedule_problem.schema.json"]["properties"]
    assert properties["fleet_constraint_mode"]["default"] == "available_upper_bound"
    assert properties["initial_fleet_positioning_mode"]["default"] == "solver_determined"


def test_fixed_initial_positioning_requires_both_terminal_values() -> None:
    problem = _load(EXAMPLE_DIR / "schedule_problem.example.json")
    problem["initial_fleet_positioning_mode"] = "fixed"
    assert _schema_errors(problem, "schedule_problem.schema.json")

    problem["fixed_initial_fleet"] = {"terminal_1": 1}
    assert _schema_errors(problem, "schedule_problem.schema.json")

    problem["fixed_initial_fleet"]["terminal_2"] = 0
    assert _schema_errors(problem, "schedule_problem.schema.json") == []


def test_bounded_positioning_validates_shape_and_domain_bounds() -> None:
    problem = _load(EXAMPLE_DIR / "schedule_problem.example.json")
    problem["initial_fleet_positioning_mode"] = "bounded"
    problem["bounded_initial_fleet"] = {
        "terminal_1": {"minimum": 0, "maximum": 2},
        "terminal_2": {"minimum": 0, "maximum": 2},
    }
    assert _schema_errors(problem, "schedule_problem.schema.json") == []
    assert _problem_domain_errors(problem) == []

    problem["bounded_initial_fleet"]["terminal_1"] = {"minimum": 2, "maximum": 1}
    assert _schema_errors(problem, "schedule_problem.schema.json") == []
    assert _problem_domain_errors(problem) == ["terminal_1 minimum initial fleet exceeds maximum"]


def test_exact_scheduled_fleet_requires_approved_value() -> None:
    problem = _load(EXAMPLE_DIR / "schedule_problem.example.json")
    problem["fleet_constraint_mode"] = "exact_scheduled_fleet"
    problem["scenario_b"].pop("approved_active_fleet", None)
    assert _schema_errors(problem, "schedule_problem.schema.json")

    problem["scenario_b"]["approved_active_fleet"] = 1
    assert _schema_errors(problem, "schedule_problem.schema.json") == []


def test_minimum_fleet_may_be_lower_than_available_limit_and_margin_reconciles() -> None:
    solution = _load(EXAMPLE_DIR / "schedule_solution.example.json")
    assert solution["minimum_required_fleet"] < solution["available_fleet_limit"]
    assert solution["fleet_margin"] == (
        solution["available_fleet_limit"] - solution["minimum_required_fleet"]
    )
    assert _solution_domain_errors(solution) == []


def test_solution_exceeding_available_limit_is_domain_invalid() -> None:
    solution = _load(EXAMPLE_DIR / "schedule_solution.example.json")
    solution["minimum_required_fleet"] = solution["available_fleet_limit"] + 1
    assert _schema_errors(solution, "schedule_solution.schema.json") == []
    assert "minimum_required_fleet exceeds available_fleet_limit" in (
        _solution_domain_errors(solution)
    )


def test_initial_terminal_fleet_totals_reconcile_with_minimum() -> None:
    solution = _load(EXAMPLE_DIR / "schedule_solution.example.json")
    assert (
        solution["recommended_initial_fleet_terminal_1"]
        + solution["recommended_initial_fleet_terminal_2"]
        == solution["minimum_required_fleet"]
    )

    invalid = deepcopy(solution)
    invalid["recommended_initial_fleet_terminal_2"] += 1
    assert "recommended initial fleet does not reconcile with minimum_required_fleet" in (
        _solution_domain_errors(invalid)
    )


def test_terminal_stock_may_never_be_negative() -> None:
    solution = _load(EXAMPLE_DIR / "schedule_solution.example.json")
    solution["vehicle_stock_profile_terminal_1"][0]["stock_after"] = -1
    assert _schema_errors(solution, "schedule_solution.schema.json")
    assert "vehicle_stock_profile_terminal_1 has negative terminal stock" in (
        _solution_domain_errors(solution)
    )


def test_demand_block_boundary_does_not_reset_terminal_stock() -> None:
    solution = _load(EXAMPLE_DIR / "schedule_solution.example.json")
    profile = solution["vehicle_stock_profile_terminal_1"]
    boundary_departure = next(event for event in profile if event["event_time"] == "07:00")
    preceding_event = profile[profile.index(boundary_departure) - 1]

    assert boundary_departure["stock_before"] == preceding_event["stock_after"]
    assert {event["event_type"] for event in profile} <= {
        "VEHICLE_READY",
        "DEPARTURE",
        "READY_AND_DEPARTURE",
    }
    assert _solution_domain_errors(solution) == []


def test_schedule_solution_schema_is_accepted_only() -> None:
    solution = _load(EXAMPLE_DIR / "schedule_solution.example.json")
    assert _schema_errors(solution, "schedule_solution.schema.json") == []

    invalid_status = deepcopy(solution)
    invalid_status["status"] = "NO_FEASIBLE_C_WITH_B_PARAMETERS"
    assert _schema_errors(invalid_status, "schedule_solution.schema.json")

    invalid_solver_status = deepcopy(solution)
    invalid_solver_status["solver_status"] = "INFEASIBLE"
    assert _schema_errors(invalid_solver_status, "schedule_solution.schema.json")


def test_accepted_outcome_requires_complete_c_and_fleet_artifacts() -> None:
    outcome = _accepted_outcome()
    assert _schema_errors(outcome, "schedule_generation_outcome.schema.json") == []

    missing_solution = deepcopy(outcome)
    missing_solution["solution"] = None
    assert _schema_errors(missing_solution, "schedule_generation_outcome.schema.json")

    missing_timetable = deepcopy(outcome)
    missing_timetable["solution"].pop("c_exact_timetable")
    assert _schema_errors(missing_timetable, "schedule_generation_outcome.schema.json")

    missing_fleet = deepcopy(outcome)
    missing_fleet["solution"].pop("fleet_assignment")
    assert _schema_errors(missing_fleet, "schedule_generation_outcome.schema.json")


def test_no_feasible_outcome_validates_without_fabricated_c() -> None:
    outcome = _load(EXAMPLE_DIR / "schedule_generation_outcome.example.json")
    outcome.update(
        {
            "result_status": "NO_FEASIBLE_C_WITH_B_PARAMETERS",
            "execution_status": "COMPLETED",
            "solver_status": "INFEASIBLE",
            "solver_adapter": "ortools_cp_sat_target_example",
            "solve_duration_seconds": 1.5,
            "solution": None,
            "diagnostic_candidate": None,
            "explanations": ["No feasible C exists under the recorded locked parameters."],
        }
    )
    assert _schema_errors(outcome, "schedule_generation_outcome.schema.json") == []


@pytest.mark.parametrize(
    "result_status",
    ["C_NOT_GENERATED_INSUFFICIENT_DATA", "C_NOT_REQUIRED_B_SUITABLE"],
)
def test_not_run_outcomes_use_engine_not_run_without_native_status(
    result_status: str,
) -> None:
    outcome = _load(EXAMPLE_DIR / "schedule_generation_outcome.example.json")
    outcome.update(
        {
            "result_status": result_status,
            "execution_status": "NOT_RUN",
            "solver_status": None,
            "solver_adapter": None,
            "solve_duration_seconds": 0,
            "solution": None,
            "diagnostic_candidate": None,
        }
    )
    assert _schema_errors(outcome, "schedule_generation_outcome.schema.json") == []

    invalid = deepcopy(outcome)
    invalid["solver_status"] = "FEASIBLE"
    assert _schema_errors(invalid, "schedule_generation_outcome.schema.json")


def test_rejected_candidate_is_diagnostic_not_authoritative_c() -> None:
    outcome = _load(EXAMPLE_DIR / "schedule_generation_outcome.example.json")
    outcome.update(
        {
            "result_status": "CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR",
            "execution_status": "COMPLETED",
            "solver_status": "FEASIBLE",
            "solver_adapter": "ortools_cp_sat_target_example",
            "solve_duration_seconds": 0.8,
            "solution": None,
            "diagnostic_candidate": {
                "candidate_fingerprint": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                "rejection_codes": ["NEGATIVE_TERMINAL_STOCK"],
                "summary": "The raw candidate violated continuous terminal stock feasibility.",
            },
        }
    )
    assert _schema_errors(outcome, "schedule_generation_outcome.schema.json") == []

    invalid = deepcopy(outcome)
    invalid["diagnostic_candidate"] = None
    assert _schema_errors(invalid, "schedule_generation_outcome.schema.json")


@pytest.mark.parametrize(
    ("result_status", "solver_status"),
    [
        ("C_NOT_FOUND_WITHIN_SOLVE_LIMIT", "UNKNOWN"),
        ("C_NOT_GENERATED_MODEL_INVALID", "MODEL_INVALID"),
    ],
)
def test_unknown_and_model_invalid_have_explicit_non_solution_outcomes(
    result_status: str,
    solver_status: str,
) -> None:
    outcome = _load(EXAMPLE_DIR / "schedule_generation_outcome.example.json")
    outcome.update(
        {
            "result_status": result_status,
            "execution_status": "COMPLETED",
            "solver_status": solver_status,
            "solver_adapter": "ortools_cp_sat_target_example",
            "solve_duration_seconds": 2.0,
            "solution": None,
            "diagnostic_candidate": None,
        }
    )
    assert _schema_errors(outcome, "schedule_generation_outcome.schema.json") == []

    wrong_status = deepcopy(outcome)
    wrong_status["result_status"] = "NO_FEASIBLE_C_WITH_B_PARAMETERS"
    assert _schema_errors(
        wrong_status,
        "schedule_generation_outcome.schema.json",
    )

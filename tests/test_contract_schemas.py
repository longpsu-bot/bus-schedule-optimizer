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
                before
                + event["arriving_or_ready_vehicle_count"]
                - event["departure_count"]
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
def test_approved_active_fleet_may_be_omitted_or_null(
    schema_name: str, example_name: str
) -> None:
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
    assert _problem_domain_errors(problem) == [
        "terminal_1 minimum initial fleet exceeds maximum"
    ]


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
    assert "minimum_required_fleet exceeds available_fleet_limit" in _solution_domain_errors(
        solution
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

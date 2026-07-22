from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, 1)


def harden_validation() -> None:
    path = Path("src/bus_schedule_engine/contracts_v1/solver_validation.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "from dataclasses import asdict, replace\n",
        "from dataclasses import replace\n",
        1,
    )
    if "from .solver_fingerprints import" not in text:
        text = replace_once(
            text,
            "from .serialization import canonical_sha256\n",
            "from .serialization import canonical_sha256\n"
            "from .solver_fingerprints import candidate_fingerprint, solution_fingerprint_payload\n",
            "solver fingerprint import anchor",
        )
    text = text.replace(
        "from .solver_problem import jsonable, legacy_direction\n",
        "from .solver_problem import legacy_direction\n",
        1,
    )

    helper_start = text.find("\ndef _solution_fingerprint_payload(")
    if helper_start >= 0:
        helper_end = text.find("\ndef _source_lock_errors(", helper_start)
        if helper_end < 0:
            raise SystemExit("solution fingerprint helper end not found")
        text = text[:helper_start] + text[helper_end:]

    mapping_anchor = (
        '    if set(source_ids) != set(expected_source_ids):\n'
        '        rejection_codes.append("SOURCE_B_MAPPING_NOT_ONE_TO_ONE")\n'
    )
    if "CANDIDATE_FINGERPRINT_MISMATCH" not in text:
        text = replace_once(
            text,
            mapping_anchor,
            mapping_anchor
            + "    expected_candidate_fingerprint = candidate_fingerprint(\n"
            + "        source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,\n"
            + "        solver_adapter=candidate.solver_adapter,\n"
            + "        exact_timetable=candidate.exact_timetable,\n"
            + "        headway_regimes=candidate.headway_regimes,\n"
            + "    )\n"
            + "    if candidate.candidate_fingerprint != expected_candidate_fingerprint:\n"
            + '        rejection_codes.append("CANDIDATE_FINGERPRINT_MISMATCH")\n',
            "candidate mapping anchor",
        )

    lock_anchor = (
        '        "available_fleet_limit": b.available_fleet_limit,\n'
        '        "operating_day_type": b.operating_day_type.value,\n'
    )
    if '"fleet_constraint_mode"' not in text:
        text = replace_once(
            text,
            lock_anchor,
            '        "available_fleet_limit": b.available_fleet_limit,\n'
            '        "approved_active_fleet": b.approved_active_fleet,\n'
            '        "fleet_constraint_mode": "available_upper_bound",\n'
            '        "initial_fleet_positioning_mode": "solver_determined",\n'
            '        "direction_trip_lock_mode": "fixed_by_direction",\n'
            '        "operating_day_type": b.operating_day_type.value,\n',
            "operating lock anchor",
        )

    if "def _maximum_simultaneous_vehicle_use" not in text:
        validation_anchor = "\ndef validate_and_build_solution_v1(\n"
        helper = (
            "\n\ndef _maximum_simultaneous_vehicle_use(assignments) -> int:\n"
            "    events: list[tuple[int, int]] = []\n"
            "    for assignment in assignments:\n"
            "        events.append((assignment.departure_seconds, 1))\n"
            "        events.append((assignment.ready_seconds, -1))\n"
            "    active = 0\n"
            "    maximum = 0\n"
            "    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):\n"
            "        active += delta\n"
            "        maximum = max(maximum, active)\n"
            "    return maximum\n"
        )
        text = replace_once(
            text,
            validation_anchor,
            helper + validation_anchor,
            "validation function anchor",
        )

    text = text.replace(
        "        maximum_simultaneous_vehicle_use=fleet.minimum_required_fleet,\n",
        "        maximum_simultaneous_vehicle_use=_maximum_simultaneous_vehicle_use(\n"
        "            assignments.assignments\n"
        "        ),\n",
        1,
    )
    text = text.replace(
        "        solution_fingerprint=canonical_sha256(_solution_fingerprint_payload(provisional)),\n",
        "        solution_fingerprint=canonical_sha256(solution_fingerprint_payload(provisional)),\n",
        1,
    )
    if "PR-03 supports available_upper_bound" not in text:
        text = replace_once(
            text,
            "        limitations=candidate.limitations,\n",
            "        limitations=candidate.limitations\n"
            "        + (\n"
            '            "PR-03 supports available_upper_bound fleet constraints and "\n'
            '            "solver_determined initial positioning only.",\n'
            "        ),\n",
            "solution limitations anchor",
        )
    path.write_text(text, encoding="utf-8")


def harden_orchestration() -> None:
    path = Path("src/bus_schedule_engine/contracts_v1/solver_orchestration.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "from dataclasses import asdict, replace\n",
        "from dataclasses import replace\n",
        1,
    )
    if "from .solver_fingerprints import outcome_fingerprint_payload" not in text:
        text = replace_once(
            text,
            "from .serialization import canonical_sha256\n",
            "from .serialization import canonical_sha256\n"
            "from .solver_fingerprints import outcome_fingerprint_payload\n",
            "outcome fingerprint import anchor",
        )
    text = text.replace("from .solver_problem import jsonable\n", "", 1)

    helper_start = text.find("\ndef _outcome_fingerprint_payload(")
    if helper_start >= 0:
        helper_end = text.find("\ndef _finalize_outcome(", helper_start)
        if helper_end < 0:
            raise SystemExit("outcome fingerprint helper end not found")
        text = text[:helper_start] + text[helper_end:]
    text = text.replace(
        "        outcome_fingerprint=canonical_sha256(_outcome_fingerprint_payload(outcome)),\n",
        "        outcome_fingerprint=canonical_sha256(outcome_fingerprint_payload(outcome)),\n",
        1,
    )

    old_invalid = (
        "    if run.execution_status != SolverExecutionStatus.COMPLETED:\n"
        "        return _not_run_outcome(\n"
        "            problem,\n"
        "            GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,\n"
        '            "Solver adapter returned an invalid execution-state combination.",\n'
        "        )\n"
    )
    new_invalid = (
        "    if run.execution_status != SolverExecutionStatus.COMPLETED:\n"
        "        return _completed_without_solution(\n"
        "            problem,\n"
        "            result_status=GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,\n"
        "            solver_status=NativeSolverStatus.MODEL_INVALID,\n"
        "            solver_adapter=run.solver_adapter,\n"
        "            solve_duration_seconds=run.solve_duration_seconds,\n"
        "            explanations=(\n"
        '                "Solver adapter returned an invalid execution-state combination.",\n'
        "            ),\n"
        "            limitations=run.limitations,\n"
        "        )\n"
    )
    if old_invalid in text:
        text = text.replace(old_invalid, new_invalid, 1)

    old_consistency = (
        "    if run.candidate is None or run.candidate.solver_status != run.solver_status:\n"
    )
    if old_consistency in text:
        text = text.replace(
            old_consistency,
            "    if (\n"
            "        run.candidate is None\n"
            "        or run.candidate.solver_status != run.solver_status\n"
            "        or run.candidate.solver_adapter != run.solver_adapter\n"
            "    ):\n",
            1,
        )
    path.write_text(text, encoding="utf-8")


def add_regression_tests() -> None:
    path = Path("tests/test_contract_v1_solver.py")
    text = path.read_text(encoding="utf-8")
    if "test_candidate_fingerprint_tampering_is_rejected" in text:
        return
    text += '''


def test_candidate_fingerprint_tampering_is_rejected() -> None:
    problem, *_ = _problem()
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    tampered = replace(run.candidate, candidate_fingerprint="0" * 64)

    validation = validate_and_build_solution_v1(problem, tampered)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "CANDIDATE_FINGERPRINT_MISMATCH" in validation.rejection_codes


def test_outcome_fingerprint_ignores_solve_duration() -> None:
    problem, *_ = _problem()
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    first = run_schedule_solver_v1(problem, _StaticSolver(run))
    delayed_candidate = replace(
        run.candidate,
        solve_duration_seconds=run.candidate.solve_duration_seconds + 9,
    )
    delayed_run = replace(
        run,
        solve_duration_seconds=run.solve_duration_seconds + 9,
        candidate=delayed_candidate,
    )
    second = run_schedule_solver_v1(problem, _StaticSolver(delayed_run))

    assert first.outcome_fingerprint == second.outcome_fingerprint
    assert first.solution is not None
    assert second.solution is not None
    assert first.solution.solution_fingerprint == second.solution.solution_fingerprint


def test_invalid_execution_state_is_completed_model_invalid_not_not_run() -> None:
    problem, *_ = _problem()
    invalid_run = SolverRunResultV1(
        execution_status=SolverExecutionStatus.NOT_RUN,
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter="invalid_test_adapter",
        solve_duration_seconds=0.1,
        candidate=None,
        explanations=("invalid",),
        limitations=(),
    )

    outcome = run_schedule_solver_v1(problem, _StaticSolver(invalid_run))

    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.MODEL_INVALID
    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID


def test_solution_reports_modes_locks_and_actual_maximum_vehicle_use() -> None:
    problem, *_ = _problem()
    outcome = run_schedule_solver_v1(problem, HeuristicScheduleSolverAdapter())
    assert outcome.solution is not None
    solution = outcome.solution
    lock_fields = {lock.field for lock in solution.operating_parameter_locks}
    assert {
        "fleet_constraint_mode",
        "initial_fleet_positioning_mode",
        "direction_trip_lock_mode",
    } <= lock_fields
    events = []
    for assignment in solution.fleet_assignment:
        events.append((assignment.departure_time, 1))
        events.append((assignment.ready_time, -1))
    active = 0
    maximum = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    assert solution.maximum_simultaneous_vehicle_use == maximum
    assert maximum <= solution.minimum_required_fleet
'''
    path.write_text(text, encoding="utf-8")


harden_validation()
harden_orchestration()
add_regression_tests()
''
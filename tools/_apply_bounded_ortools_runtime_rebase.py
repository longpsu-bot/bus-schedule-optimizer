from pathlib import Path

path = Path("src/bus_schedule_engine/optimization_service.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one occurrence, found {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


replace_once("from dataclasses import dataclass\n", "from dataclasses import dataclass, replace\n")

replace_once(
    "from .optimization_comparison import (\n"
    "    SolverComparisonV1,\n"
    "    compare_solver_outcomes_v1,\n"
    "    comparison_proof_limitations_v1,\n"
    ")\n\n\nclass OptimizationAction(StrEnum):",
    "from .optimization_comparison import (\n"
    "    SolverComparisonV1,\n"
    "    compare_solver_outcomes_v1,\n"
    "    comparison_proof_limitations_v1,\n"
    ")\n\n"
    "DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS = 120.0\n\n\n"
    "class OptimizationAction(StrEnum):",
)

replace_once(
    "_BOTH_SOLVER_BUDGET_LIMITATION = (\n"
    "    \"BOTH applies SolverPolicyV1.time_limit_seconds unchanged as a per-solver \"\n"
    "    \"invocation budget; total wall-clock execution may be up to approximately \"\n"
    "    \"two solver budgets plus application overhead.\"\n"
    ")\n",
    "",
)

replace_once(
    "def _validate_solver_choice(solver_choice: SolverChoice) -> None:\n"
    "    if not isinstance(solver_choice, SolverChoice):\n"
    "        raise TypeError(\"solver_choice must be a SolverChoice\")\n\n\n"
    "def _default_decision_policy(",
    "def _validate_solver_choice(solver_choice: SolverChoice) -> None:\n"
    "    if not isinstance(solver_choice, SolverChoice):\n"
    "        raise TypeError(\"solver_choice must be a SolverChoice\")\n\n\n"
    "def _effective_ortools_solver_policy(\n"
    "    solver_policy: SolverPolicyV1 | None,\n"
    ") -> SolverPolicyV1:\n"
    "    \"\"\"Apply the ordinary-runtime OR budget without changing low-level Contract defaults.\"\"\"\n"
    "    if solver_policy is None:\n"
    "        return SolverPolicyV1(\n"
    "            time_limit_seconds=DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS,\n"
    "        )\n"
    "    if solver_policy.time_limit_seconds is not None:\n"
    "        return solver_policy\n"
    "    return replace(\n"
    "        solver_policy,\n"
    "        time_limit_seconds=DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS,\n"
    "    )\n\n\n"
    "def _both_solver_budget_limitation(ortools_policy: SolverPolicyV1) -> str:\n"
    "    return (\n"
    "        \"BOTH may consume approximately two solver budgets when an explicit policy also bounds \"\n"
    "        \"the heuristic; with the ordinary default, the heuristic keeps its existing bounded \"\n"
    "        f\"search and OR-Tools receives one total staged budget of {ortools_policy.time_limit_seconds:g} \"\n"
    "        \"seconds, plus application overhead.\"\n"
    "    )\n\n\n"
    "def _default_decision_policy(",
)

replace_once(
    "        return _result(\n"
    "            **result_arguments,\n"
    "            solver_attempted=True,\n"
    "            heuristic_outcome=heuristic_outcome,\n"
    "            ortools_outcome=None,\n"
    "            comparison=None,\n"
    "            recommended_outcome=_accepted_outcome(heuristic_outcome),\n"
    "        )\n\n"
    "    if solver_choice == SolverChoice.OR_TOOLS:",
    "        return _result(\n"
    "            **result_arguments,\n"
    "            solver_attempted=True,\n"
    "            heuristic_outcome=heuristic_outcome,\n"
    "            ortools_outcome=None,\n"
    "            comparison=None,\n"
    "            recommended_outcome=_accepted_outcome(heuristic_outcome),\n"
    "        )\n\n"
    "    effective_ortools_policy = _effective_ortools_solver_policy(solver_policy)\n\n"
    "    if solver_choice == SolverChoice.OR_TOOLS:",
)

# The first two OR-Tools quality builder calls after the heuristic branch are the OR_TOOLS and BOTH paths.
needle = (
    "evaluation_policy=effective_evaluation_policy,\n"
    "                solver_policy=solver_policy,\n"
    "                **enforcement_request_arguments,"
)
if text.count(needle) != 2:
    raise SystemExit(f"Expected two OR-Tools solver_policy call sites, found {text.count(needle)}")
text = text.replace(
    needle,
    "evaluation_policy=effective_evaluation_policy,\n"
    "                solver_policy=effective_ortools_policy,\n"
    "                **enforcement_request_arguments,",
    2,
)

replace_once(
    "            _BOTH_SOLVER_BUDGET_LIMITATION,\n"
    "            *comparison_proof_limitations_v1(comparison, ortools_outcome),",
    "            _both_solver_budget_limitation(effective_ortools_policy),\n"
    "            *comparison_proof_limitations_v1(comparison, ortools_outcome),",
)

replace_once(
    "__all__ = [\n    \"BusScheduleOptimizationResult\",",
    "__all__ = [\n    \"DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS\",\n    \"BusScheduleOptimizationResult\",",
)

path.write_text(text, encoding="utf-8")

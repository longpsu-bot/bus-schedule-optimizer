"""Public additive façade for the Contract V1 solver boundary; no runtime cutover."""

from .heuristic_solver import HeuristicScheduleSolverAdapter
from .solver_orchestration import run_schedule_solver_v1
from .solver_problem import ScheduleProblemError, build_schedule_problem_v1
from .solver_validation import validate_and_build_solution_v1

__all__ = [
    "HeuristicScheduleSolverAdapter",
    "ScheduleProblemError",
    "build_schedule_problem_v1",
    "run_schedule_solver_v1",
    "validate_and_build_solution_v1",
]

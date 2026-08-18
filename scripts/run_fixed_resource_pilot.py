from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from bus_schedule_engine.importer import import_workbook
from bus_schedule_engine.input_authority import (
    assess_layered_data_authority_v1,
    normalization_options_from_workbook_v1,
)
from bus_schedule_engine.optimization_service import (
    SolverChoice,
    analyze_and_optimize_schedule_v1,
)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _outcome_summary(outcome: Any) -> dict[str, Any] | None:
    if outcome is None:
        return None
    solution = outcome.solution
    return {
        "result_status": outcome.result_status.value,
        "solver_status": None if outcome.solver_status is None else outcome.solver_status.value,
        "explanations": list(outcome.explanations),
        "limitations": list(outcome.limitations),
        "solution": None if solution is None else _jsonable(solution),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    imported = import_workbook(args.workbook)
    readiness = assess_layered_data_authority_v1(imported)
    options = normalization_options_from_workbook_v1(
        imported,
        source_id=args.source_id,
        imported_at=datetime.now(UTC),
    )
    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.BOTH,
    )
    payload = {
        "source_id": args.source_id,
        "workbook": args.workbook.name,
        "readiness": _jsonable(readiness),
        "selected_action": result.selected_action.value,
        "solver_choice": result.solver_choice.value,
        "solver_attempted": result.solver_attempted,
        "adjustment_assessment": _jsonable(result.adjustment_assessment),
        "heuristic": _outcome_summary(result.heuristic_outcome),
        "ortools": _outcome_summary(result.ortools_outcome),
        "comparison": _jsonable(result.comparison),
        "recommended": _outcome_summary(result.recommended_outcome),
        "explanations": list(result.explanations),
        "limitations": list(result.limitations),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

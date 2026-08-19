from __future__ import annotations

import importlib.util
from pathlib import Path


def test_phase_review_v2_script_imports() -> None:
    path = Path(__file__).parents[1] / "scripts" / "run_v3_two_stage_phase_review_v2.py"
    spec = importlib.util.spec_from_file_location("phase_review_v2", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module._bounded_phase_necessary_feasibility)

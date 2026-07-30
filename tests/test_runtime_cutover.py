from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ordinary_package_import_does_not_load_offline_side_by_side_module() -> None:
    code = (
        "import sys; import bus_schedule_engine; "
        "assert 'bus_schedule_engine.side_by_side_validation' not in sys.modules"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_streamlit_input_helpers_do_not_eagerly_import_legacy_runtime() -> None:
    code = (
        "import sys; import bus_schedule_engine.ui_utils; "
        "blocked = ("
        "'bus_schedule_engine.service', "
        "'bus_schedule_engine.diagram', "
        "'bus_schedule_engine.comparison_exporter'"
        "); "
        "assert all(name not in sys.modules for name in blocked)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_streamlit_pages_have_no_ordinary_legacy_runtime_calls() -> None:
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "app_pages").glob("*.py"))
    }
    combined = "\n".join(sources.values())
    banned = (
        "run_parallel_application_pipeline_v1",
        "run_and_build_artifacts",
        "build_side_by_side_validation_report_v1",
        "run_side_by_side_validation_v1",
        "build_comparison_diagram",
        "build_departure_detail_diagram",
        "supply_summary_frame",
        "validation_frame",
        "demand_frame",
        "recommendation_frame",
        "assign_fleet",
    )
    assert all(name not in combined for name in banned)
    assert "run_unified_application_pipeline_v1" in sources["01_nhap_du_lieu.py"]


def test_streamlit_session_initialization_only_retains_unified_result_state() -> None:
    source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    legacy_keys = (
        "analysis_bundle",
        "diagram_figure",
        "download_artifacts",
        "scenario_c_fingerprint",
        "parallel_runtime_status",
        "side_by_side_validation_report",
    )
    for key in legacy_keys:
        assert f'"{key}",' in source
        assert f'"{key}": None' not in source
    assert "st.session_state.pop(legacy_key, None)" in source
    assert '"unified_runtime_status": None' in source

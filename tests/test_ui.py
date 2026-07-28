from hashlib import sha256
from pathlib import Path

from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from bus_schedule_engine.application_pipeline import ParallelRuntimeStatusV1
from bus_schedule_engine.diagram import build_comparison_diagram
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import import_workbook
from bus_schedule_engine.service import run_analysis
from bus_schedule_engine.ui_utils import scenario_frame


def test_streamlit_default_page_starts_without_exception() -> None:
    app = AppTest.from_file("streamlit_app.py")
    app.run(timeout=30)
    assert not app.exception
    assert len(app.file_uploader) == 1


def test_input_page_accepts_inclusive_runtime_range(tmp_path) -> None:
    content = create_input_template(tmp_path / "input.xlsx").read_bytes()
    app = AppTest.from_file("app_pages/01_nhap_du_lieu.py")
    app.session_state["input_bytes"] = content

    app.run(timeout=30)

    assert not app.exception
    runtime_input = next(
        item
        for item in app.text_input
        if item.label == "Khoảng thời gian hành trình cho phép (phút)"
    )
    runtime_input.set_value("45,65")
    submit = next(item for item in app.button if item.label == "Chạy kiểm tra và sinh phương án")
    submit.click().run(timeout=60)

    assert not app.exception
    assert app.session_state["imported_workbook"].parameters_b.runtime_options == (45, 65)
    assert (
        app.session_state["parallel_runtime_status"]
        == ParallelRuntimeStatusV1.PARALLEL_VALIDATION_COMPLETE
    )
    assert app.session_state["workbook_input_readiness"].optimization_ready is True
    assert app.session_state["analysis_bundle"] is not None
    assert app.session_state["diagram_figure"] is not None
    assert app.session_state["download_artifacts"] is not None
    assert app.session_state["unified_optimization_result"] is not None
    assert app.session_state["side_by_side_validation_report"] is not None
    assert app.session_state["unified_presentation"].source_id == (
        f"streamlit-upload-sha256:{sha256(content).hexdigest()}"
    )
    assert app.session_state["unified_demand_supply_figure"] is not None
    assert app.session_state["unified_departure_figure"] is not None
    assert set(app.session_state["unified_download_artifacts"]) == {
        "xlsx",
        "presentation_fingerprint",
        "b_fingerprint",
        "accepted_solution_fingerprint",
    }
    assert app.session_state["unified_runtime_failure"] is None


def test_new_upload_clears_previous_legacy_and_unified_state(tmp_path) -> None:
    first = create_input_template(tmp_path / "first.xlsx").read_bytes()
    second_path = create_input_template(tmp_path / "second.xlsx")
    workbook = load_workbook(second_path)
    sheet = workbook["THONG_SO_B"]
    row = next(cell.row for cell in sheet["A"] if cell.value == "route_name")
    sheet.cell(row, 2).value = "Replacement upload"
    workbook.save(second_path)
    workbook.close()
    second = second_path.read_bytes()
    assert first != second

    app = AppTest.from_file("app_pages/01_nhap_du_lieu.py")
    app.session_state["input_bytes"] = first
    state_keys = (
        "imported_workbook",
        "analysis_bundle",
        "diagram_figure",
        "download_artifacts",
        "scenario_c_fingerprint",
        "parallel_runtime_status",
        "workbook_input_readiness",
        "unified_optimization_result",
        "side_by_side_validation_report",
        "unified_presentation",
        "unified_demand_supply_figure",
        "unified_departure_figure",
        "unified_download_artifacts",
        "unified_runtime_failure",
    )
    for key in state_keys:
        app.session_state[key] = object()
    app.run(timeout=30)
    assert not app.exception

    app.file_uploader[0].upload(
        "replacement.xlsx",
        second,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ).run(timeout=30)

    assert not app.exception
    assert app.session_state["input_bytes"] == second
    assert all(app.session_state[key] is None for key in state_keys)


def test_recommendation_page_remains_legacy_authoritative(tmp_path) -> None:
    bundle = run_analysis(import_workbook(create_input_template(tmp_path / "input.xlsx")))
    app = AppTest.from_file("app_pages/04_khuyen_nghi.py")
    app.session_state["analysis_bundle"] = bundle
    app.session_state["unified_presentation"] = object()
    app.session_state["unified_demand_supply_figure"] = object()
    app.session_state["unified_departure_figure"] = object()

    app.run(timeout=30)

    assert not app.exception
    assert len(app.dataframe) == 2
    assert app.dataframe[0].value.equals(scenario_frame(bundle))
    assert len(app.get("plotly_chart")) == 0


def test_export_page_shows_supply_summary_and_direction_selector(tmp_path) -> None:
    bundle = run_analysis(import_workbook(create_input_template(tmp_path / "input.xlsx")))
    app = AppTest.from_file("app_pages/05_xuat_file.py")
    app.session_state["analysis_bundle"] = bundle
    app.session_state["diagram_figure"] = build_comparison_diagram(bundle)
    app.session_state["download_artifacts"] = {
        "comparison_xlsx": b"xlsx",
        "xlsx": b"xlsx",
        "png": b"png",
        "html": b"html",
    }
    app.session_state["unified_presentation"] = object()
    app.session_state["unified_demand_supply_figure"] = object()
    app.session_state["unified_departure_figure"] = object()
    app.session_state["unified_download_artifacts"] = {
        "xlsx": b"unified-xlsx",
    }

    app.run(timeout=30)

    assert not app.exception
    assert len(app.dataframe) == 1
    assert list(app.dataframe[0].value.columns) == [
        "Phương án",
        "Tổng chuyến",
        "Xe hoạt động",
        "LF cao nhất",
        "Block đạt 85%",
        "Block 85–90%",
        "Block >90%",
    ]
    assert len(app.segmented_control) == 1
    assert app.segmented_control[0].value == "combined"
    assert len(app.get("plotly_chart")) == 2
    assert len(app.expander) == 1
    assert app.expander[0].label == "Chi tiết giờ xuất bến"
    downloads = app.get("download_button")
    assert [download.label for download in downloads] == [
        "Tải bảng so sánh B và C (.xlsx)",
        "Workbook kết quả",
        "Diagram PNG",
        "Diagram HTML tương tác",
    ]
    page_source = Path("app_pages/05_xuat_file.py").read_text(encoding="utf-8")
    for filename in (
        "so_sanh_B_C_tai_phan_bo_on_dinh.xlsx",
        "Bus_Schedule_MVP_Output.xlsx",
        "Bus_Schedule_Comparison.png",
        "Bus_Schedule_Comparison.html",
    ):
        assert f'file_name="{filename}"' in page_source
    assert "Bus_Schedule_Contract_V1_Validation.xlsx" not in page_source

    app.segmented_control[0].set_value("terminal_1_to_2").run(timeout=30)
    assert not app.exception
    assert app.segmented_control[0].value == "terminal_1_to_2"
    assert len(app.get("plotly_chart")) == 2

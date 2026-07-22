from streamlit.testing.v1 import AppTest

from bus_schedule_engine.diagram import build_comparison_diagram
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import import_workbook
from bus_schedule_engine.service import run_analysis


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

    app.segmented_control[0].set_value("terminal_1_to_2").run(timeout=30)
    assert not app.exception
    assert app.segmented_control[0].value == "terminal_1_to_2"
    assert len(app.get("plotly_chart")) == 2

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from openpyxl import load_workbook
from presentation_support import (
    build_corpus_result_and_report,
    build_result_and_report,
    rejected_result_and_report,
)
from streamlit.testing.v1 import AppTest

from bus_schedule_engine.application_pipeline import ParallelRuntimeStatusV1
from bus_schedule_engine.diagram import build_comparison_diagram
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import import_workbook
from bus_schedule_engine.input_authority import WorkbookInputReadinessV1
from bus_schedule_engine.service import run_analysis
from bus_schedule_engine.ui_result_authority import UNIFIED_VISIBLE_STATE_INCOMPLETE
from bus_schedule_engine.ui_utils import block_frame, scenario_frame, validation_frame
from bus_schedule_engine.unified_diagram import (
    build_unified_demand_supply_figure_v1,
    build_unified_departure_figure_v1,
)
from bus_schedule_engine.unified_presentation import build_unified_presentation_v1
from bus_schedule_engine.unified_ui_frames import demand_block_rows_v1


def _ready() -> WorkbookInputReadinessV1:
    return WorkbookInputReadinessV1(
        import_ready=True,
        optimization_ready=True,
        blocking_import_codes=(),
        missing_optimization_authority_codes=(),
        optional_limitations=(),
    )


def _unified_page_state(pair=None) -> dict[str, object]:
    result, report = pair or build_result_and_report()
    presentation = build_unified_presentation_v1(result, report)
    return {
        "analysis_bundle": object(),
        "parallel_runtime_status": ParallelRuntimeStatusV1.PARALLEL_VALIDATION_COMPLETE,
        "workbook_input_readiness": _ready(),
        "unified_optimization_result": result,
        "side_by_side_validation_report": report,
        "unified_presentation": presentation,
        "unified_demand_supply_figure": build_unified_demand_supply_figure_v1(presentation),
        "unified_departure_figure": build_unified_departure_figure_v1(presentation),
        "unified_download_artifacts": {
            "xlsx": b"unified-xlsx",
            "presentation_fingerprint": presentation.presentation_fingerprint,
            "b_fingerprint": presentation.source_b_fingerprint,
            "accepted_solution_fingerprint": presentation.accepted_solution_fingerprint,
        },
        "unified_runtime_failure": None,
    }


def _seed_page(app: AppTest, state: dict[str, object]) -> AppTest:
    for key, value in state.items():
        app.session_state[key] = value
    return app


def _dataframe_with_columns(app: AppTest, required: set[str]):
    return next(item for item in app.dataframe if required.issubset(set(item.value.columns)))


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


def test_page02_uses_only_unified_facts_when_authority_gate_passes() -> None:
    state = _unified_page_state()
    presentation = state["unified_presentation"]
    app = _seed_page(AppTest.from_file("app_pages/02_kiem_tra.py"), state)

    app.run(timeout=30)

    assert not app.exception
    assert app.info[0].value.startswith("Nguồn kết quả hiển thị: Contract V1.")
    frame = _dataframe_with_columns(
        app,
        {
            "Nhóm đánh giá",
            "Trạng thái",
            "Độ tin cậy",
            "Mức độ",
            "Mã",
            "Nội dung",
            "Giải thích",
            "Bằng chứng",
        },
    )
    assert set(frame.value["Trạng thái"]) == {
        dimension.status
        for dimension in presentation.dimensions
        if dimension.dimension_name != "demand_suitability"
    }
    assert any(metric.label == "Khả thi kỹ thuật" for metric in app.metric)
    assert any("DISPLAY_DERIVED" in metric.label for metric in app.metric)
    assert presentation.expert_review_required_codes
    assert all(code in app.warning[0].value for code in presentation.expert_review_required_codes)


def test_page03_shows_exact_unified_block_rows() -> None:
    state = _unified_page_state()
    presentation = state["unified_presentation"]
    expected_rows = demand_block_rows_v1(presentation)
    app = _seed_page(AppTest.from_file("app_pages/03_nhu_cau.py"), state)

    app.run(timeout=30)

    assert not app.exception
    frame = _dataframe_with_columns(
        app,
        {"Mã block", "Khung thời gian", "Chiều", "Chuyến B", "Hệ số tải B"},
    )
    assert frame.value.to_dict("records") == list(expected_rows)
    assert len(app.segmented_control) == 0


def test_page03_no_accepted_c_leaves_c_blank_and_preserves_alpha_review() -> None:
    state = _unified_page_state(build_corpus_result_and_report("corpus_alpha_80.json"))
    presentation = state["unified_presentation"]
    app = _seed_page(AppTest.from_file("app_pages/03_nhu_cau.py"), state)

    app.run(timeout=30)

    assert not app.exception
    frame = _dataframe_with_columns(
        app,
        {"Chuyến B", "Chuyến C được chấp nhận", "Hệ số tải B", "Hệ số tải C"},
    )
    assert frame.value["Chuyến B"].notna().any()
    assert frame.value["Chuyến C được chấp nhận"].isna().all()
    assert frame.value["Hệ số tải C"].isna().all()
    assert any("không dùng B thay thế C" in warning.value for warning in app.warning)
    assert "LEGACY_C_WITHOUT_UNIFIED_AUTHORITY" in (presentation.expert_review_required_codes)


def test_page03_preserves_combined_demand_without_fabricated_direction() -> None:
    state = _unified_page_state(build_result_and_report(combined_demand=True))
    app = _seed_page(AppTest.from_file("app_pages/03_nhu_cau.py"), state)

    app.run(timeout=30)

    assert not app.exception
    frame = _dataframe_with_columns(app, {"Mã block", "Chiều", "Nhu cầu hành khách"})
    assert set(frame.value["Chiều"]) == {"Tổng hợp hai chiều"}


def test_page03_beta_shows_exact_outbound_1700_1800_gap() -> None:
    state = _unified_page_state(build_corpus_result_and_report("corpus_beta_46.json"))
    app = _seed_page(AppTest.from_file("app_pages/03_nhu_cau.py"), state)

    app.run(timeout=30)

    assert not app.exception
    gap_frame = _dataframe_with_columns(
        app,
        {"Mã khoảng trống", "Chiều", "Khung thời gian"},
    )
    assert gap_frame.value["Khung thời gian"].tolist() == ["17:00–18:00"]
    assert gap_frame.value["Chiều"].str.contains("→").all()
    block_frame_value = _dataframe_with_columns(app, {"Mã block", "Chuyến B"})
    assert block_frame_value.value["Chuyến C được chấp nhận"].isna().all()


def test_page04_shows_unified_accepted_c_without_legacy_weighted_score() -> None:
    state = _unified_page_state()
    presentation = state["unified_presentation"]
    app = _seed_page(AppTest.from_file("app_pages/04_khuyen_nghi.py"), state)

    app.run(timeout=30)

    assert not app.exception
    outcome_frame = _dataframe_with_columns(app, {"Nội dung", "Giá trị"})
    labels = outcome_frame.value["Nội dung"].tolist()
    assert "Định đoạt phương án B" in labels
    assert "Hành động được chọn" in labels
    assert "Mã từ chối của validator" in labels
    assert all("Điểm" not in label and "weighted" not in label.lower() for label in labels)
    regime_frame_value = _dataframe_with_columns(
        app,
        {"Mã chế độ", "Chuỗi giãn cách thực tế", "Giãn cách ngoại lệ"},
    )
    assert len(regime_frame_value.value) == len(presentation.headway_regimes)
    assert any("DISPLAY_DERIVED" in metric.label for metric in app.metric)
    assert app.code[0].value == presentation.accepted_solution_fingerprint


def test_page04_no_accepted_c_shows_outcome_without_c_timetable() -> None:
    state = _unified_page_state(build_corpus_result_and_report("corpus_alpha_80.json"))
    app = _seed_page(AppTest.from_file("app_pages/04_khuyen_nghi.py"), state)

    app.run(timeout=30)

    assert not app.exception
    assert any(
        "Không tồn tại phương án C có thẩm quyền" in warning.value for warning in app.warning
    )
    assert not any(
        {"Mã chế độ", "Chuỗi giãn cách thực tế"}.issubset(item.value.columns)
        for item in app.dataframe
    )
    assert len(app.code) == 0


def test_page04_rejected_candidate_shows_code_without_raw_candidate() -> None:
    state = _unified_page_state(rejected_result_and_report())
    app = _seed_page(AppTest.from_file("app_pages/04_khuyen_nghi.py"), state)

    app.run(timeout=30)

    assert not app.exception
    assert any("SYNTHETIC_DOMAIN_REJECTION" in error.value for error in app.error)
    rendered = " ".join(
        str(item.value)
        for collection in (app.info, app.warning, app.error, app.markdown)
        for item in collection
    )
    assert "rejected-diagnostic-candidate" not in rendered
    assert len(app.code) == 0


def test_input_not_ready_banner_preserves_codes_and_legacy_page03_behavior(
    tmp_path,
) -> None:
    bundle = run_analysis(import_workbook(create_input_template(tmp_path / "input.xlsx")))
    codes = ("AVAILABLE_FLEET_LIMIT_REQUIRED", "DEMAND_CONFIDENCE_REQUIRED")
    state = {
        "analysis_bundle": bundle,
        "parallel_runtime_status": ParallelRuntimeStatusV1.INPUT_NOT_READY,
        "workbook_input_readiness": WorkbookInputReadinessV1(
            import_ready=True,
            optimization_ready=False,
            blocking_import_codes=(),
            missing_optimization_authority_codes=codes,
            optional_limitations=(),
        ),
    }
    app = _seed_page(AppTest.from_file("app_pages/03_nhu_cau.py"), state)

    app.run(timeout=30)

    assert not app.exception
    assert app.warning[0].value.startswith("Nguồn kết quả hiển thị: pipeline legacy.")
    assert all(code in app.warning[0].value for code in codes)
    assert len(app.segmented_control) == 1
    legacy_frame = _dataframe_with_columns(app, {"Khung thời gian", "Hệ số tải"})
    assert legacy_frame.value.equals(block_frame(bundle, "B"))


def test_unified_failure_banner_shows_stable_failure_and_legacy_page02(
    tmp_path,
) -> None:
    bundle = run_analysis(import_workbook(create_input_template(tmp_path / "input.xlsx")))
    state = {
        "analysis_bundle": bundle,
        "parallel_runtime_status": ParallelRuntimeStatusV1.UNIFIED_RUNTIME_FAILED,
        "unified_runtime_failure": {
            "code": "UNIFIED_TEST_FAILURE",
            "message": "Synthetic concise failure.",
        },
    }
    app = _seed_page(AppTest.from_file("app_pages/02_kiem_tra.py"), state)

    app.run(timeout=30)

    assert not app.exception
    assert "UNIFIED_TEST_FAILURE" in app.warning[0].value
    assert "Synthetic concise failure." in app.warning[0].value
    expected = validation_frame(bundle)
    if expected.empty:
        assert "Không phát hiện lỗi kỹ thuật." in app.dataframe[0].value["Nội dung"].tolist()
    else:
        assert app.dataframe[0].value.equals(expected)


def test_blocking_code_forces_legacy_page04(tmp_path) -> None:
    state = _unified_page_state()
    state["analysis_bundle"] = run_analysis(
        import_workbook(create_input_template(tmp_path / "input.xlsx"))
    )
    state["side_by_side_validation_report"] = replace(
        state["side_by_side_validation_report"],
        blocking_discrepancy_codes=("BLOCKING_VISIBLE_TEST",),
    )
    app = _seed_page(AppTest.from_file("app_pages/04_khuyen_nghi.py"), state)

    app.run(timeout=30)

    assert not app.exception
    assert "BLOCKING_VISIBLE_TEST" in app.warning[0].value
    assert app.warning[0].value.startswith("Nguồn kết quả hiển thị: pipeline legacy.")
    assert app.dataframe[0].value.equals(scenario_frame(state["analysis_bundle"]))


def test_incomplete_shadow_state_falls_back_without_page_exception(tmp_path) -> None:
    state = _unified_page_state()
    bundle = run_analysis(import_workbook(create_input_template(tmp_path / "input.xlsx")))
    state["analysis_bundle"] = bundle
    state["unified_departure_figure"] = None
    app = _seed_page(AppTest.from_file("app_pages/03_nhu_cau.py"), state)

    app.run(timeout=30)

    assert not app.exception
    assert UNIFIED_VISIBLE_STATE_INCOMPLETE in app.warning[0].value
    assert len(app.segmented_control) == 1


@pytest.mark.parametrize(
    "page_path",
    (
        "app_pages/02_kiem_tra.py",
        "app_pages/03_nhu_cau.py",
        "app_pages/04_khuyen_nghi.py",
    ),
)
def test_each_cutover_page_displays_consistent_unified_authority_banner(
    page_path,
) -> None:
    app = _seed_page(AppTest.from_file(page_path), _unified_page_state())

    app.run(timeout=30)

    assert not app.exception
    assert app.info[0].value == (
        "Nguồn kết quả hiển thị: Contract V1.\n\n"
        "Kết quả hỗ trợ chuyên gia và không tự động thay thế quyết định khai thác."
    )


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

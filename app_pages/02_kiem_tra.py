import streamlit as st

from bus_schedule_engine.ui_result_authority import (
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.ui_utils import validation_frame
from bus_schedule_engine.unified_ui_frames import (
    technical_dimension_rows_v1,
    technical_summary_v1,
)

bundle = st.session_state.get("analysis_bundle")
visible = resolve_visible_result_context_v1(
    legacy_bundle=bundle,
    parallel_runtime_status=st.session_state.get("parallel_runtime_status"),
    input_readiness=st.session_state.get("workbook_input_readiness"),
    unified_result=st.session_state.get("unified_optimization_result"),
    report=st.session_state.get("side_by_side_validation_report"),
    presentation=st.session_state.get("unified_presentation"),
    unified_demand_supply_figure=st.session_state.get("unified_demand_supply_figure"),
    unified_departure_figure=st.session_state.get("unified_departure_figure"),
    unified_download_artifacts=st.session_state.get("unified_download_artifacts"),
    unified_runtime_failure=st.session_state.get("unified_runtime_failure"),
)

if visible.mode == VisibleResultModeV1.NO_RESULT:
    st.warning(visible.banner_message)
    st.stop()

if visible.uses_unified:
    st.info(visible.banner_message, icon=":material/info:")
    presentation = visible.presentation
    assert presentation is not None
    if presentation.requires_expert_review:
        review_codes = "\n".join(f"- {code}" for code in presentation.expert_review_required_codes)
        st.warning(
            "Contract V1 yêu cầu chuyên gia rà soát; đây không phải phê duyệt khai thác.\n\n"
            f"{review_codes}",
            icon=":material/rate_review:",
        )

    summary = technical_summary_v1(presentation)
    with st.container(horizontal=True):
        st.metric("Khả thi kỹ thuật", summary["technical_feasibility_status"], border=True)
        st.metric("Khả thi đội xe", summary["fleet_feasibility_status"], border=True)
        st.metric("Chất lượng giãn cách", summary["headway_quality_status"], border=True)
        st.metric(
            "Tổng vấn đề (DISPLAY_DERIVED)",
            summary["total_issue_count"],
            border=True,
        )
        st.metric("Độ tin cậy kỹ thuật", summary["technical_confidence"], border=True)

    st.subheader("Đánh giá kỹ thuật Contract V1")
    st.dataframe(technical_dimension_rows_v1(presentation), hide_index=True)
else:
    st.warning(visible.banner_message, icon=":material/warning:")

    result = bundle.get("B")
    issues = validation_frame(bundle)
    blocking = 0 if issues.empty else issues["Mức độ"].isin(["BLOCKING", "ERROR"]).sum()
    cols = st.columns(3)
    cols[0].metric("Kết quả phương án B", result.validation.status)
    cols[1].metric("Tổng lỗi/cảnh báo", len(issues))
    cols[2].metric("Lỗi chặn phương án", int(blocking))

    if result.validation.passed:
        st.success(
            "Phương án B đạt các ràng buộc kỹ thuật bắt buộc.",
            icon=":material/check_circle:",
        )
    else:
        st.error(
            "Phương án B không được coi là khả thi; điểm không được tính để che lỗi kỹ thuật.",
            icon=":material/block:",
        )

    st.subheader("Danh sách lỗi và đề xuất sửa")
    if issues.empty:
        st.dataframe(
            [{"Mức độ": "INFO", "Nội dung": "Không phát hiện lỗi kỹ thuật."}],
            hide_index=True,
        )
    else:
        st.dataframe(issues, hide_index=True)

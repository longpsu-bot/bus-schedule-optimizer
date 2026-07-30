import streamlit as st

from bus_schedule_engine.ui_result_authority import (
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.unified_ui_frames import (
    technical_dimension_rows_v1,
    technical_summary_v1,
)

visible = resolve_visible_result_context_v1(
    runtime_status=st.session_state.get("unified_runtime_status"),
    input_readiness=st.session_state.get("workbook_input_readiness"),
    unified_result=st.session_state.get("unified_optimization_result"),
    presentation=st.session_state.get("unified_presentation"),
    unified_demand_supply_figure=st.session_state.get("unified_demand_supply_figure"),
    unified_departure_figure=st.session_state.get("unified_departure_figure"),
    unified_download_artifacts=st.session_state.get("unified_download_artifacts"),
    unified_runtime_failure=st.session_state.get("unified_runtime_failure"),
)

if visible.mode == VisibleResultModeV1.NO_RESULT:
    st.warning(visible.banner_message)
    st.stop()

if not visible.uses_unified:
    if visible.banner_level == "error":
        st.error(visible.banner_message, icon=":material/error:")
    else:
        st.warning(visible.banner_message, icon=":material/warning:")
    st.stop()

if visible.mode == VisibleResultModeV1.UNIFIED_ARTIFACT_FAILED:
    st.warning(visible.banner_message, icon=":material/warning:")
else:
    st.info(visible.banner_message, icon=":material/info:")

if visible.uses_unified:
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

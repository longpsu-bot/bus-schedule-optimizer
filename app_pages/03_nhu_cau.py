import streamlit as st

from bus_schedule_engine.ui_result_authority import (
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.unified_ui_frames import (
    demand_block_rows_v1,
    demand_gap_rows_v1,
    demand_summary_v1,
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

    summary = demand_summary_v1(presentation)
    maximum_b = summary["maximum_b_load_factor"]
    maximum_c = summary["maximum_c_load_factor"]
    with st.container(horizontal=True):
        st.metric("Mức phù hợp nhu cầu", summary["demand_suitability_status"], border=True)
        st.metric("Độ tin cậy nhu cầu", summary["demand_confidence"], border=True)
        st.metric(
            "Khoảng trống nhu cầu (DISPLAY_DERIVED)",
            summary["demand_gap_count"],
            border=True,
        )
        st.metric(
            "Hệ số tải B cao nhất (DISPLAY_DERIVED)",
            "—" if maximum_b is None else f"{maximum_b:.1%}",
            border=True,
        )
        st.metric(
            "Hệ số tải C cao nhất (DISPLAY_DERIVED)",
            "—" if maximum_c is None else f"{maximum_c:.1%}",
            border=True,
        )

    gaps = demand_gap_rows_v1(presentation)
    if gaps:
        st.subheader("Khoảng trống nhu cầu được Contract V1 trả về")
        st.dataframe(gaps, hide_index=True)

    if not presentation.outcome.accepted_c_exists:
        st.warning(
            "Không tồn tại phương án C có thẩm quyền trong kết quả Contract V1. "
            "Bảng giữ các cột C trống và không dùng B thay thế C.",
            icon=":material/info:",
        )
        st.write(f"Hành động được chọn: `{presentation.outcome.selected_action}`")
        for explanation in presentation.outcome.explanations:
            st.write(f"- {explanation}")
        for limitation in presentation.outcome.limitations:
            st.warning(limitation, icon=":material/warning:")

    st.subheader("Nhu cầu và cung theo đúng grain block Contract V1")
    st.caption(
        "Các số đếm và cực đại được gắn nhãn DISPLAY_DERIVED; không có nội suy, "
        "gộp block hoặc phân bổ nhu cầu theo chiều."
    )
    st.dataframe(
        demand_block_rows_v1(presentation),
        hide_index=True,
        column_config={
            "Hệ số tải B": st.column_config.NumberColumn(format="percent"),
            "Hệ số tải C": st.column_config.NumberColumn(format="percent"),
        },
    )

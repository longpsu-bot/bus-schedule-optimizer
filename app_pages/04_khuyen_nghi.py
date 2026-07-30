import streamlit as st

from bus_schedule_engine.ui_result_authority import (
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.unified_ui_frames import (
    accepted_c_summary_v1,
    headway_regime_rows_v1,
    outcome_rows_v1,
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

    st.subheader("Kết quả khuyến nghị Contract V1")
    st.dataframe(outcome_rows_v1(presentation), hide_index=True)

    accepted_summary = accepted_c_summary_v1(presentation)
    rejection_codes = presentation.outcome.validator_rejection_codes
    if rejection_codes:
        code_text = "\n".join(f"- {code}" for code in rejection_codes)
        if accepted_summary is None:
            st.error(
                "Ứng viên đã bị validator từ chối; không hiển thị dữ liệu ứng viên thô.\n\n"
                f"{code_text}",
                icon=":material/block:",
            )
        else:
            st.warning(
                "Một hoặc nhiều ứng viên solver khác đã bị validator từ chối.\n\n"
                "Các mã dưới đây được giữ lại làm bằng chứng chẩn đoán; phương án C "
                "hiển thị bên dưới là nghiệm riêng biệt đã được validator chấp nhận.\n\n"
                f"{code_text}",
                icon=":material/rate_review:",
            )

    if accepted_summary is None:
        st.warning(
            "Không tồn tại phương án C có thẩm quyền trong kết quả Contract V1. "
            "Không hiển thị lịch C và không dùng phương án B thay thế.",
            icon=":material/info:",
        )
        st.write(f"Hành động được chọn: `{presentation.outcome.selected_action}`")
        st.write(
            "Trạng thái solver: "
            f"heuristic=`{presentation.outcome.heuristic_result_status}`, "
            f"OR-Tools=`{presentation.outcome.ortools_result_status}`."
        )
    else:
        st.success(
            "Phương án C hiển thị bên dưới là nghiệm Contract V1 đã được validator độc lập "
            "chấp nhận; đây vẫn không phải phê duyệt khai thác.",
            icon=":material/check_circle:",
        )
        with st.container(horizontal=True):
            st.metric(
                "Chuyến B / C (DISPLAY_DERIVED)",
                f"{accepted_summary['b_trip_count']} / {accepted_summary['accepted_c_trip_count']}",
                border=True,
            )
            st.metric(
                "Chuyến C dịch chuyển (DISPLAY_DERIVED)",
                accepted_summary["shifted_c_trip_count"],
                border=True,
            )
            st.metric(
                "Đội xe tối thiểu / giới hạn",
                f"{accepted_summary['minimum_required_fleet']} / "
                f"{accepted_summary['available_fleet_limit']}",
                border=True,
            )
            st.metric("Biên đội xe", accepted_summary["fleet_margin"], border=True)
        with st.container(horizontal=True):
            st.metric(
                f"Xe ban đầu tại {presentation.terminal_1_name}",
                accepted_summary["terminal_1_vehicle_count"],
                border=True,
            )
            st.metric(
                f"Xe ban đầu tại {presentation.terminal_2_name}",
                accepted_summary["terminal_2_vehicle_count"],
                border=True,
            )
            maximum_b = accepted_summary["maximum_b_load_factor"]
            maximum_c = accepted_summary["maximum_c_load_factor"]
            st.metric(
                "Hệ số tải B / C cao nhất (DISPLAY_DERIVED)",
                f"{'—' if maximum_b is None else f'{maximum_b:.1%}'} / "
                f"{'—' if maximum_c is None else f'{maximum_c:.1%}'}",
                border=True,
            )
        with st.container(horizontal=True):
            st.metric(
                "Block cảnh báo B / C (DISPLAY_DERIVED)",
                f"{accepted_summary['b_warning_block_count']} / "
                f"{accepted_summary['c_warning_block_count']}",
                border=True,
            )
            st.metric(
                "Block nghiêm trọng B / C (DISPLAY_DERIVED)",
                f"{accepted_summary['b_critical_block_count']} / "
                f"{accepted_summary['c_critical_block_count']}",
                border=True,
            )
            st.metric(
                "Chế độ giãn cách (DISPLAY_DERIVED)",
                accepted_summary["headway_regime_count"],
                border=True,
            )
            st.metric(
                "Giãn cách ngoại lệ (DISPLAY_DERIVED)",
                accepted_summary["exceptional_headway_count"],
                border=True,
            )

        st.subheader("Chế độ giãn cách của phương án C được chấp nhận")
        st.dataframe(headway_regime_rows_v1(presentation), hide_index=True)
        st.write("Fingerprint nghiệm C được chấp nhận:")
        st.code(accepted_summary["accepted_solution_fingerprint"])

    if presentation.outcome.explanations:
        st.subheader("Giải thích kết quả")
        for explanation in presentation.outcome.explanations:
            st.write(f"- {explanation}")
    if presentation.outcome.limitations:
        st.subheader("Giới hạn")
        for limitation in presentation.outcome.limitations:
            st.warning(limitation, icon=":material/warning:")

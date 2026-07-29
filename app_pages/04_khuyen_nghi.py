import streamlit as st

from bus_schedule_engine.ui_result_authority import (
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.ui_utils import regime_frame, scenario_frame
from bus_schedule_engine.unified_ui_frames import (
    accepted_c_summary_v1,
    expert_review_discrepancy_rows_v1,
    headway_regime_rows_v1,
    outcome_rows_v1,
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
        with st.expander("Bằng chứng đối chiếu cần chuyên gia rà soát"):
            review_rows = expert_review_discrepancy_rows_v1(presentation)
            if review_rows:
                st.dataframe(review_rows, hide_index=True)
            else:
                st.write("Không có dòng sai lệch tương ứng được trả về.")

    st.subheader("Kết quả khuyến nghị Contract V1")
    st.dataframe(outcome_rows_v1(presentation), hide_index=True)

    rejection_codes = presentation.outcome.validator_rejection_codes
    if rejection_codes:
        st.error(
            "Ứng viên đã bị validator từ chối; không hiển thị dữ liệu ứng viên thô:\n\n"
            + "\n".join(f"- {code}" for code in rejection_codes),
            icon=":material/block:",
        )

    accepted_summary = accepted_c_summary_v1(presentation)
    if accepted_summary is None:
        st.warning(
            "Không tồn tại phương án C có thẩm quyền trong kết quả Contract V1. "
            "Không hiển thị lịch C và không dùng phương án B hoặc C legacy thay thế.",
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
else:
    st.warning(visible.banner_message, icon=":material/warning:")

    st.dataframe(
        scenario_frame(bundle),
        hide_index=True,
        column_config={
            "Điểm": st.column_config.NumberColumn(format="%.1f"),
            "Giãn cách cao điểm": st.column_config.NumberColumn(format="%.1f phút"),
            "Giãn cách thấp điểm": st.column_config.NumberColumn(format="%.1f phút"),
        },
    )

    result_b = bundle.get("B")
    result_c = bundle.get("C")
    if result_b is not None and result_c is not None:
        status = result_c.generation_status.value if result_c.generation_status else "—"
        if (
            result_c.generation_status
            and result_c.generation_status.value == "PHÙ HỢP VÀ GIÃN CÁCH ỔN ĐỊNH"
        ):
            st.success(status, icon=":material/check_circle:")
        else:
            st.warning(status, icon=":material/warning:")
        shifted = [trace for trace in result_c.trip_traces if trace.shift_minutes != 0]
        with st.container(horizontal=True):
            st.metric(
                "Tổng chuyến B / C",
                f"{len(result_b.trips)} / {len(result_c.trips)}",
                border=True,
            )
            st.metric(
                "Xe hoạt động B / C",
                f"{result_b.active_vehicle_count} / {result_c.active_vehicle_count}",
                border=True,
            )
            st.metric(
                "Xe tối thiểu B / C",
                f"{result_b.fleet.minimum_vehicles} / {result_c.fleet.minimum_vehicles}",
                border=True,
            )
            st.metric("Chuyến dịch chuyển", len(shifted), border=True)
        with st.container(horizontal=True):
            st.metric(
                "Load factor cao nhất B / C",
                f"{result_b.evaluation.maximum_load_factor or 0:.1%} / "
                f"{result_c.evaluation.maximum_load_factor or 0:.1%}",
                border=True,
            )
            st.metric(
                "Khung >85% B / C",
                f"{result_b.evaluation.blocks_over_target} / "
                f"{result_c.evaluation.blocks_over_target}",
                border=True,
            )
            st.metric(
                "Khung >90% B / C",
                f"{result_b.evaluation.blocks_over_maximum} / "
                f"{result_c.evaluation.blocks_over_maximum}",
                border=True,
            )
            st.metric(
                "Chế độ / Ngoại lệ",
                f"{result_c.regularity.number_of_headway_regimes if result_c.regularity else 0} / "
                f"{result_c.regularity.number_of_exceptional_headways if result_c.regularity else 0}",
                border=True,
            )
        st.caption(result_c.recommendation_reason)
        st.subheader("Các chế độ giãn cách của Scenario C")
        st.dataframe(
            regime_frame(bundle),
            hide_index=True,
            column_config={
                "Giãn cách mục tiêu": st.column_config.NumberColumn(format="%.1f phút"),
            },
        )

    if not bundle.generation.feasible:
        st.error("Không thể tạo phương án C khả thi.", icon=":material/block:")
        for reason in bundle.generation.reasons:
            st.write(f"- {reason}")
    else:
        st.subheader("Kết luận của bộ sinh lịch")
        if bundle.generation.missing_trips:
            st.warning(
                f"Tổng chuyến B còn thiếu tối thiểu {bundle.generation.missing_trips} chuyến để "
                f"tiệm cận target. Tổng tối thiểu đề nghị: "
                f"{bundle.generation.minimum_required_total_trips} chuyến.",
                icon=":material/warning:",
            )
        else:
            st.success("Không phát hiện thiếu tổng chuyến ở mức target từ dữ liệu hiện có.")
        if bundle.generation.blocks_requiring_more_trips:
            with st.expander("Block cần tăng hoặc điều chuyển chuyến"):
                for block in bundle.generation.blocks_requiring_more_trips:
                    st.write(f"- {block}")

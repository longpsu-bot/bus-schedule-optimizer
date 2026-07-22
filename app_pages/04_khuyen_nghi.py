import streamlit as st

from bus_schedule_engine.ui_utils import regime_frame, scenario_frame

bundle = st.session_state.analysis_bundle
if bundle is None:
    st.warning("Chưa có kết quả. Hãy chạy phân tích ở trang Nhập dữ liệu.")
    st.stop()

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
            "Tổng chuyến B / C", f"{len(result_b.trips)} / {len(result_c.trips)}", border=True
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
            f"{result_b.evaluation.blocks_over_target} / {result_c.evaluation.blocks_over_target}",
            border=True,
        )
        st.metric(
            "Khung >90% B / C",
            f"{result_b.evaluation.blocks_over_maximum} / {result_c.evaluation.blocks_over_maximum}",
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

import streamlit as st

from bus_schedule_engine.ui_utils import block_frame

bundle = st.session_state.analysis_bundle
if bundle is None:
    st.warning("Chưa có kết quả. Hãy chạy phân tích ở trang Nhập dữ liệu.")
    st.stop()

scenario_names = [result.name for result in bundle.scenarios]
scenario = st.segmented_control(
    "Phương án cần xem", scenario_names, default="B" if "B" in scenario_names else scenario_names[0]
)
result = bundle.get(scenario)
cols = st.columns(4)
cols[0].metric("Kết luận nhu cầu", result.evaluation.demand_status.value)
cols[1].metric(
    "Hệ số tải cao nhất",
    "—"
    if result.evaluation.maximum_load_factor is None
    else f"{result.evaluation.maximum_load_factor:.1%}",
)
cols[2].metric("Khung trên mục tiêu", result.evaluation.blocks_over_target)
cols[3].metric("Khung trên tối đa", result.evaluation.blocks_over_maximum)

for limitation in result.evaluation.limitations:
    st.warning(limitation, icon=":material/warning:")

frame = block_frame(bundle, scenario)
st.dataframe(
    frame,
    hide_index=True,
    column_config={
        "Hệ số tải": st.column_config.NumberColumn(format="percent"),
        "Giãn cách TB": st.column_config.NumberColumn(format="%.1f phút"),
        "Độ lệch giãn cách": st.column_config.NumberColumn(format="%.1f phút"),
        "Khoảng trống lớn nhất": st.column_config.NumberColumn(format="%.1f phút"),
    },
)

import streamlit as st

from bus_schedule_engine.block_supply import available_supply_directions
from bus_schedule_engine.diagram import (
    build_comparison_diagram,
    build_departure_detail_diagram,
)
from bus_schedule_engine.models import Direction
from bus_schedule_engine.ui_utils import supply_summary_frame

bundle = st.session_state.analysis_bundle
figure = st.session_state.diagram_figure
artifacts = st.session_state.download_artifacts
if bundle is None or figure is None or artifacts is None:
    st.warning("Chưa có kết quả. Hãy chạy phân tích ở trang Nhập dữ liệu.")
    st.stop()

st.caption(
    "Cột thể hiện nhu cầu hành khách; các đường thể hiện số chuyến A (nếu có dữ liệu), "
    "B, C và mức chuyến cần thiết trong cùng block. Hai đại lượng dùng hai trục Y riêng."
)

st.dataframe(
    supply_summary_frame(bundle),
    hide_index=True,
    column_config={
        "LF cao nhất": st.column_config.NumberColumn(format="percent", step=0.001),
    },
)

result_b = bundle.get("B")
directions = available_supply_directions(bundle)


def _direction_option_label(direction: Direction) -> str:
    if direction == Direction.COMBINED or result_b is None:
        return "Tổng hai chiều"
    if direction == Direction.TERMINAL_1_TO_2:
        return f"{result_b.parameters.terminal_1_name} → {result_b.parameters.terminal_2_name}"
    return f"{result_b.parameters.terminal_2_name} → {result_b.parameters.terminal_1_name}"


selected_direction = st.segmented_control(
    "Chế độ hiển thị:",
    options=directions,
    default=Direction.COMBINED,
    required=True,
    format_func=_direction_option_label,
    key="schedule_supply_direction",
    help="Chọn tổng hai chiều hoặc một chiều khai thác để đối chiếu nhu cầu với số chuyến.",
)
if len(directions) == 1:
    st.caption(
        "Sản lượng đang là tổng hợp hai chiều — ước tính; chưa đủ cơ sở để phân tích xác nhận "
        "theo từng chiều."
    )
display_figure = (
    figure
    if selected_direction == Direction.COMBINED
    else build_comparison_diagram(bundle, selected_direction)
)
st.plotly_chart(
    display_figure,
    width="stretch",
    config={"scrollZoom": False, "displaylogo": False},
)

with st.expander("Chi tiết giờ xuất bến"):
    st.caption(
        "Chế độ chẩn đoán theo thời gian liên tục: mỗi marker là một chuyến xuất bến; "
        "màu nền mờ thể hiện trạng thái cung ứng của block."
    )
    st.plotly_chart(
        build_departure_detail_diagram(bundle),
        width="stretch",
        config={"scrollZoom": False, "displaylogo": False},
        key="departure_detail_diagram",
    )

st.subheader("Tải kết quả")
with st.container(horizontal=True, horizontal_alignment="left"):
    st.download_button(
        "Tải bảng so sánh B và C (.xlsx)",
        artifacts["comparison_xlsx"],
        file_name="so_sanh_B_C_tai_phan_bo_on_dinh.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/compare_arrows:",
        on_click="ignore",
    )
    st.download_button(
        "Workbook kết quả",
        artifacts["xlsx"],
        file_name="Bus_Schedule_MVP_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/table_view:",
        on_click="ignore",
    )
    st.download_button(
        "Diagram PNG",
        artifacts["png"],
        file_name="Bus_Schedule_Comparison.png",
        mime="image/png",
        icon=":material/image:",
        on_click="ignore",
    )
    st.download_button(
        "Diagram HTML tương tác",
        artifacts["html"],
        file_name="Bus_Schedule_Comparison.html",
        mime="text/html",
        icon=":material/code:",
        on_click="ignore",
    )

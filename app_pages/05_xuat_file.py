from collections.abc import Mapping

import streamlit as st

from bus_schedule_engine.block_supply import available_supply_directions
from bus_schedule_engine.diagram import (
    build_comparison_diagram,
    build_departure_detail_diagram,
)
from bus_schedule_engine.models import Direction
from bus_schedule_engine.ui_result_authority import (
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.ui_utils import supply_summary_frame
from bus_schedule_engine.unified_diagram import available_unified_directions_v1
from bus_schedule_engine.unified_page5_artifacts import (
    UnifiedPage5ArtifactError,
    build_unified_page5_artifacts_v1,
)
from bus_schedule_engine.unified_ui_frames import direction_label_v1

UNIFIED_PAGE5_ARTIFACT_FAILED = "UNIFIED_PAGE5_ARTIFACT_FAILED"


def _direction_option_label(bundle, direction: Direction) -> str:
    result_b = bundle.get("B")
    if direction == Direction.COMBINED or result_b is None:
        return "Tổng hai chiều"
    if direction == Direction.TERMINAL_1_TO_2:
        return f"{result_b.parameters.terminal_1_name} → {result_b.parameters.terminal_2_name}"
    return f"{result_b.parameters.terminal_2_name} → {result_b.parameters.terminal_1_name}"


def _render_legacy_page5(bundle, figure, artifacts) -> None:
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

    directions = available_supply_directions(bundle)
    selected_direction = st.segmented_control(
        "Chế độ hiển thị:",
        options=directions,
        default=Direction.COMBINED,
        required=True,
        format_func=lambda direction: _direction_option_label(bundle, direction),
        key="schedule_supply_direction",
        help=("Chọn tổng hai chiều hoặc một chiều khai thác để đối chiếu nhu cầu với số chuyến."),
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


def _selector_option(direction: str) -> Direction:
    return {
        "combined": Direction.COMBINED,
        "outbound": Direction.TERMINAL_1_TO_2,
        "inbound": Direction.TERMINAL_2_TO_1,
    }[direction]


def _selected_unified_direction(directions: tuple[str, ...]) -> str:
    state_value = st.session_state.get("schedule_supply_direction")
    state_to_contract = {
        Direction.COMBINED: "combined",
        Direction.TERMINAL_1_TO_2: "outbound",
        Direction.TERMINAL_2_TO_1: "inbound",
        "combined": "combined",
        "terminal_1_to_2": "outbound",
        "terminal_2_to_1": "inbound",
    }
    requested = state_to_contract.get(state_value)
    return requested if requested in directions else directions[0]


def _render_unified_page5(visible, artifacts, directions: tuple[str, ...]) -> None:
    presentation = visible.presentation
    assert presentation is not None
    st.info(visible.banner_message, icon=":material/info:")
    if presentation.requires_expert_review:
        review_codes = "\n".join(f"- {code}" for code in presentation.expert_review_required_codes)
        st.warning(
            "Contract V1 yêu cầu chuyên gia rà soát; đây không phải phê duyệt khai thác.\n\n"
            f"{review_codes}\n\n"
            "Biểu đồ và tệp tải xuống unified là bằng chứng xác thực, không phải phê duyệt vận hành.",
            icon=":material/rate_review:",
        )

    if len(directions) == 1:
        st.caption(
            "Chiều block Contract V1 duy nhất được trả về: "
            f"{direction_label_v1(presentation, directions[0])}."
        )
    else:
        options = tuple(_selector_option(direction) for direction in directions)
        selected_option = _selector_option(artifacts.selected_direction)
        current = st.session_state.get("schedule_supply_direction")
        if current not in options:
            st.session_state["schedule_supply_direction"] = selected_option
        st.segmented_control(
            "Chiều block Contract V1:",
            options=options,
            default=selected_option,
            required=True,
            format_func=lambda option: direction_label_v1(
                presentation,
                {
                    Direction.COMBINED: "combined",
                    Direction.TERMINAL_1_TO_2: "outbound",
                    Direction.TERMINAL_2_TO_1: "inbound",
                }[option],
            ),
            key="schedule_supply_direction",
            help="Chỉ chọn đúng một chiều block đã được Contract V1 trả về.",
        )

    st.caption(
        "Các block giữ nguyên grain Contract V1; chỉ lọc theo đúng chiều được trả về. "
        "Không suy diễn tổng hai chiều, không tách nhu cầu theo chiều và không phân bổ lại nhu cầu."
    )
    st.plotly_chart(
        artifacts.demand_supply_figure,
        width="stretch",
        config={"scrollZoom": False, "displaylogo": False},
    )

    with st.expander("Chi tiết giờ xuất bến"):
        st.caption(
            "Hiển thị giờ xuất bến chính xác của A (nếu được cung cấp), B và chỉ Scenario C "
            "được validator chấp nhận; không hiển thị lịch ứng viên bị từ chối."
        )
        st.plotly_chart(
            artifacts.departure_figure,
            width="stretch",
            config={"scrollZoom": False, "displaylogo": False},
            key="departure_detail_diagram",
        )

    st.subheader("Tải kết quả Contract V1")
    with st.container(horizontal=True, horizontal_alignment="left"):
        st.download_button(
            "Workbook Contract V1",
            artifacts.xlsx_bytes,
            file_name=artifacts.xlsx_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/table_view:",
            on_click="ignore",
        )
        st.download_button(
            "Báo cáo biểu đồ Contract V1 (.html)",
            artifacts.html_bytes,
            file_name=artifacts.html_filename,
            mime="text/html",
            icon=":material/code:",
            on_click="ignore",
        )
        st.download_button(
            "Tổng quan đã chọn (.png)",
            artifacts.png_bytes,
            file_name=artifacts.png_filename,
            mime="image/png",
            icon=":material/image:",
            on_click="ignore",
        )


bundle = st.session_state.get("analysis_bundle")
legacy_figure = st.session_state.get("diagram_figure")
legacy_artifacts = st.session_state.get("download_artifacts")
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

if visible.mode == VisibleResultModeV1.UNIFIED_CONTRACT_V1:
    presentation = visible.presentation
    stored_downloads = st.session_state.get("unified_download_artifacts")
    try:
        assert presentation is not None
        if not isinstance(stored_downloads, Mapping):
            raise UnifiedPage5ArtifactError("unified download artifacts are missing")
        directions = available_unified_directions_v1(presentation)
        if not directions:
            raise UnifiedPage5ArtifactError("presentation contains no exact block direction")
        selected_direction = _selected_unified_direction(directions)
        unified_artifacts = build_unified_page5_artifacts_v1(
            presentation,
            st.session_state.get("unified_demand_supply_figure"),
            st.session_state.get("unified_departure_figure"),
            stored_downloads.get("xlsx"),
            selected_direction=selected_direction,
        )
    except (AssertionError, UnifiedPage5ArtifactError, TypeError, ValueError) as exc:
        st.warning(
            "Nguồn kết quả hiển thị: pipeline legacy.\n\n"
            "Không thể dựng trọn bộ biểu đồ và tệp tải xuống Contract V1; "
            "không có artifact unified từng phần nào được hiển thị.\n\n"
            f"Mã: {UNIFIED_PAGE5_ARTIFACT_FAILED}\n\n"
            f"Chi tiết chẩn đoán: {exc}",
            icon=":material/warning:",
        )
        _render_legacy_page5(bundle, legacy_figure, legacy_artifacts)
    else:
        _render_unified_page5(visible, unified_artifacts, directions)
else:
    st.warning(visible.banner_message, icon=":material/warning:")
    _render_legacy_page5(bundle, legacy_figure, legacy_artifacts)

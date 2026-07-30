from collections.abc import Mapping

import streamlit as st

from bus_schedule_engine.application_pipeline import (
    CONTRACT_V1_ARTIFACT_FAILED,
    CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH,
    build_unified_runtime_failure_v1,
)
from bus_schedule_engine.models import Direction
from bus_schedule_engine.optimization_service import OptimizationExecutionStageV1
from bus_schedule_engine.ui_result_authority import (
    VisibleResultModeV1,
    resolve_visible_result_context_v1,
)
from bus_schedule_engine.unified_diagram import available_unified_directions_v1
from bus_schedule_engine.unified_page5_artifacts import (
    UnifiedPage5ArtifactError,
    UnifiedPage5SemanticIntegrityError,
    build_unified_page5_artifacts_v1,
)
from bus_schedule_engine.unified_ui_frames import direction_label_v1


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
            "Contract V1 yêu cầu chuyên gia rà soát; đây không phải phê duyệt "
            "khai thác.\n\n"
            f"{review_codes}\n\n"
            "Biểu đồ và tệp tải xuống là bằng chứng đã xác thực, không phải phê "
            "duyệt vận hành.",
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
            st.session_state.pop("schedule_supply_direction", None)
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
        "Các block giữ nguyên grain Contract V1; chỉ lọc theo đúng chiều được "
        "trả về. Không suy diễn tổng hai chiều và không phân bổ lại nhu cầu."
    )
    st.plotly_chart(
        artifacts.demand_supply_figure,
        width="stretch",
        config={"scrollZoom": False, "displaylogo": False},
    )
    with st.expander("Chi tiết giờ xuất bến"):
        st.caption(
            "Hiển thị giờ xuất bến chính xác của A (nếu có), B và chỉ Scenario C "
            "đã được validator chấp nhận; không hiển thị ứng viên bị từ chối."
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
if visible.mode == VisibleResultModeV1.UNIFIED_ARTIFACT_FAILED:
    st.warning(visible.banner_message, icon=":material/warning:")
    st.stop()
if visible.mode != VisibleResultModeV1.UNIFIED_CONTRACT_V1:
    if visible.banner_level == "error":
        st.error(visible.banner_message, icon=":material/error:")
    else:
        st.warning(visible.banner_message, icon=":material/warning:")
    st.stop()

presentation = visible.presentation
result = visible.unified_result
readiness = visible.input_readiness
stored_downloads = st.session_state.get("unified_download_artifacts")
try:
    assert presentation is not None
    assert result is not None
    assert readiness is not None
    if not isinstance(stored_downloads, Mapping):
        raise UnifiedPage5SemanticIntegrityError("unified download artifacts are missing")
    directions = available_unified_directions_v1(presentation)
    if not directions:
        raise UnifiedPage5SemanticIntegrityError("presentation contains no exact block direction")
    selected_direction = _selected_unified_direction(directions)
    unified_artifacts = build_unified_page5_artifacts_v1(
        presentation,
        st.session_state.get("unified_demand_supply_figure"),
        st.session_state.get("unified_departure_figure"),
        stored_downloads.get("xlsx"),
        selected_direction=selected_direction,
    )
except (AssertionError, UnifiedPage5ArtifactError, TypeError, ValueError) as exc:
    semantic = isinstance(exc, UnifiedPage5SemanticIntegrityError)
    code = CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH if semantic else CONTRACT_V1_ARTIFACT_FAILED
    stage = OptimizationExecutionStageV1.ARTIFACTS.value
    if result is not None and presentation is not None and readiness is not None:
        failure = build_unified_runtime_failure_v1(
            code=code,
            stage=stage,
            exc=exc,
            retryable=not semantic,
            solver_choice=result.solver_choice,
            source_id=presentation.source_id,
            imported_at=result.normalized_inputs.scenario_b.source_metadata.imported_at,
            input_readiness=readiness,
            result=result,
            presentation=presentation,
        )
        correlation_id = failure.correlation_id
        message = failure.sanitized_message
    else:
        correlation_id = "m5c2-unavailable"
        message = "Trạng thái Page 05 không đầy đủ."
    st.error(
        f"{code}\n\nGiai đoạn: {stage}\n\nMã đối chiếu: {correlation_id}\n\n"
        f"{message}\n\nMọi biểu đồ và tệp tải xuống ở Trang 05 đã bị vô hiệu hóa.",
        icon=":material/error:",
    )
    st.stop()

_render_unified_page5(visible, unified_artifacts, directions)

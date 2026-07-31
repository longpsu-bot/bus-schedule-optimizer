from datetime import UTC, datetime
from hashlib import sha256

import streamlit as st

from bus_schedule_engine.application_pipeline import (
    CONTRACT_V1_ARTIFACT_FAILED,
    WORKBOOK_IMPORT_INVALID,
    WORKBOOK_OPTIMIZATION_NOT_READY,
    UnifiedApplicationStatusV1,
    run_unified_application_pipeline_v1,
    sanitize_import_error_message_v1,
)
from bus_schedule_engine.importer import import_workbook
from bus_schedule_engine.models import Direction
from bus_schedule_engine.protected_service_floor import (
    protected_service_floor_policy_from_workbook_v1,
)
from bus_schedule_engine.time_utils import parse_runtime_options
from bus_schedule_engine.ui_utils import (
    apply_overrides,
    preview_sheet,
    template_bytes,
    workbook_sheet_names,
)

_LEGACY_RESULT_STATE_KEYS = (
    "analysis_bundle",
    "diagram_figure",
    "download_artifacts",
    "scenario_c_fingerprint",
    "parallel_runtime_status",
    "side_by_side_validation_report",
)
_UNIFIED_RESULT_STATE_KEYS = (
    "imported_workbook",
    "workbook_input_readiness",
    "unified_optimization_result",
    "unified_presentation",
    "unified_demand_supply_figure",
    "unified_departure_figure",
    "unified_download_artifacts",
    "unified_runtime_failure",
    "unified_runtime_status",
    "trip_ridership_analysis",
    "trip_ridership_failure",
    "protected_service_floor_assessment",
    "protected_service_floor_failure",
)


def _clear_result_state() -> None:
    for state_key in _LEGACY_RESULT_STATE_KEYS:
        st.session_state.pop(state_key, None)
    for state_key in _UNIFIED_RESULT_STATE_KEYS:
        st.session_state[state_key] = None


st.subheader("Workbook và thông số chạy")
st.write(
    "Tải workbook theo template. Tối thiểu cần THONG_SO_B và BIEU_DO_B; Scenario A, "
    "sản lượng và cấu hình có thể để trống hoặc bỏ qua. Dữ liệu nguồn chỉ được đọc."
)

with st.container(horizontal=True, horizontal_alignment="left"):
    st.download_button(
        "Tải template có dữ liệu minh họa",
        data=template_bytes,
        file_name="Bus_Schedule_Input_Template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/download:",
        on_click="ignore",
    )

uploaded = st.file_uploader(
    "Chọn workbook đầu vào",
    type="xlsx",
    key="input_workbook_uploader",
    help="Tối thiểu cần THONG_SO_B và BIEU_DO_B. Thiếu sản lượng thì C chỉ báo không đủ dữ liệu.",
    max_upload_size=50,
)

if uploaded is not None:
    content = uploaded.getvalue()
    if content != st.session_state.get("input_bytes"):
        _clear_result_state()
    st.session_state.input_bytes = content
else:
    content = st.session_state.get("input_bytes")

if content:
    try:
        imported = import_workbook(content)
        sheet_names = workbook_sheet_names(content)
    except Exception as exc:
        st.error(
            f"{WORKBOOK_IMPORT_INVALID}\n\n{sanitize_import_error_message_v1(exc)}",
            icon=":material/error:",
        )
        st.info(
            "Hãy dùng template đầu vào mới, chuyển dữ liệu sang đúng sheet và trường "
            "được báo lỗi, rồi tải workbook lên lại."
        )
        st.stop()

    preview_name = st.selectbox("Sheet xem trước", sheet_names, key="input_preview_sheet")
    with st.expander("Xem dữ liệu nguồn", icon=":material/table_view:"):
        st.dataframe(preview_sheet(content, preview_name), hide_index=True)

    st.segmented_control(
        "Chế độ khuyến nghị",
        ["Tái phân bổ ổn định, giữ nguyên số chuyến và số xe"],
        default="Tái phân bổ ổn định, giữ nguyên số chuyến và số xe",
        key="recommendation_mode",
    )
    declared_vehicle_count = len({trip.vehicle_id for trip in imported.trips_b if trip.vehicle_id})
    declared_available_fleet = imported.parameters_b.available_fleet_limit
    with st.container(border=True):
        st.markdown("**Các giá trị khóa từ Scenario B**")
        with st.container(horizontal=True):
            st.metric("Tổng chuyến", len(imported.trips_b), border=True)
            st.metric(
                "Chiều 1",
                sum(trip.direction == Direction.TERMINAL_1_TO_2 for trip in imported.trips_b),
                border=True,
            )
            st.metric(
                "Chiều 2",
                sum(trip.direction == Direction.TERMINAL_2_TO_1 for trip in imported.trips_b),
                border=True,
            )
            st.metric("Số mã xe đã khai báo", declared_vehicle_count, border=True)
            st.metric(
                "Giới hạn đội xe đã khai báo",
                (
                    declared_available_fleet
                    if declared_available_fleet is not None
                    else "Chưa khai báo"
                ),
                border=True,
            )
            st.metric(
                "Quan sát sản lượng theo chuyến",
                len(imported.trip_ridership_observations),
                border=True,
            )
        st.caption(
            f"Sức chứa {imported.parameters_b.capacity} khách · hành trình "
            f"{imported.parameters_b.runtime_range_text} phút · "
            "quay đầu tối thiểu "
            f"{imported.parameters_b.effective_layover_minutes} phút · target "
            f"{imported.parameters_b.target_load_factor:.0%} · maximum "
            f"{imported.parameters_b.maximum_load_factor:.0%}."
        )
        st.caption(
            "Khung 30 hoặc 60 phút chỉ dùng để tổng hợp nhu cầu. Giãn cách được tối ưu "
            "trên chuỗi các chuyến liền kề và có thể được giữ ổn định qua nhiều khung nhu cầu liên tiếp."
        )

    try:
        protected_policy = protected_service_floor_policy_from_workbook_v1(imported)
    except (TypeError, ValueError) as exc:
        protected_policy = None
        st.warning(
            "Cấu hình kế hoạch 6A2A không hợp lệ và sẽ chỉ tạo lỗi bổ sung, "
            f"không thay đổi Contract V1: {exc}",
            icon=":material/warning:",
        )
    if protected_policy is not None:
        with st.container(border=True):
            st.markdown("**Thiết lập kế hoạch sàn dịch vụ bảo vệ 6A2A**")
            st.dataframe(
                [
                    {
                        "Thiết lập": "Headway B tối đa được bảo vệ (phút)",
                        "Giá trị": protected_policy.maximum_protected_b_headway_minutes,
                    },
                    {
                        "Thiết lập": "Dung sai làm tròn headway (phút)",
                        "Giá trị": protected_policy.headway_rounding_tolerance_minutes,
                    },
                    {
                        "Thiết lập": "Số chuyến tối thiểu/regime",
                        "Giá trị": protected_policy.minimum_departures_per_regime,
                    },
                    {
                        "Thiết lập": "Thời lượng tối thiểu/regime (phút)",
                        "Giá trị": protected_policy.minimum_regime_duration_minutes,
                    },
                    {
                        "Thiết lập": "Số ngày quan sát tối thiểu/chuyến",
                        "Giá trị": protected_policy.minimum_observed_days_per_trip,
                    },
                    {
                        "Thiết lập": "Tỷ lệ bao phủ chuyến tối thiểu",
                        "Giá trị": protected_policy.minimum_regime_trip_coverage_rate,
                    },
                    {
                        "Thiết lập": "Tỷ lệ chuyến tải cao tối thiểu",
                        "Giá trị": protected_policy.minimum_high_load_trip_share,
                    },
                    {
                        "Thiết lập": "Thống kê tải bảo vệ",
                        "Giá trị": protected_policy.protected_load_statistic,
                    },
                    {
                        "Thiết lập": "Độ tin cậy tối thiểu",
                        "Giá trị": protected_policy.minimum_trip_ridership_confidence,
                    },
                    {
                        "Thiết lập": "Dung sai biên cửa sổ tương lai (phút)",
                        "Giá trị": (
                            protected_policy.future_service_window_boundary_tolerance_minutes
                        ),
                    },
                ],
                hide_index=True,
            )
            st.caption(
                "Đây là thiết lập kế hoạch được khai báo. Regime chưa được phân loại "
                "trước khi gửi biểu mẫu."
            )

    with st.form("analysis_parameters", border=True):
        st.subheader("Thông số kiểm tra và đánh giá")
        has_scenario_a = imported.parameters_a is not None and bool(imported.trips_a)
        first_row = st.columns(4 if has_scenario_a else 3)
        field_index = 0
        if has_scenario_a:
            capacity_a = first_row[field_index].number_input(
                "Sức chứa xe A",
                min_value=1,
                step=1,
                value=imported.parameters_a.capacity,
            )
            field_index += 1
        else:
            capacity_a = None
            st.caption("Chế độ chỉ có B: bỏ qua đánh giá Scenario A.")
        capacity_b = first_row[field_index].number_input(
            "Sức chứa xe B",
            min_value=1,
            step=1,
            value=imported.parameters_b.capacity,
        )
        target = first_row[field_index + 1].number_input(
            "Hệ số tải mục tiêu",
            min_value=0.01,
            max_value=1.0,
            step=0.01,
            value=float(imported.parameters_b.target_load_factor),
            format="%.2f",
        )
        maximum = first_row[field_index + 2].number_input(
            "Hệ số tải tối đa",
            min_value=0.01,
            max_value=1.0,
            step=0.01,
            value=float(imported.parameters_b.maximum_load_factor),
            format="%.2f",
        )
        second_row = st.columns(3)
        route_type = second_row[0].selectbox(
            "Loại tuyến",
            ["intra_provincial", "inter_provincial"],
            index=0 if imported.parameters_b.route_type.value == "intra_provincial" else 1,
        )
        layover = second_row[1].number_input(
            "Thời gian quay đầu tối thiểu (phút)",
            min_value=1,
            step=1,
            value=imported.parameters_b.effective_layover_minutes,
        )
        block_minutes = second_row[2].segmented_control(
            "Khung thời gian (phút)", [30, 60], default=imported.parameters_b.time_block_minutes
        )
        allowed_runtime_text = st.text_input(
            "Khoảng thời gian hành trình cho phép (phút)",
            value=imported.parameters_b.runtime_options_text,
            key="allowed_runtime_minutes_input",
            help=(
                "Nhập hai đầu mút bằng dấu phẩy hoặc chấm phẩy, ví dụ 55,65 hoặc "
                "55;65. Khi đó mọi số phút nguyên từ 55 đến 65, gồm cả 60 và 61, đều hợp lệ."
            ),
        )
        st.caption(
            "Hai giá trị là cận dưới và cận trên của một khoảng bao gồm hai đầu. "
            "Trong Excel dùng dấu phẩy thập phân, nên nhập `55;65`."
        )
        submitted = st.form_submit_button(
            "Chạy kiểm tra và sinh phương án",
            type="primary",
            icon=":material/play_arrow:",
        )

    if submitted:
        allowed_runtime_error = False
        try:
            allowed_runtime_minutes = parse_runtime_options(allowed_runtime_text)
        except ValueError as exc:
            st.error(f"Khoảng thời gian hành trình không hợp lệ: {exc}")
            allowed_runtime_error = True
        if target > maximum:
            st.error("Hệ số tải mục tiêu không được lớn hơn hệ số tải tối đa.")
        elif not allowed_runtime_error:
            updated = apply_overrides(
                imported,
                capacity_a=None if capacity_a is None else int(capacity_a),
                capacity_b=int(capacity_b),
                target=float(target),
                maximum=float(maximum),
                route_type=route_type,
                layover=int(layover),
                block_minutes=int(block_minutes),
                allowed_runtime_minutes=allowed_runtime_minutes,
            )
            _clear_result_state()
            source_id = f"streamlit-upload-sha256:{sha256(content).hexdigest()}"
            imported_at = datetime.now(UTC)
            with st.status(
                "Đang kiểm tra, đánh giá và tạo báo cáo…",
                expanded=True,
            ) as status:
                unified_run = run_unified_application_pipeline_v1(
                    updated,
                    source_id=source_id,
                    imported_at=imported_at,
                )
                status.update(label="Hoàn tất pipeline", state="complete", expanded=False)

            st.session_state.imported_workbook = updated
            st.session_state.workbook_input_readiness = unified_run.input_readiness
            st.session_state.unified_runtime_status = unified_run.status
            st.session_state.unified_runtime_failure = unified_run.failure
            st.session_state.trip_ridership_analysis = unified_run.trip_ridership_analysis
            st.session_state.trip_ridership_failure = unified_run.trip_ridership_failure
            st.session_state.protected_service_floor_assessment = (
                unified_run.protected_service_floor_assessment
            )
            st.session_state.protected_service_floor_failure = (
                unified_run.protected_service_floor_failure
            )
            st.session_state.unified_optimization_result = unified_run.unified_result
            st.session_state.unified_presentation = unified_run.unified_presentation
            st.session_state.unified_demand_supply_figure = unified_run.unified_demand_supply_figure
            st.session_state.unified_departure_figure = unified_run.unified_departure_figure
            st.session_state.unified_download_artifacts = (
                {
                    "xlsx": unified_run.unified_xlsx_bytes,
                    "source_id": unified_run.source_id,
                    "presentation_fingerprint": (
                        unified_run.unified_presentation.presentation_fingerprint
                    ),
                    "b_fingerprint": (unified_run.unified_presentation.source_b_fingerprint),
                    "accepted_solution_fingerprint": (
                        unified_run.unified_presentation.accepted_solution_fingerprint
                    ),
                }
                if unified_run.status == UnifiedApplicationStatusV1.COMPLETE
                and unified_run.unified_xlsx_bytes is not None
                and unified_run.unified_presentation is not None
                else None
            )

            if unified_run.status == UnifiedApplicationStatusV1.INPUT_NOT_READY:
                codes = "\n".join(
                    f"- {code}"
                    for code in unified_run.input_readiness.missing_optimization_authority_codes
                )
                st.write(f"Nguồn: `{source_id}`")
                st.write(
                    f"Tuyến: `{updated.parameters_b.route_id}` · {updated.parameters_b.route_name}"
                )
                st.write(
                    f"Bến: {updated.parameters_b.terminal_1_name} ↔ "
                    f"{updated.parameters_b.terminal_2_name}"
                )
                st.write(
                    "Số dòng nhập: "
                    f"Scenario A = {len(updated.trips_a)}, "
                    f"Scenario B = {len(updated.trips_b)}, "
                    f"nhu cầu = {len(updated.demand)}, "
                    "sản lượng theo chuyến = "
                    f"{len(updated.trip_ridership_observations)}."
                )
                st.warning(
                    f"{WORKBOOK_OPTIMIZATION_NOT_READY}\n\n{codes}\n\n"
                    "Hãy dùng template mới, bổ sung các trường thẩm quyền còn thiếu "
                    "và chạy lại.",
                    icon=":material/warning:",
                )
            elif unified_run.status == UnifiedApplicationStatusV1.ARTIFACT_FAILED:
                assert unified_run.failure is not None
                st.warning(
                    f"{CONTRACT_V1_ARTIFACT_FAILED}\n\n"
                    f"Mã đối chiếu: {unified_run.failure.correlation_id}\n\n"
                    "Trang 02–04 vẫn khả dụng; mọi biểu đồ và tệp tải xuống ở "
                    "Trang 05 đã bị vô hiệu hóa.",
                    icon=":material/warning:",
                )
            elif unified_run.status == UnifiedApplicationStatusV1.FAILED:
                assert unified_run.failure is not None
                st.error(
                    f"{unified_run.failure.code}\n\n"
                    f"Giai đoạn: {unified_run.failure.stage}\n\n"
                    f"Mã đối chiếu: {unified_run.failure.correlation_id}\n\n"
                    f"{unified_run.failure.sanitized_message}",
                    icon=":material/error:",
                )
            else:
                assert unified_run.unified_presentation is not None
                outcome = unified_run.unified_presentation.outcome
                st.success(
                    f"Contract V1 B: {outcome.b_disposition}. "
                    f"Hành động: {outcome.selected_action}. "
                    f"Trạng thái solver: "
                    f"{outcome.heuristic_result_status or outcome.ortools_result_status or 'NOT_ATTEMPTED'}. "
                    f"Scenario C được chấp nhận: "
                    f"{'Có' if outcome.accepted_c_exists else 'Không'}.",
                    icon=":material/check_circle:",
                )
else:
    st.info(
        "Tải workbook hoặc tải template minh họa ở trên, điền dữ liệu rồi tải lại để bắt đầu.",
        icon=":material/info:",
    )

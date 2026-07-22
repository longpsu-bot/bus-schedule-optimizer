import streamlit as st

from bus_schedule_engine.fleet import assign_fleet
from bus_schedule_engine.importer import InputDataError, import_workbook
from bus_schedule_engine.models import Direction
from bus_schedule_engine.time_utils import parse_runtime_options
from bus_schedule_engine.ui_utils import (
    apply_overrides,
    preview_sheet,
    run_and_build_artifacts,
    template_bytes,
    workbook_sheet_names,
)

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
    st.session_state.input_bytes = content
else:
    content = st.session_state.input_bytes

if content:
    try:
        imported = import_workbook(content)
        sheet_names = workbook_sheet_names(content)
    except (InputDataError, ValueError) as exc:
        st.error(f"Workbook chưa hợp lệ: {exc}", icon=":material/error:")
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
    active_fleet = max(
        assign_fleet(imported.trips_b, imported.parameters_b).minimum_vehicles,
        len({trip.vehicle_id for trip in imported.trips_b if trip.vehicle_id}),
    )
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
            st.metric("Xe hoạt động", active_fleet, border=True)
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
            try:
                with st.status("Đang kiểm tra, đánh giá và tạo báo cáo…", expanded=True) as status:
                    bundle, figure, artifacts = run_and_build_artifacts(updated)
                    status.update(label="Hoàn tất pipeline", state="complete", expanded=False)
            except (InputDataError, ValueError) as exc:
                st.error(f"Không thể chạy pipeline: {exc}", icon=":material/error:")
            else:
                st.session_state.imported_workbook = updated
                st.session_state.analysis_bundle = bundle
                st.session_state.diagram_figure = figure
                st.session_state.download_artifacts = artifacts
                st.session_state.scenario_c_fingerprint = artifacts["c_fingerprint"].decode("utf-8")
                result_b = bundle.get("B")
                st.success(
                    f"Phương án B: {result_b.validation.status if result_b else 'N/A'}. "
                    "Dùng thanh điều hướng phía trên để xem từng phần kết quả.",
                    icon=":material/check_circle:",
                )
else:
    st.info(
        "Tải workbook hoặc tải template minh họa ở trên, điền dữ liệu rồi tải lại để bắt đầu.",
        icon=":material/info:",
    )

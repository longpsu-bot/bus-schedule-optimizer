from __future__ import annotations

from datetime import date, time
from pathlib import Path
from statistics import mean

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .comparator import load_scoring_config
from .models import (
    AnalysisBundle,
    Direction,
    RouteType,
    ScenarioCStatus,
    ScenarioParameters,
    ScenarioResult,
    Trip,
)
from .time_utils import block_label, excel_time_fraction

NAVY = "17324D"
BLUE = "2563EB"
TEAL = "0F766E"
GREEN = "DCFCE7"
AMBER = "FEF3C7"
RED = "FEE2E2"
LIGHT_BLUE = "E0F2FE"
LIGHT_GRAY = "F1F5F9"
WHITE = "FFFFFF"
TEXT = "1E293B"
MUTED = "64748B"
THIN_GRAY = Side(style="thin", color="CBD5E1")


def _title(ws, title: str, end_column: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_column)
    cell = ws.cell(1, 1, title)
    cell.fill = PatternFill("solid", fgColor=NAVY)
    cell.font = Font(name="Aptos Display", size=18, bold=True, color=WHITE)
    cell.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 34
    ws.sheet_view.showGridLines = False


def _table_header(ws, row: int, headers: list[str]) -> None:
    for column, header in enumerate(headers, 1):
        cell = ws.cell(row, column, header)
        cell.fill = PatternFill("solid", fgColor=TEAL)
        cell.font = Font(name="Aptos", bold=True, color=WHITE)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=Side(style="medium", color="0B4F4A"))
    ws.row_dimensions[row].height = 30


def _body_style(ws, start_row: int, end_row: int, end_column: int) -> None:
    if end_row < start_row:
        return
    for row in ws.iter_rows(min_row=start_row, max_row=end_row, min_col=1, max_col=end_column):
        for cell in row:
            cell.font = Font(name="Aptos", size=10, color=TEXT)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=THIN_GRAY)
        if row[0].row % 2 == 0:
            for cell in row:
                cell.fill = PatternFill("solid", fgColor="F8FAFC")


def _autowidth(ws, maximum: int = 42) -> None:
    for column_cells in ws.columns:
        column = get_column_letter(column_cells[0].column)
        length = 0
        for cell in column_cells:
            value = cell.value
            if value is not None:
                parts = str(value).splitlines() or [""]
                length = max(length, max(len(part) for part in parts))
        ws.column_dimensions[column].width = min(maximum, max(10, length + 2))


def _as_time(seconds: int) -> time:
    seconds %= 86400
    hour, remainder = divmod(seconds, 3600)
    minute, second = divmod(remainder, 60)
    return time(hour, minute, second)


def _sample_parameters() -> tuple[ScenarioParameters, ScenarioParameters]:
    common = {
        "route_id": "MVP-01",
        "route_name": "Tuyến mẫu Bến Trung Tâm – Bến Phía Đông",
        "route_type": RouteType.INTRA_PROVINCIAL,
        "trip_runtime_minutes": 65,
        "allowed_trip_runtime_minutes": (55, 65),
        "total_daily_trips": 24,
        "terminal_1_name": "Bến Trung Tâm",
        "terminal_1_first_departure": 6 * 3600,
        "terminal_1_last_departure": 18 * 3600,
        "terminal_2_name": "Bến Phía Đông",
        "terminal_2_first_departure": 6 * 3600 + 15 * 60,
        "terminal_2_last_departure": 18 * 3600 + 15 * 60,
        "vehicle_capacity_passengers": 60,
        "target_load_factor": 0.85,
        "maximum_load_factor": 0.90,
        "time_block_minutes": 60,
        "minimum_layover_minutes": 10,
    }
    return ScenarioParameters(**common), ScenarioParameters(**common)


def _inclusive_times(first: int, last: int, count: int) -> list[int]:
    if count == 1:
        return [first]
    step = (last - first) / (count - 1)
    return [round(first + index * step) for index in range(count)]


def _sample_trips(
    scenario: str, parameters: ScenarioParameters, proposed: bool = False
) -> list[Trip]:
    if proposed:
        t1_hours = [
            "06:00",
            "06:45",
            "09:30",
            "10:30",
            "11:30",
            "12:30",
            "13:30",
            "14:30",
            "15:30",
            "16:30",
            "17:30",
            "18:00",
        ]
        t2_hours = [
            "06:15",
            "07:00",
            "09:45",
            "10:45",
            "11:45",
            "12:45",
            "13:45",
            "14:45",
            "15:45",
            "16:45",
            "17:45",
            "18:15",
        ]

        def parse(text: str) -> int:
            hour, minute = (int(part) for part in text.split(":"))
            return hour * 3600 + minute * 60

        times_1 = [parse(item) for item in t1_hours]
        times_2 = [parse(item) for item in t2_hours]
    else:
        times_1 = _inclusive_times(
            parameters.terminal_1_first_departure,
            parameters.terminal_1_last_departure,
            12,
        )
        times_2 = _inclusive_times(
            parameters.terminal_2_first_departure,
            parameters.terminal_2_last_departure,
            12,
        )
    trips = []
    for direction, terminal, times in (
        (Direction.TERMINAL_1_TO_2, parameters.terminal_1_name, times_1),
        (Direction.TERMINAL_2_TO_1, parameters.terminal_2_name, times_2),
    ):
        for departure in times:
            trips.append(
                Trip(
                    scenario=scenario,
                    trip_id="",
                    departure_terminal=terminal,
                    direction=direction,
                    departure_seconds=departure,
                    arrival_seconds=departure + parameters.default_trip_runtime_minutes * 60,
                )
            )
    ordered = sorted(trips, key=lambda item: (item.departure_seconds, item.direction.value))
    return [
        Trip(
            scenario=trip.scenario,
            trip_id=f"{scenario}-{index:03d}",
            departure_terminal=trip.departure_terminal,
            direction=trip.direction,
            departure_seconds=trip.departure_seconds,
            arrival_seconds=trip.arrival_seconds,
        )
        for index, trip in enumerate(ordered, 1)
    ]


def _write_parameter_sheet(ws, parameters: ScenarioParameters, scenario: str) -> None:
    _title(ws, f"THÔNG SỐ SCENARIO {scenario}", 3)
    _table_header(ws, 3, ["Tham số", "Giá trị", "Diễn giải"])
    rows = [
        ("route_id", parameters.route_id, "Mã tuyến"),
        ("route_name", parameters.route_name, "Tên tuyến"),
        ("route_type", parameters.route_type.value, "Loại tuyến"),
        (
            "allowed_trip_runtime_minutes",
            parameters.runtime_options_text,
            "Khoảng nguyên bao gồm hai đầu; 55,65 cho phép mọi giá trị từ 55 đến 65",
        ),
        (
            "trip_runtime_minutes",
            parameters.default_trip_runtime_minutes,
            "Tương thích file cũ; dùng làm mặc định khi arrival_time để trống",
        ),
        ("total_daily_trips", parameters.total_daily_trips, "Tổng lượt hai chiều/ngày"),
        ("terminal_1_name", parameters.terminal_1_name, "Tên bến 1"),
        (
            "terminal_1_first_departure",
            _as_time(parameters.terminal_1_first_departure),
            "Giờ đầu bến 1",
        ),
        (
            "terminal_1_last_departure",
            _as_time(parameters.terminal_1_last_departure),
            "Giờ cuối bến 1",
        ),
        ("terminal_2_name", parameters.terminal_2_name, "Tên bến 2"),
        (
            "terminal_2_first_departure",
            _as_time(parameters.terminal_2_first_departure),
            "Giờ đầu bến 2",
        ),
        (
            "terminal_2_last_departure",
            _as_time(parameters.terminal_2_last_departure),
            "Giờ cuối bến 2",
        ),
        ("vehicle_capacity_passengers", parameters.capacity, "Bắt buộc; không tự suy đoán"),
        ("target_load_factor", parameters.target_load_factor, "Mặc định 85%"),
        ("maximum_load_factor", parameters.maximum_load_factor, "Trần khuyến nghị 90%"),
        ("time_block_minutes", parameters.time_block_minutes, "Chỉ 30 hoặc 60"),
        (
            "minimum_layover_minutes",
            parameters.effective_layover_minutes,
            "Không thấp hơn hard constraint",
        ),
    ]
    for row_index, row in enumerate(rows, 4):
        for column, value in enumerate(row, 1):
            ws.cell(row_index, column, value)
    _body_style(ws, 4, 3 + len(rows), 3)
    for row in range(4, 4 + len(rows)):
        key = ws.cell(row, 1).value
        if key and "departure" in key:
            ws.cell(row, 2).number_format = "HH:mm"
        if key and "load_factor" in key:
            ws.cell(row, 2).number_format = "0%"
    route_type_validation = DataValidation(
        type="list", formula1='"intra_provincial,inter_provincial"'
    )
    block_validation = DataValidation(type="list", formula1='"30,60"')
    positive_integer = DataValidation(type="whole", operator="greaterThan", formula1="0")
    load_factor_validation = DataValidation(
        type="decimal", operator="between", formula1="0.01", formula2="1"
    )
    ws.add_data_validation(route_type_validation)
    ws.add_data_validation(block_validation)
    ws.add_data_validation(positive_integer)
    ws.add_data_validation(load_factor_validation)
    key_rows = {ws.cell(row, 1).value: row for row in range(4, 4 + len(rows))}
    runtime_options_cell = ws.cell(key_rows["allowed_trip_runtime_minutes"], 2)
    runtime_options_cell.number_format = "@"
    runtime_list_validation = DataValidation(
        type="custom",
        formula1=f"=ISTEXT(B{runtime_options_cell.row})",
        allow_blank=False,
    )
    runtime_list_validation.errorTitle = "Phải nhập khoảng dạng văn bản"
    runtime_list_validation.error = (
        "Nhập hai đầu mút như 55,65 hoặc 55;65; mọi số nguyên ở giữa đều được phép."
    )
    runtime_list_validation.promptTitle = "Khoảng runtime bao gồm hai đầu"
    runtime_list_validation.prompt = (
        "Ví dụ: 55,65. Excel dùng dấu phẩy thập phân có thể nhập 55;65."
    )
    runtime_list_validation.showErrorMessage = True
    runtime_list_validation.showInputMessage = True
    ws.add_data_validation(runtime_list_validation)
    runtime_list_validation.add(runtime_options_cell)
    route_type_validation.add(ws.cell(key_rows["route_type"], 2))
    block_validation.add(ws.cell(key_rows["time_block_minutes"], 2))
    for key in (
        "trip_runtime_minutes",
        "total_daily_trips",
        "vehicle_capacity_passengers",
        "minimum_layover_minutes",
    ):
        positive_integer.add(ws.cell(key_rows[key], 2))
    for key in ("target_load_factor", "maximum_load_factor"):
        load_factor_validation.add(ws.cell(key_rows[key], 2))
    ws.freeze_panes = "A4"
    _autowidth(ws)


def _write_trip_input_sheet(ws, trips: list[Trip], parameters: ScenarioParameters) -> None:
    headers = [
        "scenario",
        "trip_id",
        "departure_terminal",
        "direction",
        "departure_time",
        "arrival_time",
        "vehicle_id",
        "vehicle_capacity_override",
    ]
    _title(ws, f"BIỂU ĐỒ SCENARIO {trips[0].scenario}", len(headers))
    _table_header(ws, 3, headers)
    for row_index, trip in enumerate(trips, 4):
        values = [
            trip.scenario,
            trip.trip_id,
            trip.departure_terminal,
            trip.direction.value,
            _as_time(trip.departure_seconds),
            _as_time(trip.resolved_arrival_seconds(parameters.default_trip_runtime_minutes)),
            None,
            None,
        ]
        for column, value in enumerate(values, 1):
            ws.cell(row_index, column, value)
        ws.cell(row_index, 5).number_format = "HH:mm"
        ws.cell(row_index, 6).number_format = "HH:mm"
    end_row = max(4, 3 + len(trips))
    _body_style(ws, 4, end_row, len(headers))
    direction_validation = DataValidation(type="list", formula1='"terminal_1_to_2,terminal_2_to_1"')
    terminal_validation = DataValidation(
        type="list",
        formula1=f'"{parameters.terminal_1_name},{parameters.terminal_2_name}"',
    )
    positive_integer = DataValidation(type="whole", operator="greaterThan", formula1="0")
    ws.add_data_validation(direction_validation)
    ws.add_data_validation(terminal_validation)
    ws.add_data_validation(positive_integer)
    direction_validation.add("D4:D1003")
    terminal_validation.add("C4:C1003")
    positive_integer.add("H4:H1003")
    ws.auto_filter.ref = f"A3:H{end_row}"
    ws.freeze_panes = "A4"
    _autowidth(ws)


def create_input_template(path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parameters_a, parameters_b = _sample_parameters()
    trips_a = _sample_trips("A", parameters_a)
    trips_b = _sample_trips("B", parameters_b, proposed=True)
    workbook = Workbook()
    workbook.remove(workbook.active)

    guide = workbook.create_sheet("HUONG_DAN")
    _title(guide, "HƯỚNG DẪN NHẬP DỮ LIỆU", 3)
    _table_header(guide, 3, ["Chủ đề", "Quy tắc", "Thao tác"])
    guide_rows = [
        (
            "Chế độ chỉ có B",
            "Tối thiểu cần THONG_SO_B và BIEU_DO_B; A, sản lượng và cấu hình là tùy chọn.",
            "Thiếu sản lượng thì C chỉ báo không đủ dữ liệu để tối ưu.",
        ),
        (
            "Tổng chuyến",
            "Là tổng lượt xuất bến của cả hai chiều trong một ngày.",
            "Luôn khai báo ở THONG_SO_B; THONG_SO_A chỉ dùng khi có Scenario A.",
        ),
        (
            "Sức chứa",
            "Tổng hành khách hợp pháp gồm ngồi và đứng; bắt buộc nhập.",
            "Không để trống vehicle_capacity_passengers.",
        ),
        (
            "Thời gian hành trình",
            "Khai báo cận dưới và cận trên trong allowed_trip_runtime_minutes, ví dụ 55,65.",
            (
                "Mọi số phút nguyên từ 55 đến 65, gồm cả 60 và 61, đều hợp lệ. Nếu Excel "
                "dùng dấu phẩy thập phân, nhập 55;65 để tránh bị đổi thành 55.65."
            ),
        ),
        (
            "Sản lượng",
            "Chọn total_observation_period nếu là tổng kỳ; average_day nếu đã là bình quân ngày.",
            "Nếu tổng kỳ, nhập đúng observation_days.",
        ),
        (
            "Không tách chiều",
            "Dùng direction = combined; hệ thống chỉ kết luận tổng hợp.",
            "Không diễn giải thành quá tải một chiều.",
        ),
        (
            "Target 85%",
            "Mức sức chứa hiệu dụng dùng để tính số chuyến cần thiết.",
            "Có thể chỉnh nhưng phải ≤ trần.",
        ),
        (
            "Trần 90%",
            "Block vượt trần là chưa phù hợp và được cảnh báo đỏ.",
            "Không dùng score để che vi phạm.",
        ),
        (
            "Quay đầu",
            "Tối thiểu 5 phút nội tỉnh, 15 phút liên tỉnh.",
            "Có thể nhập cao hơn nhưng không thấp hơn.",
        ),
        (
            "Giờ",
            "Dùng định dạng HH:mm; arrival có thể để trống khi import qua UI.",
            "Không sửa departure nguồn tự động.",
        ),
        (
            "Dữ liệu mẫu",
            "Workbook này có dữ liệu minh họa để chạy ngay.",
            "Thay thế các dòng mẫu bằng dữ liệu thật.",
        ),
    ]
    for row_index, row in enumerate(guide_rows, 4):
        for column, value in enumerate(row, 1):
            guide.cell(row_index, column, value)
    _body_style(guide, 4, 3 + len(guide_rows), 3)
    guide.freeze_panes = "A4"
    _autowidth(guide, 58)

    _write_parameter_sheet(workbook.create_sheet("THONG_SO_A"), parameters_a, "A")
    _write_trip_input_sheet(workbook.create_sheet("BIEU_DO_A"), trips_a, parameters_a)
    _write_parameter_sheet(workbook.create_sheet("THONG_SO_B"), parameters_b, "B")
    _write_trip_input_sheet(workbook.create_sheet("BIEU_DO_B"), trips_b, parameters_b)

    demand_sheet = workbook.create_sheet("SAN_LUONG")
    demand_headers = [
        "period_start",
        "period_end",
        "observation_days",
        "time_block_start",
        "time_block_end",
        "direction",
        "passenger_volume",
        "volume_type",
    ]
    _title(demand_sheet, "SẢN LƯỢNG HÀNH KHÁCH", len(demand_headers))
    _table_header(demand_sheet, 3, demand_headers)
    daily_profile = [40, 105, 95, 45, 35, 30, 35, 40, 50, 90, 105, 55, 25]
    row_index = 4
    for direction_index, direction in enumerate(
        (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    ):
        for block_index, daily_volume in enumerate(daily_profile):
            start_seconds = (6 + block_index) * 3600
            adjusted_daily = daily_volume * (0.92 if direction_index else 1)
            row = [
                date(2026, 7, 1),
                date(2026, 7, 15),
                15,
                _as_time(start_seconds),
                _as_time(start_seconds + 3600),
                direction.value,
                round(adjusted_daily * 15),
                "total_observation_period",
            ]
            for column, value in enumerate(row, 1):
                demand_sheet.cell(row_index, column, value)
            for column in (1, 2):
                demand_sheet.cell(row_index, column).number_format = "dd/mm/yyyy"
            for column in (4, 5):
                demand_sheet.cell(row_index, column).number_format = "HH:mm"
            row_index += 1
    _body_style(demand_sheet, 4, row_index - 1, len(demand_headers))
    direction_validation = DataValidation(
        type="list", formula1='"terminal_1_to_2,terminal_2_to_1,combined"'
    )
    volume_validation = DataValidation(
        type="list", formula1='"total_observation_period,average_day"'
    )
    positive_integer = DataValidation(type="whole", operator="greaterThan", formula1="0")
    demand_sheet.add_data_validation(direction_validation)
    demand_sheet.add_data_validation(volume_validation)
    demand_sheet.add_data_validation(positive_integer)
    direction_validation.add("F4:F1003")
    volume_validation.add("H4:H1003")
    positive_integer.add("C4:C1003")
    demand_sheet.auto_filter.ref = f"A3:H{row_index - 1}"
    demand_sheet.freeze_panes = "A4"
    _autowidth(demand_sheet)

    config = workbook.create_sheet("CAU_HINH")
    _title(config, "CẤU HÌNH MVP", 3)
    _table_header(config, 3, ["Tham số", "Giá trị", "Ghi chú"])
    config_rows = [
        ("final_service_block_minutes", 90, "Block cuối ngày"),
        ("diagram_time_direction", "left_to_right", "Giờ tăng từ trái sang phải trên trục X"),
        ("combined_direction_policy", "do_not_infer", "Không tự suy đoán theo chiều"),
        ("generator_mode", "deterministic", "Không dùng số ngẫu nhiên/AI"),
        ("scoring_config", "config/scoring.json", "Trọng số tập trung"),
        ("direction_trip_lock_mode", "fixed_by_direction", "Giữ tổng chuyến từng chiều của B"),
        ("lock_first_departures", True, "Khóa chuyến đầu mỗi bến"),
        ("lock_last_departures", True, "Khóa chuyến cuối mỗi bến"),
        ("headway_rounding_tolerance_minutes", 1, "Balanced rounding trong regime"),
        ("minimum_departures_per_normal_regime", 3, "Quy mô regime bình thường"),
        ("minimum_regime_duration_minutes", 60, "Thời lượng regime bình thường"),
        ("maximum_headway_regimes_per_direction", 6, "Giới hạn regime mỗi chiều"),
        ("maximum_transition_headways_per_boundary", 1, "Một headway chuyển tiếp mỗi ranh giới"),
        ("maximum_transition_deviation_minutes", 5, "Dung sai headway chuyển tiếp"),
        ("minimum_sustained_change_intervals", 2, "Không phản ứng với nhiễu một block"),
        ("minimum_material_headway_change_minutes", 5, "Biến đổi tần suất đáng kể"),
        ("minimum_material_service_rate_change_ratio", 0.15, "Biến đổi suất phục vụ đáng kể"),
        ("preferred_max_shift_per_trip_minutes", 15, "Mức dịch chuyển ưu tiên"),
        ("absolute_max_shift_per_trip_minutes", 30, "Giới hạn dịch chuyển tuyệt đối"),
        ("configuration_version", "scenario_c_regimes_v1", "Phiên bản cấu hình C"),
    ]
    for row_number, row in enumerate(config_rows, 4):
        for column, value in enumerate(row, 1):
            config.cell(row_number, column, value)
    _body_style(config, 4, 3 + len(config_rows), 3)
    _autowidth(config)
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.save(output_path)
    return output_path


def _peak_and_offpeak_headway(result: ScenarioResult) -> tuple[float | None, float | None]:
    usable = [block for block in result.evaluation.blocks if block.headway.mean_minutes is not None]
    if not usable:
        return None, None
    demands = sorted(block.demand for block in usable)
    threshold = demands[max(0, int(len(demands) * 0.75) - 1)]
    peak = [block.headway.mean_minutes for block in usable if block.demand >= threshold]
    offpeak = [block.headway.mean_minutes for block in usable if block.demand < threshold]
    return mean(peak) if peak else None, mean(offpeak) if offpeak else None


def _write_result_schedule_sheet(ws, result: ScenarioResult, title: str) -> None:
    _title(ws, title, 8)
    summary = [
        ("Kết luận tổng thể", result.evaluation.overall_status.value),
        ("Sức chứa phương tiện", result.parameters.capacity),
        ("Target load factor", result.parameters.target_load_factor),
        ("Maximum load factor", result.parameters.maximum_load_factor),
        ("Số xe tối thiểu", result.fleet.minimum_vehicles),
    ]
    for row_index, (label, value) in enumerate(summary, 2):
        ws.cell(row_index, 1, label).font = Font(name="Aptos", bold=True, color=MUTED)
        ws.cell(row_index, 2, value)
    ws["B4"].number_format = "0%"
    ws["B5"].number_format = "0%"
    metadata = [
        (
            "Tên phương án",
            result.display_name or result.name,
        ),
        ("Mã chiến lược", result.strategy_id or "—"),
        (
            "Giới hạn đội xe",
            result.resource_fleet_limit if result.resource_fleet_limit is not None else "—",
        ),
    ]
    for row_index, (label, value) in enumerate(metadata, 2):
        ws.cell(row_index, 4, label).font = Font(name="Aptos", bold=True, color=MUTED)
        ws.cell(row_index, 5, value)
    headers = [
        "trip_id",
        "Bến xuất phát",
        "Chiều",
        "Giờ đi",
        "Giờ đến",
        "Xe gán",
        "Sức chứa",
        "Ghi chú",
    ]
    _table_header(ws, 8, headers)
    assigned = {item.trip_id: item.vehicle_id for item in result.fleet.assignments}
    for row_index, trip in enumerate(result.trips, 9):
        row = [
            trip.trip_id,
            trip.departure_terminal,
            trip.direction.value,
            excel_time_fraction(trip.departure_seconds),
            excel_time_fraction(
                trip.resolved_arrival_seconds(result.parameters.default_trip_runtime_minutes)
            ),
            assigned.get(trip.trip_id),
            trip.vehicle_capacity_override or result.parameters.capacity,
            result.recommendation_reason if row_index == 9 else "",
        ]
        for column, value in enumerate(row, 1):
            ws.cell(row_index, column, value)
        ws.cell(row_index, 4).number_format = "HH:mm"
        ws.cell(row_index, 5).number_format = "HH:mm"
    end_row = max(9, 8 + len(result.trips))
    _body_style(ws, 9, end_row, len(headers))
    ws.auto_filter.ref = f"A8:H{end_row}"
    ws.freeze_panes = "A9"
    _autowidth(ws, 50)


def export_results(bundle: AnalysisBundle, path: str | Path) -> Path:
    result_b = bundle.get("B")
    result_c = bundle.get("C")
    if result_b is not None and result_c is not None:
        if result_b.trips is result_c.trips:
            raise ValueError("Từ chối export vì B và C dùng chung list chuyến")
        b_times = sorted((trip.direction.value, trip.departure_seconds) for trip in result_b.trips)
        c_times = sorted((trip.direction.value, trip.departure_seconds) for trip in result_c.trips)
        if b_times == c_times and result_c.generation_status not in {
            ScenarioCStatus.NO_BETTER_REDISTRIBUTION,
            ScenarioCStatus.INFEASIBLE_FIXED_RESOURCES,
            ScenarioCStatus.INSUFFICIENT_DATA,
        }:
            raise ValueError(
                "Từ chối export C trùng B khi không có trạng thái no-improvement rõ ràng"
            )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.remove(workbook.active)
    overview = workbook.create_sheet("TONG_QUAN")
    schedule_sheet_names: dict[str, str] = {}
    for result in bundle.scenarios:
        sheet_name = (
            f"DANH_GIA_{result.name}" if result.name in {"A", "B"} else f"KHUYEN_NGHI_{result.name}"
        )
        schedule_sheet_names[result.name] = sheet_name
        sheet = workbook.create_sheet(sheet_name)
        _write_result_schedule_sheet(
            sheet,
            result,
            (
                "C — TÁI PHÂN BỔ ỔN ĐỊNH THEO NHU CẦU"
                if result.name == "C"
                else f"{'ĐÁNH GIÁ' if result.name in {'A', 'B'} else 'KHUYẾN NGHỊ'} SCENARIO {result.name}"
            ),
        )

    block_sheet = workbook.create_sheet("DANH_GIA_THEO_BLOCK")
    block_headers = [
        "Scenario",
        "Bắt đầu",
        "Kết thúc",
        "Chiều",
        "Số chuyến",
        "Sức cung danh nghĩa",
        "Sức cung target",
        "Sức cung trần",
        "Nhu cầu/ngày",
        "Load factor",
        "Chuyến cần",
        "Chênh lệch chuyến",
        "Trạng thái",
        "Headway TB (liên tục)",
        "Headway min (liên tục)",
        "Headway max (liên tục)",
        "Độ lệch chuẩn",
        "Hệ số biến thiên",
        "Ghi chú dữ liệu",
    ]
    _title(block_sheet, "ĐÁNH GIÁ THEO BLOCK", len(block_headers))
    _table_header(block_sheet, 3, block_headers)
    row_index = 4
    for result in bundle.scenarios:
        for block in result.evaluation.blocks:
            row = [
                result.name,
                excel_time_fraction(block.block_start_seconds),
                excel_time_fraction(block.block_end_seconds),
                block.direction.value,
                block.trips,
                block.nominal_capacity,
                block.target_capacity,
                block.maximum_recommended_capacity,
                block.demand,
                block.load_factor,
                block.required_trips,
                block.trip_gap_to_target,
                block.status.value,
                block.headway.mean_minutes,
                block.headway.minimum_minutes,
                block.headway.maximum_minutes,
                block.headway.standard_deviation_minutes,
                block.headway.coefficient_of_variation,
                block.data_note,
            ]
            for column, value in enumerate(row, 1):
                block_sheet.cell(row_index, column, value)
            for column in (2, 3):
                block_sheet.cell(row_index, column).number_format = "HH:mm"
            for column in (10, 18):
                block_sheet.cell(row_index, column).number_format = "0.0%"
            row_index += 1
    block_data_end = row_index - 1
    _body_style(block_sheet, 4, block_data_end, len(block_headers))
    block_sheet.auto_filter.ref = f"A3:S{max(3, block_data_end)}"
    block_sheet.freeze_panes = "A4"
    if block_data_end >= 4:
        block_sheet.conditional_formatting.add(
            f"M4:M{block_data_end}",
            FormulaRule(
                formula=['ISNUMBER(SEARCH("CHƯA",M4))'],
                fill=PatternFill("solid", fgColor=RED),
            ),
        )
        block_sheet.conditional_formatting.add(
            f"M4:M{block_data_end}",
            FormulaRule(
                formula=['ISNUMBER(SEARCH("THEO DÕI",M4))'],
                fill=PatternFill("solid", fgColor=AMBER),
            ),
        )
    _autowidth(block_sheet, 46)

    headway_sheet = workbook.create_sheet("HEADWAY_LIEN_TUC")
    headway_headers = [
        "Scenario",
        "Mã chiến lược",
        "Chiều",
        "Chuyến trước",
        "Chuyến sau",
        "Giờ chuyến trước",
        "Giờ chuyến sau",
        "Headway (phút)",
        "Block của chuyến trước",
        "Block của chuyến sau",
        "Qua ranh giới block",
    ]
    _title(headway_sheet, "HEADWAY LIÊN TỤC THEO CHIỀU", len(headway_headers))
    _table_header(headway_sheet, 3, headway_headers)
    headway_row = 4
    for result in bundle.scenarios:
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
            ordered = sorted(
                (trip for trip in result.trips if trip.direction == direction),
                key=lambda trip: (trip.departure_seconds, trip.trip_id),
            )
            for previous, current in zip(ordered, ordered[1:], strict=False):
                previous_block = next(
                    (
                        block_label(block.block_start_seconds, block.block_end_seconds)
                        for block in result.evaluation.blocks
                        if block.direction in {direction, Direction.COMBINED}
                        and block.block_start_seconds
                        <= previous.departure_seconds
                        < block.block_end_seconds
                    ),
                    "Ngoài block nhu cầu",
                )
                current_block = next(
                    (
                        block_label(block.block_start_seconds, block.block_end_seconds)
                        for block in result.evaluation.blocks
                        if block.direction in {direction, Direction.COMBINED}
                        and block.block_start_seconds
                        <= current.departure_seconds
                        < block.block_end_seconds
                    ),
                    "Ngoài block nhu cầu",
                )
                values = [
                    result.name,
                    result.strategy_id or "—",
                    direction.value,
                    previous.trip_id,
                    current.trip_id,
                    excel_time_fraction(previous.departure_seconds),
                    excel_time_fraction(current.departure_seconds),
                    (current.departure_seconds - previous.departure_seconds) / 60,
                    previous_block,
                    current_block,
                    "Có" if previous_block != current_block else "Không",
                ]
                for column, value in enumerate(values, 1):
                    headway_sheet.cell(headway_row, column, value)
                for column in (6, 7):
                    headway_sheet.cell(headway_row, column).number_format = "HH:mm"
                headway_sheet.cell(headway_row, 8).number_format = "0.0"
                headway_row += 1
    _body_style(headway_sheet, 4, headway_row - 1, len(headway_headers))
    headway_sheet.auto_filter.ref = f"A3:K{headway_row - 1}"
    headway_sheet.freeze_panes = "A4"
    _autowidth(headway_sheet, 42)

    load_sheet = workbook.create_sheet("LOAD_FACTOR")
    load_headers = [
        "Scenario",
        "Block bắt đầu",
        "Block kết thúc",
        "Chiều",
        "Nhu cầu",
        "Số chuyến",
        "Load factor",
        "Target",
        "Maximum",
        "Trạng thái",
    ]
    _title(load_sheet, "LOAD FACTOR", len(load_headers))
    _table_header(load_sheet, 3, load_headers)
    load_row = 4
    for result in bundle.scenarios:
        for block in result.evaluation.blocks:
            values = [
                result.name,
                excel_time_fraction(block.block_start_seconds),
                excel_time_fraction(block.block_end_seconds),
                block.direction.value,
                block.demand,
                block.trips,
                block.load_factor,
                result.parameters.target_load_factor,
                result.parameters.maximum_load_factor,
                block.status.value,
            ]
            for column, value in enumerate(values, 1):
                load_sheet.cell(load_row, column, value)
            for column in (2, 3):
                load_sheet.cell(load_row, column).number_format = "HH:mm"
            for column in (7, 8, 9):
                load_sheet.cell(load_row, column).number_format = "0.0%"
            load_row += 1
    load_data_end = load_row - 1
    _body_style(load_sheet, 4, load_data_end, len(load_headers))
    load_sheet.auto_filter.ref = f"A3:J{max(3, load_data_end)}"
    load_sheet.freeze_panes = "A4"
    if load_data_end >= 4:
        load_sheet.conditional_formatting.add(
            f"G4:G{load_data_end}",
            FormulaRule(formula=["$G4>$I4"], fill=PatternFill("solid", fgColor=RED)),
        )
        load_sheet.conditional_formatting.add(
            f"G4:G{load_data_end}",
            FormulaRule(
                formula=["AND($G4>$H4,$G4<=$I4)"],
                fill=PatternFill("solid", fgColor=AMBER),
            ),
        )
    _autowidth(load_sheet)

    fleet_sheet = workbook.create_sheet("PHAN_CONG_XE")
    fleet_headers = [
        "Scenario",
        "Xe",
        "trip_id",
        "Chiều",
        "Bến đi",
        "Bến đến",
        "Giờ đi",
        "Giờ đến",
        "Sẵn sàng tiếp",
        "Chờ tại bến (phút)",
    ]
    _title(fleet_sheet, "PHÂN CÔNG VÀ VÒNG XE", len(fleet_headers))
    _table_header(fleet_sheet, 3, fleet_headers)
    fleet_row = 4
    for result in bundle.scenarios:
        for assignment in result.fleet.assignments:
            values = [
                result.name,
                assignment.vehicle_id,
                assignment.trip_id,
                assignment.direction.value,
                assignment.departure_terminal,
                assignment.arrival_terminal,
                excel_time_fraction(assignment.departure_seconds),
                excel_time_fraction(assignment.arrival_seconds),
                excel_time_fraction(assignment.ready_seconds),
                assignment.waiting_minutes,
            ]
            for column, value in enumerate(values, 1):
                fleet_sheet.cell(fleet_row, column, value)
            for column in (7, 8, 9):
                fleet_sheet.cell(fleet_row, column).number_format = "HH:mm"
            fleet_sheet.cell(fleet_row, 10).number_format = "0.0"
            fleet_row += 1
    _body_style(fleet_sheet, 4, fleet_row - 1, len(fleet_headers))
    fleet_sheet.auto_filter.ref = f"A3:J{fleet_row - 1}"
    fleet_sheet.freeze_panes = "A4"
    _autowidth(fleet_sheet)

    errors_sheet = workbook.create_sheet("LOI_KY_THUAT")
    error_headers = [
        "Scenario",
        "Trạng thái",
        "Mã lỗi",
        "Mức độ",
        "Nội dung",
        "Chuyến liên quan",
        "Block",
        "Đề xuất sửa",
    ]
    _title(errors_sheet, "LỖI KỸ THUẬT", len(error_headers))
    _table_header(errors_sheet, 3, error_headers)
    error_row = 4
    for result in bundle.scenarios:
        if not result.validation.issues:
            values = [result.name, "PASS", "", "INFO", "Không phát hiện lỗi.", "", "", ""]
            for column, value in enumerate(values, 1):
                errors_sheet.cell(error_row, column, value)
            error_row += 1
        for issue in result.validation.issues:
            values = [
                result.name,
                result.validation.status,
                issue.code,
                issue.severity.value,
                issue.message,
                ", ".join(issue.trip_ids),
                issue.block,
                issue.suggestion,
            ]
            for column, value in enumerate(values, 1):
                errors_sheet.cell(error_row, column, value)
            error_row += 1
    _body_style(errors_sheet, 4, error_row - 1, len(error_headers))
    errors_sheet.auto_filter.ref = f"A3:H{error_row - 1}"
    errors_sheet.freeze_panes = "A4"
    errors_sheet.conditional_formatting.add(
        f"D4:D{error_row - 1}",
        FormulaRule(
            formula=['OR(D4="BLOCKING",D4="ERROR")'], fill=PatternFill("solid", fgColor=RED)
        ),
    )
    _autowidth(errors_sheet, 58)

    limitations_sheet = workbook.create_sheet("GIOI_HAN_DU_LIEU")
    _title(limitations_sheet, "GIỚI HẠN DỮ LIỆU VÀ GIẢ ĐỊNH", 3)
    _table_header(limitations_sheet, 3, ["Loại", "Nội dung", "Ảnh hưởng"])
    limitation_rows = [
        ("Giới hạn", limitation, "Không diễn giải vượt quá cấp dữ liệu sẵn có")
        for limitation in bundle.limitations
    ]
    limitation_rows.extend(
        ("Generator", reason, "Không tạo kết quả giả") for reason in bundle.generation.reasons
    )
    if bundle.generation.missing_trips:
        limitation_rows.append(
            (
                "Nhu cầu",
                f"Thiếu tối thiểu {bundle.generation.missing_trips} chuyến so với target.",
                "C giữ tổng chuyến và số xe hoạt động của B; C2 tăng chuyến có ghi rõ.",
            )
        )
    c_result = bundle.get("C")
    if c_result is not None:
        limitation_rows.append(
            (
                "C",
                "Tái phân bổ theo chế độ giãn cách liên tục; block nhu cầu không phải ranh giới chế độ.",
                (
                    f"Giữ tổng chuyến B và {c_result.active_vehicle_count} xe hoạt động."
                    if c_result.active_vehicle_count is not None
                    else "Giữ giới hạn nguồn lực của B."
                ),
            )
        )
    if not limitation_rows:
        limitation_rows.append(("Thông tin", "Không có giới hạn dữ liệu nổi bật.", ""))
    for row_number, row in enumerate(limitation_rows, 4):
        for column, value in enumerate(row, 1):
            limitations_sheet.cell(row_number, column, value)
    _body_style(limitations_sheet, 4, 3 + len(limitation_rows), 3)
    limitations_sheet.freeze_panes = "A4"
    _autowidth(limitations_sheet, 72)

    config_sheet = workbook.create_sheet("CAU_HINH_DA_DUNG")
    _title(config_sheet, "CẤU HÌNH ĐÃ DÙNG", 4)
    _table_header(config_sheet, 3, ["Phạm vi", "Tham số", "Giá trị", "Ghi chú"])
    config_rows: list[tuple[object, ...]] = []
    for result in bundle.scenarios:
        params = result.parameters
        config_rows.extend(
            [
                (result.name, "route_type", params.route_type.value, ""),
                (
                    result.name,
                    "allowed_trip_runtime_minutes",
                    params.runtime_options_text,
                    "Khoảng min,max bao gồm hai đầu",
                ),
                (
                    result.name,
                    "trip_runtime_minutes",
                    params.default_trip_runtime_minutes,
                    "Mặc định khi thiếu arrival_time",
                ),
                (result.name, "total_daily_trips", params.total_daily_trips, "Tổng hai chiều"),
                (result.name, "vehicle_capacity_passengers", params.capacity, "Input bắt buộc"),
                (result.name, "target_load_factor", params.target_load_factor, ""),
                (result.name, "maximum_load_factor", params.maximum_load_factor, ""),
                (result.name, "minimum_layover_minutes", params.effective_layover_minutes, ""),
                (result.name, "time_block_minutes", params.time_block_minutes, ""),
            ]
        )
        if result.strategy_id:
            config_rows.append((result.name, "strategy_id", result.strategy_id, "Mã chiến lược"))
        if result.resource_fleet_limit is not None:
            config_rows.append(
                (
                    result.name,
                    "resource_fleet_limit",
                    result.resource_fleet_limit,
                    "Không được vượt đội xe khả dụng của B",
                )
            )
    scoring = load_scoring_config()
    for key, value in scoring["weights"].items():
        config_rows.append(("SCORING", key, value, "config/scoring.json"))
    for row_number, row in enumerate(config_rows, 4):
        for column, value in enumerate(row, 1):
            config_sheet.cell(row_number, column, value)
        if "load_factor" in str(row[1]):
            config_sheet.cell(row_number, 3).number_format = "0%"
    _body_style(config_sheet, 4, 3 + len(config_rows), 4)
    config_sheet.freeze_panes = "A4"
    _autowidth(config_sheet)

    _title(overview, "TỔNG QUAN SO SÁNH PHƯƠNG ÁN", 12)
    overview_headers = [
        "Scenario",
        "Tổng chuyến",
        "Sức chứa",
        "Target",
        "Maximum",
        "Headway liên tục — cao điểm",
        "Headway liên tục — thấp điểm",
        "Số xe tối thiểu",
        "Block trên target",
        "Block trên maximum",
        "Score",
        "Kết luận",
    ]
    _table_header(overview, 3, overview_headers)
    for row_number, result in enumerate(bundle.scenarios, 4):
        peak, offpeak = _peak_and_offpeak_headway(result)
        detail_sheet = schedule_sheet_names[result.name]
        values = [
            result.name,
            f"=COUNTA('{detail_sheet}'!$A$9:$A$1008)",
            f"='{detail_sheet}'!$B$3",
            f"='{detail_sheet}'!$B$4",
            f"='{detail_sheet}'!$B$5",
            peak,
            offpeak,
            result.fleet.minimum_vehicles,
            (
                f"=COUNTIFS('LOAD_FACTOR'!$A$4:$A${load_data_end},$A{row_number},"
                f"'LOAD_FACTOR'!$G$4:$G${load_data_end},\">\"&$D{row_number})"
                if load_data_end >= 4
                else 0
            ),
            (
                f"=COUNTIFS('LOAD_FACTOR'!$A$4:$A${load_data_end},$A{row_number},"
                f"'LOAD_FACTOR'!$G$4:$G${load_data_end},\">\"&$E{row_number})"
                if load_data_end >= 4
                else 0
            ),
            result.score,
            result.evaluation.overall_status.value,
        ]
        for column, value in enumerate(values, 1):
            overview.cell(row_number, column, value)
        for column in (4, 5):
            overview.cell(row_number, column).number_format = "0%"
        for column in (6, 7):
            overview.cell(row_number, column).number_format = "0.0"
        overview.cell(row_number, 11).number_format = "0.0"
    overview_end = 3 + len(bundle.scenarios)
    _body_style(overview, 4, overview_end, len(overview_headers))
    overview.freeze_panes = "A4"
    overview.conditional_formatting.add(
        f"L4:L{overview_end}",
        FormulaRule(
            formula=['ISNUMBER(SEARCH("CHƯA",L4))'], fill=PatternFill("solid", fgColor=RED)
        ),
    )
    overview.conditional_formatting.add(
        f"L4:L{overview_end}",
        FormulaRule(
            formula=['ISNUMBER(SEARCH("THEO DÕI",L4))'], fill=PatternFill("solid", fgColor=AMBER)
        ),
    )
    overview.conditional_formatting.add(
        f"L4:L{overview_end}",
        FormulaRule(formula=['L4="PHÙ HỢP"'], fill=PatternFill("solid", fgColor=GREEN)),
    )
    overview.sheet_properties.pageSetUpPr.fitToPage = True
    overview.page_setup.fitToWidth = 1
    _autowidth(overview, 34)
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    workbook.save(output_path)
    return output_path

from __future__ import annotations

from collections import Counter, defaultdict

from .models import (
    Direction,
    ScenarioParameters,
    Severity,
    Trip,
    ValidationIssue,
    ValidationReport,
)
from .time_utils import block_label, format_hhmm


def _issue(
    code: str,
    severity: Severity,
    message: str,
    *,
    trip_ids: tuple[str, ...] = (),
    block: str | None = None,
    suggestion: str,
) -> ValidationIssue:
    return ValidationIssue(code, severity, message, trip_ids, block, suggestion)


def _validate_parameters(parameters: ScenarioParameters) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if parameters.vehicle_capacity_passengers is None:
        issues.append(
            _issue(
                "MISSING_VEHICLE_CAPACITY",
                Severity.BLOCKING,
                "Chưa khai báo sức chứa phương tiện.",
                suggestion="Nhập số hành khách hợp pháp lớn hơn 0.",
            )
        )
    elif parameters.vehicle_capacity_passengers <= 0:
        issues.append(
            _issue(
                "INVALID_VEHICLE_CAPACITY",
                Severity.BLOCKING,
                "Sức chứa phương tiện phải là số nguyên dương.",
                suggestion="Nhập lại sức chứa phương tiện.",
            )
        )
    if not parameters.runtime_options or any(
        runtime <= 0 for runtime in parameters.runtime_options
    ):
        issues.append(
            _issue(
                "INVALID_RUNTIME",
                Severity.BLOCKING,
                "Khoảng thời gian hành trình phải gồm các số nguyên dương.",
                suggestion="Nhập hai đầu mút của khoảng, ví dụ 55,65.",
            )
        )
    if parameters.total_daily_trips <= 0:
        issues.append(
            _issue(
                "INVALID_TOTAL_TRIPS",
                Severity.BLOCKING,
                "Tổng số chuyến phải lớn hơn 0.",
                suggestion="Nhập tổng lượt xuất bến của cả hai chiều.",
            )
        )
    if parameters.time_block_minutes not in {30, 60}:
        issues.append(
            _issue(
                "INVALID_TIME_BLOCK",
                Severity.BLOCKING,
                "Block thời gian chỉ được là 30 hoặc 60 phút.",
                suggestion="Chọn 30 hoặc 60 phút.",
            )
        )
    if not 0 < parameters.target_load_factor <= parameters.maximum_load_factor <= 1:
        issues.append(
            _issue(
                "INVALID_LOAD_FACTOR_THRESHOLDS",
                Severity.BLOCKING,
                "Cần thỏa 0 < target ≤ maximum ≤ 1.",
                suggestion="Kiểm tra target load factor và maximum load factor.",
            )
        )
    if parameters.effective_layover_minutes < parameters.regulatory_minimum_layover_minutes:
        issues.append(
            _issue(
                "LAYOVER_BELOW_REGULATORY_MINIMUM",
                Severity.BLOCKING,
                (
                    f"Thời gian quay đầu {parameters.effective_layover_minutes} phút thấp hơn "
                    f"mức tối thiểu {parameters.regulatory_minimum_layover_minutes} phút."
                ),
                suggestion="Tăng thời gian quay đầu tối thiểu.",
            )
        )
    for terminal, first, last in (
        (
            parameters.terminal_1_name,
            parameters.terminal_1_first_departure,
            parameters.terminal_1_last_departure,
        ),
        (
            parameters.terminal_2_name,
            parameters.terminal_2_first_departure,
            parameters.terminal_2_last_departure,
        ),
    ):
        if first > last:
            issues.append(
                _issue(
                    "INVALID_SERVICE_WINDOW",
                    Severity.BLOCKING,
                    f"Giờ đầu lớn hơn giờ cuối tại {terminal}.",
                    suggestion="Khai báo lại cửa sổ khai thác trong cùng một ngày dịch vụ.",
                )
            )
    return issues


def _validate_vehicle_chains(
    trips: list[Trip], parameters: ScenarioParameters
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_vehicle: dict[str, list[Trip]] = defaultdict(list)
    for trip in trips:
        if trip.vehicle_id:
            by_vehicle[trip.vehicle_id].append(trip)
    for vehicle_id, assigned in sorted(by_vehicle.items()):
        ordered = sorted(assigned, key=lambda item: (item.departure_seconds, item.trip_id))
        previous: Trip | None = None
        for trip in ordered:
            if previous is not None:
                previous_arrival = previous.resolved_arrival_seconds(
                    parameters.default_trip_runtime_minutes
                )
                ready = previous_arrival + parameters.effective_layover_minutes * 60
                expected_terminal = parameters.opposite_terminal(previous.departure_terminal)
                if trip.departure_terminal != expected_terminal:
                    issues.append(
                        _issue(
                            "VEHICLE_LOCATION_CONFLICT",
                            Severity.ERROR,
                            (
                                f"Xe {vehicle_id} không ở đúng bến cho chuyến {trip.trip_id}; "
                                "MVP không giả định chạy rỗng."
                            ),
                            trip_ids=(previous.trip_id, trip.trip_id),
                            suggestion="Đổi xe hoặc sắp xếp lại chuỗi chuyến.",
                        )
                    )
                if trip.departure_seconds < ready:
                    issues.append(
                        _issue(
                            "LAYOVER_VIOLATION",
                            Severity.ERROR,
                            (
                                f"Xe {vehicle_id} cần sẵn sàng lúc {format_hhmm(ready)} nhưng "
                                f"chuyến {trip.trip_id} xuất bến lúc "
                                f"{format_hhmm(trip.departure_seconds)}."
                            ),
                            trip_ids=(previous.trip_id, trip.trip_id),
                            block=block_label(previous.departure_seconds, trip.departure_seconds),
                            suggestion="Lùi chuyến sau, tăng xe hoặc đổi phân công xe.",
                        )
                    )
            previous = trip
    return issues


def validate_schedule(trips: list[Trip], parameters: ScenarioParameters) -> ValidationReport:
    issues = _validate_parameters(parameters)
    counts = Counter(trip.trip_id for trip in trips)
    duplicates = tuple(sorted(trip_id for trip_id, count in counts.items() if count > 1))
    if duplicates:
        issues.append(
            _issue(
                "DUPLICATE_TRIP_ID",
                Severity.ERROR,
                f"Trùng mã chuyến: {', '.join(duplicates)}.",
                trip_ids=duplicates,
                suggestion="Đặt trip_id duy nhất cho từng chuyến.",
            )
        )
    if len(trips) != parameters.total_daily_trips:
        issues.append(
            _issue(
                "TRIP_COUNT_MISMATCH",
                Severity.ERROR,
                (
                    f"Timetable có {len(trips)} chuyến, khác tổng khai báo "
                    f"{parameters.total_daily_trips} chuyến."
                ),
                suggestion="Bổ sung/xóa chuyến hoặc sửa tổng chuyến khai báo.",
            )
        )

    windows = {
        parameters.terminal_1_name: (
            parameters.terminal_1_first_departure,
            parameters.terminal_1_last_departure,
            Direction.TERMINAL_1_TO_2,
        ),
        parameters.terminal_2_name: (
            parameters.terminal_2_first_departure,
            parameters.terminal_2_last_departure,
            Direction.TERMINAL_2_TO_1,
        ),
    }
    departures_by_terminal: dict[str, list[Trip]] = defaultdict(list)
    for trip in trips:
        if trip.departure_terminal not in windows:
            issues.append(
                _issue(
                    "UNKNOWN_TERMINAL",
                    Severity.ERROR,
                    f"Chuyến {trip.trip_id} xuất phát từ bến không thuộc tuyến.",
                    trip_ids=(trip.trip_id,),
                    suggestion="Dùng đúng tên bến trong sheet thông số.",
                )
            )
            continue
        first, last, expected_direction = windows[trip.departure_terminal]
        departures_by_terminal[trip.departure_terminal].append(trip)
        if trip.direction != expected_direction:
            issues.append(
                _issue(
                    "DIRECTION_TERMINAL_MISMATCH",
                    Severity.ERROR,
                    f"Chiều của chuyến {trip.trip_id} không khớp bến xuất phát.",
                    trip_ids=(trip.trip_id,),
                    suggestion="Sửa direction hoặc departure_terminal.",
                )
            )
        if not first <= trip.departure_seconds <= last:
            issues.append(
                _issue(
                    "OUTSIDE_SERVICE_WINDOW",
                    Severity.ERROR,
                    (
                        f"Chuyến {trip.trip_id} lúc {format_hhmm(trip.departure_seconds)} nằm ngoài "
                        f"{format_hhmm(first)}–{format_hhmm(last)}."
                    ),
                    trip_ids=(trip.trip_id,),
                    block=block_label(first, last),
                    suggestion="Đưa chuyến vào cửa sổ khai thác mà không sửa dữ liệu nguồn.",
                )
            )
        arrival = trip.resolved_arrival_seconds(parameters.default_trip_runtime_minutes)
        runtime_seconds = arrival - trip.departure_seconds
        runtime_minutes = runtime_seconds / 60
        if (
            runtime_seconds <= 0
            or runtime_seconds % 60 != 0
            or not parameters.accepts_trip_runtime(int(runtime_minutes))
        ):
            allowed = parameters.runtime_range_text
            issues.append(
                _issue(
                    "INVALID_TRIP_RUNTIME",
                    Severity.ERROR,
                    (
                        f"Thời gian hành trình chuyến {trip.trip_id} là "
                        f"{runtime_minutes:g} phút; ngoài khoảng cho phép {allowed} phút."
                    ),
                    trip_ids=(trip.trip_id,),
                    suggestion=(
                        "Để trống arrival_time để dùng giá trị mặc định lớn nhất, hoặc sửa "
                        f"arrival_time để thời lượng nằm trong khoảng {allowed} phút."
                    ),
                )
            )
        if trip.vehicle_capacity_override is not None and trip.vehicle_capacity_override <= 0:
            issues.append(
                _issue(
                    "INVALID_CAPACITY_OVERRIDE",
                    Severity.ERROR,
                    f"Sức chứa riêng của chuyến {trip.trip_id} không hợp lệ.",
                    trip_ids=(trip.trip_id,),
                    suggestion="Để trống hoặc nhập số nguyên dương.",
                )
            )

    for terminal, (expected_first, expected_last, _) in windows.items():
        terminal_trips = departures_by_terminal.get(terminal, [])
        if not terminal_trips:
            issues.append(
                _issue(
                    "NO_DEPARTURE_AT_TERMINAL",
                    Severity.ERROR,
                    f"Không có chuyến xuất phát tại {terminal}.",
                    suggestion="Bổ sung ít nhất chuyến đầu và chuyến cuối tại bến.",
                )
            )
            continue
        actual_first = min(item.departure_seconds for item in terminal_trips)
        actual_last = max(item.departure_seconds for item in terminal_trips)
        if actual_first != expected_first:
            issues.append(
                _issue(
                    "FIRST_DEPARTURE_MISMATCH",
                    Severity.ERROR,
                    (
                        f"Chuyến đầu tại {terminal} là {format_hhmm(actual_first)}, "
                        f"không phải {format_hhmm(expected_first)}."
                    ),
                    suggestion="Giữ một chuyến đúng giờ bắt đầu đã khai báo.",
                )
            )
        if actual_last != expected_last:
            issues.append(
                _issue(
                    "LAST_DEPARTURE_MISMATCH",
                    Severity.ERROR,
                    (
                        f"Chuyến cuối tại {terminal} là {format_hhmm(actual_last)}, "
                        f"không phải {format_hhmm(expected_last)}."
                    ),
                    suggestion="Giữ chuyến cuối sát đúng giờ kết thúc đã khai báo.",
                )
            )
            if actual_last < expected_last:
                issues.append(
                    _issue(
                        "FINAL_TRIP_TOO_EARLY",
                        Severity.WARNING,
                        f"Chuyến cuối tại {terminal} đang kết thúc độ phủ quá sớm.",
                        suggestion="Phân bổ lại block cuối ngày và giữ chuyến cuối.",
                    )
                )
    issues.extend(_validate_vehicle_chains(trips, parameters))
    return ValidationReport(issues)

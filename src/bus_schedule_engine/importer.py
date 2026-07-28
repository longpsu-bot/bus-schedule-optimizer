from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from numbers import Integral, Real
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

import pandas as pd

from .models import DemandRecord, Direction, RouteType, ScenarioParameters, Trip, VolumeType
from .time_utils import parse_runtime_options, parse_time_to_seconds

if TYPE_CHECKING:
    from .contracts_v1.models import DemandConfidence, DemandResponseMode, DemandSourceType


class InputDataError(ValueError):
    """Blocking error in the input workbook."""


@dataclass(frozen=True, slots=True)
class WorkbookAuthorityMetadata:
    """Workbook-owned demand authority; runtime provenance is intentionally excluded."""

    demand_dataset_id: str | None = None
    demand_source_type: DemandSourceType | None = None
    demand_confidence: DemandConfidence | None = None
    demand_response_mode: DemandResponseMode | None = None
    source_notes: str | None = None


@dataclass(frozen=True)
class ImportedWorkbook:
    parameters_a: ScenarioParameters | None
    trips_a: list[Trip]
    parameters_b: ScenarioParameters
    trips_b: list[Trip]
    demand: list[DemandRecord]
    configuration: dict[str, object]
    authority_metadata: WorkbookAuthorityMetadata = field(default_factory=WorkbookAuthorityMetadata)


REQUIRED_SHEETS = {
    "THONG_SO_B",
    "BIEU_DO_B",
}

SUPPORTED_SHEETS = REQUIRED_SHEETS | {
    "HUONG_DAN",
    "THONG_SO_A",
    "BIEU_DO_A",
    "SAN_LUONG",
    "THONG_TIN_DU_LIEU",
    "CAU_HINH",
}

OPERATING_DAY_TYPES = {"weekday", "saturday", "sunday", "holiday", "special"}


def _clean(value: object) -> object | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _direction(value: object) -> Direction:
    text = str(_clean(value) or "").lower().replace(" ", "_")
    aliases = {
        "terminal_1_to_2": Direction.TERMINAL_1_TO_2,
        "t1_t2": Direction.TERMINAL_1_TO_2,
        "bến_1_đến_bến_2": Direction.TERMINAL_1_TO_2,
        "ben_1_den_ben_2": Direction.TERMINAL_1_TO_2,
        "terminal_2_to_1": Direction.TERMINAL_2_TO_1,
        "t2_t1": Direction.TERMINAL_2_TO_1,
        "bến_2_đến_bến_1": Direction.TERMINAL_2_TO_1,
        "ben_2_den_ben_1": Direction.TERMINAL_2_TO_1,
        "combined": Direction.COMBINED,
        "tổng_hai_chiều": Direction.COMBINED,
        "tong_hai_chieu": Direction.COMBINED,
    }
    try:
        return aliases[text]
    except KeyError as exc:
        raise InputDataError(f"Chiều không hợp lệ: {value}") from exc


def _date(value: object) -> date:
    cleaned = _clean(value)
    if isinstance(cleaned, datetime):
        return cleaned.date()
    if isinstance(cleaned, date):
        return cleaned
    try:
        return pd.to_datetime(cleaned, dayfirst=True).date()
    except (TypeError, ValueError) as exc:
        raise InputDataError(f"Ngày không hợp lệ: {value}") from exc


def _key_value_sheet(frame: pd.DataFrame, sheet_name: str) -> dict[str, object]:
    if frame.shape[1] < 2:
        raise InputDataError(f"Sheet {sheet_name} phải có ít nhất hai cột")
    output: dict[str, object] = {}
    for key, value in frame.iloc[:, :2].itertuples(index=False, name=None):
        cleaned_key = _clean(key)
        if cleaned_key is not None:
            output[str(cleaned_key)] = _clean(value)
    return output


def _required(mapping: dict[str, object], key: str, sheet_name: str) -> object:
    value = mapping.get(key)
    if value is None:
        raise InputDataError(f"Thiếu {key} trong sheet {sheet_name}")
    return value


def _optional_positive_integer(
    value: object | None,
    *,
    key: str,
    sheet_name: str,
    allow_numeric_text: bool = False,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise InputDataError(f"{key} trong {sheet_name} phải là số nguyên >= 1")
    if isinstance(value, Integral) or (
        isinstance(value, Real) and math.isfinite(float(value)) and float(value).is_integer()
    ):
        parsed = int(value)
    elif allow_numeric_text and isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise InputDataError(f"{key} trong {sheet_name} phải là số nguyên >= 1") from exc
    else:
        raise InputDataError(f"{key} trong {sheet_name} phải là số nguyên >= 1")
    if parsed < 1:
        raise InputDataError(f"{key} trong {sheet_name} phải là số nguyên >= 1")
    return parsed


def _parameters(frame: pd.DataFrame, scenario: str) -> ScenarioParameters:
    sheet_name = f"THONG_SO_{scenario}"
    values = _key_value_sheet(frame, sheet_name)
    try:
        route_type = RouteType(str(_required(values, "route_type", sheet_name)).strip())
    except ValueError as exc:
        raise InputDataError("route_type phải là intra_provincial hoặc inter_provincial") from exc
    capacity_raw = values.get("vehicle_capacity_passengers")
    capacity = None if capacity_raw is None else int(capacity_raw)
    layover_raw = values.get("minimum_layover_minutes")
    allowed_runtime_raw = values.get("allowed_trip_runtime_minutes")
    legacy_runtime_raw = values.get("trip_runtime_minutes")
    available_fleet_raw = values.get("available_fleet_limit")
    approved_active_fleet_raw = values.get("approved_active_fleet")
    operating_day_type_raw = values.get("operating_day_type")
    terminal_1_max_occupancy_raw = values.get("terminal_1_max_occupancy_vehicles")
    terminal_2_max_occupancy_raw = values.get("terminal_2_max_occupancy_vehicles")
    operating_day_type = (
        None if operating_day_type_raw is None else str(operating_day_type_raw).strip().lower()
    )
    if operating_day_type is not None and operating_day_type not in OPERATING_DAY_TYPES:
        allowed = ", ".join(sorted(OPERATING_DAY_TYPES))
        raise InputDataError(f"operating_day_type trong {sheet_name} phải là một trong: {allowed}")
    try:
        runtime_options = parse_runtime_options(
            allowed_runtime_raw
            if allowed_runtime_raw is not None
            else _required(values, "trip_runtime_minutes", sheet_name)
        )
    except ValueError as exc:
        raise InputDataError(
            f"allowed_trip_runtime_minutes trong {sheet_name} không hợp lệ: {exc}"
        ) from exc
    runtime_default = (
        max(runtime_options) if allowed_runtime_raw is not None else int(legacy_runtime_raw)
    )
    return ScenarioParameters(
        route_id=str(_required(values, "route_id", sheet_name)),
        route_name=str(_required(values, "route_name", sheet_name)),
        route_type=route_type,
        trip_runtime_minutes=runtime_default,
        total_daily_trips=int(_required(values, "total_daily_trips", sheet_name)),
        terminal_1_name=str(_required(values, "terminal_1_name", sheet_name)),
        terminal_1_first_departure=parse_time_to_seconds(
            _required(values, "terminal_1_first_departure", sheet_name)
        ),
        terminal_1_last_departure=parse_time_to_seconds(
            _required(values, "terminal_1_last_departure", sheet_name)
        ),
        terminal_2_name=str(_required(values, "terminal_2_name", sheet_name)),
        terminal_2_first_departure=parse_time_to_seconds(
            _required(values, "terminal_2_first_departure", sheet_name)
        ),
        terminal_2_last_departure=parse_time_to_seconds(
            _required(values, "terminal_2_last_departure", sheet_name)
        ),
        vehicle_capacity_passengers=capacity,
        target_load_factor=float(values.get("target_load_factor") or 0.85),
        maximum_load_factor=float(values.get("maximum_load_factor") or 0.90),
        time_block_minutes=int(values.get("time_block_minutes") or 60),
        minimum_layover_minutes=None if layover_raw is None else int(layover_raw),
        allowed_trip_runtime_minutes=runtime_options,
        available_fleet_limit=_optional_positive_integer(
            available_fleet_raw,
            key="available_fleet_limit",
            sheet_name=sheet_name,
            allow_numeric_text=True,
        ),
        approved_active_fleet=_optional_positive_integer(
            approved_active_fleet_raw,
            key="approved_active_fleet",
            sheet_name=sheet_name,
            allow_numeric_text=True,
        ),
        operating_day_type=operating_day_type,
        terminal_1_max_occupancy_vehicles=(
            _optional_positive_integer(
                terminal_1_max_occupancy_raw,
                key="terminal_1_max_occupancy_vehicles",
                sheet_name=sheet_name,
            )
            if scenario == "B"
            else None
        ),
        terminal_2_max_occupancy_vehicles=(
            _optional_positive_integer(
                terminal_2_max_occupancy_raw,
                key="terminal_2_max_occupancy_vehicles",
                sheet_name=sheet_name,
            )
            if scenario == "B"
            else None
        ),
    )


def _authority_metadata(frame: pd.DataFrame) -> WorkbookAuthorityMetadata:
    from .contracts_v1.models import DemandConfidence, DemandResponseMode, DemandSourceType

    sheet_name = "THONG_TIN_DU_LIEU"
    values = _key_value_sheet(frame, sheet_name)

    def optional_enum(key: str, enum_type):
        raw = values.get(key)
        if raw is None:
            return None
        try:
            return enum_type(str(raw).strip())
        except ValueError as exc:
            allowed = ", ".join(item.value for item in enum_type)
            raise InputDataError(f"{key} trong {sheet_name} phải là một trong: {allowed}") from exc

    return WorkbookAuthorityMetadata(
        demand_dataset_id=(
            None
            if values.get("demand_dataset_id") is None
            else str(values["demand_dataset_id"]).strip()
        ),
        demand_source_type=optional_enum("demand_source_type", DemandSourceType),
        demand_confidence=optional_enum("demand_confidence", DemandConfidence),
        demand_response_mode=optional_enum("demand_response_mode", DemandResponseMode),
        source_notes=(
            None if values.get("source_notes") is None else str(values["source_notes"]).strip()
        ),
    )


def _trips(frame: pd.DataFrame, scenario: str) -> list[Trip]:
    required = {"trip_id", "departure_terminal", "direction", "departure_time"}
    missing = required - set(frame.columns)
    if missing:
        raise InputDataError(f"BIEU_DO_{scenario} thiếu cột: {', '.join(sorted(missing))}")
    trips: list[Trip] = []
    for row_number, row in frame.iterrows():
        if _clean(row.get("trip_id")) is None:
            continue
        try:
            arrival_raw = _clean(row.get("arrival_time"))
            override_raw = _clean(row.get("vehicle_capacity_override"))
            trips.append(
                Trip(
                    scenario=scenario,
                    trip_id=str(row["trip_id"]).strip(),
                    departure_terminal=str(row["departure_terminal"]).strip(),
                    direction=_direction(row["direction"]),
                    departure_seconds=parse_time_to_seconds(row["departure_time"]),
                    arrival_seconds=(
                        None if arrival_raw is None else parse_time_to_seconds(arrival_raw)
                    ),
                    vehicle_id=(
                        None
                        if _clean(row.get("vehicle_id")) is None
                        else str(row.get("vehicle_id")).strip()
                    ),
                    vehicle_capacity_override=(None if override_raw is None else int(override_raw)),
                )
            )
        except (TypeError, ValueError) as exc:
            raise InputDataError(f"BIEU_DO_{scenario}, dòng Excel {row_number + 2}: {exc}") from exc
    return trips


def _demand(frame: pd.DataFrame) -> list[DemandRecord]:
    required = {
        "period_start",
        "period_end",
        "observation_days",
        "time_block_start",
        "time_block_end",
        "direction",
        "passenger_volume",
        "volume_type",
    }
    missing = required - set(frame.columns)
    if missing:
        raise InputDataError(f"SAN_LUONG thiếu cột: {', '.join(sorted(missing))}")
    records: list[DemandRecord] = []
    for row_number, row in frame.iterrows():
        if _clean(row.get("time_block_start")) is None:
            continue
        try:
            records.append(
                DemandRecord(
                    period_start=_date(row["period_start"]),
                    period_end=_date(row["period_end"]),
                    observation_days=int(row["observation_days"]),
                    block_start_seconds=parse_time_to_seconds(row["time_block_start"]),
                    block_end_seconds=parse_time_to_seconds(row["time_block_end"]),
                    direction=_direction(row["direction"]),
                    passenger_volume=float(row["passenger_volume"]),
                    volume_type=VolumeType(str(row["volume_type"]).strip()),
                )
            )
        except (TypeError, ValueError) as exc:
            raise InputDataError(f"SAN_LUONG, dòng Excel {row_number + 2}: {exc}") from exc
    return records


def import_workbook(source: str | Path | bytes | BinaryIO) -> ImportedWorkbook:
    workbook_source: str | Path | BytesIO | BinaryIO
    workbook_source = BytesIO(source) if isinstance(source, bytes) else source
    with pd.ExcelFile(workbook_source, engine="openpyxl") as excel_file:
        missing_sheets = REQUIRED_SHEETS - set(excel_file.sheet_names)
        if missing_sheets:
            raise InputDataError(f"Workbook thiếu sheet: {', '.join(sorted(missing_sheets))}")
        sheets = {
            sheet_name: pd.read_excel(excel_file, sheet_name=sheet_name, header=2)
            for sheet_name in SUPPORTED_SHEETS & set(excel_file.sheet_names)
            if sheet_name != "HUONG_DAN"
        }
    configuration = (
        _key_value_sheet(sheets["CAU_HINH"], "CAU_HINH")
        if "CAU_HINH" in sheets and sheets["CAU_HINH"].shape[1] >= 2
        else {}
    )
    authority_metadata = (
        _authority_metadata(sheets["THONG_TIN_DU_LIEU"])
        if "THONG_TIN_DU_LIEU" in sheets
        else WorkbookAuthorityMetadata()
    )
    parameters_a: ScenarioParameters | None = None
    trips_a: list[Trip] = []
    schedule_a = sheets.get("BIEU_DO_A")
    if schedule_a is not None and not schedule_a.dropna(how="all").empty:
        if "trip_id" not in schedule_a.columns:
            raise InputDataError("BIEU_DO_A có dữ liệu nhưng thiếu cột trip_id")
        has_a_trips = any(_clean(value) is not None for value in schedule_a["trip_id"])
        if has_a_trips:
            if "THONG_SO_A" not in sheets:
                raise InputDataError(
                    "BIEU_DO_A có chuyến nhưng thiếu THONG_SO_A; "
                    "hãy bổ sung thông số A hoặc bỏ dữ liệu A để chạy chế độ chỉ có B"
                )
            parameters_a = _parameters(sheets["THONG_SO_A"], "A")
            trips_a = _trips(schedule_a, "A")
    demand_sheet = sheets.get("SAN_LUONG")
    demand = (
        _demand(demand_sheet)
        if demand_sheet is not None and not demand_sheet.dropna(how="all").empty
        else []
    )
    return ImportedWorkbook(
        parameters_a=parameters_a,
        trips_a=trips_a,
        parameters_b=_parameters(sheets["THONG_SO_B"], "B"),
        trips_b=_trips(sheets["BIEU_DO_B"], "B"),
        demand=demand,
        configuration=configuration,
        authority_metadata=authority_metadata,
    )

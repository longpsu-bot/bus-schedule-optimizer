from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from .importer import ImportedWorkbook
from .models import RouteType


def workbook_sheet_names(content: bytes) -> list[str]:
    with pd.ExcelFile(BytesIO(content), engine="openpyxl") as excel_file:
        return list(excel_file.sheet_names)


def preview_sheet(content: bytes, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(content), sheet_name=sheet_name, engine="openpyxl")


def apply_overrides(
    imported: ImportedWorkbook,
    *,
    capacity_a: int | None,
    capacity_b: int,
    target: float,
    maximum: float,
    route_type: str,
    layover: int,
    block_minutes: int,
    allowed_runtime_minutes: tuple[int, ...],
) -> ImportedWorkbook:
    params_a = (
        None
        if imported.parameters_a is None
        else replace(
            imported.parameters_a,
            vehicle_capacity_passengers=capacity_a or imported.parameters_a.capacity,
            target_load_factor=target,
            maximum_load_factor=maximum,
            route_type=RouteType(route_type),
            minimum_layover_minutes=layover,
            time_block_minutes=block_minutes,
            trip_runtime_minutes=max(allowed_runtime_minutes),
            allowed_trip_runtime_minutes=allowed_runtime_minutes,
        )
    )
    params_b = replace(
        imported.parameters_b,
        vehicle_capacity_passengers=capacity_b,
        target_load_factor=target,
        maximum_load_factor=maximum,
        route_type=RouteType(route_type),
        minimum_layover_minutes=layover,
        time_block_minutes=block_minutes,
        trip_runtime_minutes=max(allowed_runtime_minutes),
        allowed_trip_runtime_minutes=allowed_runtime_minutes,
    )
    return replace(imported, parameters_a=params_a, parameters_b=params_b)


def template_bytes() -> bytes:
    from .excel_exporter import create_input_template

    with TemporaryDirectory(prefix="bus_schedule_template_") as directory:
        path = create_input_template(Path(directory) / "Bus_Schedule_Input_Template.xlsx")
        return path.read_bytes()

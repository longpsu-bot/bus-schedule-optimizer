from __future__ import annotations

from openpyxl import load_workbook

from bus_schedule_engine.contracts_v1 import (
    DemandConfidence,
    DemandResponseMode,
    DemandSourceType,
)
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import WorkbookAuthorityMetadata, import_workbook


def _set_parameter(sheet, key: str, value: object | None) -> None:
    row = next(cell.row for cell in sheet["A"] if cell.value == key)
    sheet.cell(row, 2).value = value


def test_old_workbook_without_authority_sheet_still_imports(tmp_path) -> None:
    path = create_input_template(tmp_path / "old.xlsx")
    workbook = load_workbook(path)
    workbook.remove(workbook["THONG_TIN_DU_LIEU"])
    workbook.save(path)
    workbook.close()

    imported = import_workbook(path)

    assert imported.authority_metadata == WorkbookAuthorityMetadata()


def test_blank_optimization_and_optional_parameters_remain_none(tmp_path) -> None:
    path = create_input_template(tmp_path / "blank-values.xlsx")
    workbook = load_workbook(path)
    for key in (
        "available_fleet_limit",
        "approved_active_fleet",
        "terminal_1_max_occupancy_vehicles",
        "terminal_2_max_occupancy_vehicles",
    ):
        _set_parameter(workbook["THONG_SO_B"], key, None)
    _set_parameter(workbook["THONG_SO_B"], "operating_day_type", None)
    workbook.save(path)
    workbook.close()

    imported = import_workbook(path)

    assert imported.parameters_b.available_fleet_limit is None
    assert imported.parameters_b.approved_active_fleet is None
    assert imported.parameters_b.operating_day_type is None
    assert imported.parameters_b.terminal_1_max_occupancy_vehicles is None
    assert imported.parameters_b.terminal_2_max_occupancy_vehicles is None


def test_authority_metadata_round_trips_declared_values(tmp_path) -> None:
    path = create_input_template(tmp_path / "metadata.xlsx")
    workbook = load_workbook(path)
    sheet = workbook["THONG_TIN_DU_LIEU"]
    _set_parameter(sheet, "demand_dataset_id", "DEMAND-42")
    _set_parameter(sheet, "demand_source_type", "apc")
    _set_parameter(sheet, "demand_confidence", "low")
    _set_parameter(sheet, "demand_response_mode", "calibrated")
    _set_parameter(sheet, "source_notes", "Declared by operator")
    workbook.save(path)
    workbook.close()

    imported = import_workbook(path)

    assert imported.authority_metadata == WorkbookAuthorityMetadata(
        demand_dataset_id="DEMAND-42",
        demand_source_type=DemandSourceType.APC,
        demand_confidence=DemandConfidence.LOW,
        demand_response_mode=DemandResponseMode.CALIBRATED,
        source_notes="Declared by operator",
    )


def test_blank_optional_metadata_remains_none(tmp_path) -> None:
    path = create_input_template(tmp_path / "blank-metadata.xlsx")
    workbook = load_workbook(path)
    sheet = workbook["THONG_TIN_DU_LIEU"]
    _set_parameter(sheet, "demand_dataset_id", None)
    _set_parameter(sheet, "source_notes", None)
    workbook.save(path)
    workbook.close()

    imported = import_workbook(path)

    assert imported.authority_metadata.demand_dataset_id is None
    assert imported.authority_metadata.source_notes is None

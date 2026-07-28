from __future__ import annotations

from openpyxl import load_workbook

from bus_schedule_engine.excel_exporter import (
    CONDITIONAL_DEMAND_LABEL,
    OPTIONAL_LABEL,
    REQUIRED_FOR_OPTIMIZATION_LABEL,
    REQUIRED_LABEL,
    create_input_template,
)


def _rows_by_key(sheet) -> dict[str, tuple[object, object, object]]:
    return {
        str(sheet.cell(row, 1).value): (
            sheet.cell(row, 2).value,
            sheet.cell(row, 3).value,
            sheet.cell(row, 4).value,
        )
        for row in range(4, sheet.max_row + 1)
        if sheet.cell(row, 1).value is not None
    }


def test_generated_template_displays_all_requirement_levels(tmp_path) -> None:
    path = create_input_template(tmp_path / "input.xlsx")
    workbook = load_workbook(path)
    parameters_b = _rows_by_key(workbook["THONG_SO_B"])
    metadata = _rows_by_key(workbook["THONG_TIN_DU_LIEU"])

    levels = {row[1] for row in parameters_b.values()} | {row[1] for row in metadata.values()}

    assert REQUIRED_LABEL in levels
    assert REQUIRED_FOR_OPTIMIZATION_LABEL in levels
    assert OPTIONAL_LABEL in levels
    assert CONDITIONAL_DEMAND_LABEL in levels
    assert workbook["THONG_SO_B"].cell(3, 3).value == "Mức độ"
    assert workbook["THONG_TIN_DU_LIEU"].cell(3, 3).value == "Mức độ"
    workbook.close()


def test_generated_template_classifies_authority_and_optional_fields(tmp_path) -> None:
    path = create_input_template(tmp_path / "input.xlsx")
    workbook = load_workbook(path)
    parameters_a = _rows_by_key(workbook["THONG_SO_A"])
    parameters_b = _rows_by_key(workbook["THONG_SO_B"])
    metadata = _rows_by_key(workbook["THONG_TIN_DU_LIEU"])

    for parameters in (parameters_a, parameters_b):
        assert parameters["available_fleet_limit"][1] == REQUIRED_FOR_OPTIMIZATION_LABEL
        assert parameters["operating_day_type"][1] == REQUIRED_FOR_OPTIMIZATION_LABEL
        assert parameters["approved_active_fleet"][1] == OPTIONAL_LABEL

    assert parameters_b["terminal_1_max_occupancy_vehicles"][1] == OPTIONAL_LABEL
    assert parameters_b["terminal_2_max_occupancy_vehicles"][1] == OPTIONAL_LABEL
    for key in (
        "demand_source_type",
        "demand_confidence",
        "demand_response_mode",
    ):
        assert metadata[key][1] == CONDITIONAL_DEMAND_LABEL
    workbook.close()


def test_requirement_levels_are_text_and_visually_distinct(tmp_path) -> None:
    path = create_input_template(tmp_path / "input.xlsx")
    workbook = load_workbook(path)
    sheet = workbook["THONG_SO_B"]
    level_cells = {
        sheet.cell(row, 3).value: sheet.cell(row, 3) for row in range(4, sheet.max_row + 1)
    }

    assert (
        level_cells[REQUIRED_LABEL].fill.fgColor.rgb
        != level_cells[REQUIRED_FOR_OPTIMIZATION_LABEL].fill.fgColor.rgb
    )
    assert (
        level_cells[REQUIRED_FOR_OPTIMIZATION_LABEL].fill.fgColor.rgb
        != level_cells[OPTIONAL_LABEL].fill.fgColor.rgb
    )
    assert all(cell.font.bold for cell in level_cells.values())
    workbook.close()

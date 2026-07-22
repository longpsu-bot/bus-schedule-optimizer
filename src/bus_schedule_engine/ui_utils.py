from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from .block_supply import scenario_supply_summary
from .comparison_exporter import export_bc_comparison, exported_c_fingerprint
from .diagram import build_comparison_diagram, diagram_png_bytes
from .excel_exporter import create_input_template, export_results
from .importer import ImportedWorkbook
from .models import AnalysisBundle, RouteType
from .service import run_analysis
from .time_utils import format_hhmm


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


def run_and_build_artifacts(
    imported: ImportedWorkbook,
) -> tuple[AnalysisBundle, object, dict[str, bytes]]:
    bundle = run_analysis(imported)
    figure = build_comparison_diagram(bundle)
    result_c = bundle.get("C")
    c_fingerprint = result_c.timetable_fingerprint if result_c else ""
    if figure.layout.meta.get("c_timetable_fingerprint", "") != c_fingerprint:
        raise ValueError("Fingerprint C của diagram không khớp object dùng trong UI")
    with TemporaryDirectory(prefix="bus_schedule_mvp_") as directory:
        output_path = export_results(bundle, Path(directory) / "Bus_Schedule_MVP_Output.xlsx")
        output_bytes = output_path.read_bytes()
        comparison_path = export_bc_comparison(
            bundle,
            Path(directory) / "so_sanh_B_C_tai_phan_bo_on_dinh.xlsx",
        )
        comparison_bytes = comparison_path.read_bytes()
        if exported_c_fingerprint(comparison_path) != c_fingerprint:
            raise ValueError("Fingerprint C trong XLSX không khớp object dùng trong UI")
    html = figure.to_html(include_plotlyjs=True, full_html=True).encode("utf-8")
    png = diagram_png_bytes(figure)
    return (
        bundle,
        figure,
        {
            "xlsx": output_bytes,
            "comparison_xlsx": comparison_bytes,
            "html": html,
            "png": png,
            "c_fingerprint": c_fingerprint.encode("utf-8"),
        },
    )


def template_bytes() -> bytes:
    with TemporaryDirectory(prefix="bus_schedule_template_") as directory:
        path = create_input_template(Path(directory) / "Bus_Schedule_Input_Template.xlsx")
        return path.read_bytes()


def validation_frame(bundle: AnalysisBundle) -> pd.DataFrame:
    result = bundle.get("B")
    if result is None:
        return pd.DataFrame()
    rows = [
        {
            "Mã lỗi": issue.code,
            "Mức độ": issue.severity.value,
            "Nội dung": issue.message,
            "Chuyến liên quan": ", ".join(issue.trip_ids),
            "Block": issue.block or "",
            "Đề xuất sửa": issue.suggestion,
        }
        for issue in result.validation.issues
    ]
    return pd.DataFrame(rows)


def block_frame(bundle: AnalysisBundle, scenario: str) -> pd.DataFrame:
    result = bundle.get(scenario)
    if result is None:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "Khung thời gian": f"{format_hhmm(block.block_start_seconds)}–{format_hhmm(block.block_end_seconds)}",
                "Chiều": block.direction.value,
                "Số chuyến": block.trips,
                "Sức cung danh nghĩa": block.nominal_capacity,
                "Sức cung mục tiêu": block.target_capacity,
                "Sức cung trần": block.maximum_recommended_capacity,
                "Nhu cầu/ngày": block.demand,
                "Hệ số tải": block.load_factor,
                "Chuyến cần": block.required_trips,
                "Chênh lệch chuyến": block.trip_gap_to_target,
                "Giãn cách TB": block.headway.mean_minutes,
                "Độ lệch giãn cách": block.headway.standard_deviation_minutes,
                "Khoảng trống lớn nhất": block.headway.maximum_minutes,
                "Trạng thái": block.status.value,
                "Ghi chú": block.data_note,
            }
            for block in result.evaluation.blocks
        ]
    )


def scenario_frame(bundle: AnalysisBundle) -> pd.DataFrame:
    rows = []
    for result in bundle.scenarios:
        peak_blocks = sorted(result.evaluation.blocks, key=lambda block: block.demand, reverse=True)
        peak_headways = [
            block.headway.mean_minutes
            for block in peak_blocks[: max(1, len(peak_blocks) // 4)]
            if block.headway.mean_minutes is not None
        ]
        low_headways = [
            block.headway.mean_minutes
            for block in peak_blocks[max(1, len(peak_blocks) // 4) :]
            if block.headway.mean_minutes is not None
        ]
        rows.append(
            {
                "Phương án": (result.display_name or result.name),
                "Mã chiến lược": result.strategy_id or "—",
                "Điểm": result.score,
                "Tổng chuyến": len(result.trips),
                "Số xe tối thiểu": result.fleet.minimum_vehicles,
                "Giới hạn đội xe": result.resource_fleet_limit,
                "Giãn cách cao điểm": sum(peak_headways) / len(peak_headways)
                if peak_headways
                else None,
                "Giãn cách thấp điểm": sum(low_headways) / len(low_headways)
                if low_headways
                else None,
                "Khung cuối ngày": f"{result.evaluation.late_coverage_gap_minutes:.0f} phút lệch",
                "Kết luận": result.evaluation.overall_status.value,
                "Trạng thái sinh C": (
                    result.generation_status.value if result.generation_status else "—"
                ),
                "Lý do khuyến nghị": result.recommendation_reason,
            }
        )
    return pd.DataFrame(rows)


def supply_summary_frame(bundle: AnalysisBundle) -> pd.DataFrame:
    return pd.DataFrame(scenario_supply_summary(bundle))


def regime_frame(bundle: AnalysisBundle) -> pd.DataFrame:
    result = bundle.get("C")
    if result is None:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "Chế độ": regime.regime_id,
                "Chiều": regime.direction.value,
                "Từ giờ": format_hhmm(regime.start_seconds),
                "Đến giờ": format_hhmm(regime.end_seconds),
                "Số chuyến": regime.trip_count,
                "Giãn cách mục tiêu": regime.target_headway_minutes,
                "Dãy giãn cách thực tế": ", ".join(
                    f"{value:g}" for value in regime.actual_headway_sequence
                ),
                "Trạng thái": regime.headway_status,
                "Lý do ranh giới": regime.boundary_reason.value,
            }
            for regime in result.headway_regimes
        ]
    )

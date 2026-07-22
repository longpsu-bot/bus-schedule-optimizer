from pathlib import Path

from bus_schedule_engine.comparison_exporter import export_bc_comparison
from bus_schedule_engine.diagram import build_comparison_diagram, export_diagram
from bus_schedule_engine.excel_exporter import create_input_template, export_results
from bus_schedule_engine.importer import import_workbook
from bus_schedule_engine.service import run_analysis

output_dir = Path("outputs") / "bus_schedule_mvp"
template_path = create_input_template(output_dir / "Bus_Schedule_Input_Template.xlsx")
bundle = run_analysis(import_workbook(template_path))
result_path = export_results(bundle, output_dir / "Bus_Schedule_MVP_Output.xlsx")
comparison_path = export_bc_comparison(bundle, output_dir / "so_sanh_B_C_tai_phan_bo_on_dinh.xlsx")
png_path, html_path = export_diagram(build_comparison_diagram(bundle), output_dir)

print(f"Template: {template_path.resolve()}")
print(f"Workbook kết quả: {result_path.resolve()}")
print(f"Workbook so sánh B–C: {comparison_path.resolve()}")
print(f"Diagram PNG: {png_path.resolve()}")
print(f"Diagram HTML: {html_path.resolve()}")
print(
    "Scenarios: "
    + ", ".join(
        f"{result.name}={result.validation.status}/{result.evaluation.overall_status.value}"
        for result in bundle.scenarios
    )
)

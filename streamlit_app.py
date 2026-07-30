import streamlit as st

st.set_page_config(
    page_title="Bus Schedule Engine MVP",
    page_icon=":material/directions_bus:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

for legacy_key in (
    "analysis_bundle",
    "diagram_figure",
    "download_artifacts",
    "scenario_c_fingerprint",
    "parallel_runtime_status",
    "side_by_side_validation_report",
):
    st.session_state.pop(legacy_key, None)

for key, default in {
    "input_bytes": None,
    "imported_workbook": None,
    "workbook_input_readiness": None,
    "unified_optimization_result": None,
    "unified_presentation": None,
    "unified_demand_supply_figure": None,
    "unified_departure_figure": None,
    "unified_download_artifacts": None,
    "unified_runtime_failure": None,
    "unified_runtime_status": None,
}.items():
    st.session_state.setdefault(key, default)

pages = [
    st.Page(
        "app_pages/01_nhap_du_lieu.py",
        title="1. Nhập dữ liệu",
        icon=":material/upload_file:",
        default=True,
    ),
    st.Page(
        "app_pages/02_kiem_tra.py",
        title="2. Kiểm tra kỹ thuật",
        icon=":material/fact_check:",
    ),
    st.Page(
        "app_pages/03_nhu_cau.py",
        title="3. Đánh giá nhu cầu",
        icon=":material/monitoring:",
    ),
    st.Page(
        "app_pages/04_khuyen_nghi.py",
        title="4. Phương án khuyến nghị",
        icon=":material/route:",
    ),
    st.Page(
        "app_pages/05_xuat_file.py",
        title="5. Biểu đồ và xuất file",
        icon=":material/download:",
    ),
]

page = st.navigation(pages, position="top")
st.title(f"{page.icon} {page.title}")
st.caption(
    "Công cụ chẩn đoán có kết quả xác định, ưu tiên ràng buộc bắt buộc; kết quả hỗ trợ chuyên gia "
    "và không tự động thay thế quyết định khai thác."
)
page.run()

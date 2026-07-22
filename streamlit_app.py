import streamlit as st

st.set_page_config(
    page_title="Bus Schedule Engine MVP",
    page_icon=":material/directions_bus:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

for key, default in {
    "input_bytes": None,
    "imported_workbook": None,
    "analysis_bundle": None,
    "diagram_figure": None,
    "download_artifacts": None,
    "scenario_c_fingerprint": None,
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

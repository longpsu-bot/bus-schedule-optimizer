import streamlit as st

from bus_schedule_engine.ui_utils import validation_frame

bundle = st.session_state.analysis_bundle
if bundle is None:
    st.warning("Chưa có kết quả. Hãy chạy phân tích ở trang Nhập dữ liệu.")
    st.stop()

result = bundle.get("B")
issues = validation_frame(bundle)
blocking = 0 if issues.empty else issues["Mức độ"].isin(["BLOCKING", "ERROR"]).sum()
cols = st.columns(3)
cols[0].metric("Kết quả phương án B", result.validation.status)
cols[1].metric("Tổng lỗi/cảnh báo", len(issues))
cols[2].metric("Lỗi chặn phương án", int(blocking))

if result.validation.passed:
    st.success("Phương án B đạt các ràng buộc kỹ thuật bắt buộc.", icon=":material/check_circle:")
else:
    st.error(
        "Phương án B không được coi là khả thi; điểm không được tính để che lỗi kỹ thuật.",
        icon=":material/block:",
    )

st.subheader("Danh sách lỗi và đề xuất sửa")
if issues.empty:
    st.dataframe(
        [{"Mức độ": "INFO", "Nội dung": "Không phát hiện lỗi kỹ thuật."}],
        hide_index=True,
    )
else:
    st.dataframe(issues, hide_index=True)

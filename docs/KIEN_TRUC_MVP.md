# Kiến trúc Bus Schedule Engine MVP

## Hiện trạng được kiểm tra

Repository ban đầu chỉ có `Schedule template.xlsx`, gồm hai sheet `Config template` và
`Schedule Template`. Workbook thể hiện cặp giờ đi/đến tại hai bến và thời gian quay đầu,
nhưng chưa có mô hình Scenario A/B/C, dữ liệu nhu cầu, sức chứa xe, kiểm tra hard constraint,
đánh giá theo block hay báo cáo kết quả.

## Phần được giữ lại

- Quy ước một tuyến có hai đầu bến và hai chiều.
- Giá trị giờ được lưu dưới dạng thời gian Excel, hiển thị `HH:mm`.
- Arrival có thể suy ra từ departure cộng cận trên của khoảng thời gian hành trình.
- Thời gian hành trình được khai báo dưới dạng khoảng nguyên bao gồm hai đầu; `55,65` bao hàm
  mọi giá trị từ 55 đến 65.

## Phần được thay thế

- Template đầy đủ vẫn có 7 sheet, nhưng pipeline B-only chỉ bắt buộc `THONG_SO_B` và `BIEU_DO_B`; A, sản lượng và cấu hình là tùy chọn.
- Các công thức giãn cách/số xe đơn lẻ được thay bằng evaluator theo block và mô phỏng gán xe.
- Logic tạo lịch được xây mới, deterministic, không dùng AI hay số ngẫu nhiên.

## Module mới

1. `models.py`: data model và trạng thái nghiệp vụ.
2. `importer.py`: đọc template Excel, chuẩn hóa giờ và sản lượng nhiều ngày.
3. `validator.py`: kiểm tra hard constraint và xung đột xe đã khai báo.
4. `demand.py`: đánh giá block, load factor, headway và giới hạn dữ liệu.
5. `c_config.py`: cấu hình tập trung cho khóa nguồn lực, số regime, sustained change,
   balanced rounding, transition và giới hạn dịch chuyển.
6. `c_generator.py`: pipeline C theo bảy giai đoạn: sao chép/hash B; phân tích áp lực nhu cầu;
   chọn mốc neo; tạo regime plan; ghép hai chiều và gán xe; đánh giá; chọn deterministic.
7. `generator.py`: điều phối C và phương án mở rộng C2.
8. `fleet.py`: gán xe greedy theo vị trí/thời điểm sẵn sàng.
9. `comparator.py`: chấm điểm scenario hợp lệ bằng cấu hình tập trung.
10. `fingerprint.py`: fingerprint timetable dùng chung giữa service, diagram và XLSX.
11. `diagram.py`: diagram Plotly so sánh nhu cầu và các scenario, hiển thị C từ object authoritative.
12. `excel_exporter.py`: tạo template/workbook tổng hợp; `comparison_exporter.py` tạo workbook B–C.
13. `service.py`: khóa bất biến B, kiểm tra ánh xạ một-một và điều phối pipeline; `streamlit_app.py`
    cùng `app_pages/` phụ trách UI tiếng Việt.

## Scenario C ổn định theo nhu cầu

- Demand block chỉ là đơn vị đánh giá. Regime là đoạn biến thiên theo nhu cầu có mốc neo tại chuyến,
  có thể cắt qua nhiều block 30/60 phút.
- Mọi chuyến giữa hai mốc neo được sinh lại đồng thời; không chèn hay dịch một chuyến đơn lẻ.
- Khi dời giờ một chuyến C, duration của chính chuyến nguồn B được kế thừa nguyên vẹn qua `source_b_trip_id`.
- Số phút dư được rải đều bằng balanced remainder/Bresenham nên headway trong regime chỉ dùng
  floor/ceiling và chênh nhau tối đa một phút.
- Ứng viên chỉ được nhận sau validator, evaluator, fleet assignment và regularity gate.
- Nếu không có ứng viên tốt hơn, C là bản sao độc lập có truy vết của B với trạng thái
  `KHÔNG CÓ PHƯƠNG ÁN TÁI PHÂN BỔ TỐT HƠN`; trạng thái này không được đánh dấu khuyến nghị.

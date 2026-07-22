# Bus Schedule Engine MVP

Ứng dụng local, deterministic và rule-based để kiểm tra, đánh giá và đề xuất biểu đồ giờ
xe buýt. Core engine không dùng AI/LLM, không dùng số ngẫu nhiên, không có database, API server,
authentication hay cloud service. Kết quả là công cụ chẩn đoán hỗ trợ chuyên gia, không tự động
thay thế quyết định khai thác.

## Kiến trúc

Pipeline chạy theo thứ tự:

1. `importer.py` đọc workbook; tối thiểu cần `THONG_SO_B` và `BIEU_DO_B`. Scenario A, sản lượng và cấu hình là tùy chọn.
2. `validator.py` chặn hard constraint trước khi chấm điểm.
3. `demand.py` đánh giá block/chiều/toàn tuyến, load factor và headway.
4. `c_generator.py` sinh `C — Tái phân bổ ổn định theo nhu cầu` từ bản sao độc lập của B.
   C giữ tổng chuyến, chuyến theo chiều, chuyến đầu/cuối và số xe hoạt động; các cụm chuyến
   được tái giãn cách theo một số ít regime có balanced rounding. `generator.py` vẫn điều phối C2.
5. `fleet.py` gán xe greedy theo bến và thời điểm sẵn sàng.
6. `comparator.py` chấm điểm scenario hợp lệ theo `config/scoring.json`.
7. `diagram.py` dựng biểu đồ Plotly kiểu combination chart: cột nhu cầu trên trục Y trái và
   các đường số chuyến A (khi có dữ liệu), B/C cùng ngưỡng LF 85%/90% trên trục Y phải.
   Giờ xuất bến chính xác được tách sang biểu đồ chẩn đoán riêng.
8. `excel_exporter.py` tạo template/workbook tổng hợp; `comparison_exporter.py` tạo workbook
   so sánh B–C có truy vết, regime, headway liền kề, phân công xe và nhật ký tối ưu.
9. `service.py` điều phối pipeline; `streamlit_app.py` và `app_pages/` chỉ phụ trách UI.

Audit workbook tham khảo và quyết định tái sử dụng được ghi ở `docs/KIEN_TRUC_MVP.md`.

## Cài đặt

Yêu cầu Python 3.11 trở lên. Trên Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Chạy ứng dụng

```powershell
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

Ứng dụng có 5 trang tiếng Việt:

1. Nhập dữ liệu và chỉnh thông số.
2. Kiểm tra kỹ thuật Scenario B.
3. Đánh giá nhu cầu theo block.
4. So sánh A/B/C và lý do khuyến nghị.
5. Xem diagram có trục X là thời gian trong ngày, tải PNG/HTML/workbook.

## Chạy test, lint và format

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check . --exclude .artifact --exclude outputs --exclude .venv
.\.venv\Scripts\python.exe -m ruff format . --check --exclude .artifact --exclude outputs --exclude .venv
```

## Tạo lại artifact mẫu

```powershell
.\.venv\Scripts\python.exe scripts\build_sample_artifacts.py
```

Lệnh tạo năm file trong `outputs/bus_schedule_mvp/`:

- `Bus_Schedule_Input_Template.xlsx`
- `Bus_Schedule_MVP_Output.xlsx`
- `so_sanh_B_C_tai_phan_bo_on_dinh.xlsx`
- `Bus_Schedule_Comparison.png`
- `Bus_Schedule_Comparison.html`

Trong diagram, mọi chuyến và block nhu cầu dùng chung một trục X thời gian liên tục. Nhu cầu hai
chiều được xếp chồng để dễ thấy block cao nhất; trạng thái cung ứng chỉ tô trên đúng lane scenario
và chiều liên quan. Dịch vụ qua nửa đêm được đặt sang ngày kế tiếp để giữ đúng thứ tự thời gian.

Template có dữ liệu minh họa và data validation. Hãy thay dữ liệu mẫu, không đổi tên các sheet/cột được dùng.
Workbook nguồn `Schedule template.xlsx` không bị sửa.

## Quy ước input

Các sheet tối thiểu để chạy chế độ chỉ có B:

- `THONG_SO_B`
- `BIEU_DO_B`

Các sheet tùy chọn:

- `HUONG_DAN`
- `THONG_SO_A` và `BIEU_DO_A` nếu cần so sánh Scenario A
- `SAN_LUONG`
- `CAU_HINH`

Nếu thiếu `SAN_LUONG`, pipeline vẫn kiểm tra B và xuất báo cáo; Scenario C mang trạng thái
`KHÔNG ĐỦ DỮ LIỆU ĐỂ TỐI ƯU` và không được gắn nhãn khuyến nghị.

`total_daily_trips` là tổng lượt hai chiều. `vehicle_capacity_passengers` là bắt buộc.
`allowed_trip_runtime_minutes` khai báo cận dưới và cận trên, phân tách bằng dấu phẩy.
Ví dụ `55,65` chấp nhận mọi số phút nguyên từ 55 đến 65, bao gồm 59, 60 và 61. Nếu `arrival_time`
để trống, engine dùng cận trên làm mặc định an toàn. File cũ chỉ có
`trip_runtime_minutes` vẫn chạy và được hiểu là danh sách chỉ có một giá trị.
Nếu Excel đang dùng dấu phẩy làm dấu thập phân, có thể nhập `55;65`; importer cũng tự khôi phục
trường hợp Excel đã lưu nhầm `55,65` thành số `55.65`.
Giờ dùng `HH:mm`, ngày dùng `dd/mm/yyyy`. Với sản lượng tổng nhiều ngày, chọn
`total_observation_period` và nhập đúng `observation_days`. Nếu không tách chiều, dùng
`direction = combined`; engine chỉ kết luận tổng hợp.

## Guardrails đã triển khai

- Không sửa giờ xuất bến nguồn khi import.
- C giữ nguyên thời gian hành trình cụ thể của từng chuyến nguồn B khi tái phân bổ giờ xuất bến,
  miễn thời lượng đó nằm trong khoảng đã khai báo.
- Không suy đoán sức chứa.
- Không dùng tổng sản lượng nhiều ngày như một ngày.
- Không kết luận một chiều từ dữ liệu `combined`.
- Không chấm điểm scenario vi phạm hard constraint.
- C có mã `fixed_resource_redistribution`; B được hash trước/sau và không dùng chung object với C.
- C giữ tổng chuyến, tổng chuyến từng chiều, tham số khai thác, chuyến đầu/cuối và số xe hoạt động B.
- Headway được tính theo các chuyến liên tiếp cùng chiều trên timeline liên tục; ranh giới block
  nhu cầu 30/60 phút không reset chuỗi headway.
- Regime được tạo từ thay đổi nhu cầu kéo dài, không từ từng block; trong regime, headway bằng nhau
  hoặc dùng balanced rounding với chênh lệch tối đa một phút.
- UI, diagram và XLSX dùng chung fingerprint của object C; export không sinh lại timetable.
- C chỉ được đánh dấu khuyến nghị chính khi đạt cả nhu cầu, hard constraints và regularity gate.
- C2 chỉ xuất hiện khi có nhu cầu tăng tổng chuyến và ghi rõ mức tăng.
- Phân công xe và generator có thứ tự ổn định nên cùng input cho cùng output.

## Giới hạn MVP

- Một tuyến, hai bến, một sức chứa mặc định cho mỗi scenario.
- Chưa tối ưu mixed fleet, nhiều tuyến, deadhead, ca tài xế, giao ca hay bảo dưỡng.
- Dữ liệu `combined` được đánh giá tổng hợp; tỷ trọng chuyến B chỉ là giả định công khai khi
  generator cần phân bổ hai chiều.
- Dịch vụ qua nửa đêm chưa phải case tối ưu chính; giờ đến có thể vượt 24:00 trong nội bộ nhưng
  cửa sổ xuất bến được nhập trong một ngày dịch vụ.
- Greedy fleet assignment phù hợp MVP hai bến; chưa giải bài toán tái định vị xe phức tạp.
- C chỉ hỗ trợ `fixed_by_direction` trong MVP. Chế độ đổi tổng chuyến giữa hai chiều chưa được bật;
  dữ liệu `combined` luôn giữ số chuyến từng chiều của B.
- Bộ sinh regime dùng tập ứng viên deterministic và giới hạn dịch chuyển; chưa phải solver tối ưu toàn cục.
- Khi nguồn lực cố định không đủ, C có thể giữ B và trả trạng thái rõ ràng thay vì xuất một lịch giả
  hoặc gắn nhãn khuyến nghị. C2 vẫn thể hiện tổng tối thiểu theo target nếu khả thi.

## Đề xuất Sprint tiếp theo

- Cho phép sức chứa riêng theo chuyến và nhiều loại xe, chưa tối ưu mixed fleet.
- Thêm khai báo nhu cầu xã hội/mức phục vụ tối thiểu theo block.
- Bổ sung service-day qua nửa đêm và kiểm thử lịch dài hơn 24 giờ.
- Nâng generator từ largest-remainder sang tối ưu ràng buộc một tuyến có giải thích.
- Thêm kiểm thử UI upload/download và benchmark workbook lớn.

Không mở rộng Sprint này sang nhiều tuyến, điều chuyển xe giữa tuyến, lập ca tài xế, bảo dưỡng
hoặc dự báo nhu cầu bằng machine learning.

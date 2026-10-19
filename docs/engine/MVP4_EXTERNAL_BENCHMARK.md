# MVP-4: Đối chiếu biểu đồ giờ bên ngoài

MVP-4 nhập và rà soát độc lập biểu đồ hiện hữu B và phương án ngoài X trong báo cáo tám sheet. Chế độ độc lập chỉ cần workbook báo cáo, không cần dữ liệu KH/HT, đầu vào V3 hoặc chạy bộ tối ưu. Nhãn `Xanh SM` được giữ nguyên; đơn vị hoặc hệ thống lập báo cáo chưa được xác minh.

```powershell
python scripts/run_external_benchmark.py --input local_inputs/external_report.xlsx --output-dir outputs/external_benchmark
```

Đầu ra riêng gồm `external_benchmark.json`, `external_normalized_timetable.json` và `external_benchmark.html`. HTML tiếng Việt có thể mở trực tiếp trong trình duyệt, không tải thư viện từ mạng. Các đầu ra và quy tắc lựa chọn của MVP-1/2/3 được giữ nguyên. Workbook nguồn được đọc, không ghi lại; bản gốc và báo cáo riêng tư không đưa vào Git.

## Phạm vi bộ nhập

Adapter áp dụng đúng cấu trúc đã kiểm tra: `Tong Quan`, bốn sheet giờ `hien_huu_From_MienTay`, `xanh_sm_From_MienTay`, `hien_huu_From_DHQG-A.`, `xanh_sm_From_DHQG-A.`, cùng `Lich cho tai xe`, `So chuyen cho tung xe`, `Du lieu bieu do`. Không tự nhận dạng mọi mẫu Excel.

Giờ xuất bến được ghép từ tiêu đề giờ và từng ô phút nguyên. Bộ nhập kiểm tra thứ tự, trùng giờ, tổng theo giờ, tổng theo chiều và chuyến đầu/cuối trong tổng quan. Không dùng tổng để bổ sung chuyến thiếu. JSON chuẩn hoá lưu SHA-256, sheet, từng ô giờ/phút, các ô tổng và trường tổng hợp. Công thức không được thực thi; chỉ đọc kết quả lưu sẵn nếu có, đồng thời nêu rõ chưa xác minh lần tính lại. Công thức thiếu kết quả lưu sẵn bị từ chối.

Nhu cầu nửa giờ chỉ được chuẩn hoá khi hai dòng hiển thị lặp trùng nhau, chuỗi thời gian liên tục và mỗi tổng nửa giờ khớp với quan sát riêng trong cột K/L hoặc O/P. Phạm vi nhu cầu phải bao phủ toàn bộ thời gian phục vụ của cả B và X. Giữ khoảng có giá trị không. Khi thiếu bằng chứng hoặc không khớp, báo vấn đề tổng hợp chưa giải quyết và không tính chờ; giãn cách vẫn được đánh giá. Các quan sát ngoài khung tại M/Q được lưu riêng với ô nguồn, không cộng vào chuỗi trong khung. Quan sát ngoài khung thiếu thời điểm không bị bỏ qua.

Dữ liệu lên xe lịch sử là chỉ báo thay thế cho nhu cầu, chưa phải quan sát độc lập về khách đến. Ước tính chờ dùng giả định khách đến đều trong mỗi khoảng nửa giờ và hàm tích phân `quality.waiting` hiện có. `review.bucket_evidence` giữ đủ cặp chuyến trước/sau khi giãn cách cắt qua biên khoảng. Khách ngoài chuyến đầu/cuối được nêu riêng, không bịa chuyến ngày kế tiếp. Nếu phạm vi phục vụ thay đổi, không coi chờ trung bình trên tập khách khác nhau là bằng chứng cải thiện; khoảng mất phục vụ được cảnh báo riêng.

## Bằng chứng xe và giới hạn kết luận

Hai bảng chiều trong lịch xe được đọc riêng, sau đó ghép theo mã xe và mốc giờ. Kiểm tra bao phủ chuyến X, thứ tự chuyến, không trùng việc và bến nối tiếp. Thời gian nghỉ ghi nguồn và thời gian nghỉ suy từ giờ đến/đi được giữ riêng; sai khác nửa phút không bị tự làm tròn để ép khớp. Tổng chuyến, các nhãn đếm chiều trong nguồn, giờ đầu/cuối và thời lượng theo xe được đối chiếu; khác biệt được nêu với ô nguồn. Không tự đổi nghĩa `n_inbound`/`n_outbound` theo tên mã xe.

`REPORTED_FLEET` là số xe do tổng quan khai báo. `CHAIN_VALIDATED` chỉ xác nhận phân công ghi nhận về mốc giờ, bao phủ và vị trí. `MINIMUM_FLEET_UNVERIFIED` cho biết chưa chứng minh số xe tối thiểu theo mô hình chung. Thiếu thời gian chạy B được nêu là `BASELINE_RUNTIME_UNAVAILABLE`, không lấy thời gian chạy X gán cho B.

Không tự áp dụng ngưỡng nghỉ 5 phút. Khi cần rà soát kịch bản được khai báo riêng:

```powershell
python scripts/run_external_benchmark.py --input local_inputs/external_report.xlsx --minimum-layover-scenario 5 --output-dir outputs/external_layover_scenario
```

Ngưỡng này là giả định kịch bản, không trở thành yêu cầu bắt buộc của đơn vị khai thác. Lịch xe không chứng nhận ca lái xe, điều kiện lao động, sức chứa thực tế hoặc hệ số đầy tải 0,8. Số xe ban đầu tại mỗi bến chỉ là yêu cầu của chuỗi ghi nhận, chưa xác nhận tồn xe thực tế. Báo cáo không cấp phê duyệt vận hành.

## Đối chiếu thêm kết quả C

`--comparison comparison.json` nhận giờ xuất bến thực tế của C và bối cảnh đánh giá. `--benchmark-context context.json` khai báo bối cảnh dùng chung. Không dùng lại các chỉ tiêu chờ lịch sử trong báo cáo khác. C được tính lại bằng cùng nhu cầu; khi chưa đủ điều kiện, hiển thị riêng và nêu lý do không xếp hạng.

Hai bối cảnh phải đủ và trùng tám trường sau:

| Trường | Nội dung |
|---|---|
| `route_identity` | Đúng object `route_identity` trong JSON chuẩn hoá |
| `operating_day_profile` | Chuỗi không rỗng xác định ngày/loại ngày; không dùng `UNKNOWN` hoặc `UNVERIFIED` |
| `direction_definitions` | Cùng định nghĩa hai chiều với `route_identity` |
| `demand_basis` | `demand_fingerprint` của báo cáo benchmark |
| `runtime_layover_assumptions` | `runtime_minutes` và `layover_minutes`, mỗi trường có hai chiều |
| `trip_count_policy` | Tổng chuyến yêu cầu cho từng chiều |
| `protected_service_policy` | Danh sách khung bảo vệ theo chiều; danh sách rỗng phải được khai báo rõ |
| `fleet_assumptions` | `fleet_ceiling` và, nếu có, `initial_vehicles` theo chiều |

Ví dụ cấu trúc kết quả C:

```json
{
  "id": "C",
  "departures": {"outbound": [300, 315, 330], "inbound": [300, 315, 330]},
  "context": {}
}
```

Object `context` rỗng trong ví dụ chỉ minh hoạ kết quả chưa đủ điều kiện xếp hạng. Cần điền đầy đủ tám trường từ bằng chứng và giả định được khai báo; không sao chép bối cảnh không tương thích để qua kiểm tra.

Phiên bản này chỉ chứng minh bối cảnh chung với thời gian chạy cố định theo từng chiều. Thời gian chạy khai báo phải khớp từng chuyến X có mốc đến, các phương án phải chung chính sách chuyến và mốc đầu/cuối. Hệ thống dùng lại `validate_bundle`, `assign_fleet`, `evaluate` để kiểm tra cả ba phương án trong kịch bản chung. Chỉ đưa ra thứ tự chờ mô hình khi giá trị chờ có nghĩa và các ràng buộc đã khai báo đều qua kiểm tra. Không coi kết quả đó là thời gian chạy quan sát của B, lựa chọn sản xuất hoặc phê duyệt. Mô hình thời gian chạy thay đổi, chính sách không xác định hoặc thiếu dữ liệu dẫn đến kết quả riêng, không ép xếp hạng.

## Kiểm tra

`tests/fixtures/external_report.xlsx` là dữ liệu hoàn toàn tổng hợp, gồm tám sheet, 51 chuyến mỗi chiều cho B/X, hai xe, giãn cách không đều và khoảng nhu cầu bằng không. Không chứa số liệu từ workbook riêng tư. Bộ kiểm tra bao gồm lỗi nhập, chống cộng lặp nhu cầu, giãn cách cắt biên, tích phân chờ tính tay, sai chuỗi xe, phạm vi bằng chứng, đối chiếu ba phương án, thoát HTML và xuất lặp xác định.

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_external_import.py tests/test_external_benchmark.py --basetemp outputs/external_tests
```

Kết quả đánh giá workbook thực được giữ trong thư mục đầu ra cục bộ. Các lỗi fingerprint do CRLF và giới hạn bộ đếm thời gian trên Windows được đối chiếu với bộ kiểm tra trước sửa; không sửa bằng chứng đóng băng để che lỗi kế thừa.

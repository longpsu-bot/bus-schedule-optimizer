"""Vietnamese offline external benchmark; all numbers come from benchmark evidence."""

from __future__ import annotations

import json

from .input import DIRECTIONS
from .review_html import CSS, _gaps, _svg, _table, clock, e, label, n

SOURCES = {"BASELINE": "Hiện hữu B", "EXTERNAL_CANDIDATE": "Phương án ngoài X"}
MISSING = {
    "BASELINE_RUNTIME_UNAVAILABLE": "Chưa có thời gian chạy của B; không đối chiếu số xe tối thiểu B với X.",
    "MINIMUM_FLEET_UNVERIFIED": "Chưa chứng minh số xe tối thiểu theo mô hình thời gian chạy và nghỉ bến thống nhất.",
    "MANDATORY_LAYOVER_NOT_PROVIDED": "Chưa có thời gian nghỉ bến tối thiểu bắt buộc do đơn vị khai thác cung cấp.",
    "INITIAL_STOCK_UNCONFIRMED": "Chưa xác nhận số xe ban đầu thực có tại từng đầu bến.",
    "PROTECTION_AUTHORITY_MISSING": "Chưa cung cấp chính sách bảo vệ dịch vụ có thẩm quyền.",
    "ONBOARD_LOAD_UNCERTIFIED": "Chưa có dữ liệu lên, xuống và số khách trên xe theo điểm dừng để kiểm tra sức chứa thực tế.",
    "OPERATING_DAY_PROFILE_UNVERIFIED": "Chưa xác định ngày và loại ngày khai thác của báo cáo.",
    "PRODUCER_UNVERIFIED": "Nguồn dùng nhãn Xanh SM; chưa xác minh đơn vị hoặc hệ thống lập báo cáo.",
    "DRIVER_SHIFTS_UNVERIFIED": "Lịch xe chưa đủ căn cứ để kết luận về ca lái xe hoặc tuân thủ lao động.",
    "RECORDED_FIELDS_INCONSISTENT": "Có trường dữ liệu ghi trong nguồn không khớp với các mốc giờ; cần làm rõ sai khác độ chính xác.",
    "UNRESOLVED_DEMAND_AGGREGATION": "Chưa xác định được quy tắc tổng hợp nhu cầu; tạm không tính thời gian chờ.",
    "SOURCE_FORMULA_CACHES_UNVERIFIED": "Có giá trị công thức lưu sẵn; chưa xác minh lần tính lại trong ứng dụng nguồn.",
}


def _time(value):
    if value is None:
        return "—"
    seconds = round(value * 60)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}" + (
        f":{seconds % 60:02d}" if seconds % 60 else ""
    )


def _metric(key, value):
    return f'<span data-metric="{e(key)}" data-value="{e(json.dumps(value))}">{n(value, 0 if isinstance(value, int) else 3)}</span>'


def _charts(report, d, demand):
    a = report["alternatives"]
    start = min(a[s]["directions"][d]["first_departure"] for s in SOURCES)
    end = max(a[s]["directions"][d]["last_departure"] for s in SOURCES)
    if demand:
        start, end = min(start, demand[0]["interval_start"]), max(end, demand[-1]["interval_end"])

    def x(t):
        return 65 + 1020 * (t - start) / max(1, end - start)

    maximum = max(a[s]["directions"][d]["maximum_headway"] for s in SOURCES)
    body = ""
    for t in range((start // 60) * 60, end + 1, 60):
        if t >= start:
            body += f'<line x1="{x(t):.2f}" x2="{x(t):.2f}" y1="25" y2="375" stroke="#dfe5df"/><text x="{x(t):.2f}" y="402" text-anchor="middle">{clock(t)}</text>'
    for source, color, y in [("BASELINE", "#486978", 55), ("EXTERNAL_CANDIDATE", "#146450", 100)]:
        v = a[source]["directions"][d]
        body += f'<text x="8" y="{y + 4}">{"B" if source == "BASELINE" else "X"}</text><line x1="65" x2="1085" y1="{y}" y2="{y}" stroke="{color}"/>'
        for t in v["departures"]:
            body += f'<line x1="{x(t):.2f}" x2="{x(t):.2f}" y1="{y - 12}" y2="{y + 12}" stroke="{color}" stroke-width="2"><title>{e(SOURCES[source])}: {clock(t)}</title></line>'
        points = []
        for g in v["gaps"]:
            gy = 270 - 120 * g["gap_minutes"] / max(1, maximum)
            points.extend(
                [
                    f"{x(g['preceding_departure']):.2f},{gy:.2f}",
                    f"{x(g['following_departure']):.2f},{gy:.2f}",
                ]
            )
        body += f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"><title>{e(SOURCES[source])}: giãn cách thực tế theo từng cặp chuyến, phút</title></polyline>'
    body += f'<text x="8" y="145">{maximum}′</text><text x="8" y="272">0′</text><text x="65" y="135">Giãn cách thực tế: B (xám xanh), X (xanh lá)</text>'
    if demand:
        peak = max(b["demand_passengers"] for b in demand)
        body += '<text x="65" y="300">Nhu cầu nửa giờ từ nguồn; mô hình khách đến đều trong từng khoảng</text>'
        for b in demand:
            height = 60 * b["demand_passengers"] / max(1, peak)
            body += f'<rect x="{x(b["interval_start"]):.2f}" y="{375 - height:.2f}" width="{max(1, x(b["interval_end"]) - x(b["interval_start"]) - 1):.2f}" height="{height:.2f}" fill="#9eb7a5"><title>{clock(b["interval_start"])}–{clock(b["interval_end"])}: {n(b["demand_passengers"])} khách/ngày</title></rect>'
    else:
        body += '<text x="65" y="335">Chưa đủ bằng chứng chuẩn hoá nhu cầu; không vẽ giá trị thay thế.</text>'
    return _svg(
        f"{'Chiều đi' if d == 'outbound' else 'Chiều về'}: giờ xuất bến, giãn cách và nhu cầu",
        420,
        body,
    )


def render_external_html(report, data):
    a, fleet = report["alternatives"], report["fleet"]
    parts = [
        f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đối chiếu biểu đồ giờ bên ngoài</title><style>{CSS}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style></head><body><main>',
        "<header><p>RÀ SOÁT BIỂU ĐỒ GIỜ · MVP-4</p><h1>Đối chiếu hiện hữu B và phương án ngoài X</h1>",
        f'<p>{e(report["route_identity"]["outbound"])}</p><p>Nguồn: {e(report["source"]["workbook"])}</p><p class="code">SHA-256: {e(report["source"]["sha256"])}</p>',
        '<p class="decision">Chưa phải phê duyệt. Kết quả dùng để rà soát độc lập và xác định bằng chứng còn thiếu.</p></header>',
        '<nav><a href="#summary">Tổng hợp</a><a href="#timetable">Biểu đồ hai chiều</a><a href="#deterioration">Suy giảm dịch vụ</a><a href="#circulation">Chuỗi xe</a><a href="#ledger">Nguồn và kiểm tra</a></nav>',
        '<section id="summary"><h2>Tổng hợp đối chiếu</h2>',
    ]
    rows = []
    for d in DIRECTIONS:
        for key, title in [
            ("trip_count", "Số chuyến"),
            ("minimum_headway", "Giãn cách nhỏ nhất (phút)"),
            ("maximum_headway", "Giãn cách lớn nhất (phút)"),
            ("distinct_headway_values", "Số giá trị giãn cách khác nhau"),
            ("waiting_minutes", "Thời gian chờ mô hình (phút)"),
        ]:
            rows.append(
                [
                    f"{title} · {'chiều đi' if d == 'outbound' else 'chiều về'}",
                    *[_metric(f"{s}.{d}.{key}", a[s]["directions"][d][key]) for s in SOURCES],
                    "Ước tính mô hình"
                    if key == "waiting_minutes"
                    else "Tính lại độc lập từ từng ô giờ xuất bến",
                ]
            )
        rows.append(
            [
                f"Chuyến đầu/cuối · {'chiều đi' if d == 'outbound' else 'chiều về'}",
                *[
                    f"{_time(a[s]['directions'][d]['first_departure'])} / {_time(a[s]['directions'][d]['last_departure'])}"
                    for s in SOURCES
                ],
                "Đối chiếu với bảng tổng quan",
            ]
        )
    for key, title in [
        ("waiting_minutes", "Thời gian chờ mô hình trong thời gian có phục vụ (phút)"),
        ("outside_service_passengers", "Nhu cầu ngoài chuyến đầu/cuối; không tính chờ"),
    ]:
        rows.append(
            [
                title,
                *[_metric(f"{s}.{key}", a[s][key]) for s in SOURCES],
                "Ước tính theo khách đến đều; không bịa chuyến ngày kế tiếp",
            ]
        )
    for key, title, status in [
        ("reported_fleet", "Số xe báo cáo", "Do nguồn khai báo"),
        (
            "validated_assignment_fleet",
            "Số xe trong phương án chuỗi đã kiểm tra",
            "Kiểm tra mốc giờ, vị trí và không trùng việc",
        ),
        (
            "minimum_fleet",
            "Số xe tối thiểu đã chứng minh",
            "Chưa xác minh; thiếu mô hình dùng chung",
        ),
    ]:
        rows.append([title, *[_metric(f"{s}.{key}", fleet[s][key]) for s in SOURCES], status])
    parts.append(
        _table(["Chỉ tiêu", "Hiện hữu B", "Phương án ngoài X", "Phạm vi bằng chứng"], rows)
    )
    x = fleet["EXTERNAL_CANDIDATE"]
    parts.extend(
        [
            f"<p><strong>Tình trạng rà soát:</strong> {e({'RECORDED_CHAIN_FAILURE': 'Có lỗi trong chuỗi xe ghi nhận', 'HUMAN_REVIEW_REQUIRED': 'Cần người có thẩm quyền rà soát', 'INSUFFICIENT_OPERATIONAL_EVIDENCE': 'Chưa đủ bằng chứng vận hành'}[report['readiness']])}.</p>",
            "<p>Đối chiếu chờ: "
            + e(
                {
                    "UNAVAILABLE": "Chưa đủ dữ liệu",
                    "SAME_MODELED_POPULATION": "Hai phương án có cùng tập khách trong phạm vi mô hình",
                    "DIFFERENT_SERVED_POPULATIONS": "Hai phương án phục vụ tập khách khác nhau; không diễn giải mức chờ trung bình thấp hơn là cải thiện. Các khoảng mất phục vụ được ưu tiên rà soát.",
                }[report["waiting_comparison_status"]]
            )
            + ".</p>",
            "<p>Thời gian chờ được tính bằng cùng hàm tích phân của MVP-3 trên các giờ xuất bến thực tế. Dữ liệu lịch sử lên xe không tự động là quan sát độc lập về khách đến bến. Tổng hợp nửa giờ chỉ được dùng sau khi khớp từng cặp hiển thị với các quan sát trong khung; phần ngoài khung ở nguồn được giữ riêng.</p>",
            "<p>Giá trị cao điểm/thấp điểm trong tổng quan là tuyên bố của nguồn; giãn cách lớn nhất ở bảng trên được tính từ từng cặp chuyến. Nhiều giá trị giãn cách là dấu hiệu cần rà soát tính đều đặn, chưa đủ để kết luận vi phạm.</p>",
            "<ul>"
            + "".join(f"<li>{e(MISSING.get(m, m))}</li>" for m in report["missing_evidence"])
            + "</ul></section>",
            '<section id="timetable"><h2>Biểu đồ hai chiều</h2>',
        ]
    )
    for d in DIRECTIONS:
        parts.append(_charts(report, d, [b for b in data["demand"] if b["direction"] == d]))
        rows = []
        for source in SOURCES:
            v = a[source]["directions"][d]
            rows.extend(
                [
                    [
                        e(SOURCES[source]),
                        str(i + 1),
                        clock(t),
                        str(v["headways"][i - 1]) if i else "—",
                    ]
                    for i, t in enumerate(v["departures"])
                ]
            )
        parts.append(
            "<details><summary>Giờ xuất bến và giãn cách chính xác · "
            + ("chiều đi" if d == "outbound" else "chiều về")
            + "</summary>"
            + _table(["Phương án", "STT", "Xuất bến", "Giãn cách từ chuyến trước (phút)"], rows)
            + "</details>"
        )
        tail = a["EXTERNAL_CANDIDATE"]["directions"][d]["end_tail"]
        parts.append(
            f"<p>Đuôi cuối ngày X · {'chiều đi' if d == 'outbound' else 'chiều về'}: "
            + "; ".join(
                f"{clock(g['preceding_departure'])}–{clock(g['following_departure'])}: {g['gap_minutes']} phút"
                for g in tail["last_three_gaps"]
            )
            + ".</p>"
        )
    parts.append(
        '</section><section id="deterioration"><h2>Suy giảm dịch vụ theo khoảng nhu cầu</h2><p>Ưu tiên mất phạm vi phục vụ, sau đó xếp theo tác động tăng chờ (khách-phút). Không tính chênh lệch chờ khi tập khách được phục vụ khác nhau. Mỗi giãn cách được giữ đủ cặp chuyến trước/sau dù cắt qua biên nửa giờ. Cảnh báo là ngưỡng rà soát; chưa có thẩm quyền bảo vệ dịch vụ trong nguồn.</p>'
    )
    rows = []
    for b in report["deterioration_intervals"]:
        rows.append(
            [
                label(b["direction"]),
                f"{clock(b['interval_start'])}–{clock(b['interval_end'])}",
                n(b["demand_passengers"]),
                str(b["baseline"]["departure_count"]),
                str(b["candidate"]["departure_count"]),
                n(b["baseline"]["waiting_minutes"]),
                n(b["candidate"]["waiting_minutes"]),
                n(b["demand_weighted_waiting_impact"]),
                n(b["outside_service_passenger_change"]),
                _gaps(b["baseline"]["gaps"]),
                _gaps(b["candidate"]["gaps"]),
                "Chưa xác minh bảo vệ; khách đến đều trong khoảng, dùng dữ liệu lên xe lịch sử",
            ]
        )
    parts.append(
        _table(
            [
                "Chiều",
                "Khoảng giờ",
                "Khách/ngày",
                "Chuyến B",
                "Chuyến X",
                "Chờ B (phút)",
                "Chờ X (phút)",
                "Tăng khách-phút",
                "Tăng khách ngoài giờ phục vụ",
                "Cặp chuyến B",
                "Cặp chuyến X",
                "Bảo vệ và giới hạn",
            ],
            rows,
        )
    )
    parts.append(
        "<details><summary>Toàn bộ khoảng nhu cầu, kể cả giá trị không</summary>"
        + _table(
            ["Chiều", "Khoảng giờ", "Khách/ngày", "Chờ B", "Chờ X", "Chênh lệch chờ (phút)"],
            [
                [
                    label(b["direction"]),
                    f"{clock(b['interval_start'])}–{clock(b['interval_end'])}",
                    n(b["demand_passengers"]),
                    n(b["baseline"]["waiting_minutes"]),
                    n(b["candidate"]["waiting_minutes"]),
                    n(b["waiting_difference_minutes"]),
                ]
                for b in report["buckets"]
            ],
        )
        + "</details></section>"
    )
    parts.append('<section id="circulation"><h2>Rà soát chuỗi xe ghi nhận</h2>')
    parts.append(
        f"<p>Chuỗi đúng về mốc giờ và vị trí: {x['validated_chain_count']}/{x['recorded_vehicle_count']}; trạng thái toàn bộ phân công: {e(x['schedule_status'])}. Cần đặt ban đầu {x['initial_terminal_requirements']['outbound']} xe tại Miền Tây và {x['initial_terminal_requirements']['inbound']} xe tại ĐHQG-A theo chuỗi ghi nhận; chưa đối chiếu tồn xe thực tế.</p>"
    )
    parts.append(
        "<p>Nghỉ bến tối thiểu bắt buộc: chưa cung cấp. "
        + (
            f"Kịch bản được khai báo riêng: {n(x['minimum_layover_assumption'])} phút; biên quay đầu chỉ có ý nghĩa trong kịch bản này."
            if x["minimum_layover_assumption"] is not None
            else "Không tự áp dụng ngưỡng 5 phút."
        )
        + " Không suy ra ca lái xe hoặc tuân thủ lao động từ lịch xe.</p>"
    )
    summaries = {s["vehicle_id"]: s for s in data["vehicle_summaries"]}
    parts.append(
        _table(
            [
                "Xe",
                "Bến đầu",
                "Chuyến ghi nhận",
                "Chuyến theo tổng hợp",
                "Giờ đầu/cuối",
                "Thời lượng nguồn",
                "Tổng chạy tính lại",
                "Khoảng hoạt động",
            ],
            [
                [
                    e(v["vehicle_id"]),
                    label(v["starting_terminal"]),
                    str(v["trip_count"]),
                    n(summaries.get(v["vehicle_id"], {}).get("trip_count")),
                    f"{_time(v['first_departure'])} / {_time(v['last_arrival'])}",
                    n(summaries.get(v["vehicle_id"], {}).get("reported_operating_duration")),
                    n(v["running_duration"]),
                    n(v["operating_span"]),
                ]
                for v in x["vehicles"]
            ],
        )
    )
    for v in x["vehicles"]:
        parts.append(
            f"<details><summary>Xe {e(v['vehicle_id'])} · {v['trip_count']} chuyến</summary>"
            + _table(
                [
                    "Chiều",
                    "STT chiều",
                    "Xuất bến",
                    "Đến bến",
                    "Nghỉ ghi nguồn",
                    "Nghỉ theo mốc giờ",
                    "Biên kịch bản",
                    "Tham chiếu nguồn",
                ],
                [
                    [
                        label(t["direction"]),
                        str(t["trip_sequence"]),
                        _time(t["departure"]),
                        _time(t["arrival"]),
                        n(t["recorded_layover"]),
                        n(t["implied_layover"]),
                        n(t["turnaround_margin"]),
                        e(t["source_sheet"] + "!" + ", ".join(t["source_cells"])),
                    ]
                    for t in v["trips"]
                ],
            )
            + "</details>"
        )
    for title, values in [
        ("Lỗi chuỗi xe", x["chain_issues"]),
        ("Sai khác trường ghi nguồn", x["source_discrepancies"]),
        ("Vấn đề khi trích xuất", report["issues"]),
    ]:
        parts.append(
            f"<details><summary>{title}: {len(values)}</summary>"
            + _table(
                ["Mã kiểm tra", "Bằng chứng"],
                [
                    [
                        e(v["code"]),
                        '<pre class="code">'
                        + e(json.dumps(v, ensure_ascii=False, indent=2))
                        + "</pre>",
                    ]
                    for v in values
                ],
            )
            + "</details>"
        )
    parts.append("</section><section><h2>Đối chiếu ba phương án</h2>")
    three = report["three_way"]
    parts.append(
        "<p>"
        + (
            "Chỉ xếp thứ tự thời gian chờ trong kịch bản chung được khai báo; không tự chọn phương án hoặc phê duyệt."
            if three["rankable"]
            else "Chưa đủ điều kiện xếp hạng ba phương án. Kết quả C, nếu có, được trình bày riêng; không dùng lại chỉ tiêu lịch sử làm đối chứng cùng điều kiện."
        )
        + "</p>"
    )
    parts.append(
        "<ul>"
        + "".join(f'<li class="code">{e(reason)}</li>' for reason in three["reasons"])
        + "</ul>"
    )
    if three["separate_result"]:
        c = three["separate_result"]
        parts.append(
            _table(
                ["Kết quả C tính lại trên nhu cầu báo cáo", "Giá trị"],
                [
                    ["Thời gian chờ mô hình (phút)", n(c["waiting_minutes"])],
                    ["Thứ tự trong kịch bản chung", e(three["waiting_order"])],
                ],
            )
        )
    parts.append('</section><section id="ledger"><h2>Nguồn và sổ kiểm tra</h2>')
    parts.append(
        _table(
            ["Nhóm bằng chứng", "Phạm vi"],
            [
                [
                    "Trích từ nguồn",
                    "Tổng quan, bốn bảng giờ, hai bảng lịch xe và tổng hợp theo xe; từng ô nguồn được lưu trong JSON chuẩn hoá.",
                ],
                [
                    "Tính lại độc lập",
                    "Số chuyến, từng giãn cách, khớp chuyến, mốc đến/đi, bến nối tiếp và sai khác trường nguồn.",
                ],
                [
                    "Ước tính mô hình",
                    "Thời gian chờ với khách đến đều trong nửa giờ; số khách không có chuyến phục vụ được nêu riêng.",
                ],
                [
                    "Giả định được cấu hình",
                    e(json.dumps(report["ledger"]["configured_assumptions"], ensure_ascii=False)),
                ],
                [
                    "Chưa xác minh",
                    "Nguồn phát hành, số xe tối thiểu, thời gian chạy B, ngưỡng nghỉ bắt buộc, sức chứa, ca lái xe và chính sách bảo vệ.",
                ],
            ],
        )
    )
    parts.append(
        '<details><summary>Vết trích xuất và tuyên bố trong tổng quan</summary><pre class="code">'
        + e(
            json.dumps(
                {
                    "source": data["source"],
                    "summary": data["summary"],
                    "demand_status": data["demand_status"],
                    "vehicle_summaries": data["vehicle_summaries"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        + "</pre></details></section>"
    )
    encoded = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    parts.append(
        f'<script type="application/json" id="benchmark-data">{encoded}</script></main></body></html>'
    )
    return "".join(parts)

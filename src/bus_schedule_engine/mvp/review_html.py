"""Offline Vietnamese review: native tables/details and accessible inline SVG."""

from __future__ import annotations

import json
from html import escape

from .input import DIRECTIONS
from .review import INSUFFICIENT

LABELS = {
    "outbound": "Chiều đi",
    "inbound": "Chiều về",
    "REPLACE_BASELINE": "Đề xuất thay B bằng C; cần rà soát trước khi phê duyệt",
    "KEEP_BASELINE": "Giữ biểu đồ B",
    "UNRESOLVED": "Chưa có quyết định tự động đủ căn cứ",
    "CONFIRMED_HARD_RULE_FAILURE": "Vi phạm ràng buộc đã xác nhận — yêu cầu sửa phương án",
    "HUMAN_REVIEW_REQUIRED": "Có suy giảm dịch vụ đáng kể — cần người có thẩm quyền rà soát",
    "INSUFFICIENT_OPERATIONAL_EVIDENCE": "Chưa đủ bằng chứng vận hành",
    "READY_FOR_HUMAN_APPROVAL_CONSIDERATION": "Đủ điều kiện trình xem xét phê duyệt",
    "PASS_DECLARED_RULES": "Đạt các ràng buộc đã khai báo",
    "CONFIRMED_FAILURE": "Có vi phạm đã xác nhận",
    "MATERIAL_WAIT_DETERIORATION": "Thời gian chờ tăng đáng kể",
    "HIGH_DEMAND_FREQUENCY_REDUCTION": "Giảm chuyến trong khoảng nhu cầu cao",
    "HIGH_DEMAND_LONGER_GAP": "Giãn cách dài hơn trong khoảng nhu cầu cao",
    "PROTECTION_AUTHORITY_MISSING": "Chưa cung cấp khung giờ và ngưỡng bảo vệ dịch vụ cho đủ hai chiều.",
    "INITIAL_STOCK_UNCONFIRMED": "Chưa xác nhận số xe ban đầu thực có tại từng đầu bến.",
    "INITIAL_STOCK_COMPARISON_INCOMPLETE": "Chưa hoàn thành đối chiếu xe ban đầu với chuỗi xe chính xác.",
    "LAYOVER_UNVERIFIED": "Thời gian nghỉ đầu bến là giả định được khai báo; chưa xác minh vận hành.",
    "RUNTIME_UNVERIFIED": "Thời gian chạy là đầu vào mô hình; chưa xác minh trong điều kiện khai thác.",
    "ONBOARD_LOAD_UNCERTIFIED": "Thiếu dữ liệu lên xe, xuống xe và số khách trên xe theo điểm dừng để chứng nhận hệ số đầy tải thực tế.",
    "EXACT_CIRCULATION_INCOMPLETE": "Chưa chứng minh được chuỗi xe và số xe tối thiểu theo các giả định đã khai báo.",
    "TIMETABLE_UNAVAILABLE": "Chưa có biểu đồ đủ bằng chứng để đánh giá.",
    "DEMAND_OUTSIDE_SERVICE": "Có nhu cầu ngoài giờ chuyến đầu/cuối; chưa tính thời gian chờ cho phần này.",
    "UNVERIFIED": "Chưa xác minh",
    "VERIFIED_AGAINST_DECLARED_STOCK": "Đã đối chiếu với số xe được khai báo; chưa phải xác nhận tại hiện trường",
    "CONFIRMED_INFEASIBLE": "Không đáp ứng số xe/giới hạn đội xe đã khai báo",
    "FLEET_SAVING_WITH_EQUIVALENT_WAIT": "Giảm số xe, thời gian chờ toàn ngày trong biên tương đương được cấu hình",
    "NO_JUSTIFIED_REPLACEMENT_WITHIN_SEARCH": "Trong phạm vi tìm kiếm, chưa có phương án thay B đủ căn cứ",
    "SERVICE_DETERIORATION_EXCEEDS_EQUIVALENCE": "Suy giảm dịch vụ vượt biên tương đương được cấu hình",
    "MATERIAL_PASSENGER_WAIT_IMPROVEMENT": "Thời gian chờ mô hình cải thiện đáng kể",
    "MATERIAL_PROTECTED_SERVICE_IMPROVEMENT": "Dịch vụ trong khung giờ bảo vệ được cải thiện",
    "REPLACE_NONCOMPLIANT_BASELINE": "Thay biểu đồ B có vi phạm đã được chứng minh",
}
METRICS = {
    "baseline_fleet": "Số xe của B",
    "selected_fleet": "Số xe phương án được đề xuất",
    "fleet_ceiling": "Giới hạn đội xe",
    "baseline_waiting_minutes": "Thời gian chờ B (phút)",
    "selected_waiting_minutes": "Thời gian chờ phương án được đề xuất (phút)",
    "waiting_difference_minutes": "Chênh lệch thời gian chờ (phút)",
    "waiting_difference_percent": "Chênh lệch thời gian chờ (%)",
    "baseline_maximum_headway": "Giãn cách lớn nhất của B (phút)",
    "selected_maximum_headway": "Giãn cách lớn nhất của phương án được đề xuất (phút)",
    "maximum_headway_difference": "Chênh lệch giãn cách lớn nhất (phút)",
    "comparison_fleet": "Số xe phương án đang đối chiếu",
    "comparison_waiting_minutes": "Thời gian chờ phương án đang đối chiếu (phút)",
    "comparison_waiting_difference_minutes": "Chênh lệch chờ phương án đang đối chiếu (phút)",
    "comparison_maximum_headway": "Giãn cách lớn nhất phương án đang đối chiếu (phút)",
}
CSS = """
:root{color-scheme:light;--ink:#16302f;--muted:#48645e;--paper:#f4f4ee;--line:#c9d4cc;--b:#486978;--c:#146450;--warn:#9b3e20}
*{box-sizing:border-box}html{scroll-behavior:auto}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 'Segoe UI',Arial,sans-serif}
main{max-width:1280px;margin:auto;padding:42px 36px 72px}h1{font-family:Georgia,'Times New Roman',serif;font-size:clamp(28px,4vw,48px);line-height:1.18;max-width:900px;margin:12px 0 28px}
h2{font-size:26px;line-height:1.3;margin:40px 0 16px}h3{font-size:20px;margin:28px 0 10px}p{max-width:78ch;margin:12px 0}a{color:var(--c);text-underline-offset:.2em}a:focus-visible,summary:focus-visible{outline:3px solid var(--c);outline-offset:4px}
nav{display:flex;flex-wrap:wrap;gap:10px 24px;border-block:1px solid var(--line);padding:13px 0;margin-bottom:28px}header{border-bottom:2px solid var(--ink);padding-bottom:20px}.decision{font-size:22px;font-weight:650}.code{font-size:14px;color:var(--muted);overflow-wrap:anywhere}
.review{background:#e6eee8;padding:20px 24px;margin:22px 0}.warn{color:var(--warn)}.muted{color:var(--muted)}.columns{display:grid;grid-template-columns:1.15fr 1fr;gap:36px}.scroll{overflow-x:auto;margin:18px 0}.scroll:focus-visible{outline:2px solid var(--c)}
table{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}caption{text-align:left;font-weight:650;padding-bottom:12px}th{text-align:left;color:var(--muted);font-weight:650;background:#e9eee8}td,th{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}td{overflow-wrap:anywhere}tbody tr:hover{background:#edf1e9}tr.problem{background:#fbede4}
summary{cursor:pointer;color:var(--c);font-weight:600;padding:10px 0}details{margin:12px 0;border-bottom:1px solid var(--line)}details p{margin-top:0}ul{padding-left:22px}li{margin:6px 0}.fine{font-size:14px;color:var(--muted)}
svg{display:block;width:100%;height:auto;min-width:680px;background:#fff}svg text{font-family:'Segoe UI',Arial,sans-serif;font-size:12px;fill:var(--ink)}figure{margin:20px 0}figcaption{font-size:14px;color:var(--muted);margin:10px 0}.b{color:var(--b)}.c{color:var(--c)}.pair{white-space:nowrap}.stock{font-weight:650;font-size:19px}.provenance{overflow-wrap:anywhere}
::selection{background:#d4e7dc;color:var(--ink)}@media(max-width:760px){main{padding:24px 18px 48px}.columns{display:block}h2{font-size:23px}td,th{padding:8px}.review{padding:15px}nav{gap:8px 16px}}
[data-metric]{white-space:nowrap}
@page{size:A4 landscape;margin:12mm}@media print{body{background:white;font-size:11px}main{max-width:none;padding:0}nav{display:none}h1{font-size:28px}h2{font-size:20px;margin-top:22px}h3{font-size:16px}.columns{grid-template-columns:1fr 1fr;gap:20px}table{font-size:10px}td,th{padding:5px}.scroll{overflow:visible}svg{min-width:0}details{break-inside:avoid}details>summary{display:none}details>*:not(summary){display:block!important}figure{break-inside:avoid}.review{padding:12px}thead{display:table-header-group}tr{break-inside:avoid}a{color:inherit;text-decoration:none}}
@media print{details[open]::details-content{content-visibility:visible!important}details{break-inside:auto}details>summary{display:block;list-style:none}}
"""


def e(value):
    return escape(str(value), quote=True)


def label(value):
    return e(LABELS.get(value, value if value is not None else "Chưa có"))


def n(value, digits=3):
    return "—" if value is None else f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def clock(minute):
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _table(headings, rows, caption=None):
    return (
        '<div class="scroll" tabindex="0"><table>'
        + (f"<caption>{e(caption)}</caption>" if caption else "")
        + "<thead><tr>"
        + "".join(f'<th scope="col">{e(h)}</th>' for h in headings)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


def _gaps(gaps):
    return (
        "<br>".join(
            f'<span class="pair">{clock(g["preceding_departure"])} → {clock(g["following_departure"])}</span>: {g["gap_minutes"]} phút; giao {clock(g["overlap_start"])}–{clock(g["overlap_end"])} ({g["overlap_minutes"]} phút)'
            for g in gaps
        )
        or "Không có khoảng giãn cách giao với khoảng nhu cầu"
    )


def _svg(title, height, body):
    return f'<figure><div class="scroll" tabindex="0"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 {height}" role="img" aria-label="{e(title)}"><title>{e(title)}</title>{body}</svg></div><figcaption>{e(title)}</figcaption></figure>'


def _axis(start, end, y, maximum, height):
    parts = []
    for t in range((start // 60 + 1) * 60, end + 1, 60):
        x = 65 + (t - start) / max(1, end - start) * 1020
        parts.append(
            f'<line x1="{x:.2f}" y1="20" x2="{x:.2f}" y2="{height - 35}" stroke="#dfe5df"/><text x="{x:.2f}" y="{height - 12}" text-anchor="middle">{clock(t)}</text>'
        )
    for value in (0, maximum / 2, maximum) if maximum is not None else ():
        position = y(value)
        parts.append(f'<text x="55" y="{position + 4:.2f}" text-anchor="end">{n(value, 1)}</text>')
    return "".join(parts)


def _direction_charts(review, direction):
    buckets = [b for b in review["buckets"] if b["direction"] == direction]
    if not buckets:
        return f"<p>{INSUFFICIENT}</p>"
    start, end = buckets[0]["interval_start"], buckets[-1]["interval_end"]

    def x(t):
        return 65 + (t - start) / max(1, end - start) * 1020

    maximum = max(
        g["gap_minutes"]
        for key in ("baseline", "candidate")
        for b in buckets
        for g in b[key]["gaps"]
    )

    def y(v):
        return 170 - v / max(1, maximum) * 140

    body = _axis(start, end, y, maximum, 250)
    for b in buckets:
        if b["warnings"]:
            body += f'<rect x="{x(b["interval_start"]):.2f}" y="20" width="{x(b["interval_end"]) - x(b["interval_start"]):.2f}" height="200" fill="#f9e6da" opacity="0.65"><title>{clock(b["interval_start"])}–{clock(b["interval_end"])}: {e(", ".join(LABELS[w] for w in b["warnings"]))}</title></rect>'
    for key, color, departure_y in (
        ("baseline_departures", "#486978", 190),
        ("comparison_departures", "#146450", 210),
    ):
        times = review[key][direction]
        for a, z in zip(times, times[1:], strict=False):
            body += f'<line x1="{x(a):.2f}" y1="{y(z - a):.2f}" x2="{x(z):.2f}" y2="{y(z - a):.2f}" stroke="{color}" stroke-width="2"><title>{clock(a)} → {clock(z)}: {z - a} phút</title></line>'
        for t in times:
            body += f'<line x1="{x(t):.2f}" y1="{departure_y - 5}" x2="{x(t):.2f}" y2="{departure_y + 5}" stroke="{color}"><title>{clock(t)}</title></line>'
    for r in review["regimes"]:
        if r["direction"] == direction:
            body += f'<line x1="{x(r["start_time"]):.2f}" x2="{x(r["start_time"]):.2f}" y1="20" y2="220" stroke="#715b33" stroke-dasharray="4 4"><title>ServiceRegime {clock(r["start_time"])}–{clock(r["end_time"])}: {r["headway_minutes"]} phút</title></line>'
    body += '<text x="12" y="194">B</text><text x="12" y="214">C</text><text x="65" y="15">Giãn cách (phút); vạch dưới: giờ xuất bến</text>'
    charts = _svg(
        f"{LABELS[direction]}: B màu xanh xám; phương án đối chiếu màu xanh lá. Nền cam: cảnh báo; nét đứt: ranh giới ServiceRegime.",
        250,
        body,
    )
    max_demand = max(b["demand_rate_per_minute"] * 60 for b in buckets)

    def yd(v):
        return 155 - v / max(1, max_demand) * 125

    body = _axis(start, end, yd, max_demand, 200)
    for b in buckets:
        a, z, demand = b["interval_start"], b["interval_end"], b["demand_rate_per_minute"] * 60
        body += f'<rect x="{x(a):.2f}" y="{yd(demand):.2f}" width="{max(0, x(z) - x(a) - 1):.2f}" height="{155 - yd(demand):.2f}" fill="{"#9b3e20" if b["high_demand"] else "#77978b"}"><title>{clock(a)}–{clock(z)}: {n(b["demand_passengers"])} khách; {n(demand)} khách/giờ</title></rect>'
    body += '<text x="65" y="15">Nhu cầu quy đổi khách/giờ; màu đậm: nhu cầu cao theo ngưỡng rà soát</text>'
    charts += _svg(
        "Nhu cầu theo từng khoảng thời gian; cường độ được chuẩn hoá theo độ dài khoảng.", 200, body
    )
    max_wait = max(
        (b[key]["waiting_minutes"] or 0) for b in buckets for key in ("baseline", "candidate")
    )

    def yw(v):
        return 155 - v / max(1, max_wait) * 125

    body = _axis(start, end, yw, max_wait, 200)
    for key, color in (("baseline", "#486978"), ("candidate", "#146450")):
        for b in buckets:
            wait = b[key]["waiting_minutes"]
            if wait is not None:
                body += f'<line x1="{x(b["interval_start"]):.2f}" x2="{x(b["interval_end"]):.2f}" y1="{yw(wait):.2f}" y2="{yw(wait):.2f}" stroke="{color}" stroke-width="3"><title>{clock(b["interval_start"])}–{clock(b["interval_end"])} {key}: {n(wait, 6)} phút</title></line>'
    body += '<text x="65" y="15">Thời gian chờ mô hình theo khoảng nhu cầu (phút)</text>'
    return charts + _svg(
        "So sánh thời gian chờ theo khoảng; không thay thế bằng trung bình toàn ngày.", 200, body
    )


def _assessment_html(assessment):
    content = f"<p><strong>{label(assessment['readiness'])}</strong></p><p>Ràng buộc: {label(assessment['hard_rule_status'])}. Xe ban đầu: {label(assessment['stock_status'])}.</p>"
    if assessment["hard_failures"]:
        content += (
            '<p class="warn">Chặn phê duyệt: ' + e(", ".join(assessment["hard_failures"])) + "</p>"
        )
    content += (
        f"<p><strong>{e(assessment['evidence_label'])}</strong></p><ul>"
        + "".join(f"<li>{label(m)}</li>" for m in assessment["missing_evidence"])
        + "</ul>"
    )
    if assessment["stock_comparison"]:
        content += _table(
            ["Đầu bến", "Cần theo chuỗi", "Đã khai báo", "Đối chiếu"],
            [
                [
                    label(d),
                    n(s["required"], 0),
                    n(s["declared"], 0),
                    "Đủ" if s["sufficient"] else "Thiếu",
                ]
                for d, s in assessment["stock_comparison"].items()
            ],
        )
    return content


def _circulation_html(circulation, title):
    if not circulation or not circulation["vehicles"]:
        return f"<h3>{e(title)}</h3><p>{INSUFFICIENT}: chưa có chuỗi xe chính xác.</p>"
    required = circulation["initial_vehicles_required"]
    content = f'<h3>{e(title)}</h3><p class="stock">Xe ban đầu theo mô hình: đầu bến chiều đi {required["outbound"]} xe · đầu bến chiều về {required["inbound"]} xe.</p><p>Cần {circulation["required_fleet"]} xe; giới hạn {circulation["fleet_ceiling"]} xe. Đồng thời đang chạy tối đa {circulation["maximum_running"]}; đang chạy hoặc nghỉ bắt buộc tối đa {circulation["maximum_runtime_plus_layover"]}. Đây là yêu cầu mô hình, chưa phải tồn xe thực tế.</p>'
    trips = [t for v in circulation["vehicles"] for t in v["trips"]]
    start, end = min(t["departure"] for t in trips), max(t["ready"] for t in trips)

    def x(t):
        return 65 + (t - start) / max(1, end - start) * 1020

    height = 50 + len(circulation["vehicles"]) * 28
    body = _axis(start, end, lambda _: 0, None, height)
    for i, vehicle in enumerate(circulation["vehicles"]):
        y = 30 + i * 28
        body += f'<text x="8" y="{y + 4}">{e(vehicle["vehicle_id"])}</text>'
        for trip in vehicle["trips"]:
            color = "#486978" if trip["direction"] == "outbound" else "#146450"
            body += f'<rect x="{x(trip["departure"]):.2f}" y="{y - 5}" width="{x(trip["arrival"]) - x(trip["departure"]):.2f}" height="10" fill="{color}"><title>{e(trip["trip_id"])} {clock(trip["departure"])} → {clock(trip["arrival"])}; sẵn sàng {clock(trip["ready"])}</title></rect><line x1="{x(trip["arrival"]):.2f}" x2="{x(trip["ready"]):.2f}" y1="{y}" y2="{y}" stroke="#9b3e20" stroke-width="4"/>'
    content += _svg(
        "Chuỗi xe chính xác: xanh xám = chiều đi; xanh lá = chiều về; đoạn cam = nghỉ bắt buộc.",
        height,
        body,
    )
    for d in DIRECTIONS:
        events = circulation["terminal_flow"]
        flow_start, flow_end = events[0]["minute"], events[-1]["minute"]

        def xf(t, flow_start=flow_start, flow_end=flow_end):
            return 65 + (t - flow_start) / max(1, flow_end - flow_start) * 1020

        maximum = max(ev[d]["physically_present"] for ev in events)

        def yf(v, maximum=maximum):
            return 155 - v / max(1, maximum) * 125

        body = _axis(flow_start, flow_end, yf, maximum, 200)
        for metric, color in (("physically_present", "#486978"), ("ready", "#146450")):
            points = []
            previous = events[0][d][metric]
            for event in events:
                points.extend(
                    [
                        f"{xf(event['minute']):.2f},{yf(previous):.2f}",
                        f"{xf(event['minute']):.2f},{yf(event[d][metric]):.2f}",
                    ]
                )
                previous = event[d][metric]
            dash = 'stroke-dasharray="5 3"' if metric == "ready" else ""
            body += f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2" {dash}/>'
        content += _svg(
            f"Đầu bến {LABELS[d].lower()}: xanh xám liền = xe hiện diện; xanh lá đứt = xe sẵn sàng xuất bến. Trạng thái sau các sự kiện cùng phút.",
            200,
            body,
        )
    content += '<p class="fine">Phân bố chỉ gồm đội xe cần theo mô hình, không cộng xe dư trong khai báo hoặc điều chuyển từ depot. Chuỗi và biểu đồ giữ nguyên thời gian chạy/nghỉ đã khai báo.</p>'
    for vehicle in circulation["vehicles"]:
        content += f"<details><summary>{e(vehicle['vehicle_id'])} · đầu bến {label(vehicle['starting_terminal'])} · {len(vehicle['trips'])} chuyến</summary>"
        content += (
            _table(
                [
                    "Chuyến",
                    "Chiều",
                    "Xuất bến",
                    "Đến bến",
                    "Sẵn sàng sau nghỉ",
                    "Quay đầu thực tế (phút)",
                    "Dư thời gian trước chuyến kế (phút)",
                ],
                [
                    [
                        e(t["trip_id"]),
                        label(t["direction"]),
                        clock(t["departure"]),
                        clock(t["arrival"]),
                        clock(t["ready"]),
                        n(t["actual_turnaround_minutes"], 0),
                        n(t["turnaround_slack_minutes"], 0),
                    ]
                    for t in vehicle["trips"]
                ],
            )
            + "</details>"
        )
    content += (
        "<details><summary>Phân bố xe tại mọi thời điểm sự kiện</summary>"
        + _table(
            [
                "Thời điểm",
                "Hiện diện đi",
                "Sẵn sàng đi",
                "Hiện diện về",
                "Sẵn sàng về",
                "Đang chạy",
                "Chạy/nghỉ bắt buộc",
            ],
            [
                [
                    clock(ev["minute"]),
                    *[n(ev[d][k], 0) for d in DIRECTIONS for k in ("physically_present", "ready")],
                    n(ev["running"], 0),
                    n(ev["unavailable"], 0),
                ]
                for ev in circulation["terminal_flow"]
            ],
        )
        + "</details>"
    )
    return content


def render_review_html(review):
    if not review or "summary" not in review:
        return f'<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chưa đủ bằng chứng vận hành</title><style>{CSS}</style><main><h1>Rà soát vận hành</h1><p>UNRESOLVED — {INSUFFICIENT}</p><p>Kiểm tra run_diagnostics.json; chưa có đầu vào/biểu đồ đã được xác thực.</p></main></html>\n'
    route, decision, summary = review["route_id"], review["operator_decision"], review["summary"]
    title = f"Rà soát vận hành · Tuyến {route}"
    content = f'<header><h1>{e(title)}</h1><p class="decision">{label(decision)}</p><p class="code">{e(decision)} · B → {e(review["comparison_id"])} · Phương án được đề xuất: {e(review["selected_id"])} ({e(review["selected_source"])})</p><p>Báo cáo phục vụ xem xét vận hành. Lựa chọn của bộ tối ưu chưa phải phê duyệt triển khai.</p></header>'
    content += '<nav aria-label="Mục báo cáo"><a href="#executive">Kết luận</a><a href="#timetable">Dịch vụ hai chiều</a><a href="#exceptions">Điểm cần rà soát</a><a href="#circulation">Luân chuyển xe</a><a href="#evidence">Giả định và nguồn</a><a href="#decision">Quyết định tiếp theo</a></nav>'
    content += '<section id="executive"><h2>Kết luận điều hành</h2><div class="columns"><div>'
    content += _table(
        ["Chỉ tiêu", "Giá trị"],
        [
            [
                e(METRICS[k]),
                f'<span data-metric="{e(k)}" data-value="{e(json.dumps(v, allow_nan=False))}">{n(v, 6 if "waiting" in k else 0)}</span>',
            ]
            for k, v in summary.items()
            if not k.startswith("comparison_")
        ],
    )
    content += (
        f'<p>Căn cứ quyết định: {label((review.get("decision") or {}).get("reason"))}.</p></div><div class="review">'
        + _assessment_html(review["selected_assessment"])
        + "</div></div>"
    )
    if review["exceptions"]:
        first = review["exceptions"][0]
        content += f'<p class="warn"><strong>Điểm ưu tiên:</strong> {label(first["direction"])} {clock(first["interval_start"])}–{clock(first["interval_end"])}; chờ {n(first["baseline"]["waiting_minutes"])} → {n(first["candidate"]["waiting_minutes"])} phút; tác động {n(first["demand_weighted_waiting_impact"])} khách-phút. Xem cặp chuyến cụ thể trong bảng ngoại lệ.</p>'
    content += "<p>Trung bình toàn ngày gần bằng nhau có thể che khuất mức tăng chờ ở một khoảng cụ thể: phần cải thiện ở giờ khác hoặc chiều khác bù lại phần suy giảm. Cần đọc cả tác động theo nhu cầu và các cặp chuyến, kể cả khi giãn cách chưa phải dài nhất ngày.</p></section>"
    content += '<section id="timetable"><h2>So sánh dịch vụ theo thời gian</h2>'
    if review["comparison_role"] == "GENERATED_ALTERNATIVE":
        retained = (
            "B được giữ nguyên."
            if decision == "KEEP_BASELINE"
            else "Chưa chọn biểu đồ để triển khai."
        )
        content += f'<p class="review">{retained} Các biểu đồ B–C dưới đây đối chiếu với phương án thử {e(review["comparison_id"])}; đây không phải biểu đồ được chọn. Căn cứ: {label((review["comparison_change_assessment"] or {}).get("reason"))}.</p>'
    elif review["comparison_role"] == "BASELINE_REFERENCE":
        content += '<p class="review">Chưa chọn biểu đồ để triển khai. Dưới đây là biểu đồ B thực có để rà soát; hai chuỗi số liệu đều là B, chưa có phương án C đủ căn cứ.</p>'
    content += _table(
        ["Chỉ tiêu phương án đối chiếu", "Giá trị"],
        [
            [
                e(METRICS[k]),
                f'<span data-metric="{e(k)}" data-value="{e(json.dumps(v, allow_nan=False))}">{n(v, 6 if "waiting" in k else 0)}</span>',
            ]
            for k, v in summary.items()
            if k.startswith("comparison_")
        ],
    )
    content += '<p class="fine">Không dựng ServiceRegime cho B. Giữ giờ xuất bến thực có; không tạo ranh giới giả.</p>'
    for direction in DIRECTIONS:
        content += f"<h3>{label(direction)}</h3>" + _direction_charts(review, direction)
        rows = [b for b in review["buckets"] if b["direction"] == direction]
        content += "<details><summary>Bảng số liệu từng khoảng nhu cầu và giờ xuất bến</summary>"
        content += (
            _table(
                [
                    "Khoảng",
                    "Khách",
                    "Chuyến B/C",
                    "Chờ B/C (phút)",
                    "Δ chờ / %",
                    "Tác động (khách-phút)",
                    "Giờ xuất bến B / C",
                    "Giãn cách giao lớn nhất B/C",
                    "Khách ngoài giờ B/C",
                ],
                [
                    [
                        f"{clock(b['interval_start'])}–{clock(b['interval_end'])}",
                        n(b["demand_passengers"]),
                        f"{b['baseline']['departure_count']}/{b['candidate']['departure_count']}",
                        f"{n(b['baseline']['waiting_minutes'], 6)} / {n(b['candidate']['waiting_minutes'], 6)}",
                        f"{n(b['waiting_difference_minutes'])} / {n(b['waiting_difference_percent'])}%",
                        n(b["demand_weighted_waiting_impact"]),
                        e(" ".join(clock(t) for t in b["baseline"]["departures"]))
                        + "<br>"
                        + e(" ".join(clock(t) for t in b["candidate"]["departures"])),
                        f"{b['baseline']['maximum_intersecting_headway']}/{b['candidate']['maximum_intersecting_headway']}",
                        f"{n(b['baseline']['outside_service_passengers'])}/{n(b['candidate']['outside_service_passengers'])}",
                    ]
                    for b in rows
                ],
            )
            + "</details>"
        )
        content += (
            "<details><summary>Tất cả giãn cách đầy đủ và phần giao với từng khoảng nhu cầu</summary>"
            + _table(
                [
                    "Khoảng",
                    "B: chuyến trước → sau; phần giao",
                    "C: chuyến trước → sau; phần giao",
                    "Căn cứ bảo vệ",
                ],
                [
                    [
                        f"{clock(b['interval_start'])}–{clock(b['interval_end'])}",
                        _gaps(b["baseline"]["gaps"]),
                        _gaps(b["candidate"]["gaps"]),
                        e(b["protection_authority"]),
                    ]
                    for b in rows
                ],
            )
            + "</details>"
        )
    content += (
        "<details><summary>ServiceRegime của phương án đối chiếu</summary>"
        + _table(
            [
                "Chiều",
                "Bắt đầu",
                "Kết thúc",
                "Giãn cách",
                "Số chuyến phân bổ",
                "Số khoảng giãn cách",
            ],
            [
                [
                    label(r["direction"]),
                    clock(r["start_time"]),
                    clock(r["end_time"]),
                    n(r["headway_minutes"], 0),
                    n(r["planned_departure_count"], 0),
                    n(r["gap_count"], 0),
                ]
                for r in review["regimes"]
            ],
        )
        + "</details></section>"
    )
    content += '<section id="exceptions"><h2>Điểm cần rà soát theo mức ưu tiên</h2><p>Ưu tiên vi phạm có căn cứ, sau đó tác động khách-phút tăng. Các cặp chuyến dưới đây là toàn bộ khoảng giãn cách giao với khoảng nhu cầu, bao gồm phần giao tại ranh giới; không quy toàn bộ mức suy giảm cho riêng khoảng dài nhất.</p>'
    rows = []
    for b in review["exceptions"]:
        protection = (
            "<br>".join(
                f"{clock(w['start'])}–{clock(w['end'])}: tối đa {w['maximum_allowed_gap']} phút; tối thiểu {w['minimum_departures']} chuyến; thực tế {w['maximum_gap']} phút/{w['departures']} chuyến; {'ĐẠT' if w['pass'] else 'VI PHẠM'}"
                for w in b["protected_windows"]
            )
            or INSUFFICIENT
        )
        rows.append(
            [
                f"{label(b['direction'])}<br>{clock(b['interval_start'])}–{clock(b['interval_end'])}",
                "<br>".join(label(w) for w in b["warnings"]) or "Vi phạm bảo vệ dịch vụ",
                f"{n(b['demand_passengers'])} khách<br>{n(b['waiting_difference_minutes'])} phút ({n(b['waiting_difference_percent'])}%)<br>{n(b['demand_weighted_waiting_impact'])} khách-phút",
                _gaps(b["candidate"]["gaps"]),
                protection,
            ]
        )
    content += (
        _table(
            [
                "Chiều / khoảng",
                "Vấn đề",
                "Mức độ / nhu cầu",
                "Chuyến trước → sau; giãn cách đầy đủ và phần giao",
                "Ngưỡng có thẩm quyền",
            ],
            rows,
        )
        if rows
        else "<p>Không phát hiện ngoại lệ theo ngưỡng rà soát đã cấu hình.</p>"
    )
    content += (
        "<details><summary>Những cặp chuyến có giãn cách dài nhất trong phương án đối chiếu</summary>"
        + _table(
            ["Chiều", "Chuyến trước", "Chuyến sau", "Giãn cách (phút)"],
            [
                [
                    label(g["direction"]),
                    clock(g["preceding_departure"]),
                    clock(g["following_departure"]),
                    n(g["gap_minutes"], 0),
                ]
                for g in review["maximum_headway_gaps"]
            ],
        )
        + "</details>"
    )
    if review["comparison_role"] != "SELECTED_TIMETABLE":
        content += (
            "<details><summary>Điều kiện xem xét biểu đồ đang đối chiếu</summary>"
            + _assessment_html(review["comparison_assessment"])
            + "</details>"
        )
    for kind in ("selected_assessment", "comparison_assessment"):
        a = review[kind]
        if a["protected_windows"]:
            content += (
                "<details><summary>Ràng buộc bảo vệ đã khai báo · "
                + e(a["candidate_id"])
                + "</summary>"
                + _table(
                    [
                        "Chiều",
                        "Khoảng",
                        "Tối đa / thực tế (phút)",
                        "Tối thiểu / thực tế (chuyến)",
                        "Kết quả",
                    ],
                    [
                        [
                            label(w["direction"]),
                            f"{clock(w['start'])}–{clock(w['end'])}",
                            f"{w['maximum_allowed_gap']}/{w['maximum_gap']}",
                            f"{w['minimum_departures']}/{w['departures']}",
                            "ĐẠT" if w["pass"] else "VI PHẠM",
                        ]
                        for w in a["protected_windows"]
                    ],
                )
                + "</details>"
            )
    if review["rejected_hard_failures"]:
        content += (
            "<details><summary>Phương án bị loại: các vi phạm được bộ máy ghi nhận</summary><p>"
            + e(", ".join(review["rejected_hard_failures"]))
            + "</p>"
            + _table(
                ["Chiều", "Khoảng", "Vấn đề", "Mức vượt", "Đơn vị"],
                [
                    [
                        label(v["direction"]),
                        f"{clock(v['interval_start'])}–{clock(v['interval_end'])}",
                        e(v["problem"]),
                        n(v["severity"]),
                        e(v["severity_units"]),
                    ]
                    for v in review["rejected_service_violations"]
                ],
            )
            + "</details>"
        )
    content += (
        '</section><section id="circulation"><h2>Luân chuyển và phân bố xe</h2>'
        + _circulation_html(review["circulation"], "Đội xe của phương án được đề xuất")
    )
    if review["comparison_circulation"]:
        content += (
            "<details><summary>Luân chuyển của biểu đồ đang đối chiếu</summary>"
            + _circulation_html(
                review["comparison_circulation"], "Đội xe của biểu đồ đối chiếu; chưa được chọn"
            )
            + "</details>"
        )
    content += '</section><section id="evidence"><h2>Giả định, nguồn và giới hạn chứng nhận</h2>'
    content += (
        "<p>Nhu cầu: "
        + (
            "lượt lên xe lịch sử được dùng làm đại diện cho khách đến bến"
            if review["demand_basis"] == "historical_boardings"
            else "khách đến bến độc lập được khai báo"
        )
        + ". Mô hình giả định khách đến đều trong từng khoảng. Thời gian chờ là thời gian chờ lịch trình, không phải đo thực địa; nhu cầu ngoài chuyến đầu/cuối được loại khỏi trung bình và công khai trong chi tiết.</p>"
    )
    content += _table(
        [
            "Chiều",
            "Chuyến đầu/cuối bắt buộc",
            "Số chuyến",
            "Thời gian chạy (phút)",
            "Nghỉ tại đầu bến (phút)",
        ],
        [
            [
                label(d),
                f"{clock(a['first'])} / {clock(a['last'])}",
                n(a["trip_count"], 0),
                n(a.get("runtime_minutes"), 0)
                if "runtime_minutes" in a
                else e(
                    "; ".join(
                        f"{clock(p['start'])}–{clock(p['end'])}: {p['minutes']}"
                        for p in a["runtime_periods"]
                    )
                ),
                n(review["assumptions"]["layover_minutes"][d], 0),
            ]
            for d, a in review["assumptions"]["directions"].items()
        ],
    )
    capacity = (
        review["selected_assessment"]["capacity_proxy"]
        or review["comparison_assessment"]["capacity_proxy"]
    )
    if capacity:
        factor = str(capacity["maximum_load_factor"]).replace(".", ",")
        content += f"<p><strong>Chỉ số đại diện lượt lên xe:</strong> hệ số {e(factor)} × sức chứa {n(capacity['physical_capacity_passengers'], 0)} = ngưỡng {n(capacity['planning_limit'])} khách; mức đại diện lớn nhất {n(capacity['maximum_modeled_boardings'])}. Chính sách {e(capacity['policy'])}; {'trong ngưỡng' if capacity['within_policy'] else 'vượt ngưỡng'}. Đây là mức phơi nhiễm nhu cầu lên xe giữa hai chuyến, không phải chứng nhận số khách trên xe hoặc hệ số đầy tải thực tế.</p>"
    else:
        content += f"<p>Sức chứa: {INSUFFICIENT}; chưa chứng nhận hệ số đầy tải thực tế.</p>"
    content += (
        "<p>Không tự suy ra giờ học sinh/công nhân, phân loại pháp lý tuyến hoặc quy tắc nghỉ đầu bến. Nhu cầu cao chỉ được suy từ cường độ trong dữ liệu đã cung cấp.</p><details><summary>Nguồn dữ liệu và định danh kiểm chứng</summary>"
        + _table(
            ["Trường nguồn", "Giá trị"],
            [
                [e(k), e(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)]
                for k, v in review["provenance"].items()
            ],
        )
        + "</details>"
    )
    content += (
        "<details><summary>Ngưỡng cảnh báo có thể cấu hình — không phải quy định vận tải</summary><p>Cảnh báo tăng chờ khi mức tăng lớn hơn max(ngưỡng phút, ngưỡng tương đối × chờ B). Nhu cầu cao được xác định bằng tỷ lệ của cường độ lớn nhất trong cùng chiều. Ngưỡng chỉ phục vụ rà soát; không trở thành ràng buộc cứng.</p>"
        + _table(
            ["Cấu hình", "Giá trị"], [[e(k), n(v)] for k, v in review["warning_policy"].items()]
        )
        + "</details>"
    )
    if review["sensitivities"]:
        content += "<h3>Kịch bản vận hành được khai báo rõ</h3><p>Giữ nguyên giờ xuất bến; mỗi kịch bản tự tính lại chuỗi xe và kiểm tra ràng buộc. Kết quả không thay thế phương án chính hoặc tự thay đổi quyết định.</p>"
        for s in review["sensitivities"]:
            content += (
                f"<details><summary>{e(s['name'])} · {'đã xác minh chuỗi độc lập' if s['independently_validated'] else 'chưa chứng minh được chuỗi'}</summary><p>Thay đổi: {e(json.dumps(s['changes'], ensure_ascii=False))}</p>"
                + _assessment_html(s["assessment"])
                + _circulation_html(s["circulation"], "Chuỗi theo giả định mới")
                + "</details>"
            )
    content += '</section><section id="decision"><h2>Quyết định tiếp theo</h2>'
    content += '<p class="fine">Bản in gồm phần nội dung chính và các mục chi tiết đang mở. Mở các bảng chi tiết cần kèm theo trước khi in.</p>'
    content += f"<p><strong>{e(decision)}</strong> — {label(decision)}. Phân loại sẵn sàng riêng: {label(review['selected_assessment']['readiness'])}.</p>"
    content += "<p>Yêu cầu sửa nếu có vi phạm ràng buộc đã xác nhận. Khi có suy giảm đáng kể, rà soát các khoảng và cặp chuyến được nêu. Xác nhận ngưỡng bảo vệ, xe ban đầu thực có và giả định chạy/nghỉ trước khi quyết định triển khai. Không coi bằng chứng còn thiếu là đạt hoặc vi phạm. Giới hạn tìm kiếm không chứng minh tối ưu toàn cục hoặc tuyến bất khả thi.</p></section>"
    return f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>{CSS}</style></head><body><main>{content}</main></body></html>\n'

"""Deterministic Vietnamese pilot report and offline SVG evidence views."""

from __future__ import annotations

from html import escape

from .fleet_timespace import meal_policy

LABELS = {
    "IN_PASSENGER_SERVICE": "Chở khách",
    "TECHNICAL_TURNAROUND": "Quay đầu kỹ thuật",
    "RECOVERY_RESERVED": "Dự phòng giao thông",
    "TERMINAL_IDLE": "Chờ / tác nghiệp tại bến",
    "CREW_MEAL_BREAK": "Cơ hội ăn ca",
    "TEMPORARILY_STOOD_DOWN": "Tạm dừng theo phương án",
    "NOT_YET_DEPLOYED": "Chưa triển khai",
    "FINISHED_SERVICE": "Kết thúc phục vụ",
}
COLORS = dict(
    zip(
        LABELS,
        ("#147d92", "#aa6d20", "#9368b7", "#b5bdc9", "#218148", "#dc8c43", "#e2e7ee", "#64748b"),
        strict=True,
    )
)


def clock(t):
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}" + (f"+{t % 1:.2f} phút" if t % 1 else "")


def render_report(report):
    cs = report["candidates"]
    policy = report.get("policy") or meal_policy()
    lunch = "–".join(clock(t) for t in policy["windows"]["lunch"])
    dinner = "–".join(clock(t) for t in policy["windows"]["dinner"])
    lines = [
        "# Thí điểm triển khai xe cao điểm và thấp điểm — Tuyến 10",
        "",
        f"Kết quả: **{report['status']}**. `{report['selection']}`.",
        "",
        "Phạm vi chỉ gồm Phase 1 và Phase 2. P0 là tham chiếu đóng băng; kết quả không thay thế khuyến nghị P0 hoặc phê duyệt khai thác.",
        "",
        "## So sánh các phương án",
        "",
        "| Chỉ tiêu | " + " | ".join(cs) + " |",
        "|---|" + "---:|" * len(cs),
    ]
    metrics = [
        (
            "Chuyến hướng đi / hướng về",
            lambda c: "/".join(
                str(len(c["candidate"]["departures"][d])) for d in ("outbound", "inbound")
            ),
        ),
        (
            "Xe tối thiểu chính xác p50",
            lambda c: c["nominal"]["metrics"]["unique_vehicles_required"],
        ),
        (
            "Xe đồng thời chở khách lớn nhất",
            lambda c: c["nominal"]["metrics"]["max_concurrent_passenger_service"],
        ),
        (
            "Giờ xe chở khách",
            lambda c: round(c["nominal"]["metrics"]["passenger_vehicle_hours"], 3),
        ),
        (
            "Giờ xe hiện diện tại bến, gồm trước/sau phục vụ",
            lambda c: round(c["nominal"]["metrics"]["terminal_vehicle_hours"], 3),
        ),
        (
            "Giờ chờ/tác nghiệp + tạm dừng giữa chuỗi",
            lambda c: round(
                sum(
                    c["nominal"]["metrics"]["state_vehicle_hours"].get(s, 0)
                    for s in ("TERMINAL_IDLE", "TEMPORARILY_STOOD_DOWN")
                ),
                3,
            ),
        ),
        (
            "Giờ tạm dừng được mô hình hóa",
            lambda c: round(
                c["nominal"]["metrics"]["state_vehicle_hours"].get("TEMPORARILY_STOOD_DOWN", 0), 3
            ),
        ),
        (
            "Xe đầu bến A/B cần cho phép gán p50",
            lambda c: f"{c['initial_required']['outbound']}/{c['initial_required']['inbound']}",
        ),
        (
            "Chờ khách mô hình (phút)",
            lambda c: round(c["candidate"]["quality"]["waiting_minutes"], 6),
        ),
        (
            "Giãn cách lớn nhất đi/về (phút)",
            lambda c: "/".join(
                str(c["candidate"]["maximum_directional_headways"][d])
                for d in ("outbound", "inbound")
            ),
        ),
        (
            "Khoảng nhu cầu xấu đi so P0",
            lambda c: sum(
                r["waiting_change_minutes"] is not None and r["waiting_change_minutes"] > 1e-9
                for r in c["service_changes_vs_P0"]
            ),
        ),
        (
            "Tăng chờ cục bộ lớn nhất so P0 (phút)",
            lambda c: round(
                max(
                    (
                        r["waiting_change_minutes"]
                        for r in c["service_changes_vs_P0"]
                        if r["waiting_change_minutes"] is not None
                    ),
                    default=0,
                ),
                3,
            ),
        ),
        ("Ngoại lệ rà soát dịch vụ so B", lambda c: len(c["candidate"]["review_exceptions"])),
        (
            "Nối chuỗi p50 thất bại khi thử p75",
            lambda c: c["fixed_p75"]["summary"]["incompatible_connections"],
        ),
        (
            "Xe tối thiểu khi gán lại tại p75, giờ đi giữ nguyên",
            lambda c: c["reassigned_p75"]["fleet"]["required_fleet"],
        ),
        (
            "Xe tối thiểu cho dự phòng p75 và tác nghiệp đầy đủ",
            lambda c: c["exact_recovery_task_fleet"]["required_fleet"],
        ),
        (
            "Nối p50 thiếu dự phòng/tác nghiệp",
            lambda c: c["nominal"]["audit"]["recovery_task_deficit_connections"],
        ),
        (
            "Cơ hội trưa / số tổ cần",
            lambda c: (
                f"{c['nominal']['crew']['lunch_covered']}/{c['nominal']['crew']['lunch_required']}"
            ),
        ),
        (
            "Cơ hội tối / số tổ cần",
            lambda c: (
                f"{c['nominal']['crew']['dinner_covered']}/{c['nominal']['crew']['dinner_required']}"
            ),
        ),
        ("Tổ có cả hai cơ hội", lambda c: c["nominal"]["crew"]["both_meals"]),
        (
            "Khoảng nhiệm vụ dài hơn 8 giờ cần rà soát",
            lambda c: c["nominal"]["crew"]["duty_span_concerns"],
        ),
        (
            "Quyền tồn xe / sức chứa bến / depot",
            lambda c: "Chưa xác nhận / chưa biết / không cho phép di chuyển",
        ),
    ]
    if cs:
        for title, getter in metrics:
            lines.append(
                "| " + title + " | " + " | ".join(str(getter(c)) for c in cs.values()) + " |"
            )
    lines += [
        "",
        "Giảm giờ chở khách có thể do chuyển chuyến sang khung runtime thấp hơn. Số xe vật lý cần cả ngày và thời gian xe bị ràng buộc vào chuỗi phải được xét riêng. Xe đứng bến vẫn có thể chiếm dụng tổ lái.",
        "",
        "## Xe hoạt động theo giờ và vị trí tại bến",
        "",
        "Mở `fleet_timeline.html` để xem biểu đồ xe chở khách, xe sẵn sàng, xe tạm dừng, tồn bến A/B và timeline từng xe. `fleet_utilization.csv` chứa trung bình theo thời lượng chính xác và cực đại trong từng ô 15 phút; không lấy mẫu đơn thuần tại đầu ô.",
        "",
        "A = Miền Tây; B = ĐHQG-A. Mọi xe có vị trí đầu ngày được khai báo; không có xe từ depot, chuyển bến rỗng hoặc xuất hiện tức thời. Phân bố 8/6 là giả định, chưa phải tồn xe của đơn vị.",
        "",
    ]
    if "P0" in cs:
        p0 = cs["P0"]["nominal"]
        lines += [
            "| Khung giờ P0 | Xe chở khách trung bình / cực đại | Tồn A/B trung bình |",
            "|---|---:|---:|",
        ]
        for a, b in [(285, 420), (420, 660), (660, 840), (840, 1020), (1020, 1200), (1200, 1380)]:
            rows = [(r, max(0, min(b, r["end"]) - max(a, r["start"]))) for r in p0["utilization"]]
            rows = [(r, duration) for r, duration in rows if duration]
            if not rows:
                continue
            duration = sum(z for _, z in rows)

            def mean(key, rows=rows, duration=duration):
                return sum(r[key + "_mean"] * z for r, z in rows) / duration

            lines.append(
                f"| {clock(a)}–{clock(b)} | {mean('in_passenger_service'):.2f} / {max(r['in_passenger_service_max'] for r, _ in rows)} | {mean('terminal_A'):.2f}/{mean('terminal_B'):.2f} |"
            )
        gaps = [
            r
            for r in p0["opportunities"]
            if min(r["end"], policy["windows"]["lunch"][1])
            - max(r["start"], policy["windows"]["lunch"][0])
            >= policy["minutes"]
        ]
        lines += [
            "",
            "P0 không gán trạng thái tạm dừng. Các khoảng dưới đây chỉ là cơ hội thử nghiệm sau khi trừ kỹ thuật, công việc và dự phòng; chưa có chứng cứ sức chứa bến hoặc thời gian nghỉ thực tế.",
            "",
            "| Xe P0 | Bến | Khoảng trống liên tục | Xuất lại theo chuỗi |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {r['vehicle_id']} | {r['terminal']} | {clock(r['start'])}–{clock(r['end'])} | {clock(r['planned_reactivation'])} |"
            for r in gaps
        ]
        if not gaps:
            lines.append(
                f"| Không có khoảng đủ {policy['minutes']} phút trong khung trưa | — | — | — |"
            )
    lines += ["", "## Lý do biên và phân bổ ServiceRegime", ""]
    for name, plan in report.get("authored_plans", {}).items():
        lines += [
            f"### {name}",
            "",
            "Biên thủ công được chọn từ các ô nhu cầu độc lập theo hướng. Compiler chỉ dịch biên tối đa 30 phút, giữ nguyên phân bổ khoảng cách và ràng buộc chuyển giãn cách tối đa 10 phút; không có vòng tìm kiếm timetable mới.",
            "",
        ]
        for d, reasons in plan["rationale"].items():
            lines += [f"**{'Hướng đi' if d == 'outbound' else 'Hướng về'}**", ""]
            lines += [f"- {reason}" for reason in reasons]
            compiled = plan.get("compilation", {})
            regimes = [r for r in compiled.get("regimes", []) if r["direction"] == d]
            lines += [
                "",
                "| Biên đề xuất | Biên chính xác | Số khoảng cách | Giãn cách |",
                "|---|---|---:|---:|",
            ]
            for proposed, r in zip(plan["directions"][d], regimes, strict=False):
                lines.append(
                    f"| {clock(proposed['end'])} | {clock(r['start_time'])}–{clock(r['end_time'])} | {r['gap_count']} | {r['headway_minutes']} |"
                )
            lines.append("")
    lines += [
        "## Chính sách tổ lái cố định, dự phòng và giới hạn bằng chứng",
        "",
        f"`ONE_CREW_PER_FULL_VEHICLE_CHAIN`: một tổ gắn với cả chuỗi xe, không thay lái, đổi tổ hoặc chuyển giữa xe. Yêu cầu ăn ca được sàng lọc bảo thủ khi khoảng nhiệm vụ **giao** cửa sổ {lunch} hoặc {dinner}, kể cả giao một phần. Đây là cách diễn giải thử nghiệm công khai của “spans”; không miễn yêu cầu bằng cách chỉ giao một phần cửa sổ.",
        "",
        f"Mỗi bữa cần {policy['minutes']} phút liên tục. Sau đến bến: {policy['technical']} phút kỹ thuật, {policy['tasks_after']} phút công việc, rồi dự phòng p75−p50 riêng cho hướng và giờ đi; trước chuyến sau giữ {policy['tasks_before']} phút công việc. Các phần không dùng chung thời gian. Tại p75 không trừ dự phòng lần thứ hai. Khoảng nối thiếu thời gian vẫn được báo lỗi, không tự trì hoãn chuyến hoặc làm biến mất nhiệm vụ.",
        "",
        f"Khoảng nhiệm vụ bắt đầu {policy['tasks_before']} phút trước chuyến đầu, kết thúc sau chuyến cuối cộng {policy['technical']} phút kỹ thuật và {policy['tasks_after']} phút công việc. Chỉ cơ hội ăn ca đã chọn mới đặt lại chỉ số lái liên tục mô hình; thời gian chờ ngắn không được cộng dồn. Mốc 8 giờ chỉ là dấu hiệu cần rà soát, không phải kết luận pháp lý. Không chứng nhận tuân thủ luật lao động.",
        "",
        f"Nguồn thẩm quyền của tham số thử nghiệm: `{policy['authority']}`. Giờ đỉnh kiểm tra vị trí được khai báo riêng từ nhu cầu: hướng đi 15:30–17:00, hướng về 15:30–17:30; cùng giờ bắt đầu là kết quả đọc hai chuỗi nhu cầu độc lập.",
        "",
        "p50/p75 dùng lại mô hình giả định suy ra từ báo cáo; p75 không phải cận trên tắc nghẽn được bảo đảm thống kê. Chưa có tồn xe thực tế, sức chứa/ủy quyền đỗ bến, lịch nhân sự, nhiệm vụ thực đo hoặc bảo vệ dịch vụ do đơn vị ban hành. Không đưa ra kết luận bãi đỗ có sức chứa vô hạn.",
        "",
    ]
    for name, c in cs.items():
        crew = c["nominal"]["crew"]
        lines += [
            f"### {name}: tổ lái và tồn xe giả định",
            "",
            "| Xe | Khoảng nhiệm vụ | Lái mô hình / liên tục lớn nhất (phút) | Trưa | Tối |",
            "|---|---|---:|---|---|",
        ]
        for row in crew["chains"]:
            meals = [
                "Không yêu cầu"
                if not m["required"]
                else "Thiếu cơ hội"
                if not m["opportunity"]
                else f"{clock(m['opportunity'][0])}–{clock(m['opportunity'][1])}, bến {m['terminal']}"
                for m in (row["meals"][key] for key in ("lunch", "dinner"))
            ]
            lines.append(
                f"| {row['vehicle_id']} | {clock(row['duty_start'])}–{clock(row['duty_end'])} | {row['driving_minutes']}/{row['modeled_max_continuous_driving_minutes']} | {' | '.join(meals)} |"
            )
        lines += [
            "",
            "Kiểm tra tồn xe giả định 8/6 bằng solver hiện có: "
            + "; ".join(f"{k}: {v['status']}" for k, v in c["hypothetical_stock_8_6"].items())
            + ".",
            "",
            "Tại p75 sau gán lại: "
            + f"{c['reassigned_p75']['timeline']['crew']['lunch_covered']}/{c['reassigned_p75']['timeline']['crew']['lunch_required']} cơ hội trưa; {c['reassigned_p75']['timeline']['crew']['dinner_covered']}/{c['reassigned_p75']['timeline']['crew']['dinner_required']} cơ hội tối. Phép gán này khác chuỗi p50.",
            "",
        ]
        sensitivity = c["sensitivity_15"]
        if sensitivity and "nominal" in sensitivity:
            s = sensitivity["nominal"]
            lines += [
                f"Độ nhạy 15 xe: `{sensitivity['status']}`; tồn A/B {s['audit']['initial_stock']}; trưa {s['crew']['lunch_covered']}/{s['crew']['lunch_required']}, tối {s['crew']['dinner_covered']}/{s['crew']['dinner_required']}, cả hai {s['crew']['both_meals']}; thiếu dự phòng/tác nghiệp {s['audit']['recovery_task_deficit_connections']} nối. "
                f"Thất bại chuỗi cố định tại p75: {sensitivity['fixed_p75']['summary']['incompatible_connections']}. Xe bổ sung ở bến {sensitivity.get('additional_vehicle_start_terminal', 'theo phép gán chính xác')}. Không giả định thêm xe sẽ đủ bữa ăn hoặc ca hợp lệ.",
                "",
            ]
        lines += [
            "Các ô nhu cầu xấu đi nhiều nhất so P0:",
            "",
            "| Hướng | Khung | Nhu cầu proxy | Tăng chờ (phút) |",
            "|---|---|---:|---:|",
        ]
        for r in sorted(
            [r for r in c["service_changes_vs_P0"] if r["waiting_change_minutes"] is not None],
            key=lambda r: (-r["waiting_change_minutes"], r["direction"], r["start"]),
        )[:5]:
            lines.append(
                f"| {'Đi' if r['direction'] == 'outbound' else 'Về'} | {clock(r['start'])}–{clock(r['end'])} | {r['passengers']:.1f} | {r['waiting_change_minutes']:.3f} |"
            )
        lines.append("")
    lines += [
        "## Quyết định Product Owner",
        "",
        "1. Số xe chở khách theo từng phần ngày thể hiện trong bảng P0, CSV 15 phút và biểu đồ; xe vật lý cả ngày không được đồng nhất với số xe chở khách đồng thời.",
        "2. Danh sách khoảng trống P0 ở trên cho biết xe và bến có thể xem xét tạm dừng. Tất cả còn điều kiện về bãi đỗ và tổ lái; không có phê duyệt “an toàn” tự động.",
        "3. Bảng trưa/tối và từng tổ cho biết ServiceRegime có tạo thêm cơ hội thực sự sau mọi khoản dự trữ hay chỉ đổi vị trí thời gian chờ. Các phương án vẫn phải đáp ứng riêng chất lượng hành khách.",
        "4. Đối chiếu trần 14 với số xe chính xác p75 và dự phòng/tác nghiệp đầy đủ trong bảng. Giữ nguyên chuỗi p50 và gán lại ở p75 là hai phép thử khác nhau.",
        "5. Xe phục vụ chiều đều có nguồn gốc tồn đầu ngày và chuỗi đến/đi thực. `deployment_scenarios.json` ghi các khoảng xe sai bến, chuyến tiếp theo và lead time; không cho phép chuyển bến không có chứng cứ.",
        "6. Độ nhạy 15 xe là một lần chia chuỗi được khai báo, không tìm kiếm mọi cách chia. So sánh độ phủ bữa ăn và thiếu hụt còn lại ở trên; không suy rộng thành bảo đảm lợi ích của mọi phép gán 15 xe.",
        "7. Chưa đủ căn cứ để phê duyệt xây Fleet Deployment Optimizer đầy đủ. Kết quả đo cho thấy các đánh đổi cần xử lý, nhưng quyền đỗ bến, nhân sự, bảo vệ dịch vụ và runtime thực tế phải được xác nhận trước.",
        "",
        "Không có phương án được chấp nhận vận hành trong phạm vi pilot. Kết quả này không chứng minh mọi thời khóa biểu khả dĩ đều vô nghiệm. P0 được giữ nguyên.",
        "",
        "## Truy nguyên và kiểm tra",
        "",
        "Các khóa baseline: `" + str(report.get("baseline_verification", {})) + "`.",
        "",
        "Nguồn và fingerprint mã: `" + str(report["source"]) + "`.",
        "",
        "JSON chứa giờ đi chính xác, ServiceRegime, chuỗi xe, ledger sự kiện, kiểm toán bảo toàn và lý do bác bỏ. Kiểm tra độc lập và lệnh tái lập được ghi trong tài liệu public của pilot. Các kiểm tra là chạy local; không suy ra GitHub Actions đã thành công.",
        "",
    ]
    return "\n".join(lines)


def _chart(timeline, keys, title):
    rows = timeline["snapshots"]
    if not rows:
        return ""
    start, end = timeline["audit"]["horizon"]
    ymax = max(max(r[k] for k, _, _ in keys) for r in rows) or 1

    def x(t):
        return 60 + 800 * (t - start) / (end - start)

    def y(v):
        return 210 - 170 * v / ymax

    parts = [
        f'<h3>{escape(title)}</h3><svg viewBox="0 0 920 285" role="img" aria-label="{escape(title)}">'
    ]
    for v in range(0, ymax + 1, max(1, ymax // 5)):
        parts.append(
            f'<path d="M60 {y(v):.2f} H860" stroke="#dce2e9"/><text x="40" y="{y(v) + 4:.2f}">{v}</text>'
        )
    for t in range(((int(start) + 59) // 60) * 60, int(end), 120):
        parts.append(f'<text x="{x(t):.2f}" y="235">{clock(t)}</text>')
    for i, (key, label, color) in enumerate(keys):
        points = [(x(rows[0]["time"]), y(rows[0][key]))]
        for a, b in zip(rows, rows[1:], strict=False):
            points.extend([(x(b["time"]), y(a[key])), (x(b["time"]), y(b[key]))])
        points.append((x(end), y(rows[-1][key])))
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="'
            + " ".join(f"{a:.2f},{b:.2f}" for a, b in points)
            + '"/>'
        )
        parts.append(f'<text x="{60 + i * 265}" y="270" fill="{color}">{escape(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_html(report):
    parts = [
        '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Thí điểm triển khai xe — Tuyến 10</title><style>body{font:16px system-ui;color:#203048;background:#f4f6f9;margin:auto;max-width:1100px;padding:24px}section{background:white;padding:20px;margin:24px 0;border-radius:8px}svg{width:100%;height:auto}svg text{font:12px system-ui}h1{font-size:28px}p{line-height:1.6}.legend{display:flex;flex-wrap:wrap;gap:14px}.legend span{padding-left:10px;border-left:14px solid var(--c)}</style>",
        "<h1>Triển khai xe và cơ hội ăn ca — Tuyến 10</h1>",
        f"<p>{escape(report['status'])} · {escape(report['selection'])}</p>",
        "<p>Xe vật lý, xe chở khách và tổ lái là các nguồn lực riêng. Mọi khoảng tạm dừng đều có điều kiện; sức chứa và quyền đỗ bến chưa xác nhận. Tải bảng CSV và đọc báo cáo Markdown cùng bộ JSON bên cạnh để đối soát.</p>",
    ]
    for name, c in report["candidates"].items():
        t = c["nominal"]
        parts += [
            f"<section><h2>{escape(name)} — {t['metrics']['unique_vehicles_required']} xe cả ngày</h2>",
            "<p>"
            + (
                "Vượt trần 14 xe: lịch thử nghiệm bị loại; biểu đồ chỉ tái dựng yêu cầu xe không giới hạn tồn đầu bến."
                if t["metrics"]["unique_vehicles_required"] > 14
                else "Trong trần 14 xe tại p50; vẫn cần kiểm tra riêng dự phòng, bữa ăn và bảo vệ dịch vụ."
            )
            + "</p>",
            _chart(
                t,
                [
                    ("in_passenger_service", "Chở khách", "#147d92"),
                    ("terminal_ready", "Sẵn sàng tại bến", "#218148"),
                    ("temporarily_stood_down", "Tạm dừng theo phương án", "#dc8c43"),
                ],
                "Số xe đồng thời theo sự kiện chính xác",
            ),
            _chart(
                t,
                [
                    ("terminal_A", "Tồn A — Miền Tây", "#17609d"),
                    ("terminal_B", "Tồn B — ĐHQG-A", "#9368b7"),
                ],
                "Tồn xe vật lý tại hai bến",
            ),
        ]
        vehicles = sorted({s["vehicle_id"] for s in t["segments"]})
        start, end = t["audit"]["horizon"]
        height = 60 + 30 * len(vehicles)
        parts.append(
            f'<h3>Timeline từng xe</h3><svg viewBox="0 0 1000 {height}" role="img" aria-label="Hoạt động từng xe">'
        )
        for minute in range(((int(start) + 59) // 60) * 60, int(end), 120):
            tick_x = 60 + 900 * (minute - start) / (end - start)
            parts.append(f'<text x="{tick_x:.2f}" y="15">{clock(minute)}</text>')
        for i, v in enumerate(vehicles):
            parts.append(f'<text x="5" y="{40 + i * 30}">{escape(v)}</text>')
            for s in [s for s in t["segments"] if s["vehicle_id"] == v]:
                x = 60 + 900 * (s["start"] - start) / (end - start)
                width = 900 * (s["end"] - s["start"]) / (end - start)
                label = f"{v}: {clock(s['start'])}–{clock(s['end'])}; {LABELS[s['vehicle_state']]}; {s['location']}; {s['crew_activity']}"
                parts.append(
                    f'<rect x="{x:.2f}" y="{25 + i * 30}" width="{width:.2f}" height="22" fill="{COLORS[s["vehicle_state"]]}"><title>{escape(label)}</title></rect>'
                )
        parts.append(
            '</svg><div class="legend">'
            + "".join(
                f'<span style="--c:{color}">{escape(LABELS[state])}</span>'
                for state, color in COLORS.items()
            )
            + "</div></section>"
        )
    parts.append("</html>")
    return "".join(parts)

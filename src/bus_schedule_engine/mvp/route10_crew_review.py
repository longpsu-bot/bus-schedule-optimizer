"""Reproduce a private Route 10 review from frozen evidence, without timetable search."""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import date
from hashlib import sha256
from pathlib import Path

from .circulation import assign_fleet, validate_chains
from .crew_review import analyze_chains, illustrative_policies, validate_policies
from .external_benchmark import _json
from .external_import import import_external_workbook
from .input import DIRECTIONS
from .route10_fleet_pilot import _best, audit_fleet
from .route10_pilot import WORKBOOK_SHA256, compare_timetable, planning_bundle, runtime_scenarios

LEGAL_NOTE = """Ngày xác minh pháp lý: 27/10/2026; ngày khai thác trong workbook chưa xác định.

1. [Điều 64, bản hợp nhất 55/VBHN-VPQH](https://vanban.chinhphu.vn/?classid=0&docid=217295&pageid=27160), được sửa bởi khoản 15 Điều 7 Luật 118/2025/QH15, áp dụng sửa đổi từ 01/07/2026: lái xe liên tục tối đa 4 giờ, trừ bất khả kháng hoặc trở ngại khách quan; thời gian làm việc ngày/tuần theo Bộ luật Lao động. Trước ngày đó, Điều 64 còn quy định giới hạn lái 10 giờ/ngày, 48 giờ/tuần. Không áp giới hạn cũ như luật hiện hành sau 01/07/2026.
2. [Điều 109 Bộ luật Lao động 2019](https://vanban.chinhphu.vn/?classid=1&docid=198540&pageid=27160&typegroupid=3), hiệu lực 01/01/2021; [bản hợp nhất 18/VBHN-VPQH năm 2026](https://chinhphu.vn/?docid=217002&pageid=27160): làm việc từ 6 giờ/ngày được nghỉ ít nhất 30 phút liên tục; trường hợp làm ban đêm là 45 phút theo điều kiện áp dụng. Điều 105 quy định giờ làm bình thường tối đa 8 giờ/ngày, 48 giờ/tuần; tổ chức theo tuần có thể tới 10 giờ/ngày, vẫn tối đa 48 giờ/tuần. Làm thêm và ngoại lệ cần hồ sơ, thỏa thuận và căn cứ riêng. Điều 116 về công việc đặc biệt, gồm vận tải đường bộ, vẫn yêu cầu tuân thủ Điều 109.
3. [Điều 63–64 NĐ 145/2020/NĐ-CP](https://vanban.chinhphu.vn/default.aspx?docid=201967&pageid=27160), hiệu lực ban đầu 01/02/2021, hiện hết hiệu lực một phần: nghỉ 45 phút khi làm từ 6 giờ/ngày, trong đó có ít nhất 3 giờ thuộc 22:00–06:00; thời điểm nghỉ do người sử dụng lao động bố trí, không đặt vào đầu/cuối ca. Ca liên tục để tính nghỉ vào giờ làm: ca từ 6 giờ, chuyển tiếp giữa hai ca không quá 45 phút. Không phát hiện sửa đổi Điều 63–64 trong nguồn đã kiểm tra. Điều 68 và Điều 116 đòi hỏi kiểm tra thêm quy định công việc đặc biệt.
4. [NĐ 158/2024/NĐ-CP](https://chinhphu.vn/?classid=1&docid=212082&pageid=27160) thay NĐ 10/2020 từ 01/01/2025; [NĐ 218/2026/NĐ-CP](https://chinhphu.vn/?classid=1&docid=218537&pageid=27160&typegroupid=4) sửa NĐ 158, hiệu lực 10/08/2026. Không mang quy tắc dừng 5/15 phút của văn bản cũ sang quy định hiện hành khi chưa xác minh căn cứ. Không coi 5 phút là chứng cứ tự động đặt lại chu kỳ lái hoặc thay nghỉ lao động 30/45 phút.

Không xác minh được ngày khai thác, toàn bộ quy định ngành/địa phương áp riêng cho tuyến hoặc nội quy doanh nghiệp. Không có khung giờ ăn trưa/nghỉ chiều bắt buộc chung trong các điều đã kiểm tra. Giới hạn lái xe không tự động áp cho phụ xe. Cần hồ sơ lao động và ca riêng cho từng vai trò. Không kết luận tuân thủ hoặc vi phạm từ mã xe, tổng giờ xe chạy hay một cơ hội nghỉ giả định.
"""


def recorded_fleet(source):
    """Preserve original recorded vehicle grouping and actual report clocks."""
    groups = defaultdict(list)
    for trip in source["vehicle_trips"]:
        groups[trip["vehicle_id"]].append(dict(trip))
    chains, trips = [], []
    for vehicle in sorted(groups):
        local = sorted(groups[vehicle], key=lambda t: (t["departure"], t["direction"]))
        for trip in local:
            trip["trip_id"] = f"{trip['direction']}-{trip['trip_sequence']:03d}"
        trips.extend(local)
        chains.append([t["trip_id"] for t in local])
    return {
        "status": "RECORDED_NOT_MINIMUM_CERTIFICATE",
        "required_fleet": len(chains),
        "chains": chains,
        "trips": trips,
    }


def _profiles(fleet, layovers, profiles, runtime_data=None):
    return {
        name: analyze_chains(fleet, layovers, p, runtime_data=runtime_data)
        for name, p in profiles.items()
    }


def run_review(
    workbook, evidence_path, output_dir, *, policies=None, operating_date=None, evidence_sha256=None
):
    workbook, evidence_path = Path(workbook), Path(evidence_path)
    if sha256(workbook.read_bytes()).hexdigest() != WORKBOOK_SHA256:
        raise ValueError("workbook SHA-256 differs from verified Route 10 source")
    if operating_date is not None:
        date.fromisoformat(operating_date)
    raw = evidence_path.read_bytes()
    digest = sha256(raw).hexdigest()
    if evidence_sha256 is not None and digest != evidence_sha256:
        raise ValueError("frozen evidence SHA-256 mismatch")
    evidence = json.loads(raw)
    if (
        evidence["schema_version"] != "route10_fleet_pilot_v1"
        or evidence["source"]["sha256"] != WORKBOOK_SHA256
    ):
        raise ValueError("frozen evidence schema/source mismatch")
    if policies is not None and (
        not isinstance(policies, dict)
        or not policies
        or any(not isinstance(k, str) or not k for k in policies)
    ):
        raise ValueError("profiles must be a nonempty object with nonempty names")
    profiles = (
        illustrative_policies()
        if policies is None
        else {name: validate_policies(p) for name, p in policies.items()}
    )
    if not profiles:
        raise ValueError("provide at least one explicit profile, or a named empty/unknown policy")
    source = import_external_workbook(workbook)
    definitions = {s["id"]: s for s in runtime_scenarios(source)}
    report = {
        "schema_version": "crew_rest_review_v1",
        "status": "PARTIAL_EVIDENCE",
        "review_date": "2026-10-27",
        "legal_verification_date": "2026-10-27",
        "operating_date": operating_date,
        "source": source["source"]
        | {
            "frozen_evidence_sha256": digest,
            "frozen_evidence_schema": evidence["schema_version"],
            "engine_base_sha": "6f8f7644b8ac642f6eabc0ad5e6ba0ca0ef9f56e",
            "analysis_code_sha256": {
                name: sha256(
                    Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n")
                ).hexdigest()
                for name in ("crew_review.py", "route10_crew_review.py")
            },
        },
        "policies": profiles,
        "scenarios": [],
        "fixed_chain_stress": {},
        "reassignment_stress": {},
        "legal_note": LEGAL_NOTE,
        "missing_evidence": [
            "Ngày khai thác và quy định ngành/địa phương áp dụng",
            "Phân công lái xe/phụ xe, quan hệ lao động và lịch sử ca ngày/tuần",
            "Chấm công, giờ lái thực tế, nghỉ thực tế và công việc khác",
            "Nội quy ăn ca/nghỉ chiều, làm đêm, làm thêm, chuyển ca",
            "Thời gian chuẩn bị, đón khách, vệ sinh, kiểm tra và bàn giao tại từng bến",
            "Nhân sự thay ca đủ điều kiện, vị trí, giờ sẵn có và phân công sau nghỉ",
            "Tồn xe đầu bến, tải khách và phân bố runtime thực đo theo ngày",
        ],
    }
    rows = {row["id"]: row for row in evidence["scenarios"]}
    if len(rows) != len(evidence["scenarios"]) or not {"report_p50", "report_p75"} <= set(rows):
        raise ValueError("frozen scenarios missing or duplicated")
    for scenario_id in ("report_p50", "report_p75", "report_p50_B25_guardrail"):
        if scenario_id not in rows:
            continue
        row = rows[scenario_id]
        definition = definitions["report_p75" if scenario_id == "report_p75" else "report_p50"]
        data = planning_bundle(
            source, definition, headway_guardrail=25 if "B25" in scenario_id else None
        )
        if row["bundle"] != data:
            raise ValueError("frozen bundle differs from workbook-derived common scenario")
        best = _best(row["guided"])
        if not best or any(
            best[k] != row["comparison"]["C"][k] for k in ("id", "departures", "regimes")
        ):
            raise ValueError("C differs from frozen guided selection/trial")
        alternatives = {}
        for label in ("B", "X", "C"):
            c = row["comparison"][label]
            if label in {"B", "X"}:
                source_key = "BASELINE" if label == "B" else "EXTERNAL_CANDIDATE"
                expected = {
                    d: [t["departure"] for t in source["timetables"][source_key][d]]
                    for d in DIRECTIONS
                }
                if c["departures"] != expected:
                    raise ValueError("B/X frozen departures differ from source")
            validate_chains(data, c["departures"], c["vehicle_chains"])
            required = audit_fleet(data, c["departures"], c["vehicle_chains"])
            fresh = compare_timetable(data, c["id"], c["departures"], c["regimes"])
            if (
                fresh["quality"] != c["quality"]
                or fresh["review_exceptions"] != c["review_exceptions"]
            ):
                raise ValueError("frozen quality/review differs on independent recomputation")
            alternatives[label] = {
                "exact_vehicle_requirement": required,
                "within_14_vehicle_ceiling": required <= data["fleet_ceiling"],
                "candidate_id": c["id"],
                "waiting_minutes": c["quality"]["waiting_minutes"],
                "review_exceptions": len(c["review_exceptions"]),
                "source_pointer": f"scenarios[{scenario_id}].comparison.{label}.vehicle_chains",
                "profiles": _profiles(c["vehicle_chains"], data["layover_minutes"], profiles),
            }
        report["scenarios"].append(
            {
                "id": scenario_id,
                "timetable_role": row["c_role"],
                "runtime_authority": definition["authority"],
                "runtime_definition": definition,
                "technical_turnaround_authority": "EXPERIMENTAL_5_MINUTES_NOT_CREW_REST",
                "alternatives": alternatives,
            }
        )
    incumbent = rows["report_p50"]["comparison"]["C"]
    if (
        incumbent["id"] != "I001"
        or incumbent["quality"]["required_fleet"] != 14
        or abs(incumbent["quality"]["waiting_minutes"] - 9.441295) > 1e-6
        or len(incumbent["review_exceptions"]) != 9
        or any(len(v) != 51 for v in incumbent["departures"].values())
    ):
        raise ValueError("verified p50 incumbent lock differs")
    stressed_data = rows["report_p75"]["bundle"]
    for label in ("B", "X", "C"):
        original = rows["report_p50"]["comparison"][label]
        report["fixed_chain_stress"][label] = {
            "basis": "p50 timetable AND p50 assignment; p75 arrivals; no delay propagation",
            "source_pointer": f"scenarios[report_p50].comparison.{label}.vehicle_chains",
            "profiles": _profiles(
                original["vehicle_chains"],
                stressed_data["layover_minutes"],
                profiles,
                stressed_data,
            ),
        }
        fleet = assign_fleet(stressed_data, original["departures"])
        required = audit_fleet(stressed_data, original["departures"], fleet)
        report["reassignment_stress"][label] = {
            "basis": "UNCHANGED p50 timetable; fresh exact assignment at p75 runtime",
            "exact_vehicle_requirement": required,
            "within_14_vehicle_ceiling": required <= 14,
            "profiles": _profiles(fleet, stressed_data["layover_minutes"], profiles),
        }
    recorded = recorded_fleet(source)
    recorded_profiles = _profiles(recorded, dict.fromkeys(DIRECTIONS, 5), profiles)
    mismatches = []
    for chain in next(iter(recorded_profiles.values()))["chains"]:
        by_id = {t["trip_id"]: t for t in chain["trips"]}
        for interval in chain["intervals"]:
            reported = by_id[interval["from_trip_id"]].get("recorded_layover")
            if reported is not None and abs(reported - interval["scheduled_dwell"]) > 1e-6:
                mismatches.append(
                    {"vehicle_id": chain["vehicle_id"], **interval, "reported_layover": reported}
                )
    report["recorded_x"] = {
        "basis": "ORIGINAL_RECORDED_X_CLOCKS_AND_VEHICLE_IDS; experimental technical minimum5",
        "exact_vehicle_requirement": None,
        "assigned_vehicles": recorded["required_fleet"],
        "recorded_layover_discrepancies": mismatches,
        "profiles": recorded_profiles,
    }
    if (Path(output_dir) / "crew_review.json").resolve() == evidence_path.resolve():
        raise ValueError("output must not overwrite source evidence")
    export_review(report, output_dir)
    return report


def _role_text(summary, role, name):
    row = next((r for r in summary["roles"].get(role, []) if r["name"] == name), None)
    if row is None:
        return "thiếu chính sách"
    return f"{row['fixed_possible_chains']}/{row['applicable_chains']}; thay ca {row['relief_dependency_chains']}"


def _summary_table(alternatives, profile):
    keys = list(alternatives)
    lines = ["| Chỉ tiêu | " + " | ".join(keys) + " |", "|---|" + "---:|" * len(keys)]
    for label, getter in (
        ("Xe tối thiểu chính xác", lambda a, s: a.get("exact_vehicle_requirement", "giữ chuỗi")),
        ("Số xe trong phép gán được xét", lambda a, s: s["assigned_vehicles"]),
        (
            "Trong trần thử nghiệm 14 xe",
            lambda a, s: a.get("within_14_vehicle_ceiling", "chưa áp trong phép thử này"),
        ),
        (
            "Chờ khách mô hình (phút)",
            lambda a, s: round(a["waiting_minutes"], 6) if "waiting_minutes" in a else "—",
        ),
        ("Ngoại lệ rà soát dịch vụ", lambda a, s: a.get("review_exceptions", "—")),
        (
            "Quay đầu nhỏ nhất / trung vị (phút)",
            lambda a, s: f"{s['minimum_dwell']} / {s['median_dwell']}",
        ),
        (
            "Quay đầu ngắn / số nối chuyến",
            lambda a, s: f"{s['short_turnarounds']} / {s['connections']}",
        ),
        ("Chuỗi liên tiếp quay đầu ngắn dài nhất", lambda a, s: s["longest_short_run"]),
        ("Dự phòng nhỏ nhất sau quay đầu kỹ thuật (phút)", lambda a, s: s["minimum_slack"]),
        ("Nối chuyến không tương thích", lambda a, s: s["incompatible_connections"]),
        (
            "Nối thiếu dự phòng riêng của profile",
            lambda a, s: (
                "; ".join(
                    f"{r['reserve_minutes']} phút: {r['connections_below_reserve']}"
                    for r in s.get("recovery_reserve_sensitivity", [])
                )
                or "chưa khai báo"
            ),
        ),
        (
            "Lái xe: nghỉ ăn / chuỗi giao khung; cần thay ca",
            lambda a, s: _role_text(s, "driver", "meal"),
        ),
        (
            "Lái xe: nghỉ chiều / chuỗi giao khung; cần thay ca",
            lambda a, s: _role_text(s, "driver", "afternoon"),
        ),
        (
            "Phụ xe: nghỉ ăn / chuỗi giao khung; cần thay ca",
            lambda a, s: _role_text(s, "attendant", "meal"),
        ),
        (
            "Phụ xe: nghỉ chiều / chuỗi giao khung; cần thay ca",
            lambda a, s: _role_text(s, "attendant", "afternoon"),
        ),
        ("Bằng chứng nhân sự", lambda a, s: "INSUFFICIENT_CREW_EVIDENCE"),
    ):
        lines.append(
            "| "
            + label
            + " | "
            + " | ".join(
                str(getter(alternatives[k], alternatives[k]["profiles"][profile]["summary"]))
                for k in keys
            )
            + " |"
        )
    return lines


def render_report(report):
    primary = (
        "illustrative" if "illustrative" in report["policies"] else next(iter(report["policies"]))
    )
    findings = []
    for scenario in report["scenarios"]:
        c = scenario["alternatives"].get("C")
        if c:
            s = c["profiles"][primary]["summary"]
            findings.append(
                f"- C `{scenario['id']}`: {c['exact_vehicle_requirement']} xe; "
                f"chờ mô hình {c['waiting_minutes']:.6f} phút; quay đầu nhỏ nhất/trung vị "
                f"{s['minimum_dwell']}/{s['median_dwell']} phút; "
                f"{s['short_turnarounds']}/{s['connections']} khoảng ngắn; "
                f"dự phòng nhỏ nhất {s['minimum_slack']} phút. "
                "Đánh giá: chịu áp lực; nhân sự INSUFFICIENT_CREW_EVIDENCE."
            )
            if scenario["id"] == "report_p50":
                findings.append(
                    f"- C p50, profile `{primary}`: lái xe nghỉ ăn "
                    + _role_text(s, "driver", "meal")
                    + "; nghỉ chiều "
                    + _role_text(s, "driver", "afternoon")
                    + ". Đây là số chuỗi xe theo giả định, không phải số nhân viên."
                )
                chains = c["profiles"][primary]["chains"]
                pressure = sorted(chains, key=lambda ch: (ch["minimum_slack"], ch["vehicle_id"]))[
                    :3
                ]
                findings.append(
                    "- Chuỗi C p50 chịu áp lực quay đầu cao: "
                    + ", ".join(ch["vehicle_id"] for ch in pressure)
                    + f". Nếu một lái xe chạy trọn chuỗi, tổng phút lái sẽ là "
                    f"{min(ch['driving_minutes'] for ch in chains)}–{max(ch['driving_minutes'] for ch in chains)}; "
                    "cần đối soát phân công và chia nhiệm vụ. Không coi tổng này là giờ làm đã xác minh."
                )
                b = scenario["alternatives"].get("B")
                x = scenario["alternatives"].get("X")
                if b and x:
                    findings.append(
                        f"- C p50 giảm {b['exact_vehicle_requirement'] - c['exact_vehicle_requirement']} xe so với B "
                        f"và {x['exact_vehicle_requirement'] - c['exact_vehicle_requirement']} xe so với X dưới runtime chung. "
                        f"Chờ khách giảm {b['waiting_minutes'] - c['waiting_minutes']:.6f} phút so với B, "
                        f"{x['waiting_minutes'] - c['waiting_minutes']:.6f} phút so với X; "
                        "đổi lại tỷ lệ khoảng quay đầu ngắn của chuỗi C cao hơn (xem bảng D)."
                    )
    if "C" in report["fixed_chain_stress"]:
        s = report["fixed_chain_stress"]["C"]["profiles"][primary]["summary"]
        n = report["reassignment_stress"]["C"]["exact_vehicle_requirement"]
        findings.append(
            f"- C p50 khi thử p75: {s['incompatible_connections']} nối trên "
            f"{s['chains_with_failures']} xe không tương thích; dự phòng nhỏ nhất "
            f"{s['minimum_slack']} phút. Gán lại cùng giờ xuất bến cần chính xác {n} xe."
        )
    lines = [
        "# Rà soát tính thực tế của mô hình: nghỉ nhân sự và dự phòng quay đầu",
        "",
        f"Trạng thái: **{report['status']}**. Ngày rà soát: {report['review_date']}. "
        f"Ngày khai thác: {report['operating_date'] or 'chưa xác định'}.",
        "",
        "## A. Nhận định điều hành",
        "",
        "C p50 khả thi về lưu thông xe theo giả định thử nghiệm nhưng có áp lực quay đầu; "
        "chưa đủ bằng chứng để phê duyệt nhân sự hoặc xác nhận vận hành bền vững. "
        "C p75 trong bằng chứng gốc là phương án thử, cần 15 xe, vượt trần 14; không phải khuyến nghị mới. "
        "Đứt nối chuỗi cố định không chứng minh mọi phép gán xe đều thất bại.",
        "",
        *findings,
        "",
        "Bốn kết luận cần bằng chứng riêng: **xe khả thi — dự phòng chịu biến động — "
        "nhân sự có kỳ nghỉ khả thi — đơn vị chấp thuận khai thác**. "
        "Chưa xác lập ba kết luận sau. Không suy lái xe từ mã xe.",
        "",
        "## B. Bằng chứng chuỗi xe",
        "",
        "Từng chuyến, giờ đi/đến, khoảng dừng, quay đầu kỹ thuật, dự phòng, số chuyến, "
        "tổng phút chạy và khoảng hoạt động của mọi xe nằm trong `chain_evidence_vi.md` và JSON. "
        "Mỗi dòng giữ ID chuyến và nguồn/kịch bản. Khoảng hoạt động xe không phải giờ làm nhân viên.",
        "",
        "## C. Cơ hội nghỉ theo giả định",
        "",
        "Mỗi kỳ nghỉ phải nằm trong một khoảng liên tục giữa hai chuyến, không cộng các lần chờ. "
        "Phân bổ bảo thủ theo thứ tự: quay đầu kỹ thuật → việc sau đến → dự phòng giữ lại → "
        "thời gian có thể nghỉ → việc trước đi. Không tính cùng phút thành nghỉ bảo đảm và dự phòng bảo đảm. "
        "Công việc thực tế chưa biết; các con số chỉ là điều kiện giả định, không phải kỳ nghỉ đã diễn ra.",
        "",
        "Thay ca giả định bắt đầu tại bến, cần đủ thời gian bàn giao trước chuyến kế tiếp và người thay "
        "đảm nhiệm các chuyến ghi trong JSON. Không chứng minh có người thay, nơi quay lại sau nghỉ, "
        "định biên hoặc ca có thể thực hiện. Thiếu cơ hội nghỉ trên một chuỗi không chứng minh tuyến "
        "không có lịch phân công nhân sự khác.",
        "",
        "Các khung ăn/nghỉ chiều, nhiệm vụ và thời gian nghỉ dưới đây là độ nhạy minh họa, "
        "không phải nội quy đã xác nhận hoặc khung giờ pháp luật bắt buộc.",
        "Vai trò phụ xe được xét riêng trong trường hợp đơn vị có bố trí; sự hiện diện, "
        "công việc và phân công thực tế của vai trò này chưa được xác minh.",
        "",
    ]
    lines += [
        "| Profile / vai trò / kỳ nghỉ | Khung (phút từ 00:00) | Nghỉ | Việc sau/trước | Dự phòng | Bàn giao |",
        "|---|---|---:|---|---:|---:|",
    ]
    for name, policy in report["policies"].items():
        for role, windows in policy.get("roles", {}).items():
            for w in windows:
                lines.append(
                    f"| {name}/{role}/{w['name']} | {w['start']}–{w['end']} | "
                    f"{w['minutes']} | {w['tasks_after']}/{w['tasks_before']} | "
                    f"{w['reserve']} | {w['handover']} |"
                )
    lines += [
        "",
        "## D. So sánh B/X/C",
        "",
        "‘Ngắn’ là nhỏ hơn ngưỡng của từng profile (mặc định 10 phút), không phải kết luận vi phạm. "
        "Mẫu số nghỉ là số chuỗi xe giao khung, không phải số nhân viên phải nghỉ. "
        "Các tỷ lệ là cơ hội riêng cho từng kỳ; không phải chứng nhận đầy đủ ca.",
        "",
        "Runtime chung là phân vị mô tả từ giờ chạy X ghi trong báo cáo, không phải dữ liệu thực đo "
        "đại diện của B/C; một số nhóm chỉ có 5–7 quan sát. p75 không phải bảo đảm xác suất đúng giờ. "
        "Số xe tối thiểu được kiểm chứng, nhưng chỉ số dừng/nghỉ chỉ thuộc phép gán đang xét, "
        "không phải phép gán tối ưu về nghỉ trong mọi phương án cùng số xe.",
        "",
    ]
    for scenario in report["scenarios"]:
        lines += [f"### {scenario['id']} — {scenario['timetable_role']}", ""]
        lines += [
            f"Profile chính `{primary}`:",
            "",
            *_summary_table(scenario["alternatives"], primary),
            "",
        ]
    lines += [
        "### Độ nhạy cơ hội nghỉ (mọi profile)",
        "",
        "Mỗi ô: số chuỗi có khoảng nghỉ / số chuỗi giao khung; số chuỗi phụ thuộc thay ca giả định.",
        "",
        "| Kịch bản / phương án / profile | Lái: ăn | Lái: chiều | Phụ: ăn | Phụ: chiều |",
        "|---|---|---|---|---|",
    ]
    for scenario in report["scenarios"]:
        for label, alternative in scenario["alternatives"].items():
            for profile, analysis in alternative["profiles"].items():
                s = analysis["summary"]
                lines.append(
                    f"| {scenario['id']}/{label}/{profile} | "
                    + " | ".join(
                        _role_text(s, role, name)
                        for role in ("driver", "attendant")
                        for name in ("meal", "afternoon")
                    )
                    + " |"
                )
    lines.append("")
    if report["fixed_chain_stress"]:
        for name, key in (
            ("Giữ nguyên chuỗi p50, thử runtime p75", "fixed_chain_stress"),
            ("Giữ giờ xuất bến p50, gán lại xe ở runtime p75", "reassignment_stress"),
        ):
            lines += [
                f"### {name}",
                "",
                "Chỉ thử tương thích kết nối, không lan truyền trễ; các khoảng âm là thiếu hụt so với giờ kế hoạch.",
                "",
            ]
            lines += [f"Profile chính `{primary}`:", "", *_summary_table(report[key], primary), ""]
    lines += [
        "### X ghi gốc trong workbook",
        "",
        f"Số xe ghi gốc: {report['recorded_x'].get('assigned_vehicles', '—')}; "
        "không phải chứng cứ số xe tối thiểu dưới runtime chung. "
        f"Số khoảng dừng báo cáo khác phép trừ giờ kế tiếp: {len(report['recorded_x'].get('recorded_layover_discrepancies', []))}. "
        "Giữ nguyên cả số báo cáo và số tính lại để đối soát; không ghi đè bằng chứng.",
        "",
    ]
    lines += [
        f"Profile chính `{primary}`:",
        "",
        *_summary_table({"X ghi gốc": report["recorded_x"]}, primary),
        "",
    ]
    lines += [
        "## E. Căn cứ và thông tin đơn vị phải xác nhận",
        "",
        report["legal_note"],
        "",
        "Ba loại căn cứ: quy định đã xác minh ở trên; chính sách đơn vị chưa cung cấp; "
        "runtime p50/p75, quay đầu 5 phút và các profile là giả định thử nghiệm.",
        "",
    ]
    lines += [f"- {item}." for item in report.get("missing_evidence", [])]
    lines += [
        "",
        "## F. Quyết định mô hình đề nghị",
        "",
        "Ưu tiên thu thập phân công nhân sự, công việc tại bến và hiệu chuẩn runtime trước khi đổi thuật toán. "
        "Sau khi có các dữ liệu này, Product Owner xác nhận mức dự phòng và nhu cầu thay ca; "
        "chưa đủ bằng chứng để chọn bộ tối ưu nhân sự tích hợp hoặc áp ràng buộc nghỉ cứng. "
        "Giữ nguyên thời khóa biểu C p50 và mọi khuyến nghị hiện có trong lần rà soát này.",
        "",
        "Nguồn tái lập: `"
        + json.dumps(report["source"], ensure_ascii=False, sort_keys=True)
        + "`.",
        "",
    ]
    return "\n".join(lines)


def render_annex(report):
    lines = [
        "# Phụ lục bằng chứng từng chuỗi xe",
        "",
        "Đơn vị giờ là phút từ 00:00 của ngày mô hình. outbound = đầu Miền Tây đi; "
        "inbound = đầu ĐHQG-A đi. ID xe chỉ là ID chuỗi. Các cơ hội nghỉ là điều kiện giả định.",
        "",
    ]
    datasets = [
        (f"{s['id']}/{label}", a)
        for s in report["scenarios"]
        for label, a in s["alternatives"].items()
    ]
    datasets += [
        (f"{key}/{label}", a)
        for key in ("fixed_chain_stress", "reassignment_stress")
        for label, a in report[key].items()
    ]
    datasets.append(("recorded_x/ORIGINAL", report["recorded_x"]))
    for label, alternative in datasets:
        first = next(iter(alternative["profiles"].values()))
        pressure = sorted(
            first["chains"],
            key=lambda c: (
                -c["incompatible_connections"],
                c["minimum_slack"] if c["minimum_slack"] is not None else float("inf"),
                -c["longest_short_run"],
                c["vehicle_id"],
            ),
        )
        lines += [
            f"## {label}",
            "",
            "Xe chịu áp lực cao nhất: " + ", ".join(c["vehicle_id"] for c in pressure[:3]) + ".",
            "",
        ]
        for chain in first["chains"]:
            lines += [
                f"### {chain['vehicle_id']}",
                "",
                f"{chain['trip_count']} chuyến; {chain['driving_minutes']} phút chạy; "
                f"khoảng hoạt động {chain['span_minutes']} phút; "
                f"{chain['first_departure']}–{chain['last_arrival']}. "
                f"Dự phòng nhỏ nhất {chain['minimum_slack']}; "
                f"{chain['incompatible_connections']} nối không tương thích.",
                "",
                "| Chuyến | Hướng | Đi | Đến | Chuyến sau | Dừng | Kỹ thuật | Dự phòng |",
                "|---|---|---:|---:|---|---:|---:|---:|",
            ]
            intervals = {i["from_trip_id"]: i for i in chain["intervals"]}
            for trip in chain["trips"]:
                interval = intervals.get(trip["trip_id"], {})
                lines.append(
                    f"| {trip['trip_id']} | {trip['direction']} | {trip['departure']} | {trip['arrival']} | "
                    + " | ".join(
                        str(interval.get(k, "—"))
                        for k in ("to_trip_id", "scheduled_dwell", "technical_turnaround", "slack")
                    )
                    + " |"
                )
            lines.append("")
            for profile, analysis in alternative["profiles"].items():
                c = next(c for c in analysis["chains"] if c["vehicle_id"] == chain["vehicle_id"])
                for role, windows in c["crew"].items():
                    for window in windows:
                        opportunities = window["fixed_vehicle_opportunities"]
                        fixed = (
                            ", ".join(
                                f"{o['free_start']}–{o['free_end']} tại {o['terminal']} sau {o['after_trip_id']}"
                                for o in opportunities
                            )
                            or "không có"
                        )
                        relief = (
                            ", ".join(
                                f"{o['release']}–{o['break_end']} tại {o['terminal']}"
                                for o in window["relief_opportunities"]
                            )
                            or "chưa có"
                        )
                        lines.append(
                            f"- {profile}/{role}/{window['policy']['name']}: nghỉ cùng xe {fixed}; "
                            f"cơ hội thay ca {relief}; INSUFFICIENT_CREW_EVIDENCE."
                        )
            lines.append("")
    return "\n".join(lines)


def export_review(report, output_dir):
    output_dir = Path(output_dir).resolve()
    repo = Path(__file__).resolve().parents[3]
    if output_dir.is_relative_to(repo):
        for name in ("crew_review.json", "crew_report_vi.md", "chain_evidence_vi.md"):
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(output_dir / name)],
                cwd=repo,
                check=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )
            if ignored.returncode != 0:
                raise ValueError(
                    "private generated evidence must be Git-ignored or outside repository"
                )
    contents = {
        "crew_review.json": _json(report),
        "crew_report_vi.md": render_report(report),
        "chain_evidence_vi.md": render_annex(report),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        (output_dir / name).write_bytes(content.encode("utf-8"))

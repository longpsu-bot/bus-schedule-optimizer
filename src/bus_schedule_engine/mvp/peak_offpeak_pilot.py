"""Approved Phase 1/2 experiment: two authored plans, existing compiler and fleet solver."""

from __future__ import annotations

import csv
import io
import json
import subprocess
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from .circulation import assign_fleet, validate_chains
from .crew_review import analyze_chains
from .external_benchmark import _json
from .fleet_timespace import TERMINALS, meal_policy, reconstruct
from .input import DIRECTIONS, runtime_at
from .planning import compile_plan
from .quality import waiting
from .route10_crew_review import run_review
from .route10_fleet_pilot import audit_fleet
from .route10_pilot import compare_timetable

BASE_SHA = "8982dca0777435cc86a005c6ef613b05ca4d9f0a"
FROZEN_SHA = "1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3"
COMPILE_SETTINGS = dict(
    boundary_settlement_minutes=30,
    minimum_internal_gaps=2,
    minimum_regime_minutes=30,
    maximum_transition_jump=10,
    solver_seconds=5,
    solver_work_limit=1,
)
EXPORT_NAMES = (
    "peak_offpeak_report_vi.md",
    "fleet_timespace.json",
    "fleet_utilization.csv",
    "deployment_scenarios.json",
    "crew_meal_recovery.json",
    "fleet_timeline.html",
)


def authored_plans():
    """Fixed manual choices: no neighborhood search or fleet-driven timetable revision."""
    definitions = {
        "P1": {
            "outbound": ([390, 690, 840, 1020, 1260], [8, 15, 6, 10, 11]),
            "inbound": ([420, 720, 870, 1050, 1260], [8, 16, 6, 10, 10]),
        },
        "P2": {
            "outbound": ([390, 660, 840, 930, 1020, 1140, 1260], [8, 14, 7, 5, 6, 5, 5]),
            "inbound": ([420, 690, 870, 960, 1050, 1170, 1260], [8, 14, 7, 5, 6, 6, 4]),
        },
    }
    reasons = {
        "P1": {
            "outbound": [
                "06:30 kết thúc cụm nhu cầu sáng 05:30–06:30; dành 8 khoảng cách cho đầu ngày.",
                "11:30 giữ phục vụ cụm tăng 11:00–11:30; 15 khoảng cách cho phần sáng còn lại.",
                "14:00 kết thúc khoảng giảm cường độ 11:30–14:00; 6 khoảng cách, thưa hơn P0.",
                "17:00 giữ 10 khoảng cách cho chiều, gồm nhu cầu cao 15:30–17:00.",
                "21:00 giữ chuyến cuối; 11 khoảng cách đuôi ngày, phân bổ lại để đủ 50 khoảng cách.",
            ],
            "inbound": [
                "07:00 giữ 8 khoảng cách quanh cụm nhu cầu 06:00–07:00, muộn hơn hướng đi.",
                "12:00 giữ 16 khoảng cách qua cụm nhu cầu 11:30–12:00.",
                "14:30 kết thúc giảm cường độ sau đỉnh trưa, giữ 6 khoảng cách và theo dõi tăng lúc 14:30.",
                "17:30 giữ 10 khoảng cách cho cao điểm chiều kéo dài hơn hướng đi.",
                "21:00 giữ chuyến cuối và 10 khoảng cách cuối ngày.",
            ],
        },
        "P2": {
            "outbound": [
                "06:30 giữ 8 khoảng cách phục vụ đỉnh sáng.",
                "11:00 kết thúc khối sáng 14 khoảng cách, thử phasing trước cửa sổ ăn trưa.",
                "14:00 khối 7 khoảng cách tạo khoảng chờ bến; có rủi ro giảm dịch vụ 11:00–11:30 cần báo cáo.",
                "15:30 khối 5 khoảng cách tăng dần trước tắc nghẽn chiều.",
                "17:00 khối 6 khoảng cách dày ở đỉnh 15:30–17:00.",
                "19:00 khối 5 khoảng cách thưa sau đỉnh nhằm thử cơ hội ăn tối; không tự coi là nghỉ.",
                "21:00 khối cuối 5 khoảng cách bảo toàn chuyến cuối và tổng chuyến.",
            ],
            "inbound": [
                "07:00 giữ 8 khoảng cách qua đỉnh sáng muộn hơn hướng đi.",
                "11:30 giữ 14 khoảng cách khối sáng, thử phasing ăn trưa lệch hướng đi 30 phút.",
                "14:30 khối 7 khoảng cách giảm cường độ; báo cáo tác động cụm 11:30–12:00.",
                "16:00 khối 5 khoảng cách tăng cường trước cao điểm hướng về.",
                "17:30 khối 6 khoảng cách dày, giữ đỉnh hướng về muộn hơn hướng đi.",
                "19:30 khối 6 khoảng cách thử cơ hội tối sau cao điểm, tránh giảm quá mạnh lúc 17:00.",
                "21:00 khối 4 khoảng cách giữ đuôi ngày và tổng chuyến.",
            ],
        },
    }
    return {
        name: dict(
            authority="MANUALLY_AUTHORED_EXPERIMENTAL_SERVICEPLAN",
            directions={
                d: [dict(end=e, gaps=g) for e, g in zip(ends, gaps, strict=True)]
                for d, (ends, gaps) in dirs.items()
            },
            rationale=reasons[name],
        )
        for name, dirs in definitions.items()
    }


def compile_manual(data, plans):
    results = {
        d: compile_plan(data["directions"][d], plans[d], COMPILE_SETTINGS) for d in DIRECTIONS
    }
    if any(r["status"] != "COMPILED" for r in results.values()):
        return dict(
            status="FAMILY_INFEASIBLE"
            if any(r["status"] == "FAMILY_INFEASIBLE" for r in results.values())
            else "COMPILATION_INCOMPLETE",
            directions=results,
        )
    return dict(
        status="COMPILED",
        departures={d: r["departures"] for d, r in results.items()},
        regimes=[
            dict(direction=d, **regime) for d, r in results.items() for regime in r["regimes"]
        ],
        boundary_settlement={d: r["boundary_settlement"] for d, r in results.items()},
    )


def service_changes(data, reference, departures):
    rows = []
    for d in DIRECTIONS:
        for b in data["directions"][d]["demand"]:
            old = waiting(reference[d], [b])
            new = waiting(departures[d], [b])
            rows.append(
                dict(
                    direction=d,
                    **b,
                    waiting_before=old["wait"],
                    waiting_after=new["wait"],
                    waiting_change_minutes=new["wait"] - old["wait"]
                    if new["wait"] is not None and old["wait"] is not None
                    else None,
                    added_waiting_passenger_minutes=new["integral"] - old["integral"],
                    outside_service_passengers_before=old["unserved"],
                    outside_service_passengers_after=new["unserved"],
                )
            )
    return rows


def split_sensitivity(fleet):
    """One declared split of the longest duty near noon; no search for an optimal cover."""
    if not any(len(c) > 1 for c in fleet["chains"]):
        return dict(status="NO_SPLIT_AVAILABLE")
    f = deepcopy(fleet)
    by_id = {t["trip_id"]: t for t in f["trips"]}
    chain = max(
        (c for c in f["chains"] if len(c) > 1),
        key=lambda c: (by_id[c[-1]]["arrival"] - by_id[c[0]]["departure"], c[0]),
    )
    cut = min(range(1, len(chain)), key=lambda i: (abs(by_id[chain[i]]["departure"] - 720), i))
    suffix = chain[cut:]
    del chain[cut:]
    f["chains"].append(suffix)
    new_id = f"V{len(f['chains']):03d}"
    for tid in suffix:
        by_id[tid]["vehicle_id"] = new_id
    f["required_fleet"] = len(f["chains"])
    f["within_fleet_ceiling"] = f["required_fleet"] <= 15
    initial = Counter(by_id[c[0]]["direction"] for c in f["chains"])
    f["initial_vehicles_required"] = {d: initial[d] for d in DIRECTIONS}
    return dict(
        status="EXPLICIT_SINGLE_CHAIN_SPLIT",
        fleet=f,
        split_before_trip=suffix[0],
        additional_vehicle_id=new_id,
        additional_vehicle_start_terminal=TERMINALS[by_id[suffix[0]]["direction"]],
        authority="EXPERIMENTAL_ADDITIONAL_TERMINAL_STOCK_NOT_OPERATOR_CONFIRMED",
        rationale="Split longest duty at its departure closest to 12:00; one authored split only.",
    )


def _existing_crew_profile(p):
    return dict(
        authority="OPERATOR_SUPPLIED_UNVERIFIED",
        short_turnaround_minutes=10,
        roles={
            "driver": [
                dict(
                    name=name,
                    start=a,
                    end=b,
                    minutes=p["minutes"],
                    tasks_after=p["tasks_after"],
                    tasks_before=p["tasks_before"],
                    reserve=0,
                    handover=0,
                )
                for name, (a, b) in p["windows"].items()
            ]
        },
    )


def _evaluate(data, stressed, candidate, reference, policy, standdown):
    fleet = candidate["vehicle_chains"]
    validate_chains(data, candidate["departures"], fleet)
    audit_fleet(data, candidate["departures"], fleet)
    margins = {
        t["trip_id"]: max(
            0,
            runtime_at(stressed["directions"][t["direction"]], t["departure"])
            - runtime_at(data["directions"][t["direction"]], t["departure"]),
        )
        for t in fleet["trips"]
    }
    nominal = reconstruct(
        fleet,
        fleet["initial_vehicles_required"],
        margins=margins,
        policy=policy,
        standdown=standdown,
    )
    fixed = analyze_chains(
        fleet, stressed["layover_minutes"], _existing_crew_profile(policy), runtime_data=stressed
    )
    reassigned = assign_fleet(stressed, candidate["departures"])
    audit_fleet(stressed, candidate["departures"], reassigned)
    stress_timeline = reconstruct(
        reassigned,
        reassigned["initial_vehicles_required"],
        margins=margins,
        policy=policy,
        runtime_basis="p75",
        standdown=standdown,
    )
    full_data = deepcopy(stressed)
    full_data["layover_minutes"] = dict.fromkeys(
        DIRECTIONS, policy["technical"] + policy["tasks_after"] + policy["tasks_before"]
    )
    full_fleet = assign_fleet(full_data, candidate["departures"])
    audit_fleet(full_data, candidate["departures"], full_fleet)
    stock = {}
    for name, bundle in [("p50", data), ("p75", stressed), ("recovery_and_tasks", full_data)]:
        constrained = deepcopy(bundle)
        constrained["initial_vehicles"] = dict(outbound=8, inbound=6)
        constrained["fleet_ceiling"] = 14
        assigned = assign_fleet(
            constrained,
            candidate["departures"],
            seconds=10,
            settings={"solver_seconds": 10, "solver_work_limit": 2},
        )
        stock[name] = assigned
    changes = service_changes(data, reference, candidate["departures"])
    crew = nominal["crew"]
    requirements = dict(
        fleet_14=fleet["required_fleet"] <= 14,
        fixed_chain_p75=fixed["summary"]["incompatible_connections"] == 0,
        recovery_tasks_14=full_fleet["required_fleet"] <= 14,
        assigned_recovery_tasks=nominal["audit"]["recovery_task_deficit_connections"] == 0,
        lunch=crew["lunch_covered"] == crew["lunch_required"],
        dinner=crew["dinner_covered"] == crew["dinner_required"],
        inherited_mandatory_constraints=candidate["quality"]["hard_constraints_pass"],
        explicit_service_protection_authority="NOT_SUPPLIED",
        terminal_stock_and_parking_authority="UNCONFIRMED",
    )
    result = dict(
        candidate=candidate,
        initial_required=fleet["initial_vehicles_required"],
        nominal=nominal,
        fixed_p75=fixed,
        reassigned_p75=dict(fleet=reassigned, timeline=stress_timeline),
        exact_recovery_task_fleet=full_fleet,
        hypothetical_stock_8_6=stock,
        service_changes_vs_P0=changes,
        operating_requirements=requirements,
        operationally_acceptable=False,
        sensitivity_15=None,
    )
    if fleet["required_fleet"] == 14:
        split = split_sensitivity(fleet)
        if split["status"] == "EXPLICIT_SINGLE_CHAIN_SPLIT":
            split_data = deepcopy(data)
            split_data["fleet_ceiling"] = 15
            validate_chains(split_data, candidate["departures"], split["fleet"])
            split["nominal"] = reconstruct(
                split["fleet"],
                split["fleet"]["initial_vehicles_required"],
                margins=margins,
                policy=policy,
                standdown=standdown,
            )
            split["fixed_p75"] = analyze_chains(
                split["fleet"],
                stressed["layover_minutes"],
                _existing_crew_profile(policy),
                runtime_data=stressed,
            )
        result["sensitivity_15"] = split
    elif fleet["required_fleet"] == 15:
        result["sensitivity_15"] = dict(
            status="EXACT_REQUIRED_FLEET_ALREADY_15",
            fleet=fleet,
            nominal=nominal,
            fixed_p75=fixed,
            authority="EXPERIMENTAL_INITIAL_STOCK_NOT_OPERATOR_CONFIRMED",
        )
    elif fleet["required_fleet"] > 15:
        result["sensitivity_15"] = dict(
            status="PROVED_INFEASIBLE_AT_15_FOR_THIS_TIMETABLE",
            exact_minimum=fleet["required_fleet"],
        )
    return result


def _deployment_opportunities(candidates, data, stressed):
    """Report actual assigned passenger movements, never hypothetical repositioning."""
    # Independently inspected demand clusters share a start, but have different ends.
    peaks = {"outbound": (930, 1020), "inbound": (930, 1050)}
    for candidate in candidates.values():
        by_id = {t["trip_id"]: t for t in candidate["candidate"]["vehicle_chains"]["trips"]}
        candidate["peak_windows"] = {
            d: dict(
                start=a,
                end=b,
                authority="MANUALLY_DECLARED_FROM_FROZEN_DIRECTIONAL_DEMAND",
                demand_buckets=[r for r in data["directions"][d]["demand"] if a <= r["start"] < b],
            )
            for d, (a, b) in peaks.items()
        }
        rows = []
        for gap in candidate["nominal"]["opportunities"]:
            row = dict(gap)
            row["next_peak_by_direction"] = {}
            local = sorted(
                (t for t in by_id.values() if t["vehicle_id"] == gap["vehicle_id"]),
                key=lambda t: t["departure"],
            )
            crew = next(
                c
                for c in candidate["nominal"]["crew"]["chains"]
                if c["vehicle_id"] == gap["vehicle_id"]
            )
            for d, (peak_start, peak_end) in peaks.items():
                same = gap["terminal"] == TERMINALS[d]
                p = candidate["nominal"]["crew"]["policy"]
                target = next(
                    (
                        t
                        for t in local
                        if t["direction"] == d
                        and max(peak_start, gap["start"]) <= t["departure"] < peak_end
                    ),
                    None,
                )
                previous = (
                    local[local.index(target) - 1] if target and local.index(target) else None
                )
                ready = None
                if target:
                    ready = (
                        target["departure"]
                        if previous is None
                        else (
                            previous["departure"]
                            + runtime_at(
                                stressed["directions"][previous["direction"]], previous["departure"]
                            )
                            + p["technical"]
                            + p["tasks_after"]
                            + p["tasks_before"]
                        )
                    )
                    for meal in crew["meals"].values():
                        if (
                            meal["opportunity"]
                            and previous
                            and previous["arrival"] <= meal["opportunity"][0]
                            and meal["opportunity"][1] <= target["departure"]
                        ):
                            ready = max(ready, meal["opportunity"][1] + p["tasks_before"])
                row["next_peak_by_direction"][d] = dict(
                    window=[peak_start, peak_end],
                    assigned_peak_trip=target["trip_id"] if target else None,
                    assigned_peak_departure=target["departure"] if target else None,
                    at_correct_terminal=same,
                    transfer_authorized=False,
                    ready_for_assigned_peak_with_recovery_tasks_and_selected_meals=ready,
                    actual_previous_passenger_trip=previous["trip_id"] if previous else None,
                    additional_lead_minutes=None
                    if ready is None
                    else max(0, ready - gap["earliest_reactivation"]),
                    assigned_peak_recovery_tasks_pass=ready <= target["departure"]
                    if target
                    else None,
                    explanation="Xe khác bến không thể phục vụ ngay; chỉ chuyến chở khách được phân công mới đưa xe sang bến kia.",
                )
            row["assigned_next_departure"] = by_id[gap["next_trip_id"]]["departure"]
            rows.append(row)
        candidate["deployment_opportunities"] = rows


def run_pilot(workbook, evidence, output_dir, *, policy=None, policy_source=None):
    output_dir = Path(output_dir).resolve()
    _check_output(output_dir)
    targets = {(output_dir / name).resolve() for name in EXPORT_NAMES} | {
        (output_dir / "source_revalidation" / name).resolve()
        for name in ("crew_review.json", "crew_report_vi.md", "chain_evidence_vi.md")
    }
    sources = (workbook, evidence) + ((policy_source,) if policy_source is not None else ())
    if any(Path(source).resolve() in targets for source in sources):
        raise ValueError("pilot exports must not overwrite source inputs")
    policy = meal_policy() if policy is None else policy
    # Reuse every frozen source/compiler/fleet/quality lock from the prior read-only review.
    review = run_review(
        workbook, evidence, output_dir / "source_revalidation", evidence_sha256=FROZEN_SHA
    )
    frozen = json.loads(Path(evidence).read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in frozen["scenarios"]}
    data, stressed = rows["report_p50"]["bundle"], rows["report_p75"]["bundle"]
    incumbent = deepcopy(rows["report_p50"]["comparison"]["C"])
    prior = next(r for r in review["scenarios"] if r["id"] == "report_p50")["alternatives"]["C"][
        "profiles"
    ]["illustrative"]["summary"]
    locks = dict(
        trip_counts={d: len(incumbent["departures"][d]) for d in DIRECTIONS}
        == dict.fromkeys(DIRECTIONS, 51),
        endpoints=incumbent["departures"]["outbound"][0] == 285
        and incumbent["departures"]["inbound"][0] == 300
        and all(ts[-1] == 1260 for ts in incumbent["departures"].values()),
        fleet=incumbent["vehicle_chains"]["required_fleet"] == 14,
        starting_stock=incumbent["vehicle_chains"]["initial_vehicles_required"]
        == dict(outbound=8, inbound=6),
        review_exceptions=len(incumbent["review_exceptions"]) == 9,
        short_connections=(prior["short_turnarounds"], prior["connections"]) == (21, 88),
        prior_illustrative_lunch=prior["roles"]["driver"][0]["fixed_possible_chains"] == 6,
        fixed_p75_failures=review["fixed_chain_stress"]["C"]["profiles"]["illustrative"]["summary"][
            "incompatible_connections"
        ]
        == 15,
    )
    if not all(locks.values()):
        raise ValueError("frozen Route 10 acceptance lock failed")
    report = dict(
        schema_version="peak_offpeak_pilot_v1",
        status="PARTIAL_EVIDENCE",
        selection="NO_OPERATIONALLY_ACCEPTABLE_CANDIDATE_FOUND_WITHIN_PILOT",
        source=dict(
            workbook_sha256=review["source"]["sha256"],
            frozen_sha256=FROZEN_SHA,
            sha256=review["source"]["sha256"],
            engine_base_sha=BASE_SHA,
            prior_crew_evidence="RECOMPUTED_WITH_EXISTING_READ_ONLY_REVIEW",
            analysis_code_sha256={
                name: sha256(
                    Path(__file__).with_name(name).read_bytes().replace(b"\r\n", b"\n")
                ).hexdigest()
                for name in (
                    "fleet_timespace.py",
                    "peak_offpeak_pilot.py",
                    "peak_offpeak_report.py",
                )
            },
        ),
        baseline_verification=dict(
            locks=locks,
            all_locks_pass=True,
            frozen_C_sha256=sha256(_json(incumbent).encode("utf-8")).hexdigest(),
        ),
        policy=policy,
        runtime_definitions={k: rows[k]["definition"] for k in ("report_p50", "report_p75")},
        authored_plans=authored_plans(),
        candidates={},
        rejections=[],
    )
    report["candidates"]["P0"] = _evaluate(
        data, stressed, incumbent, incumbent["departures"], policy, False
    )
    for name, plan in report["authored_plans"].items():
        compiled = compile_manual(data, plan["directions"])
        plan["compilation"] = compiled
        if compiled["status"] != "COMPILED":
            report["rejections"].append(dict(candidate=name, **compiled))
            continue
        candidate = compare_timetable(data, name, compiled["departures"], compiled["regimes"])
        candidate["source"] = "MANUALLY_AUTHORED_EXPERIMENTAL_SERVICEPLAN"
        report["candidates"][name] = _evaluate(
            data, stressed, candidate, incumbent["departures"], policy, True
        )
    _deployment_opportunities(report["candidates"], data, stressed)
    report["rejections"].extend(
        dict(candidate=k, requirements=v["operating_requirements"])
        for k, v in report["candidates"].items()
    )
    if (
        sha256(_json(rows["report_p50"]["comparison"]["C"]).encode("utf-8")).hexdigest()
        != report["baseline_verification"]["frozen_C_sha256"]
    ):
        raise ValueError("frozen reference was modified")
    export_pilot(report, output_dir)
    return report


def _check_output(output_dir):
    repo = Path(__file__).resolve().parents[3]
    if output_dir.is_relative_to(repo):
        for name in EXPORT_NAMES:
            check = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(output_dir / name)],
                cwd=repo,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
            )
            if check.returncode != 0:
                raise ValueError(
                    "generated private evidence must be Git-ignored or outside repository"
                )


def export_pilot(report, output_dir):
    from .peak_offpeak_report import render_html, render_report

    output_dir = Path(output_dir).resolve()
    _check_output(output_dir)
    candidates = report["candidates"]
    provenance = dict(source=report["source"], schema_version="peak_offpeak_pilot_v1")
    ledger = {
        k: {field: c["nominal"][field] for field in ("ledger", "segments", "snapshots", "audit")}
        for k, c in candidates.items()
    }
    crews = {
        k: dict(
            nominal=c["nominal"]["crew"],
            fixed_p75=c["fixed_p75"],
            reassigned_p75=c["reassigned_p75"]["timeline"]["crew"],
            sensitivity_15=c["sensitivity_15"],
        )
        for k, c in candidates.items()
    }
    stream = io.StringIO(newline="")
    all_rows = [
        dict(candidate=k, **r) for k, c in candidates.items() for r in c["nominal"]["utilization"]
    ]
    writer = csv.DictWriter(
        stream,
        fieldnames=list(all_rows[0]) if all_rows else ["candidate", "start", "end"],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(all_rows)
    contents = {
        "deployment_scenarios.json": _json(report),
        "fleet_timespace.json": _json(provenance | dict(candidates=ledger)),
        "crew_meal_recovery.json": _json(
            provenance | dict(policy=report.get("policy"), candidates=crews)
        ),
        "fleet_utilization.csv": stream.getvalue(),
        "peak_offpeak_report_vi.md": render_report(report),
        "fleet_timeline.html": render_html(report),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        (output_dir / name).write_bytes(content.encode("utf-8"))

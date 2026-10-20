"""Route 10 MVP-5B acceptance alongside the unchanged MVP-5A control."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from .circulation import validate_chains
from .input import DIRECTIONS
from .joint import local_key
from .route10_pilot import _statistics, compare_timetable, run_pilot
from .runner import export_result, run_bundle

JOINT_SETTINGS = {
    "compilation_lookahead": 256,
    "directional_settlements": 4,
    "pair_evaluation_budget": 160,
    "pairs_per_plan": 16,
}


def retained_trials(result):
    return result["diagnostics"].get("incumbents", []) + [
        p["candidate"]
        for f in result["diagnostics"]["feedback"]
        for p in f.get("pairs", [])
        if "candidate" in p
    ]


def run_joint_pilot(path, output_dir, *, pairs_per_plan=16):
    output_dir = Path(output_dir)
    joint_settings = JOINT_SETTINGS | {"pairs_per_plan": pairs_per_plan}
    control = run_pilot(path, output_dir / "mvp5a_control")
    incumbent = control["scenarios"][0]["comparison"]["C"]
    if not incumbent or not incumbent["quality"]["hard_constraints_pass"]:
        raise ValueError("MVP-5A p50 incumbent could not be independently recovered")
    if (
        incumbent["quality"]["required_fleet"] != 14
        or abs(incumbent["quality"]["waiting_minutes"] - 9.441295) > 0.000001
        or len(incumbent["review_exceptions"]) != 9
    ):
        raise ValueError("MVP-5A frozen p50 evidence differs; inspect before continuing")
    report = {
        "schema_version": "route10_joint_pilot_v1",
        "source": control["source"],
        "scenarios": [],
        "limitations": control["limitations"][:],
        "incumbent_origin": "Independent MVP-5A p50 rerun; no production timestamp fixture",
        "joint_settings": joint_settings,
    }
    report["limitations"] = [
        s for s in report["limitations"] if not s.startswith("The compiler ranks")
    ]
    report["limitations"].append(
        f"Joint search retains at most four directional vectors per plan, {pairs_per_plan} pairs per plan, 25 plans and 160 distinct exact pair evaluations, plus the separately disclosed baseline and independent acceptance validations. Unexamined directional and plan families remain; no global infeasibility or optimality proof exists."
    )
    for old in control["scenarios"]:
        data = old["bundle"]
        seed = {k: incumbent[k] for k in ("departures", "regimes")}
        started = perf_counter()
        result = run_bundle(data, joint_settings, incumbents=[seed])
        elapsed = perf_counter() - started
        trials = retained_trials(result)
        selected = result["recommended"]
        trial = selected or min(
            trials,
            key=lambda c: (
                len(c["quality"]["proven_hard_failures"]),
                c["quality"]["required_fleet"]
                if c["quality"]["required_fleet"] is not None
                else float("inf"),
                local_key(c),
                c["quality"]["waiting_minutes"] or 0,
                c["id"],
            ),
            default=None,
        )
        c = (
            compare_timetable(data, trial["id"], trial["departures"], trial["regimes"])
            if trial
            else None
        )
        revalidated_incumbent = compare_timetable(
            data, "MVP5A_incumbent", seed["departures"], seed["regimes"]
        )
        if c:
            validate_chains(data, c["departures"], c["vehicle_chains"])
            if (
                c["quality"] != trial["quality"]
                or c["vehicle_chains"]["required_fleet"]
                != trial["vehicle_chains"]["required_fleet"]
            ):
                raise ValueError(
                    "Independent joint timetable validation differs from search evidence"
                )
        if selected:
            for d in DIRECTIONS:
                assert len(selected["departures"][d]) == 51
            assert selected["quality"]["required_fleet"] <= 14
            assert all(r["gap_count"] >= 2 for r in selected["regimes"])
            assert not selected["quality"]["proven_hard_failures"]
        if old["id"] == "report_p50":
            assert selected is not None
            assert (
                selected["quality"]["waiting_minutes"]
                <= incumbent["quality"]["waiting_minutes"] + 1e-9
            )
        statistics = _statistics(result, elapsed) | {
            k: result["diagnostics"][k]
            for k in (
                "exact_pair_evaluations",
                "pair_evaluation_budget",
                "directional_compilation_cache_hits",
                "unexamined_retained_pairs",
                "feasible_generated_candidates",
            )
        }
        row = {
            "id": old["id"],
            "definition": old["definition"],
            "bundle": data,
            "mvp5a": {"statistics": old["statistics"]["improved"], "comparison": old["comparison"]},
            "joint": result,
            "statistics": statistics,
            "comparison": old["comparison"] | {"C": c},
            "revalidated_incumbent": revalidated_incumbent,
            "c_role": "VERIFIED_RECOMMENDATION" if selected else "NEAR_FEASIBLE_TRIAL_ONLY",
            "outcome": "CONDITIONAL_C_REQUIRES_SERVICE_REVIEW" if selected else "SEARCH_INCOMPLETE",
            "trial_fleets": [
                {
                    "id": t["id"],
                    "required_fleet": t["quality"]["required_fleet"],
                    "fleet_ceiling_shortfall": max(0, t["quality"]["required_fleet"] - 14)
                    if t["quality"]["required_fleet"] is not None
                    else None,
                    "failures": t["quality"]["failures"],
                    "waiting_minutes": t["quality"]["waiting_minutes"],
                    "local_service": t.get("local_service"),
                }
                for t in trials
            ],
            "infeasibility_proof": None,
        }
        report["scenarios"].append(row)
        export_result(result, output_dir / old["id"])
    (output_dir / "joint_report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "comparison_report.md").write_text(render_joint_report(report), encoding="utf-8")
    return report


def render_joint_report(report):
    from .route10_pilot import render_report

    lines = [
        "# MVP-5B joint Route 10 acceptance",
        "",
        "Conditional experiments; unchanged private inputs, runtime windows, five-minute layover and 51/51 trips.",
        "",
    ]
    for row in report["scenarios"]:
        old, new = row["mvp5a"]["comparison"]["C"], row["comparison"]["C"]
        stats = row["statistics"]
        lines += [f"## {row['id']}", "", "| Metric | MVP-5A | MVP-5B |", "|---|---:|---:|"]
        for label, getter in (
            ("Exact fleet", lambda c: c["quality"]["required_fleet"]),
            ("Modeled wait", lambda c: f"{c['quality']['waiting_minutes']:.6f}"),
            ("Review exceptions", lambda c: len(c["review_exceptions"])),
            (
                "Positive deterioration passenger-minutes",
                lambda c: f"{c['positive_deterioration_passenger_minutes']:.3f}",
            ),
        ):
            lines.append(f"| {label} | {getter(old)} | {getter(new)} |")
        lines += [
            "",
            f"Role: {row['c_role']}; plans {stats['evaluations']}; distinct exact pairs {stats['exact_pair_evaluations']}/160; feasible generated {stats['feasible_generated_candidates']}; directional cache hits {stats['directional_compilation_cache_hits']}; previews {stats['settlement_previews']}; runtime {stats['runtime_seconds']:.3f}s; stop {stats['search_limit_reason']}.",
            "",
            "All retained trial fleet counts, shortfalls, rejection reasons and local-service summaries are in joint_report.json. All exact evaluated trials retain timetable/regimes/chains/quality under joint diagnostics. Remaining retained pairs and incomplete directional compilations are disclosed separately; the ungenerated plan space is uncounted.",
            "",
        ]
    # Existing report renders exact departures, regimes and interval warnings, without a new presentation layer.
    detail_rows = [
        row | {"statistics": {"control": row["mvp5a"]["statistics"], "improved": row["statistics"]}}
        for row in report["scenarios"]
    ]
    lines.append(render_report(report | {"scenarios": detail_rows}))
    return "\n".join(lines)

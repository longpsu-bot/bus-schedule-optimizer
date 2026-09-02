from __future__ import annotations

import importlib
from pathlib import Path


def _runner():
    return importlib.import_module("scripts.run_pr62_i_worst_bucket_passenger_access")


def test_h_to_i_comparison_identifies_only_new_dimension_removals() -> None:
    runner = _runner()
    records = (
        {"fingerprint": "old", "metrics": {**runner._equal_metrics(), "max_wait": 20.0}},
        {"fingerprint": "better", "metrics": {**runner._equal_metrics(), "max_wait": 15.0}},
        {
            "fingerprint": "tradeoff",
            "metrics": {
                **runner._equal_metrics(),
                "average_wait": 4.0,
                "max_wait": 25.0,
                "mismatch": 2.0,
            },
        },
    )

    comparison = runner._compare_h_to_i_frontiers(records)

    assert comparison["h_pareto_fingerprints"] == ["better", "old", "tradeoff"]
    assert comparison["i_pareto_fingerprints"] == ["better", "tradeoff"]
    assert comparison["removed_only_by_maximum_bucket_wait"] == [
        {"fingerprint": "old", "dominated_by": ["better"]}
    ]


def test_review_roles_are_deterministic_and_include_maximum_access() -> None:
    runner = _runner()
    records = (
        runner._synthetic_record("a", average_wait=5.0, max_wait=20.0, fleet=4),
        runner._synthetic_record("b", average_wait=6.0, max_wait=15.0, fleet=5),
    )

    roles = runner._review_roles(records)

    assert roles["MINIMUM_AVERAGE_WAIT"]["fingerprint"] == "a"
    assert roles["MINIMUM_MAXIMUM_BUCKET_WAIT"]["fingerprint"] == "b"
    assert roles["MINIMUM_FLEET"]["fingerprint"] == "a"


def test_canonical_json_render_is_byte_identical() -> None:
    runner = _runner()
    payload = {"route": 6, "fingerprints": ["b", "a"]}

    assert runner._canonical_json_bytes(payload) == runner._canonical_json_bytes(payload)


def test_human_final_uses_the_h_accepted_private_workbook() -> None:
    runner = _runner()
    repo_root = Path(__file__).resolve().parents[1]

    workbook = runner._human_final_workbook(repo_root)

    assert workbook == repo_root / "private" / "Route_6_Current_ExternalAI_HumanFinal.xlsx"


def test_evidence_names_the_exact_ten_production_pareto_dimensions() -> None:
    runner = _runner()

    assert len(runner.PRODUCTION_I_DIMENSIONS) == 10
    assert runner.PRODUCTION_I_DIMENSIONS[2] == "maximum_bucket_expected_wait_minutes"

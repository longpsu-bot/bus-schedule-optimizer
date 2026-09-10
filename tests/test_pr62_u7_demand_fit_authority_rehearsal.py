from __future__ import annotations

import ast
import builtins
import importlib.util
import itertools
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_pr62_u7_demand_fit_authority_rehearsal as u7  # noqa: E402

SSE_BEST = "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
TE_BEST = "da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90"
CONTINUOUS_BEST = "1d3e0a6bf5508c30a45f919c37e30f81ea4857de806947288014c8d549f7d241"
ROUTE6_COMMON = "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"


def candidate(
    fingerprint: str,
    *,
    sse: float,
    te: float,
    continuous: float,
    hard_feasible: bool = True,
    access_safe: bool = True,
) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "sse": sse,
        "te": te,
        "continuous_exposure": continuous,
        "hard_feasible": hard_feasible,
        "access_safe": access_safe,
    }


def classification(error: pytest.ExceptionInfo[u7.ReviewError]) -> str:
    return error.value.classification


def test_scalar_authorities_choose_exact_unique_minima_after_hard_access_gates() -> None:
    rows = [
        candidate("a", sse=1.0, te=3.0, continuous=2.0),
        candidate("b", sse=2.0, te=1.0, continuous=3.0),
        candidate("c", sse=3.0, te=2.0, continuous=1.0),
        candidate("blocked", sse=0.0, te=0.0, continuous=0.0, access_safe=False),
    ]

    assert u7.unique_minimum(rows, "sse")["fingerprint"] == "a"
    assert u7.unique_minimum(rows, "te")["fingerprint"] == "b"
    assert u7.unique_minimum(rows, "continuous_exposure")["fingerprint"] == "c"


@pytest.mark.parametrize(
    "delta",
    [0.0, 0.5e-12, math.nextafter(1.0 + 1e-12, -math.inf) - 1.0],
)
def test_scalar_authority_ties_at_epsilon_fail_closed(delta: float) -> None:
    rows = [
        candidate("a", sse=1.0, te=1.0, continuous=1.0),
        candidate("b", sse=1.0 + delta, te=2.0, continuous=2.0),
    ]

    with pytest.raises(u7.ReviewError) as error:
        u7.unique_minimum(rows, "sse")

    assert classification(error) == "AUTHORITY_NOT_UNIQUE"


def test_scalar_authority_just_beyond_epsilon_is_unique() -> None:
    rows = [
        candidate("a", sse=1.0, te=1.0, continuous=1.0),
        candidate("b", sse=1.0 + 1.01e-12, te=2.0, continuous=2.0),
    ]

    assert u7.unique_minimum(rows, "sse")["fingerprint"] == "a"


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([], "EMPTY_AUTHORITY_UNIVERSE"),
        ([candidate("nan", sse=math.nan, te=1.0, continuous=1.0)], "NONFINITE_AUTHORITY_METRIC"),
        ([candidate("inf", sse=1.0, te=math.inf, continuous=1.0)], "NONFINITE_AUTHORITY_METRIC"),
        (
            [
                {
                    **candidate("bad", sse=1.0, te=1.0, continuous=1.0),
                    "hard_feasible": 1,
                }
            ],
            "MALFORMED_HARD_ACCESS_FLAG",
        ),
        (
            [
                {
                    **candidate("bad", sse=1.0, te=1.0, continuous=1.0),
                    "access_safe": "yes",
                }
            ],
            "MALFORMED_HARD_ACCESS_FLAG",
        ),
    ],
)
def test_authority_inputs_fail_closed(rows: list[dict[str, object]], expected: str) -> None:
    for authority in (
        lambda: u7.unique_minimum(rows, "sse"),
        lambda: u7.pareto_frontier(rows),
    ):
        with pytest.raises(u7.ReviewError) as error:
            authority()

        assert classification(error) == expected


def test_d_all_equal_metrics_retains_every_candidate_in_fingerprint_order() -> None:
    rows = [
        candidate("c", sse=1.0, te=1.0, continuous=9.0),
        candidate("a", sse=1.0, te=1.0, continuous=1.0),
        candidate("b", sse=1.0, te=1.0, continuous=5.0),
    ]

    frontier = u7.pareto_frontier(rows)

    assert [row["fingerprint"] for row in frontier] == ["a", "b", "c"]


def test_d_uses_strict_sse_te_dominance_and_keeps_tradeoff_points() -> None:
    rows = [
        candidate("left", sse=0.0, te=2.0, continuous=4.0),
        candidate("middle", sse=1.0, te=1.0, continuous=3.0),
        candidate("right", sse=2.0, te=0.0, continuous=2.0),
        candidate("dominated", sse=2.0, te=2.0, continuous=1.0),
    ]

    frontier = u7.pareto_frontier(rows)

    assert [row["fingerprint"] for row in frontier] == ["left", "middle", "right"]


def test_d_epsilon_dominance_requires_one_improvement_beyond_epsilon() -> None:
    rows = [
        candidate("best", sse=1.0, te=1.0, continuous=9.0),
        candidate("dominated", sse=1.0 + 0.5e-12, te=1.0 + 2e-12, continuous=1.0),
        candidate("epsilon_equal", sse=1.0 + 0.5e-12, te=1.0 + 0.5e-12, continuous=0.0),
    ]

    frontier = u7.pareto_frontier(rows)

    assert [row["fingerprint"] for row in frontier] == ["best", "epsilon_equal"]


def test_d_transitivity_sensitive_chain_leaves_only_true_nondominated_point() -> None:
    rows = [
        candidate("a", sse=0.0, te=0.0, continuous=9.0),
        candidate("b", sse=0.5e-12, te=1.0, continuous=5.0),
        candidate("c", sse=1.0e-12, te=2.0, continuous=1.0),
    ]

    assert [row["fingerprint"] for row in u7.pareto_frontier(rows)] == ["a"]


def test_d_is_caller_order_deterministic_and_continuous_is_not_a_dimension() -> None:
    rows = [
        candidate("a", sse=0.0, te=2.0, continuous=99.0),
        candidate("b", sse=1.0, te=1.0, continuous=50.0),
        candidate("c", sse=2.0, te=0.0, continuous=0.0),
    ]
    expected = ["a", "b", "c"]

    for permutation in itertools.permutations(rows):
        assert [row["fingerprint"] for row in u7.pareto_frontier(permutation)] == expected


@pytest.fixture(scope="module")
def authorities() -> dict[str, object]:
    return u7.load_authorities(ROOT)


@pytest.fixture(scope="module")
def cap_universes(authorities: dict[str, object]) -> dict[str, tuple[dict[str, object], ...]]:
    return u7.reconstruct_route10_cap_universes(authorities)


@pytest.fixture(scope="module")
def evidence() -> dict[str, object]:
    return u7.build_evidence(ROOT)


def test_saved_authority_hashes_and_historical_epsilon_are_frozen(
    authorities: dict[str, object],
) -> None:
    source_artifacts = authorities["source_artifacts"]
    assert (
        source_artifacts[
            "docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json"
        ]["sha256"]
        == "0dcb75205c329a3fc512f475cb619eee61be9b3d25342ae6e12fa923a9bf6877"
    )
    assert (
        source_artifacts["docs/engine/evidence/PR62_U6_V3_ANCHOR_CONFLICT_REVIEW.json"]["sha256"]
        == "2f1e40faca338cb799801667c02d949b34c4ee5f71658e005e6267e3afefb426"
    )
    assert authorities["numerical_epsilon"] == {
        "value": 1e-12,
        "source_path": "src/bus_schedule_engine/contracts_v1/operational_selection_policy.py",
        "source_sha256": "ba0f48b5d0f3d9ed3dacb96aaff2b13d69c68961d835ac2cd33c2f356b40c0d3",
        "source_line": 10,
    }
    assert authorities["u6"]["ROUTE 6"] == {
        "global_coordinator_executions": 0,
        "state": "NOT_RUN_ROUTE10_GATE_FAILED",
    }


def test_cap_reconstruction_matches_saved_a_b_c_authorities_and_exact_d_frontiers(
    cap_universes: dict[str, tuple[dict[str, object], ...]],
) -> None:
    expected = {
        "16": {
            "count": 55,
            "A": SSE_BEST,
            "B": "9da4067ec1f7f7e7372cc9ea1062317c2f37ef6d72d4f556324833c8b59c5eec",
            "C": SSE_BEST,
            "D": [
                "9da4067ec1f7f7e7372cc9ea1062317c2f37ef6d72d4f556324833c8b59c5eec",
                SSE_BEST,
                TE_BEST,
            ],
        },
        "32": {
            "count": 83,
            "A": SSE_BEST,
            "B": TE_BEST,
            "C": CONTINUOUS_BEST,
            "D": [SSE_BEST, TE_BEST],
        },
        "64": {
            "count": 154,
            "A": SSE_BEST,
            "B": "47230f4b711a8d9d36213e62e93ff507ac28258ba494fea0b569edc44495317f",
            "C": "08937da28a0d515dd72f6258d2515a3b2e2dd0055222fb9023994b7d184028c5",
            "D": [
                "47230f4b711a8d9d36213e62e93ff507ac28258ba494fea0b569edc44495317f",
                SSE_BEST,
            ],
        },
    }
    for cap, want in expected.items():
        rows = cap_universes[cap]
        assert len(rows) == want["count"]
        assert u7.unique_minimum(rows, "sse")["fingerprint"] == want["A"]
        assert u7.unique_minimum(rows, "te")["fingerprint"] == want["B"]
        assert u7.unique_minimum(rows, "continuous_exposure")["fingerprint"] == want["C"]
        assert [row["fingerprint"] for row in u7.pareto_frontier(rows)] == want["D"]


def test_canonical_83_reconstruction_matches_every_saved_review_metric(
    authorities: dict[str, object],
    cap_universes: dict[str, tuple[dict[str, object], ...]],
) -> None:
    saved = {row["fingerprint"]: row for row in authorities["u6_review"]["candidate_rankings"]}
    reconstructed = {row["fingerprint"]: row for row in cap_universes["32"]}

    assert reconstructed.keys() == saved.keys()
    for fingerprint, row in reconstructed.items():
        assert row["sse"] == pytest.approx(saved[fingerprint]["sse"], abs=1e-12)
        assert row["te"] == pytest.approx(saved[fingerprint]["te"], abs=1e-12)
        assert row["continuous_exposure"] == pytest.approx(
            saved[fingerprint]["continuous_exposure"], abs=1e-12
        )


def test_source_batch_reconstruction_has_exact_switch_and_frontier_history(
    authorities: dict[str, object],
) -> None:
    batches = u7.reconstruct_route10_source_batch_universes(authorities)

    assert [len(batch["candidates"]) for batch in batches] == [7, 23, 35, 55, 60, 66, 83]
    assert [u7.unique_minimum(batch["candidates"], "sse")["fingerprint"] for batch in batches] == [
        SSE_BEST
    ] * 7
    assert [u7.unique_minimum(batch["candidates"], "te")["fingerprint"] for batch in batches] == [
        SSE_BEST,
        "f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f",
        "f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f",
        "f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f",
        "f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f",
        TE_BEST,
        TE_BEST,
    ]
    assert [
        u7.unique_minimum(batch["candidates"], "continuous_exposure")["fingerprint"]
        for batch in batches
    ] == [
        SSE_BEST,
        SSE_BEST,
        SSE_BEST,
        SSE_BEST,
        CONTINUOUS_BEST,
        CONTINUOUS_BEST,
        CONTINUOUS_BEST,
    ]
    assert [len(u7.pareto_frontier(batch["candidates"])) for batch in batches] == [
        1,
        2,
        2,
        2,
        2,
        2,
        2,
    ]


def test_historical_route6_snapshot_only_authorities_are_preserved(
    authorities: dict[str, object],
) -> None:
    rows = u7.reconstruct_historical_route6_universe(authorities)

    assert len(rows) == 41
    assert u7.unique_minimum(rows, "sse")["fingerprint"] == ROUTE6_COMMON
    assert u7.unique_minimum(rows, "te")["fingerprint"] == ROUTE6_COMMON
    assert u7.unique_minimum(rows, "continuous_exposure")["fingerprint"] == ROUTE6_COMMON
    assert [row["fingerprint"] for row in u7.pareto_frontier(rows)] == [ROUTE6_COMMON]


def test_evidence_contains_special_table_criterion_matrix_and_no_hidden_blend(
    evidence: dict[str, object],
) -> None:
    route10 = evidence["route_10"]
    special = {row["fingerprint"]: row for row in route10["special_candidate_table"]}
    assert special.keys() == {SSE_BEST, TE_BEST, CONTINUOUS_BEST}
    assert special[SSE_BEST]["in_D_frontier"] is True
    assert special[TE_BEST]["in_D_frontier"] is True
    assert special[CONTINUOUS_BEST]["in_D_frontier"] is False
    assert special[CONTINUOUS_BEST]["continuous_rank"] == 1
    assert special[CONTINUOUS_BEST]["fleet"] == 13
    assert special[CONTINUOUS_BEST]["rhythm_tuple"] == [9, 9, 6, 0]
    assert set(evidence["criterion_matrix"]) == {"A", "B", "C", "D"}
    assert all(
        set(row) == {f"C{index}" for index in range(1, 10)}
        for row in evidence["criterion_matrix"].values()
    )
    assert evidence["policies"]["D"]["dimensions"] == ["sse", "te"]
    assert evidence["policies"]["D"]["weights_added"] is False
    assert evidence["policies"]["D"]["continuous_is_primary_dimension"] is False


def test_protected_production_and_all_tracked_xlsx_hashes_are_unchanged(
    evidence: dict[str, object],
) -> None:
    locks = evidence["protected_artifact_hashes"]
    assert locks
    assert all(row["before_sha256"] == row["after_sha256"] for row in locks.values())
    assert all(row["unchanged"] is True for row in locks.values())
    assert {
        path
        for path, row in locks.items()
        if row["baseline_classification"] == "CONTROLLED_CRLF_WORKTREE_BASELINE"
    } == set(u7.CONTROLLED_CRLF_WORKTREE_SHA256)
    assert all(row["u7_start_worktree_sha256"] == row["before_sha256"] for row in locks.values())
    xlsx = {path: row for path, row in locks.items() if path.endswith(".xlsx")}
    assert set(xlsx) == {
        "Schedule template.xlsx",
        "outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx",
        "outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx",
        "outputs/final_pilot/archive/pr62_g/Route_10_Final_Pilot_Timetable.xlsx",
        "outputs/final_pilot/archive/pr62_g/Route_6_Final_Pilot_Timetable.xlsx",
    }


def test_review_module_builds_under_a_production_import_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "bus_schedule_engine" or name.startswith("bus_schedule_engine."):
            raise RuntimeError("PRODUCTION_IMPORT_PROHIBITED")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    spec = importlib.util.spec_from_file_location(
        "u7_under_production_import_blocker",
        ROOT / "scripts" / "run_pr62_u7_demand_fit_authority_rehearsal.py",
    )
    assert spec is not None and spec.loader is not None
    isolated_u7 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolated_u7)
    isolated_evidence = isolated_u7.build_evidence(ROOT)

    assert isolated_evidence["invariants"]["Route 6 global executions"] == 0


def test_review_source_has_no_production_or_process_execution_imports() -> None:
    source_path = ROOT / "scripts" / "run_pr62_u7_demand_fit_authority_rehearsal.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])

    assert imported_roots.isdisjoint({"bus_schedule_engine", "subprocess", "runpy"})
    assert "service_plan_coordinator" not in source


def test_rendering_is_deterministic_compact_and_write_once(
    evidence: dict[str, object], tmp_path: Path
) -> None:
    first_json = u7.canonical_json_bytes(evidence)
    second_json = u7.canonical_json_bytes(evidence)
    first_markdown = u7.render_markdown(evidence).encode("utf-8")
    second_markdown = u7.render_markdown(evidence).encode("utf-8")

    assert first_json == second_json
    assert first_markdown == second_markdown
    assert len(first_json) < 1_000_000
    assert len(first_json) < 5 * 1024 * 1024
    paths = u7.write_artifacts(evidence, tmp_path)
    assert paths["json"].read_bytes() == first_json
    assert paths["markdown"].read_bytes() == first_markdown
    with pytest.raises(FileExistsError):
        u7.write_artifacts(evidence, tmp_path)


def test_markdown_surfaces_growth_boundedness_edges_and_lineage(
    evidence: dict[str, object],
) -> None:
    markdown = u7.render_markdown(evidence)

    assert "Scalar growth summary" in markdown
    assert "D boundedness audit" in markdown
    assert "D cap-set overlaps" in markdown
    assert "Exact bucket-edge comparison summary" in markdown
    assert "Lineage" in markdown


def test_committed_artifacts_are_exact_deterministic_renders(
    evidence: dict[str, object],
) -> None:
    output_dir = ROOT / "docs" / "engine" / "evidence"
    json_path = output_dir / u7.OUTPUT_JSON
    markdown_path = output_dir / u7.OUTPUT_MARKDOWN

    assert json_path.read_bytes() == u7.canonical_json_bytes(evidence)
    assert markdown_path.read_text(encoding="utf-8") == u7.render_markdown(evidence)
    assert json_path.stat().st_size < 1_000_000
    assert json_path.stat().st_size < 5 * 1024 * 1024


def test_final_policy_classifications_and_invariants_are_explicit(
    evidence: dict[str, object],
) -> None:
    assert evidence["policy_classifications"] == {
        "A": "SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT",
        "B": "SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT",
        "C": "SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT",
        "D": "SUPPORTED_WITH_UNRESOLVED_POLICY_QUESTION",
    }
    assert evidence["primary_classification"] == "MULTIPLE_DEMAND_FIT_AUTHORITIES_REMAIN_PLAUSIBLE"
    assert evidence["next_decision"]["count"] == 1
    assert evidence["invariants"] == {
        "production selector changed": False,
        "U6 changed": False,
        "Route 10 production timetable selected": False,
        "Route 6 global executions": 0,
        "final pilot workbooks changed": False,
        "PR #62 modified": False,
    }

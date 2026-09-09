from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_pr62_u6_v3_anchor_conflict_review as review  # noqa: E402


def buckets_from_shares(shares: list[float]) -> tuple[SimpleNamespace, ...]:
    return tuple(
        SimpleNamespace(start=index * 1_000, end=(index + 1) * 1_000, observed_demand=share)
        for index, share in enumerate(shares)
    )


def departures_from_counts(counts: list[int]) -> list[int]:
    return [
        index * 1_000 + offset + 1 for index, count in enumerate(counts) for offset in range(count)
    ]


def test_independent_metrics_demonstrate_l2_l1_ranking_reversal():
    buckets = buckets_from_shares([0.14, 0.14, 0.18, 0.18, 0.18, 0.18])
    spread = review.demand_bucket_rows(departures_from_counts([10, 10, 8, 8, 7, 7]), buckets)
    concentrated = review.demand_bucket_rows(departures_from_counts([12, 2, 9, 9, 9, 9]), buckets)

    assert spread["sse"] < concentrated["sse"]
    assert spread["te"] > concentrated["te"]
    assert spread["l1_residual"] > concentrated["l1_residual"]


def test_rank_is_epsilon_tie_safe():
    assert review.rank(1.0, [1.0, 1.0 + review.NUMERICAL_EPSILON / 2, 2.0]) == 1
    assert review.rank(2.0, [1.0, 1.0 + review.NUMERICAL_EPSILON / 2, 2.0]) == 3


def test_half_open_boundary_assignment_and_exposure_overlap():
    buckets = buckets_from_shares([0.5, 0.5])

    assert review.bucket_index(999, buckets) == 0
    assert review.bucket_index(1_000, buckets) == 1
    assert review.exposure_units_by_bucket([500, 1_500], buckets) == pytest.approx([0.5, 0.5])


def test_write_once_fails_closed_on_existing_artifact(tmp_path: Path):
    target = tmp_path / "evidence.json"
    review.write_once(target, b"first")

    with pytest.raises(FileExistsError):
        review.write_once(target, b"replacement")
    assert target.read_bytes() == b"first"


def test_load_authorities_rejects_wrong_canonical_bytes_before_deserialization(
    tmp_path: Path,
):
    evidence = tmp_path / review.EVIDENCE_NAME
    evidence.write_text("{}", encoding="utf-8")
    saved = tmp_path / "route10.pickle"
    saved.write_bytes(b"not a pickle")

    with pytest.raises(review.ReviewError, match="U6_EVIDENCE_BYTE_HASH_MISMATCH"):
        review.load_authorities(
            repo_root=ROOT,
            evidence_path=evidence,
            saved_base_path=saved,
        )

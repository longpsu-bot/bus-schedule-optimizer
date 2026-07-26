from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest
from route_corpus_support import (
    CORPUS_DIR,
    FIXTURE_FILES,
    fact_fingerprint,
    imported_workbook_from_fixture,
    load_corpus_fixture,
    load_manifest,
    normalization_options_from_fixture,
    normalized_bundle_from_fixture,
    proxy_demand_blocks,
    raw_trip_observations,
    render_sanitized_xlsx,
)

from bus_schedule_engine import (
    OptimizationAction,
    SolverChoice,
    analyze_and_optimize_schedule_v1,
)
from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.contracts_v1 import (
    BDisposition,
    DemandConfidence,
    ScenarioBEvaluationPolicyV1,
    SolverPolicyV1,
    build_heuristic_schedule_request_v1,
    build_ortools_service_quality_request_v1,
    evaluate_scenario_b_v1,
)
from bus_schedule_engine.importer import import_workbook

EXPECTED = {
    "corpus_alpha_80.json": {
        "a": (52, 26),
        "b": (80, 40),
        "runtime": (55, 65),
        "raw": 52,
        "overlaps": (50, 20, 40),
    },
    "corpus_beta_46.json": {
        "a": (26, 13),
        "b": (46, 23),
        "runtime": (100, 100),
        "raw": 26,
        "overlaps": (24, 10, 55),
    },
}
HISTORICAL_SHEETS = {
    "DANH_GIA_TOI_UU",
    "PHAN_BO_THEO_GIO",
    "BIEU_DO_TOI_UU",
}


def _private_root() -> Path | None:
    raw = os.environ.get("BUS_SCHEDULE_PRIVATE_CORPUS_DIR")
    return Path(raw).resolve() if raw else None


def _minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_json_is_structural_and_byte_deterministic(filename: str) -> None:
    path = CORPUS_DIR / filename
    fixture = load_corpus_fixture(filename)

    assert path.read_bytes() == _canonical_bytes(fixture)
    assert fixture["corpus_version"] == "1"
    assert fixture["fixture_id"] == fixture["scenario_a"]["parameters"]["route_id"]
    assert fixture["fixture_id"] == fixture["scenario_b"]["parameters"]["route_id"]
    assert set(fixture["demand_observations"]) == {
        "raw_trip_observations",
        "departure_hour_proxy_v1",
    }
    assert (
        fixture["demand_observations"]["raw_trip_observations"][
            "contract_v1_demand_interval_eligible"
        ]
        is False
    )
    assert (
        fixture["demand_observations"]["departure_hour_proxy_v1"][
            "contract_v1_demand_interval_eligible"
        ]
        is True
    )


def test_manifest_hashes_classifications_and_proxy_policy() -> None:
    manifest = load_manifest()

    assert manifest["corpus_version"] == "1"
    assert "generated_timestamp" not in manifest
    assert manifest["proxy_policy"] == "PROXY_SENSITIVITY_ONLY"
    assert manifest["historical_source_sheet_policy"] == ("HISTORICAL_NON_AUTHORITATIVE_REFERENCE")
    for entry in manifest["fixtures"]:
        assert re.fullmatch(r"[0-9a-f]{64}", entry["source_sha256"])
        assert all(
            fact["classification"] == "observed_source_fact"
            for fact in entry["observed_source_facts"]
        )
        assert all(
            item["classification"] == "derived_proxy_dataset"
            and item["status"] == "PROXY_SENSITIVITY_ONLY"
            for item in entry["derived_datasets"]
        )
        assert all(
            correction["classification"] == "exact_timetable_derived_correction"
            and correction["approved_for_corpus_construction"] is True
            for correction in entry["corrections"]
        )
        assert all(
            assumption["classification"] == "corpus_scenario_assumption"
            for assumption in entry["scenario_assumptions"]
        )


def test_committed_payload_has_no_absolute_path_or_private_route_identifier() -> None:
    text = "\n".join(
        (CORPUS_DIR / filename).read_text(encoding="utf-8")
        for filename in (*FIXTURE_FILES, "manifest.json")
    )

    assert not re.search(r"[A-Za-z]:[\\/]", text)
    assert "/Users/" not in text
    assert "\\Users\\" not in text
    assert "61-8" not in text
    assert "61-4" not in text
    assert "danh_gia_va_bieu_do" not in text.lower()


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_public_route_terminal_values_and_historical_exclusion(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    route_name = {
        "CORPUS-ALPHA-80": "Anonymized Route Alpha",
        "CORPUS-BETA-46": "Anonymized Route Beta",
    }[fixture["fixture_id"]]

    assert set(fixture["excluded_source_sheets"]) == HISTORICAL_SHEETS
    assert not HISTORICAL_SHEETS.intersection(fixture)
    for scenario in ("scenario_a", "scenario_b"):
        parameters = fixture[scenario]["parameters"]
        assert parameters["route_name"] == route_name
        assert parameters["terminal_1_name"] == "Terminal 1"
        assert parameters["terminal_2_name"] == "Terminal 2"


def test_private_names_are_redacted_when_sources_are_available() -> None:
    root = _private_root()
    if root is None:
        pytest.skip("private source directory is not configured")
    private_values: set[str] = set()
    for source_name in (
        "61-8_danh_gia_va_bieu_do_toi_uu.xlsx",
        "61-4_danh_gia_va_bieu_do_toi_uu.xlsx",
    ):
        imported = import_workbook(root / source_name)
        for parameters in (imported.parameters_a, imported.parameters_b):
            assert parameters is not None
            private_values.update(
                {
                    parameters.route_id,
                    parameters.route_name,
                    parameters.terminal_1_name,
                    parameters.terminal_2_name,
                }
            )
    corpus_text = "\n".join(
        (CORPUS_DIR / filename).read_text(encoding="utf-8")
        for filename in (*FIXTURE_FILES, "manifest.json")
    )
    assert all(value not in corpus_text for value in private_values)


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_exact_timetable_counts_endpoints_and_runtimes(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    expected = EXPECTED[filename]

    for scenario in ("a", "b"):
        trips = fixture[f"scenario_{scenario}"]["exact_trips"]
        parameters = fixture[f"scenario_{scenario}"]["parameters"]
        total, directional = expected[scenario]
        assert len(trips) == total
        assert parameters["total_daily_trips"] == total
        assert Counter(trip["direction"] for trip in trips) == {
            "terminal_1_to_2": directional,
            "terminal_2_to_1": directional,
        }
        for direction, terminal, first_field, last_field in (
            (
                "terminal_1_to_2",
                "Terminal 1",
                "terminal_1_first_departure",
                "terminal_1_last_departure",
            ),
            (
                "terminal_2_to_1",
                "Terminal 2",
                "terminal_2_first_departure",
                "terminal_2_last_departure",
            ),
        ):
            directional_trips = sorted(
                (trip for trip in trips if trip["direction"] == direction),
                key=lambda trip: (trip["departure_time"], trip["trip_id"]),
            )
            assert {trip["departure_terminal"] for trip in directional_trips} == {terminal}
            assert parameters[first_field] == directional_trips[0]["departure_time"]
            assert parameters[last_field] == directional_trips[-1]["departure_time"]
    runtimes = [trip["runtime_minutes"] for trip in fixture["scenario_b"]["exact_trips"]]
    assert (min(runtimes), max(runtimes)) == expected["runtime"]
    assert set(runtimes) == ({55, 60, 65} if filename.startswith("corpus_alpha") else {100})


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_raw_trip_observations_match_scenario_a_one_to_one(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    raw = raw_trip_observations(fixture)
    trips = {trip["trip_id"]: trip for trip in fixture["scenario_a"]["exact_trips"]}

    assert len(raw) == EXPECTED[filename]["raw"] == len(trips)
    assert {row["source_trip_id"] for row in raw} == set(trips)
    for row in raw:
        trip = trips[row["source_trip_id"]]
        assert row["direction"] == trip["direction"]
        assert row["raw_interval_start"] == trip["departure_time"]
        assert row["raw_interval_end"] == trip["arrival_time"]
        assert row["observation_days"] == 15
        assert row["volume_type"] == "total_observation_period"


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_raw_overlaps_are_preserved_and_documented(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    raw_dataset = fixture["demand_observations"]["raw_trip_observations"]
    overlaps: list[int] = []
    for direction in ("terminal_1_to_2", "terminal_2_to_1"):
        rows = sorted(
            (row for row in raw_dataset["rows"] if row["direction"] == direction),
            key=lambda row: (row["raw_interval_start"], row["source_trip_id"]),
        )
        for earlier, later in zip(rows, rows[1:], strict=False):
            overlap = _minutes(earlier["raw_interval_end"]) - _minutes(later["raw_interval_start"])
            if overlap > 0:
                overlaps.append(overlap)
    expected_count, expected_minimum, expected_maximum = EXPECTED[filename]["overlaps"]
    documentation = raw_dataset["overlap_documentation"]

    assert (len(overlaps), min(overlaps), max(overlaps)) == (
        expected_count,
        expected_minimum,
        expected_maximum,
    )
    assert documentation["overlaps_preserved"] is True
    assert documentation["adjacent_overlap_pair_count"] == expected_count
    assert documentation["minimum_overlap_minutes"] == expected_minimum
    assert documentation["maximum_overlap_minutes"] == expected_maximum


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_proxy_is_directional_contiguous_nonoverlapping_and_fully_provenanced(
    filename: str,
) -> None:
    fixture = load_corpus_fixture(filename)
    blocks = proxy_demand_blocks(fixture)
    raw_ids = {row["source_trip_id"] for row in raw_trip_observations(fixture)}
    proxy_ids: list[str] = []

    assert {block["direction"] for block in blocks} == {
        "terminal_1_to_2",
        "terminal_2_to_1",
    }
    for block in blocks:
        assert _minutes(block["time_block_end"]) - _minutes(block["time_block_start"]) >= 60
        assert block["source_trip_ids"]
        assert block["source_observation_count"] == len(block["source_trip_ids"])
        proxy_ids.extend(block["source_trip_ids"])
    for direction in ("terminal_1_to_2", "terminal_2_to_1"):
        directional = sorted(
            (block for block in blocks if block["direction"] == direction),
            key=lambda block: block["time_block_start"],
        )
        assert all(
            earlier["time_block_end"] == later["time_block_start"]
            for earlier, later in zip(directional, directional[1:], strict=False)
        )
    assert Counter(proxy_ids) == Counter(raw_ids)


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_proxy_conserves_directional_and_total_passenger_volumes(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    raw = raw_trip_observations(fixture)
    proxy = proxy_demand_blocks(fixture)

    raw_by_direction = {
        direction: sum(row["passenger_volume"] for row in raw if row["direction"] == direction)
        for direction in ("terminal_1_to_2", "terminal_2_to_1")
    }
    proxy_by_direction = {
        direction: sum(
            block["passenger_volume"] for block in proxy if block["direction"] == direction
        )
        for direction in ("terminal_1_to_2", "terminal_2_to_1")
    }
    assert proxy_by_direction == raw_by_direction
    assert sum(proxy_by_direction.values()) == sum(raw_by_direction.values())


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_proxy_fabricates_no_interior_empty_hour(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    trips = fixture["scenario_a"]["exact_trips"]
    proxy = proxy_demand_blocks(fixture)

    for direction in ("terminal_1_to_2", "terminal_2_to_1"):
        source_hours = {
            int(trip["departure_time"][:2]) for trip in trips if trip["direction"] == direction
        }
        proxy_hours = {
            int(block["time_block_start"][:2]) for block in proxy if block["direction"] == direction
        }
        assert proxy_hours == source_hours


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_raw_rows_are_never_supplied_to_contract_v1(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    imported = imported_workbook_from_fixture(fixture)
    proxy = proxy_demand_blocks(fixture)
    raw = raw_trip_observations(fixture)

    assert len(imported.demand) == len(proxy)
    assert (
        fixture["demand_observations"]["raw_trip_observations"][
            "contract_v1_demand_interval_eligible"
        ]
        is False
    )
    assert (
        fixture["demand_observations"]["departure_hour_proxy_v1"][
            "contract_v1_demand_interval_eligible"
        ]
        is True
    )
    assert {
        (
            row.block_start_seconds,
            row.block_end_seconds,
            row.direction.value,
            row.passenger_volume,
        )
        for row in imported.demand
    } == {
        (
            _minutes(block["time_block_start"]) * 60,
            _minutes(block["time_block_end"]) * 60,
            block["direction"],
            float(block["passenger_volume"]),
        )
        for block in proxy
    }
    for direction in ("terminal_1_to_2", "terminal_2_to_1"):
        directional = sorted(
            (row for row in imported.demand if row.direction.value == direction),
            key=lambda row: row.block_start_seconds,
        )
        assert all(
            earlier.block_end_seconds == later.block_start_seconds
            for earlier, later in zip(directional, directional[1:], strict=False)
        )
    assert any(
        _minutes(earlier["raw_interval_end"]) > _minutes(later["raw_interval_start"])
        for direction in ("terminal_1_to_2", "terminal_2_to_1")
        for earlier, later in zip(
            sorted(
                (row for row in raw if row["direction"] == direction),
                key=lambda row: row["raw_interval_start"],
            ),
            sorted(
                (row for row in raw if row["direction"] == direction),
                key=lambda row: row["raw_interval_start"],
            )[1:],
            strict=False,
        )
    )


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_capacity_turnaround_fleet_and_low_confidence_labels(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    manifest_entry = next(
        entry
        for entry in load_manifest()["fixtures"]
        if entry["fixture_id"] == fixture["fixture_id"]
    )

    for scenario in ("scenario_a", "scenario_b"):
        parameters = fixture[scenario]["parameters"]
        assert parameters["vehicle_capacity_passengers"] == 28
        assert parameters["minimum_layover_minutes"] >= 5
        assert parameters["route_type"] == "intra_provincial"
    assert fixture["normalization_options"]["demand_confidence"] == "LOW"
    assumptions = {item["field"]: item for item in manifest_entry["scenario_assumptions"]}
    assert assumptions["demand_confidence"]["value"] == "LOW"
    assert all(
        item["classification"] == "corpus_scenario_assumption" for item in assumptions.values()
    )


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_constructs_imported_workbook_and_normalizes(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    imported = imported_workbook_from_fixture(fixture)
    normalized = normalized_bundle_from_fixture(fixture)

    assert imported.parameters_a is not None
    assert normalized.scenario_a is not None
    assert normalized.scenario_b.total_daily_trips == EXPECTED[filename]["b"][0]
    assert normalized.observed_demand is not None
    assert normalized.observed_demand.observations
    assert {
        observation.demand_confidence for observation in normalized.observed_demand.observations
    } == {DemandConfidence.LOW}


@pytest.mark.parametrize("filename", FIXTURE_FILES)
@pytest.mark.parametrize("solver_choice", tuple(SolverChoice))
def test_natural_default_policy_characterization_attempts_no_solver(
    filename: str,
    solver_choice: SolverChoice,
) -> None:
    fixture = load_corpus_fixture(filename)
    result = analyze_and_optimize_schedule_v1(
        imported_workbook_from_fixture(fixture),
        normalization_options_from_fixture(fixture),
        solver_choice=solver_choice,
    )

    assert result.b_evaluation.evaluation.disposition == BDisposition.INSUFFICIENT_DATA
    assert result.selected_action == OptimizationAction.INSUFFICIENT_DATA
    assert result.solver_attempted is False
    assert result.heuristic_outcome is None
    assert result.ortools_outcome is None
    assert result.comparison is None


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_low_confidence_proxy_sensitivity_constructs_canonical_quality_requests(
    filename: str,
) -> None:
    fixture = load_corpus_fixture(filename)
    imported = imported_workbook_from_fixture(fixture)
    normalized = normalized_bundle_from_fixture(fixture)
    policy = ScenarioBEvaluationPolicyV1(
        minimum_authoritative_demand_confidence=DemandConfidence.LOW
    )
    evaluation = evaluate_scenario_b_v1(normalized, policy)
    heuristic_context, heuristic_solver = build_heuristic_schedule_request_v1(
        normalized,
        evaluation,
        imported.parameters_b,
        imported.trips_b,
        imported.demand,
        ScenarioCConfig.from_mapping(imported.configuration),
        evaluation_policy=policy,
    )
    quality_context, quality_solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        evaluation_policy=policy,
        solver_policy=SolverPolicyV1(
            time_limit_seconds=30,
            worker_count=1,
            random_seed=0,
        ),
    )

    assert heuristic_context.problem.solver_adapter == heuristic_solver.adapter_id
    assert quality_context.problem.solver_adapter == quality_solver.adapter_id
    assert (
        heuristic_context.problem.source_b_fingerprint
        == quality_context.problem.source_b_fingerprint
    )
    assert quality_context.problem.scenario_b.total_daily_trips == (EXPECTED[filename]["b"][0])


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_problem_and_input_fingerprints_are_deterministic(filename: str) -> None:
    first_fixture = load_corpus_fixture(filename)
    second_fixture = load_corpus_fixture(filename)
    first = normalized_bundle_from_fixture(first_fixture)
    second = normalized_bundle_from_fixture(second_fixture)
    policy = ScenarioBEvaluationPolicyV1(
        minimum_authoritative_demand_confidence=DemandConfidence.LOW
    )
    first_evaluation = evaluate_scenario_b_v1(first, policy)
    second_evaluation = evaluate_scenario_b_v1(second, policy)
    first_context, _ = build_ortools_service_quality_request_v1(
        first,
        first_evaluation,
        evaluation_policy=policy,
    )
    second_context, _ = build_ortools_service_quality_request_v1(
        second,
        second_evaluation,
        evaluation_policy=policy,
    )

    assert fact_fingerprint(first_fixture) == fact_fingerprint(second_fixture)
    assert first.scenario_a_fingerprint == second.scenario_a_fingerprint
    assert first.scenario_b_fingerprint == second.scenario_b_fingerprint
    assert first.observed_demand_fingerprint == second.observed_demand_fingerprint
    assert first_context.problem.problem_fingerprint == second_context.problem.problem_fingerprint


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_temporary_sanitized_xlsx_imports_identical_timetable_and_proxy(
    filename: str,
    tmp_path: Path,
) -> None:
    fixture = load_corpus_fixture(filename)
    direct = imported_workbook_from_fixture(fixture)
    workbook_path = render_sanitized_xlsx(
        fixture,
        tmp_path / filename.replace(".json", ".xlsx"),
    )
    rendered = import_workbook(workbook_path)

    assert rendered.parameters_a == direct.parameters_a
    assert rendered.parameters_b == direct.parameters_b
    assert rendered.trips_a == direct.trips_a
    assert rendered.trips_b == direct.trips_b
    assert rendered.demand == direct.demand


def test_private_source_values_match_raw_evidence_when_available() -> None:
    root = _private_root()
    if root is None:
        pytest.skip("private source directory is not configured")
    for filename, source_name in (
        ("corpus_alpha_80.json", "61-8_danh_gia_va_bieu_do_toi_uu.xlsx"),
        ("corpus_beta_46.json", "61-4_danh_gia_va_bieu_do_toi_uu.xlsx"),
    ):
        fixture = load_corpus_fixture(filename)
        source = import_workbook(root / source_name)
        extracted = sorted(
            (
                trip.trip_id,
                record.direction.value,
                (record.period_start + timedelta(days=-365)).isoformat(),
                (record.period_end + timedelta(days=-365)).isoformat(),
                record.block_start_seconds,
                record.block_end_seconds,
                record.passenger_volume,
            )
            for record in source.demand
            for trip in source.trips_a
            if (
                trip.direction == record.direction
                and trip.departure_seconds == record.block_start_seconds
                and trip.arrival_seconds == record.block_end_seconds
            )
        )
        committed = sorted(
            (
                row["source_trip_id"],
                row["direction"],
                row["period_start"],
                row["period_end"],
                _minutes(row["raw_interval_start"]) * 60,
                _minutes(row["raw_interval_end"]) * 60,
                float(row["passenger_volume"]),
            )
            for row in raw_trip_observations(fixture)
        )
        assert committed == extracted


def test_private_builder_verify_is_byte_identical() -> None:
    if _private_root() is None:
        pytest.skip("private source directory is not configured")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "tools" / "build_route_corpus_v1.py"),
            "--verify",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    assert "Verified deterministic route corpus v1 JSON." in result.stdout


def test_private_originals_are_external_and_untracked() -> None:
    root = _private_root()
    if root is None:
        pytest.skip("private source directory is not configured")
    repository = Path(__file__).parents[1].resolve()
    approved_names = {
        "61-8_danh_gia_va_bieu_do_toi_uu.xlsx",
        "61-4_danh_gia_va_bieu_do_toi_uu.xlsx",
    }
    assert not root.is_relative_to(repository)
    assert {path.name for path in root.iterdir()} == approved_names
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert approved_names.isdisjoint(Path(item).name for item in tracked)


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_proxy_sensitivity_is_never_operationally_approved(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    proxy = fixture["demand_observations"]["departure_hour_proxy_v1"]
    serialized = json.dumps(proxy, ensure_ascii=False).lower()

    assert "sensitivity evidence only" in serialized
    assert "operational" in serialized
    assert "approved" in serialized
    assert "operationally_approved" not in proxy

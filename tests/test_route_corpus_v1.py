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
from bus_schedule_engine.contracts_v1 import (
    BDisposition,
    DemandConfidence,
    ScenarioBEvaluationPolicyV1,
    ScheduleProblemError,
    build_ortools_service_quality_request_v1,
    evaluate_scenario_b_v1,
)
from bus_schedule_engine.importer import import_workbook
from tools import characterize_route_corpus_v1 as characterizer

EXPECTED = {
    "corpus_alpha_80.json": {
        "a": (52, 26),
        "b": (80, 40),
        "runtime": (55, 65),
        "raw": 52,
        "overlaps": (50, 20, 40),
        "coverage": "COMPLETE",
        "eligible": True,
        "coverage_issues": (),
        "boundaries": {
            "terminal_1_to_2": ("04:30", "18:31"),
            "terminal_2_to_1": ("05:35", "20:01"),
        },
    },
    "corpus_beta_46.json": {
        "a": (26, 13),
        "b": (46, 23),
        "runtime": (100, 100),
        "raw": 26,
        "overlaps": (24, 10, 55),
        "coverage": "PROXY_COVERAGE_INCOMPLETE",
        "eligible": False,
        "coverage_issues": (
            (
                "PROXY_INTERIOR_HOUR_UNOBSERVED",
                "terminal_1_to_2",
                "17:00",
                "18:00",
                ("16:00", "18:00"),
            ),
        ),
        "boundaries": {
            "terminal_1_to_2": ("05:30", "18:26"),
            "terminal_2_to_1": ("05:00", "18:11"),
        },
    },
}
HISTORICAL_SHEETS = {
    "DANH_GIA_TOI_UU",
    "PHAN_BO_THEO_GIO",
    "BIEU_DO_TOI_UU",
}
REPORT_PATH = (
    Path(__file__).parents[1] / "docs" / "engine" / "ROUTE_CORPUS_CHARACTERIZATION_DRAFT_V1.md"
)


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
    proxy = fixture["demand_observations"]["departure_hour_proxy_v1"]
    assert proxy["proxy_status"] == "PROXY_SENSITIVITY_ONLY"
    assert proxy["coverage_status"] == EXPECTED[filename]["coverage"]
    assert proxy["contract_v1_demand_interval_eligible"] is EXPECTED[filename]["eligible"]


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
        for item in entry["derived_datasets"]:
            expected = next(
                value
                for filename, value in EXPECTED.items()
                if load_corpus_fixture(filename)["fixture_id"] == entry["fixture_id"]
            )
            assert item["classification"] == "derived_proxy_dataset"
            assert item["status"] == "PROXY_SENSITIVITY_ONLY"
            assert item["coverage_status"] == expected["coverage"]
            assert item["contract_v1_demand_interval_eligible"] is expected["eligible"]
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
def test_proxy_blocks_use_exact_hour_and_service_endpoint_boundaries(
    filename: str,
) -> None:
    fixture = load_corpus_fixture(filename)
    blocks = proxy_demand_blocks(fixture)
    raw_by_trip_id = {row["source_trip_id"]: row for row in raw_trip_observations(fixture)}
    raw_ids = set(raw_by_trip_id)
    proxy_ids: list[str] = []

    assert {block["direction"] for block in blocks} == {
        "terminal_1_to_2",
        "terminal_2_to_1",
    }
    for direction in ("terminal_1_to_2", "terminal_2_to_1"):
        directional = sorted(
            (block for block in blocks if block["direction"] == direction),
            key=lambda block: block["time_block_start"],
        )
        scenario_b_departures = [
            _minutes(trip["departure_time"])
            for trip in fixture["scenario_b"]["exact_trips"]
            if trip["direction"] == direction
        ]
        first_b = min(scenario_b_departures)
        last_b = max(scenario_b_departures)
        first = directional[0]
        final = directional[-1]

        assert _minutes(first["time_block_start"]) == max(
            _minutes(first["observed_departure_hour_start"]),
            first_b,
        )
        assert _minutes(final["time_block_end"]) == last_b + 1
        assert (
            first["time_block_start"],
            final["time_block_end"],
        ) == EXPECTED[filename]["boundaries"][direction]
        for block in directional:
            start = _minutes(block["time_block_start"])
            end = _minutes(block["time_block_end"])
            observed_hour = _minutes(block["observed_departure_hour_start"])
            assert block["source_trip_ids"]
            assert block["source_observation_count"] == len(block["source_trip_ids"])
            assert block["passenger_volume"] > 0
            assert block["passenger_volume"] == sum(
                raw_by_trip_id[trip_id]["passenger_volume"] for trip_id in block["source_trip_ids"]
            )
            assert block["duration_minutes"] == end - start
            assert block["volume_type"] == "total_observation_period"
            assert block["source_volume_type"] == "total_observation_period"
            assert block["observation_days"] == 15
            if block["boundary_role"] == "ordinary":
                assert start == observed_hour
                assert end == observed_hour + 60
                assert end - start == 60
            elif block["boundary_role"] == "first":
                assert end == observed_hour + 60
                assert end - start <= 60
            else:
                assert block["boundary_role"] == "final"
                assert start == observed_hour
                assert end == last_b + 1
            proxy_ids.extend(block["source_trip_ids"])
        assert all(
            _minutes(earlier["time_block_end"]) <= _minutes(later["time_block_start"])
            for earlier, later in zip(directional, directional[1:], strict=False)
        )
        assert all(
            _minutes(block["time_block_end"])
            == _minutes(block["observed_departure_hour_start"]) + 60
            for block in directional[:-1]
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
def test_contract_normalizes_proxy_total_by_exact_observation_days(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    imported = imported_workbook_from_fixture(fixture)
    normalized = normalized_bundle_from_fixture(fixture)
    assert normalized.observed_demand is not None
    assert normalized.observed_demand.observation_days == 15

    for source, observation in zip(
        imported.demand,
        normalized.observed_demand.observations,
        strict=True,
    ):
        assert source.volume_type.value == "total_observation_period"
        assert observation.volume_classification.value == "total_observation_period"
        assert observation.passenger_count == source.passenger_volume
        daily = observation.average_daily_passenger_count(
            normalized.observed_demand.observation_days
        )
        assert daily == pytest.approx(source.passenger_volume / 15)
        assert daily != pytest.approx(source.passenger_volume * 15)


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_proxy_coverage_issues_preserve_unobserved_interior_gaps(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    trips = fixture["scenario_a"]["exact_trips"]
    proxy_dataset = fixture["demand_observations"]["departure_hour_proxy_v1"]
    proxy = proxy_dataset["blocks"]

    for direction in ("terminal_1_to_2", "terminal_2_to_1"):
        source_hours = {
            int(trip["departure_time"][:2]) for trip in trips if trip["direction"] == direction
        }
        proxy_hours = {
            int(block["observed_departure_hour_start"][:2])
            for block in proxy
            if block["direction"] == direction
        }
        assert proxy_hours == source_hours
    issues = tuple(
        (
            issue["code"],
            issue["direction"],
            issue["interval_start"],
            issue["interval_end"],
            tuple(issue["surrounding_observed_hours"]),
        )
        for issue in proxy_dataset["coverage_issues"]
    )
    assert issues == EXPECTED[filename]["coverage_issues"]
    assert proxy_dataset["coverage_status"] == EXPECTED[filename]["coverage"]
    assert proxy_dataset["contract_v1_demand_interval_eligible"] is EXPECTED[filename]["eligible"]
    for issue in proxy_dataset["coverage_issues"]:
        issue_start = _minutes(issue["interval_start"])
        issue_end = _minutes(issue["interval_end"])
        assert not any(
            _minutes(block["time_block_start"]) < issue_end
            and _minutes(block["time_block_end"]) > issue_start
            for block in proxy
            if block["direction"] == issue["direction"]
        )
        assert not any(
            block["passenger_volume"] == 0
            and block["time_block_start"] == issue["interval_start"]
            and block["time_block_end"] == issue["interval_end"]
            for block in proxy
        )


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
        is EXPECTED[filename]["eligible"]
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
    assert {row.volume_type.value for row in imported.demand} == {"total_observation_period"}
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


def test_complete_proxy_precision_rejection_prevents_both_solver_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args, **kwargs):
        raise AssertionError("No solver or heuristic request may run without a quality problem")

    monkeypatch.setattr(characterizer, "build_heuristic_schedule_request_v1", unexpected)
    monkeypatch.setattr(characterizer, "run_schedule_solver_v1", unexpected)
    summary, benchmark_rows = characterizer.characterize_fixture("corpus_alpha_80.json")
    diagnostic = summary["proxy_sensitivity_only"]

    assert diagnostic["coverage_status"] == "COMPLETE"
    assert diagnostic["diagnostic_status"] == "NOT_RUN"
    assert diagnostic["reason_code"] == ("QUALITY_REQUEST_UNREPRESENTABLE_DEMAND_PRECISION")
    assert diagnostic["quality_request"]["attempted"] is True
    assert diagnostic["quality_request"]["constructed"] is False
    assert diagnostic["quality_request"]["builder_error_code"] == (
        "ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY"
    )
    assert (
        "ORTOOLS_QUALITY_DEMAND_PRECISION_UNSUPPORTED"
        in (diagnostic["quality_request"]["builder_error_codes"])
    )
    assert diagnostic["heuristic_outcome"] is None
    assert diagnostic["ortools_outcome"] is None
    assert diagnostic["comparison"] is None
    assert diagnostic["recommendation"] is None
    assert benchmark_rows == []


def test_incomplete_proxy_prevents_quality_construction_and_solver_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args, **kwargs):
        raise AssertionError("Incomplete proxy must stop before request construction")

    monkeypatch.setattr(
        characterizer,
        "build_ortools_service_quality_request_v1",
        unexpected,
    )
    monkeypatch.setattr(characterizer, "build_heuristic_schedule_request_v1", unexpected)
    monkeypatch.setattr(characterizer, "run_schedule_solver_v1", unexpected)
    summary, benchmark_rows = characterizer.characterize_fixture("corpus_beta_46.json")
    diagnostic = summary["proxy_sensitivity_only"]

    assert diagnostic["coverage_status"] == "PROXY_COVERAGE_INCOMPLETE"
    assert diagnostic["diagnostic_status"] == "NOT_RUN"
    assert diagnostic["reason_code"] == "PROXY_COVERAGE_INCOMPLETE"
    assert diagnostic["quality_request"]["attempted"] is False
    assert diagnostic["heuristic_outcome"] is None
    assert diagnostic["ortools_outcome"] is None
    assert diagnostic["comparison"] is None
    assert diagnostic["recommendation"] is None
    assert benchmark_rows == []


def test_canonical_quality_builder_exposes_exact_precision_error() -> None:
    normalized = normalized_bundle_from_fixture(load_corpus_fixture("corpus_alpha_80.json"))
    policy = ScenarioBEvaluationPolicyV1(
        minimum_authoritative_demand_confidence=DemandConfidence.LOW
    )
    evaluation = evaluate_scenario_b_v1(normalized, policy)

    with pytest.raises(ScheduleProblemError) as caught:
        build_ortools_service_quality_request_v1(
            normalized,
            evaluation,
            evaluation_policy=policy,
        )

    assert caught.value.code == "ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY"
    assert "ORTOOLS_QUALITY_DEMAND_PRECISION_UNSUPPORTED" in caught.value.codes


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_input_fingerprints_are_deterministic_without_quality_problem(filename: str) -> None:
    first_fixture = load_corpus_fixture(filename)
    second_fixture = load_corpus_fixture(filename)
    first = normalized_bundle_from_fixture(first_fixture)
    second = normalized_bundle_from_fixture(second_fixture)

    assert fact_fingerprint(first_fixture) == fact_fingerprint(second_fixture)
    assert first.scenario_a_fingerprint == second.scenario_a_fingerprint
    assert first.scenario_b_fingerprint == second.scenario_b_fingerprint
    assert first.observed_demand_fingerprint == second.observed_demand_fingerprint


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
    assert {row.volume_type.value for row in rendered.demand} == {"total_observation_period"}
    assert all(row.observation_days == 15 for row in rendered.demand)


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


def test_draft_report_discards_invalid_average_day_characterization() -> None:
    report = REPORT_PATH.read_text(encoding="utf-8")

    assert "HEURISTIC_VECTOR_BETTER" not in report
    assert "408,920" not in report
    assert "440,920" not in report
    assert "unscaled proxy weights" not in report
    assert "unscaled 15-day" not in report
    assert "TOTAL_OBSERVATION_PERIOD" in report
    assert "observation_days=15" in report


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_proxy_sensitivity_is_never_operationally_approved(filename: str) -> None:
    fixture = load_corpus_fixture(filename)
    proxy = fixture["demand_observations"]["departure_hour_proxy_v1"]
    serialized = json.dumps(proxy, ensure_ascii=False).lower()

    assert "sensitivity evidence only" in serialized
    assert "operational" in serialized
    assert "approved" in serialized
    assert "operationally_approved" not in proxy

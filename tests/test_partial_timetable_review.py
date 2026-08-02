from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import bus_schedule_engine.fleet as fleet_module
import bus_schedule_engine.optimization_service as optimization_module
from bus_schedule_engine.contracts_v1 import (
    DemandConfidence,
    DemandResponseMode,
    DemandSourceType,
    InputSourceType,
    normalize_imported_workbook_v1,
)
from bus_schedule_engine.contracts_v1.terminal_occupancy import (
    TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,
)
from bus_schedule_engine.data_authority_review import main as cli_main
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import ImportedWorkbook, WorkbookAuthorityMetadata
from bus_schedule_engine.input_authority import (
    DIRECTIONAL_DEMAND_REQUIRED_FOR_DIRECTIONAL_OPTIMIZATION,
    SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED,
    DataAuthorityCapabilityV1,
    normalization_options_from_workbook_v1,
)
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    RouteType,
    ScenarioParameters,
    TimetableAuthorityMetadataV1,
    TimetableAuthorityStatusV1,
    Trip,
    VolumeType,
)
from bus_schedule_engine.partial_timetable_review import (
    DATA_AUTHORITY_REVIEW_JSON_FILENAME,
    DATA_AUTHORITY_REVIEW_MARKDOWN_FILENAME,
    DECLARED_ENDPOINT_MISMATCH,
    DECLARED_TRIP_COUNT_MISMATCH,
    PARTIAL_REVIEW_PROFILE_V1,
    SOURCE_ASSIGNMENT_OVERLAP_DETECTED,
    SOURCE_ASSIGNMENT_OVERLAP_FREE,
    TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE,
    DataAuthorityReviewPackageV1,
    PartialTimetableReviewV1,
    TurnaroundComplianceStatusV1,
    build_partial_timetable_review_v1,
    create_data_authority_review_package_v1,
    render_partial_timetable_review_markdown_v1,
    serialize_partial_timetable_review_v1,
    verify_partial_timetable_review_fingerprint_v1,
    verify_partial_timetable_review_json_bytes_v1,
    write_data_authority_review_package_v1,
)
from bus_schedule_engine.protected_service_floor import (
    derive_current_b_service_regimes_v1,
    derive_exact_timetable_service_regimes_v1,
    protected_service_floor_policy_from_workbook_v1,
)


def _demand(direction: Direction) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 7),
        observation_days=7,
        block_start_seconds=5 * 3600,
        block_end_seconds=12 * 3600,
        direction=direction,
        passenger_volume=700,
        volume_type=VolumeType.TOTAL_OBSERVATION_PERIOD,
    )


def _authority(
    status: TimetableAuthorityStatusV1 = TimetableAuthorityStatusV1.APPROVED_OPERATIONAL,
) -> WorkbookAuthorityMetadata:
    return WorkbookAuthorityMetadata(
        timetable_authority=TimetableAuthorityMetadataV1(
            status=status,
            reference="AUTHORITY-61-4-SYNTHETIC",
            effective_date=date(2026, 8, 1),
        ),
        demand_dataset_id="SYNTHETIC-COMBINED",
        demand_source_type=DemandSourceType.MANUAL_COUNT,
        demand_confidence=DemandConfidence.MEDIUM,
        demand_response_mode=DemandResponseMode.CALIBRATED,
        source_notes="Synthetic fixture only.",
    )


def _synthetic_61_4_like(
    *,
    capacity: int | None = None,
    available_fleet: int | None = None,
    minimum_turnaround: int | None = 10,
    terminal_limits: tuple[int | None, int | None] = (None, None),
    demand: list[DemandRecord] | None = None,
    authority_status: TimetableAuthorityStatusV1 = (
        TimetableAuthorityStatusV1.APPROVED_OPERATIONAL
    ),
) -> ImportedWorkbook:
    trips: list[Trip] = []
    for vehicle_index in range(7):
        trip_count = 7 if vehicle_index < 4 else 6
        first_departure = 5 * 3600 + vehicle_index * 2 * 60
        for cycle_index in range(trip_count):
            departure = first_departure + cycle_index * 60 * 60
            outbound = (vehicle_index + cycle_index) % 2 == 0
            direction = Direction.TERMINAL_1_TO_2 if outbound else Direction.TERMINAL_2_TO_1
            trips.append(
                Trip(
                    scenario="B",
                    trip_id=f"B-{vehicle_index + 1:02d}-{cycle_index + 1:02d}",
                    departure_terminal="Terminal 1" if outbound else "Terminal 2",
                    direction=direction,
                    departure_seconds=departure,
                    arrival_seconds=departure + 50 * 60,
                    vehicle_id=f"BUS-{vehicle_index + 1:02d}",
                )
            )
    trips.sort(key=lambda trip: (trip.departure_seconds, trip.trip_id))
    outbound_departures = [
        trip.departure_seconds for trip in trips if trip.direction == Direction.TERMINAL_1_TO_2
    ]
    inbound_departures = [
        trip.departure_seconds for trip in trips if trip.direction == Direction.TERMINAL_2_TO_1
    ]
    parameters = ScenarioParameters(
        route_id="SYNTHETIC-61-4",
        route_name="Synthetic 61-4-like route",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=50,
        allowed_trip_runtime_minutes=(50,),
        total_daily_trips=46,
        terminal_1_name="Terminal 1",
        terminal_1_first_departure=min(outbound_departures),
        terminal_1_last_departure=max(outbound_departures),
        terminal_2_name="Terminal 2",
        terminal_2_first_departure=min(inbound_departures),
        terminal_2_last_departure=max(inbound_departures),
        vehicle_capacity_passengers=capacity,
        minimum_layover_minutes=minimum_turnaround,
        available_fleet_limit=available_fleet,
        approved_active_fleet=7,
        operating_day_type="weekday",
        terminal_1_max_occupancy_vehicles=terminal_limits[0],
        terminal_2_max_occupancy_vehicles=terminal_limits[1],
    )
    return ImportedWorkbook(
        parameters_a=None,
        trips_a=[],
        parameters_b=parameters,
        trips_b=trips,
        demand=list(demand) if demand is not None else [_demand(Direction.COMBINED)],
        configuration={},
        authority_metadata=_authority(authority_status),
    )


def _review(imported: ImportedWorkbook | None = None):
    return build_partial_timetable_review_v1(
        imported or _synthetic_61_4_like(),
        source_id="synthetic-authority-review",
    )


def test_61_4_like_review_has_46_trips_seven_overlap_free_cycles_and_ten_minute_gap() -> None:
    review = _review()

    assert PartialTimetableReviewV1.__dataclass_params__.frozen is True
    assert "__slots__" in PartialTimetableReviewV1.__dict__
    assert review.profile == PARTIAL_REVIEW_PROFILE_V1
    assert review.exact_timetable_consistency["exact_total_daily_trips"] == 46
    assert review.source_vehicle_cycle_review["supplied_vehicle_cycle_count"] == 7
    assert review.source_vehicle_cycle_review["assignment_status"] == (
        SOURCE_ASSIGNMENT_OVERLAP_FREE
    )
    assert review.source_vehicle_cycle_review["overlap_issues"] == ()
    assert review.source_vehicle_cycle_review["observed_minimum_inter_trip_gap_minutes"] == 10
    assert review.turnaround_review["compliance_status"] == (
        TurnaroundComplianceStatusV1.COMPLIANT.value
    )


def test_missing_turnaround_reports_gaps_and_overlaps_without_compliance() -> None:
    imported = _synthetic_61_4_like(minimum_turnaround=None)
    review = _review(imported)

    assert review.source_vehicle_cycle_review["observed_minimum_inter_trip_gap_minutes"] == 10
    assert review.source_vehicle_cycle_review["overlap_issues"] == ()
    assert review.turnaround_review["compliance_status"] == (
        TurnaroundComplianceStatusV1.NOT_EVALUATED.value
    )


def test_overlapping_source_cycle_is_detected() -> None:
    imported = _synthetic_61_4_like()
    trips = list(imported.trips_b)
    first_vehicle = sorted(
        (trip for trip in trips if trip.vehicle_id == "BUS-01"),
        key=lambda trip: trip.departure_seconds,
    )
    overlapping = replace(
        first_vehicle[1],
        departure_seconds=first_vehicle[0].arrival_seconds - 5 * 60,
        arrival_seconds=first_vehicle[0].arrival_seconds + 45 * 60,
    )
    trips[trips.index(first_vehicle[1])] = overlapping
    review = _review(replace(imported, trips_b=trips))

    assert review.source_vehicle_cycle_review["assignment_status"] == (
        SOURCE_ASSIGNMENT_OVERLAP_DETECTED
    )
    assert review.source_vehicle_cycle_review["overlap_issues"][0]["overlap_minutes"] == 5
    assert review.turnaround_review["compliance_status"] == (
        TurnaroundComplianceStatusV1.NON_COMPLIANT.value
    )


def test_absent_source_vehicle_ids_are_reported_without_fabrication() -> None:
    imported = _synthetic_61_4_like()
    imported = replace(
        imported,
        trips_b=[replace(trip, vehicle_id=None) for trip in imported.trips_b],
    )

    review = _review(imported)

    assert review.source_vehicle_cycle_review["assignment_status"] == (
        SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED
    )
    assert review.source_vehicle_cycle_review["supplied_vehicle_cycle_count"] == 0
    assert review.turnaround_review["compliance_status"] == (
        TurnaroundComplianceStatusV1.NOT_EVALUATED.value
    )
    assert review.optimization_eligibility["solver_called"] is False


def test_combined_demand_stays_combined_and_directional_demand_is_not_fabricated() -> None:
    review = _review(_synthetic_61_4_like(capacity=60))
    demand = review.demand_authority_review

    assert demand["record_counts_by_declared_direction"] == {"combined": 1}
    assert demand["combined_descriptive_review_available"] is True
    assert demand["directional_descriptive_review_available"] is False
    assert demand["directional_demand_fabricated"] is False
    assert (
        DIRECTIONAL_DEMAND_REQUIRED_FOR_DIRECTIONAL_OPTIMIZATION
        in review.missing_authority_codes_by_capability[
            DataAuthorityCapabilityV1.DEMAND_EVALUATION.value
        ]
    )
    assert b"passenger_volume" not in serialize_partial_timetable_review_v1(review)


def test_missing_terminal_limits_remain_not_evaluated() -> None:
    review = _review(_synthetic_61_4_like(terminal_limits=(None, None)))

    assert review.fleet_and_terminal_authority["terminal_capacity_status"] == "BLOCKED"
    assert review.fleet_and_terminal_authority["terminal_capacity_limitation_codes"] == (
        TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    )
    assert review.fleet_and_terminal_authority["fleet_or_terminal_limits_inferred"] is False


@pytest.mark.parametrize(
    ("status", "approved"),
    [
        (TimetableAuthorityStatusV1.APPROVED_OPERATIONAL, True),
        (TimetableAuthorityStatusV1.PROPOSED, False),
        (TimetableAuthorityStatusV1.UNKNOWN, False),
    ],
)
def test_timetable_authority_is_preserved_and_never_promoted(
    status: TimetableAuthorityStatusV1,
    approved: bool,
) -> None:
    review = _review(_synthetic_61_4_like(authority_status=status))

    assert review.timetable_authority == {
        "status": status.value,
        "reference": "AUTHORITY-61-4-SYNTHETIC",
        "effective_date": "2026-08-01",
        "source_approved": approved,
    }


def test_declared_count_mismatch_is_reported() -> None:
    imported = _synthetic_61_4_like()
    imported = replace(
        imported,
        parameters_b=replace(imported.parameters_b, total_daily_trips=45),
    )

    review = _review(imported)

    assert DECLARED_TRIP_COUNT_MISMATCH in review.exact_timetable_consistency["issue_codes"]


def test_declared_endpoint_mismatch_is_reported() -> None:
    imported = _synthetic_61_4_like()
    imported = replace(
        imported,
        parameters_b=replace(
            imported.parameters_b,
            terminal_1_first_departure=(imported.parameters_b.terminal_1_first_departure + 60),
        ),
    )

    review = _review(imported)

    assert DECLARED_ENDPOINT_MISMATCH in review.exact_timetable_consistency["issue_codes"]
    assert (
        review.exact_timetable_consistency["declared_versus_exact_service_windows"]["terminal_1"][
            "matches"
        ]
        is False
    )


def test_runtime_outside_supplied_authority_is_reported() -> None:
    imported = _synthetic_61_4_like()
    trips = list(imported.trips_b)
    trips[0] = replace(
        trips[0],
        arrival_seconds=trips[0].departure_seconds + 70 * 60,
    )

    review = _review(replace(imported, trips_b=trips))

    violations = review.runtime_review["runtime_violations"]
    assert violations[0]["code"] == TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE
    assert violations[0]["runtime_minutes"] == 70


def test_review_reuses_canonical_exact_timetable_regime_derivation() -> None:
    imported = _synthetic_61_4_like(
        capacity=60,
        available_fleet=8,
        terminal_limits=(4, 4),
        demand=[],
    )
    options = normalization_options_from_workbook_v1(
        imported,
        source_id="canonical-regime-check",
        imported_at=datetime(2026, 8, 2, tzinfo=UTC),
        source_type=InputSourceType.XLSX,
    )
    scenario_b = normalize_imported_workbook_v1(imported, options).scenario_b
    policy = protected_service_floor_policy_from_workbook_v1(imported)

    assert derive_exact_timetable_service_regimes_v1(
        scenario_b.exact_timetable,
        policy,
    ) == derive_current_b_service_regimes_v1(scenario_b, policy)
    assert _review(imported).headway_and_regime_review["canonical_regime_derivation_reused"] is True


def test_review_never_calls_solver_or_fleet_assignment(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("solver or fleet assignment was called")

    monkeypatch.setattr(optimization_module, "analyze_and_optimize_schedule_v1", forbidden)
    monkeypatch.setattr(fleet_module, "assign_fleet", forbidden)

    review = _review()

    assert review.optimization_eligibility["solver_called"] is False


def test_deterministic_fingerprint_markdown_sections_and_tamper_detection() -> None:
    first = _review()
    second = _review()
    content = serialize_partial_timetable_review_v1(first)
    markdown = render_partial_timetable_review_markdown_v1(first).decode("utf-8")

    assert first == second
    assert verify_partial_timetable_review_fingerprint_v1(first) is True
    assert verify_partial_timetable_review_json_bytes_v1(content) is True
    assert len([line for line in markdown.splitlines() if line.startswith("## ")]) == 14
    assert "does not grant or revoke" in markdown
    assert "not a technical rejection" in markdown
    assert (
        verify_partial_timetable_review_fingerprint_v1(replace(first, source_id="tampered"))
        is False
    )
    payload = json.loads(content)
    payload["source_id"] = "tampered"
    tampered = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert verify_partial_timetable_review_json_bytes_v1(tampered) is False


def test_bounded_writer_verifies_before_filesystem_mutation(tmp_path) -> None:
    review = _review()
    package = DataAuthorityReviewPackageV1(
        review=review,
        json_bytes=b"tampered",
        markdown_bytes=render_partial_timetable_review_markdown_v1(review),
        exit_code=0,
    )
    output_dir = tmp_path / "must-not-exist"

    with pytest.raises(ValueError, match="JSON does not belong"):
        write_data_authority_review_package_v1(package, output_dir)

    assert output_dir.exists() is False


def test_cli_writes_exactly_two_bounded_files_and_handles_collision(tmp_path) -> None:
    workbook_path = create_input_template(tmp_path / "input.xlsx")
    output_dir = tmp_path / "review"
    arguments = [
        "--workbook",
        str(workbook_path),
        "--source-id",
        "cli-review",
        "--output-dir",
        str(output_dir),
    ]

    assert cli_main(arguments) == 0
    assert {path.name for path in output_dir.iterdir()} == {
        DATA_AUTHORITY_REVIEW_JSON_FILENAME,
        DATA_AUTHORITY_REVIEW_MARKDOWN_FILENAME,
    }
    assert cli_main(arguments) == 5
    assert cli_main([*arguments, "--overwrite"]) == 0


def test_core_import_failure_returns_exit_two_with_review_files(tmp_path) -> None:
    workbook_path = tmp_path / "invalid.xlsx"
    workbook_path.write_bytes(b"not an xlsx workbook")
    output_dir = tmp_path / "review"

    exit_code = cli_main(
        [
            "--workbook",
            str(workbook_path),
            "--source-id",
            "invalid-core-input",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    package = create_data_authority_review_package_v1(
        workbook_path,
        source_id="invalid-core-input",
    )
    assert package.exit_code == 2
    assert {path.name for path in output_dir.iterdir()} == {
        DATA_AUTHORITY_REVIEW_JSON_FILENAME,
        DATA_AUTHORITY_REVIEW_MARKDOWN_FILENAME,
    }

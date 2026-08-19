from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from bus_schedule_engine.contracts_v1 import MultiPeriodDemandError
from bus_schedule_engine.v3_runner import write_deterministic_json
from bus_schedule_engine.v3_workbook import import_v3_multi_period_workbook_v1
from scripts.run_v3_two_stage import main


def _write_v3_workbook(path: Path) -> Path:
    workbook = Workbook()
    parameters = workbook.active
    parameters.title = "THONG_SO_B"
    parameters.append(["THÔNG SỐ SCENARIO B", None, None, None])
    parameters.append(["Tham số", "Giá trị", "Mức độ", "Diễn giải"])
    parameter_values = {
        "route_id": "SYNTH",
        "route_name": "Synthetic route",
        "route_type": "intra_provincial",
        "allowed_trip_runtime_minutes": "30",
        "trip_runtime_minutes": "30",
        "total_daily_trips": 6,
        "terminal_1_name": "Terminal 1",
        "terminal_1_first_departure": "06:00:00",
        "terminal_1_last_departure": "08:00:00",
        "terminal_2_name": "Terminal 2",
        "terminal_2_first_departure": "06:10:00",
        "terminal_2_last_departure": "08:10:00",
        "vehicle_capacity_passengers": 60,
        "minimum_layover_minutes": 5,
        "available_fleet_limit": 4,
        "operating_day_type": "all_days",
    }
    for key, value in parameter_values.items():
        parameters.append([key, value, "REQUIRED", ""])

    timetable = workbook.create_sheet("BIEU_DO_B")
    timetable.append(["SCENARIO B", None, None, None])
    timetable.append(["Synthetic", None, None, None])
    timetable.append(
        [
            "scenario",
            "trip_id",
            "departure_terminal",
            "direction",
            "departure_time",
            "arrival_time",
            "vehicle_id",
            "vehicle_capacity_override",
        ]
    )
    definitions = [
        ("O1", "Terminal 1", "terminal_1_to_2", "06:00:00", "06:30:00"),
        ("I1", "Terminal 2", "terminal_2_to_1", "06:10:00", "06:40:00"),
        ("O2", "Terminal 1", "terminal_1_to_2", "07:00:00", "07:30:00"),
        ("I2", "Terminal 2", "terminal_2_to_1", "07:10:00", "07:40:00"),
        ("O3", "Terminal 1", "terminal_1_to_2", "08:00:00", "08:30:00"),
        ("I3", "Terminal 2", "terminal_2_to_1", "08:10:00", "08:40:00"),
    ]
    for trip_id, terminal, direction, departure, arrival in definitions:
        timetable.append(["B", trip_id, terminal, direction, departure, arrival, None, None])

    catalog = workbook.create_sheet("PERIOD_CATALOG")
    catalog.append(
        [
            "period_id",
            "period_start",
            "period_end",
            "observation_days",
            "period_role",
            "status",
            "source_dataset_id",
            "notes",
        ]
    )
    catalog.append(["p1", date(2026, 3, 1), date(2026, 3, 2), 2, "CURRENT", "READY", "ds-p1", ""])
    catalog.append(["p2", date(2026, 4, 1), date(2026, 4, 4), 4, "CURRENT", "READY", "ds-p2", ""])

    demand = workbook.create_sheet("SAN_LUONG_MULTI_PERIOD")
    demand.append(
        [
            "period_id",
            "period_start",
            "period_end",
            "observation_days",
            "time_block_start",
            "time_block_end",
            "direction",
            "passenger_volume",
            "volume_type",
            "source_time_basis",
            "source_dataset_id",
        ]
    )
    for period_id, start_date, end_date, days, dataset, factor in (
        ("p1", date(2026, 3, 1), date(2026, 3, 2), 2, "ds-p1", 1),
        ("p2", date(2026, 4, 1), date(2026, 4, 4), 4, "ds-p2", 2),
    ):
        for direction in ("terminal_1_to_2", "terminal_2_to_1"):
            for block_index, (block_start, block_end) in enumerate(
                (
                    ("06:00:00", "07:00:00"),
                    ("07:00:00", "08:00:00"),
                    ("08:00:00", "08:30:00"),
                ),
                start=1,
            ):
                demand.append(
                    [
                        period_id,
                        start_date,
                        end_date,
                        days,
                        block_start,
                        block_end,
                        direction,
                        factor * block_index * 10,
                        "average_day",
                        "actual_departure_time",
                        dataset,
                    ]
                )

    profiles = workbook.create_sheet("DEMAND_PROFILE_CONFIG")
    profiles.append(
        [
            "profile_id",
            "included_period_ids",
            "aggregation_method",
            "period_weight",
            "authority_role",
            "status",
            "description",
        ]
    )
    profiles.append(
        ["stable", "p1,p2", "day_weighted_mean", "observation_days", "PRIMARY", "READY", ""]
    )
    profiles.append(
        ["current", "p2", "single_period", "observation_days", "SENSITIVITY", "READY", ""]
    )

    metadata = workbook.create_sheet("THONG_TIN_DU_LIEU")
    metadata.append(["DATA AUTHORITY", None, None, None])
    metadata.append(["Tham số", "Giá trị", "Mức độ", "Diễn giải"])
    for key, value in (
        ("demand_dataset_id", "synthetic-multi"),
        ("demand_source_type", "ticketing"),
        ("demand_confidence", "high"),
        ("demand_response_mode", "static"),
        ("default_demand_profile", "stable"),
        ("sensitivity_profiles", "current"),
    ):
        metadata.append([key, value, "REQUIRED", ""])

    guide = workbook.create_sheet("HUONG_DAN", 0)
    guide["A1"] = "Synthetic V3 fixture"
    workbook.save(path)
    return path


@pytest.fixture
def v3_workbook(tmp_path: Path) -> Path:
    return _write_v3_workbook(tmp_path / "synthetic_v3.xlsx")


def test_v3_reader_loads_default_and_multiple_periods(v3_workbook: Path) -> None:
    imported = import_v3_multi_period_workbook_v1(v3_workbook)

    assert imported.base_workbook.parameters_b.route_id == "SYNTH"
    assert imported.multi_period_demand.default_profile_id == "stable"
    assert [item.period_id for item in imported.multi_period_demand.periods] == ["p1", "p2"]


def test_v3_reader_rejects_period_row_catalog_mismatch(v3_workbook: Path) -> None:
    workbook = load_workbook(v3_workbook)
    workbook["SAN_LUONG_MULTI_PERIOD"]["D2"] = 3
    workbook.save(v3_workbook)

    with pytest.raises(MultiPeriodDemandError) as exc_info:
        import_v3_multi_period_workbook_v1(v3_workbook)

    assert exc_info.value.code == "PERIOD_ROW_OBSERVATION_DAYS_MISMATCH"


def test_v3_reader_rejects_missing_observation_days(v3_workbook: Path) -> None:
    workbook = load_workbook(v3_workbook)
    workbook["PERIOD_CATALOG"]["D2"] = None
    workbook.save(v3_workbook)

    with pytest.raises(MultiPeriodDemandError) as exc_info:
        import_v3_multi_period_workbook_v1(v3_workbook)

    assert exc_info.value.code == "OBSERVATION_DAYS_MISSING"


def test_default_profile_cli_creates_deterministic_json_and_required_xlsx(
    v3_workbook: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "default"

    assert (
        main(
            [
                "--input",
                str(v3_workbook),
                "--output-dir",
                str(output),
                "--solve-budget-seconds",
                "0.001",
            ]
        )
        == 0
    )

    payload = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert payload["selected_profile"]["profile_id"] == "stable"
    result_workbook = load_workbook(output / "result.xlsx", read_only=False)
    assert result_workbook.sheetnames == [
        "SUMMARY",
        "DEMAND_PROFILE",
        "STAGE1_ALLOCATION",
        "REGIMES",
        "TIMETABLE_B",
        "TIMETABLE_C",
        "DIAGNOSTICS",
    ]
    assert len(result_workbook["DEMAND_PROFILE"]._charts) == 1
    first = write_deterministic_json(tmp_path / "one.json", payload).read_bytes()
    second = write_deterministic_json(tmp_path / "two.json", payload).read_bytes()
    assert first == second


def test_explicit_profile_and_batch_profile_outputs(
    v3_workbook: Path,
    tmp_path: Path,
) -> None:
    single = tmp_path / "single"
    assert (
        main(
            [
                "--input",
                str(v3_workbook),
                "--profile",
                "current",
                "--output-dir",
                str(single),
                "--solve-budget-seconds",
                "0.001",
            ]
        )
        == 0
    )
    assert (
        json.loads((single / "result.json").read_text(encoding="utf-8"))["selected_profile"][
            "profile_id"
        ]
        == "current"
    )

    batch = tmp_path / "batch"
    assert (
        main(
            [
                "--input",
                str(v3_workbook),
                "--profiles",
                "stable,current",
                "--output-dir",
                str(batch),
                "--solve-budget-seconds",
                "0.001",
            ]
        )
        == 0
    )
    for profile_id in ("stable", "current"):
        assert (batch / profile_id / "result.json").is_file()
        assert (batch / profile_id / "result.xlsx").is_file()
    assert (batch / "profile_comparison.json").is_file()
    assert (batch / "profile_comparison.xlsx").is_file()
    assert not any(item.name == v3_workbook.name for item in batch.rglob("*"))

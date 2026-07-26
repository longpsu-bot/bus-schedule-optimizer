"""Build or verify the deterministic anonymized route corpus v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from bus_schedule_engine.importer import ImportedWorkbook, import_workbook
from bus_schedule_engine.models import DemandRecord, Direction, ScenarioParameters, Trip

CORPUS_VERSION = "1"
PRIVATE_CORPUS_ENV = "BUS_SCHEDULE_PRIVATE_CORPUS_DIR"
DATE_SHIFT_DAYS = -365
FIXED_IMPORTED_AT = "2025-07-16T00:00:00+00:00"
HISTORICAL_SHEETS = (
    "DANH_GIA_TOI_UU",
    "PHAN_BO_THEO_GIO",
    "BIEU_DO_TOI_UU",
)
EXPECTED_SHEETS = (
    "HUONG_DAN",
    "THONG_SO_A",
    "BIEU_DO_A",
    "THONG_SO_B",
    "BIEU_DO_B",
    "SAN_LUONG",
    "CAU_HINH",
    *HISTORICAL_SHEETS,
)


class CorpusBuildError(RuntimeError):
    """Raised when private source validation or deterministic verification fails."""


@dataclass(frozen=True, slots=True)
class CorrectionSpec:
    scenario: str
    field: str
    source_value: int | str
    derived_value: int | str
    code: str
    explanation: str


@dataclass(frozen=True, slots=True)
class SourceSpec:
    filename: str
    source_label: str
    fixture_id: str
    public_route_name: str
    output_filename: str
    a_total: int
    directional_a: int
    b_total: int
    directional_b: int
    b_runtime_range: tuple[int, int]
    raw_rows: int
    overlap_pairs: int
    overlap_range: tuple[int, int]
    fleet_a: int
    fleet_b: int
    corrections: tuple[CorrectionSpec, ...]


SOURCE_SPECS = (
    SourceSpec(
        filename="61-8_danh_gia_va_bieu_do_toi_uu.xlsx",
        source_label="APPROVED_PRIVATE_SOURCE_ALPHA",
        fixture_id="CORPUS-ALPHA-80",
        public_route_name="Anonymized Route Alpha",
        output_filename="corpus_alpha_80.json",
        a_total=52,
        directional_a=26,
        b_total=80,
        directional_b=40,
        b_runtime_range=(55, 65),
        raw_rows=52,
        overlap_pairs=50,
        overlap_range=(20, 40),
        fleet_a=5,
        fleet_b=8,
        corrections=(
            CorrectionSpec(
                scenario="A",
                field="total_daily_trips",
                source_value=80,
                derived_value=52,
                code="A_TOTAL_FROM_EXACT_TIMETABLE",
                explanation=(
                    "Scenario A total is reconciled to the authoritative exact timetable rows."
                ),
            ),
        ),
    ),
    SourceSpec(
        filename="61-4_danh_gia_va_bieu_do_toi_uu.xlsx",
        source_label="APPROVED_PRIVATE_SOURCE_BETA",
        fixture_id="CORPUS-BETA-46",
        public_route_name="Anonymized Route Beta",
        output_filename="corpus_beta_46.json",
        a_total=26,
        directional_a=13,
        b_total=46,
        directional_b=23,
        b_runtime_range=(100, 100),
        raw_rows=26,
        overlap_pairs=24,
        overlap_range=(10, 55),
        fleet_a=4,
        fleet_b=7,
        corrections=(
            CorrectionSpec(
                "A",
                "terminal_1_first_departure",
                "04:30",
                "05:30",
                "A_ENDPOINT_FROM_EXACT_TIMETABLE",
                "Scenario A Terminal 1 first departure is reconciled to exact trip A-001.",
            ),
            CorrectionSpec(
                "A",
                "terminal_1_last_departure",
                "18:25",
                "18:15",
                "A_ENDPOINT_FROM_EXACT_TIMETABLE",
                "Scenario A Terminal 1 last departure is reconciled to exact trip A-013.",
            ),
            CorrectionSpec(
                "A",
                "terminal_2_first_departure",
                "05:35",
                "05:30",
                "A_ENDPOINT_FROM_EXACT_TIMETABLE",
                "Scenario A Terminal 2 first departure is reconciled to exact trip A-014.",
            ),
            CorrectionSpec(
                "A",
                "terminal_2_last_departure",
                "19:40",
                "17:20",
                "A_ENDPOINT_FROM_EXACT_TIMETABLE",
                "Scenario A Terminal 2 last departure is reconciled to exact trip A-026.",
            ),
        ),
    ),
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def corpus_dir() -> Path:
    return repo_root() / "tests" / "fixtures" / "route_corpus" / "v1"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def locate_private_sources() -> dict[SourceSpec, Path]:
    raw = os.environ.get(PRIVATE_CORPUS_ENV)
    if not raw:
        raise CorpusBuildError(f"{PRIVATE_CORPUS_ENV} is required")
    try:
        root = Path(raw).expanduser().resolve(strict=True)
    except OSError as exc:
        raise CorpusBuildError("Private corpus directory is unavailable") from exc
    if not root.is_dir():
        raise CorpusBuildError("Private corpus location must be a directory")
    repository = repo_root().resolve()
    if _is_within(root, repository):
        raise CorpusBuildError("Private corpus directory must be outside the Git worktree")
    try:
        entries = tuple(root.iterdir())
    except OSError as exc:
        raise CorpusBuildError("Private corpus directory is unreadable") from exc
    expected_names = {spec.filename for spec in SOURCE_SPECS}
    if len(entries) != 2 or {entry.name for entry in entries} != expected_names:
        raise CorpusBuildError(
            "Private corpus directory must contain exactly the two approved workbooks"
        )
    sources: dict[SourceSpec, Path] = {}
    for spec in SOURCE_SPECS:
        try:
            path = (root / spec.filename).resolve(strict=True)
            with path.open("rb") as source:
                source.read(1)
        except OSError as exc:
            raise CorpusBuildError(f"{spec.source_label} is absent or unreadable") from exc
        if not path.is_file() or _is_within(path, repository):
            raise CorpusBuildError(f"{spec.source_label} is not a valid external file")
        sources[spec] = path
    return sources


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_time(seconds: int) -> str:
    if not 0 <= seconds < 24 * 3600 or seconds % 60:
        raise CorpusBuildError(f"Unsupported timetable time: {seconds}")
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def _runtime(trip: Trip) -> int:
    if trip.arrival_seconds is None:
        raise CorpusBuildError(f"Exact trip {trip.trip_id} has no arrival time")
    seconds = trip.arrival_seconds - trip.departure_seconds
    if seconds <= 0 or seconds % 60:
        raise CorpusBuildError(f"Exact trip {trip.trip_id} has invalid runtime")
    return seconds // 60


def _directional(trips: list[Trip], direction: Direction) -> list[Trip]:
    return sorted(
        (trip for trip in trips if trip.direction == direction),
        key=lambda trip: (trip.departure_seconds, trip.trip_id),
    )


def _endpoints(trips: list[Trip]) -> dict[str, int]:
    terminal_1 = _directional(trips, Direction.TERMINAL_1_TO_2)
    terminal_2 = _directional(trips, Direction.TERMINAL_2_TO_1)
    if not terminal_1 or not terminal_2:
        raise CorpusBuildError("Both timetable directions are required")
    return {
        "terminal_1_first_departure": terminal_1[0].departure_seconds,
        "terminal_1_last_departure": terminal_1[-1].departure_seconds,
        "terminal_2_first_departure": terminal_2[0].departure_seconds,
        "terminal_2_last_departure": terminal_2[-1].departure_seconds,
    }


def _audit_scenario(
    scenario: str,
    parameters: ScenarioParameters,
    trips: list[Trip],
) -> list[tuple[str, str, int | str, int | str]]:
    if len({trip.trip_id for trip in trips}) != len(trips):
        raise CorpusBuildError(f"Scenario {scenario} has duplicate trip IDs")
    expected_terminal = {
        Direction.TERMINAL_1_TO_2: parameters.terminal_1_name,
        Direction.TERMINAL_2_TO_1: parameters.terminal_2_name,
    }
    for trip in trips:
        if trip.scenario != scenario:
            raise CorpusBuildError(f"Scenario {scenario} has a mismatched trip label")
        if trip.direction not in expected_terminal:
            raise CorpusBuildError(f"Scenario {scenario} has a combined timetable trip")
        if trip.departure_terminal != expected_terminal[trip.direction]:
            raise CorpusBuildError(
                f"Scenario {scenario} has an unexplained terminal/direction contradiction"
            )
        if trip.vehicle_id is not None or trip.vehicle_capacity_override is not None:
            raise CorpusBuildError(f"Scenario {scenario} contains private vehicle fields")
        if not parameters.accepts_trip_runtime(_runtime(trip)):
            raise CorpusBuildError(
                f"Scenario {scenario} contains runtime outside the declared inclusive range"
            )
    contradictions: list[tuple[str, str, int | str, int | str]] = []
    if parameters.total_daily_trips != len(trips):
        contradictions.append(
            (scenario, "total_daily_trips", parameters.total_daily_trips, len(trips))
        )
    for field, derived in _endpoints(trips).items():
        source = int(getattr(parameters, field))
        if source != derived:
            contradictions.append((scenario, field, _format_time(source), _format_time(derived)))
    return contradictions


def _overlap_summary(records: list[DemandRecord]) -> tuple[int, tuple[int, int]]:
    overlaps: list[int] = []
    for direction in (
        Direction.TERMINAL_1_TO_2,
        Direction.TERMINAL_2_TO_1,
    ):
        ordered = sorted(
            (record for record in records if record.direction == direction),
            key=lambda record: (record.block_start_seconds, record.block_end_seconds),
        )
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if earlier.block_end_seconds > later.block_start_seconds:
                overlaps.append((earlier.block_end_seconds - later.block_start_seconds) // 60)
    if not overlaps:
        raise CorpusBuildError("Approved raw trip observations unexpectedly have no overlaps")
    return len(overlaps), (min(overlaps), max(overlaps))


def _raw_trip_mapping(
    imported: ImportedWorkbook,
) -> list[tuple[DemandRecord, Trip]]:
    trips_by_interval: dict[tuple[Direction, int, int], list[Trip]] = defaultdict(list)
    for trip in imported.trips_a:
        if trip.arrival_seconds is None:
            raise CorpusBuildError("Scenario A trip has no exact arrival")
        trips_by_interval[(trip.direction, trip.departure_seconds, trip.arrival_seconds)].append(
            trip
        )
    mapping: list[tuple[DemandRecord, Trip]] = []
    for record in imported.demand:
        key = (
            record.direction,
            record.block_start_seconds,
            record.block_end_seconds,
        )
        matches = trips_by_interval.get(key, [])
        if len(matches) != 1:
            raise CorpusBuildError("SAN_LUONG rows do not map one-to-one to Scenario A exact trips")
        mapping.append((record, matches[0]))
    if len(mapping) != len(imported.trips_a):
        raise CorpusBuildError("SAN_LUONG and Scenario A do not have the same evidence row count")
    if {trip.trip_id for _, trip in mapping} != {trip.trip_id for trip in imported.trips_a}:
        raise CorpusBuildError("SAN_LUONG does not cover every Scenario A trip exactly once")
    return sorted(mapping, key=lambda item: item[1].trip_id)


def _audit_source(
    spec: SourceSpec,
    path: Path,
) -> tuple[ImportedWorkbook, list[dict[str, Any]], list[tuple[DemandRecord, Trip]]]:
    try:
        with pd.ExcelFile(path, engine="openpyxl") as excel:
            sheets = tuple(excel.sheet_names)
    except Exception as exc:
        raise CorpusBuildError(f"{spec.source_label} cannot be opened as XLSX") from exc
    if sheets != EXPECTED_SHEETS:
        raise CorpusBuildError(f"{spec.source_label} sheet topology changed")
    try:
        imported = import_workbook(path)
    except Exception as exc:
        raise CorpusBuildError(f"{spec.source_label} cannot be imported") from exc
    if imported.parameters_a is None:
        raise CorpusBuildError(f"{spec.source_label} has no Scenario A")

    invariant_fields = (
        "route_id",
        "route_name",
        "route_type",
        "terminal_1_name",
        "terminal_2_name",
        "vehicle_capacity_passengers",
        "target_load_factor",
        "maximum_load_factor",
        "minimum_layover_minutes",
    )
    if any(
        getattr(imported.parameters_a, field) != getattr(imported.parameters_b, field)
        for field in invariant_fields
    ):
        raise CorpusBuildError(
            f"{spec.source_label} has an unknown Scenario A/B parameter contradiction"
        )
    observed = [
        *_audit_scenario("A", imported.parameters_a, imported.trips_a),
        *_audit_scenario("B", imported.parameters_b, imported.trips_b),
    ]
    expected = [
        (
            correction.scenario,
            correction.field,
            correction.source_value,
            correction.derived_value,
        )
        for correction in spec.corrections
    ]
    if observed != expected:
        raise CorpusBuildError(
            f"{spec.source_label} has unknown, missing, or changed contradictions: {observed!r}"
        )
    for label, trips, total, directional in (
        ("A", imported.trips_a, spec.a_total, spec.directional_a),
        ("B", imported.trips_b, spec.b_total, spec.directional_b),
    ):
        counts = Counter(trip.direction for trip in trips)
        if len(trips) != total or counts != {
            Direction.TERMINAL_1_TO_2: directional,
            Direction.TERMINAL_2_TO_1: directional,
        }:
            raise CorpusBuildError(f"{spec.source_label} Scenario {label} counts changed")
    b_runtimes = [_runtime(trip) for trip in imported.trips_b]
    if (min(b_runtimes), max(b_runtimes)) != spec.b_runtime_range:
        raise CorpusBuildError(f"{spec.source_label} Scenario B runtime range changed")
    if len(imported.demand) != spec.raw_rows:
        raise CorpusBuildError(f"{spec.source_label} SAN_LUONG row count changed")
    period_keys = {
        (row.period_start, row.period_end, row.observation_days) for row in imported.demand
    }
    if len(period_keys) != 1:
        raise CorpusBuildError(f"{spec.source_label} has multiple raw observation periods")
    start, end, days = next(iter(period_keys))
    if (end - start).days + 1 != 15 or days != 15:
        raise CorpusBuildError(f"{spec.source_label} raw observation period changed")
    mapping = _raw_trip_mapping(imported)
    if _overlap_summary(imported.demand) != (
        spec.overlap_pairs,
        spec.overlap_range,
    ):
        raise CorpusBuildError(f"{spec.source_label} raw overlap topology changed")

    correction_entries: list[dict[str, Any]] = []
    for correction in spec.corrections:
        trips = imported.trips_a if correction.scenario == "A" else imported.trips_b
        if correction.field == "total_daily_trips":
            evidence = [trip.trip_id for trip in sorted(trips, key=lambda trip: trip.trip_id)]
        else:
            direction = (
                Direction.TERMINAL_1_TO_2
                if "terminal_1" in correction.field
                else Direction.TERMINAL_2_TO_1
            )
            index = 0 if "first_departure" in correction.field else -1
            evidence = [_directional(trips, direction)[index].trip_id]
        correction_entries.append(
            {
                "approved_for_corpus_construction": True,
                "classification": "exact_timetable_derived_correction",
                "correction_code": correction.code,
                "evidence_row_count": len(evidence),
                "evidence_trip_ids": evidence,
                "exact_timetable_derived_value": correction.derived_value,
                "explanation": correction.explanation,
                "fixture_id": spec.fixture_id,
                "source_field": correction.field,
                "source_scenario": correction.scenario,
                "source_sheet": f"THONG_SO_{correction.scenario}",
                "source_value": correction.source_value,
            }
        )
    return imported, correction_entries, mapping


def _corrected_parameters(
    parameters: ScenarioParameters,
    trips: list[Trip],
) -> ScenarioParameters:
    endpoints = _endpoints(trips)
    return replace(
        parameters,
        total_daily_trips=len(trips),
        terminal_1_first_departure=endpoints["terminal_1_first_departure"],
        terminal_1_last_departure=endpoints["terminal_1_last_departure"],
        terminal_2_first_departure=endpoints["terminal_2_first_departure"],
        terminal_2_last_departure=endpoints["terminal_2_last_departure"],
    )


def _parameters_payload(
    spec: SourceSpec,
    parameters: ScenarioParameters,
) -> dict[str, Any]:
    return {
        "allowed_trip_runtime_minutes": list(parameters.runtime_options),
        "maximum_load_factor": parameters.maximum_load_factor,
        "minimum_layover_minutes": parameters.effective_layover_minutes,
        "route_id": spec.fixture_id,
        "route_name": spec.public_route_name,
        "route_type": parameters.route_type.value,
        "target_load_factor": parameters.target_load_factor,
        "terminal_1_first_departure": _format_time(parameters.terminal_1_first_departure),
        "terminal_1_last_departure": _format_time(parameters.terminal_1_last_departure),
        "terminal_1_name": "Terminal 1",
        "terminal_2_first_departure": _format_time(parameters.terminal_2_first_departure),
        "terminal_2_last_departure": _format_time(parameters.terminal_2_last_departure),
        "terminal_2_name": "Terminal 2",
        "time_block_minutes": parameters.time_block_minutes,
        "total_daily_trips": parameters.total_daily_trips,
        "trip_runtime_minutes": parameters.trip_runtime_minutes,
        "vehicle_capacity_passengers": parameters.vehicle_capacity_passengers,
    }


def _trips_payload(trips: list[Trip]) -> list[dict[str, Any]]:
    terminal_by_direction = {
        Direction.TERMINAL_1_TO_2: "Terminal 1",
        Direction.TERMINAL_2_TO_1: "Terminal 2",
    }
    ordered = sorted(
        trips,
        key=lambda trip: (
            trip.departure_seconds,
            trip.direction.value,
            trip.trip_id,
        ),
    )
    return [
        {
            "arrival_time": _format_time(int(trip.arrival_seconds)),
            "departure_terminal": terminal_by_direction[trip.direction],
            "departure_time": _format_time(trip.departure_seconds),
            "direction": trip.direction.value,
            "runtime_minutes": _runtime(trip),
            "scenario": trip.scenario,
            "trip_id": trip.trip_id,
        }
        for trip in ordered
    ]


def _volume(value: float) -> int | float:
    return int(value) if float(value).is_integer() else float(value)


def _shifted_dates(record: DemandRecord) -> tuple[str, str]:
    return (
        (record.period_start + timedelta(days=DATE_SHIFT_DAYS)).isoformat(),
        (record.period_end + timedelta(days=DATE_SHIFT_DAYS)).isoformat(),
    )


def _raw_payload(
    spec: SourceSpec,
    mapping: list[tuple[DemandRecord, Trip]],
) -> dict[str, Any]:
    rows = []
    for record, trip in mapping:
        period_start, period_end = _shifted_dates(record)
        rows.append(
            {
                "direction": record.direction.value,
                "observation_days": record.observation_days,
                "passenger_volume": _volume(record.passenger_volume),
                "period_end": period_end,
                "period_start": period_start,
                "raw_interval_end": _format_time(record.block_end_seconds),
                "raw_interval_start": _format_time(record.block_start_seconds),
                "source_trip_id": trip.trip_id,
                "volume_type": record.volume_type.value,
            }
        )
    return {
        "classification": "raw_trip_observation_evidence",
        "contract_v1_demand_interval_eligible": False,
        "dataset_id": f"{spec.fixture_id}:raw_trip_observations",
        "overlap_documentation": {
            "adjacent_overlap_pair_count": spec.overlap_pairs,
            "maximum_overlap_minutes": spec.overlap_range[1],
            "minimum_overlap_minutes": spec.overlap_range[0],
            "overlaps_preserved": True,
            "reason": (
                "Raw intervals equal Scenario A trip departure-to-arrival spans and are "
                "preserved as evidence, not interpreted as Contract V1 demand intervals."
            ),
        },
        "rows": rows,
    }


def _proxy_payload(
    spec: SourceSpec,
    mapping: list[tuple[DemandRecord, Trip]],
    trips_b: list[Trip],
) -> dict[str, Any]:
    groups: dict[tuple[Direction, int], list[tuple[DemandRecord, Trip]]] = defaultdict(list)
    for record, trip in mapping:
        groups[(trip.direction, trip.departure_seconds // 3600)].append((record, trip))
    blocks: list[dict[str, Any]] = []
    for direction in (
        Direction.TERMINAL_1_TO_2,
        Direction.TERMINAL_2_TO_1,
    ):
        observed_hours = sorted(
            hour for item_direction, hour in groups if item_direction == direction
        )
        if not observed_hours:
            raise CorpusBuildError(
                "Proxy requires observed Scenario A departures in both directions"
            )
        b_departures = [trip.departure_seconds for trip in trips_b if trip.direction == direction]
        coverage_start_hour = min(observed_hours[0], min(b_departures) // 3600)
        coverage_end_hour = max(observed_hours[-1], max(b_departures) // 3600) + 1
        for index, hour in enumerate(observed_hours):
            rows = groups[(direction, hour)]
            first_record = rows[0][0]
            period_start, period_end = _shifted_dates(first_record)
            source_trip_ids = sorted(trip.trip_id for _, trip in rows)
            start_hour = coverage_start_hour if index == 0 else hour
            end_hour = (
                observed_hours[index + 1] if index + 1 < len(observed_hours) else coverage_end_hour
            )
            blocks.append(
                {
                    "block_id": f"PROXY-{direction.value.upper()}-{hour:02d}",
                    "coverage_extension_minutes": max(0, (end_hour - start_hour - 1) * 60),
                    "direction": direction.value,
                    "observation_days": first_record.observation_days,
                    "observed_departure_hour_start": _format_time(hour * 3600),
                    "passenger_volume": _volume(sum(record.passenger_volume for record, _ in rows)),
                    "period_end": period_end,
                    "period_start": period_start,
                    "source_observation_count": len(rows),
                    "source_trip_ids": source_trip_ids,
                    "source_volume_type": first_record.volume_type.value,
                    "time_block_end": _format_time(end_hour * 3600),
                    "time_block_start": _format_time(start_hour * 3600),
                    "volume_type": "average_day",
                }
            )
    blocks.sort(
        key=lambda block: (
            block["time_block_start"],
            block["direction"],
            block["block_id"],
        )
    )
    return {
        "classification": "derived_proxy_dataset",
        "contract_v1_weight_interpretation": (
            "unscaled_15_day_observation_total_used_as_sensitivity_weight"
        ),
        "contract_v1_demand_interval_eligible": True,
        "dataset_id": f"{spec.fixture_id}:departure_hour_proxy_v1",
        "demand_confidence": "LOW",
        "limitations": [
            "This proxy groups raw trip passenger observations by Scenario A departure hour.",
            (
                "A nonempty observed-hour block may extend to the next observed hour or through "
                "the Scenario B endpoint to maintain contiguous solver coverage without "
                "fabricating an empty zero-demand block."
            ),
            (
                "Contract V1 receives the exactly conserved 15-day totals as unscaled proxy "
                "weights via its average_day transport classification; these are not observed "
                "average-day passenger counts."
            ),
            "It is sensitivity evidence only and is not an observed hourly demand series.",
            "It must never be presented as an approved operational demand baseline.",
        ],
        "proxy_method": "departure_hour_proxy_v1",
        "blocks": blocks,
    }


def _fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _fixture_payload(
    spec: SourceSpec,
    source_hash: str,
    imported: ImportedWorkbook,
    corrections: list[dict[str, Any]],
    mapping: list[tuple[DemandRecord, Trip]],
) -> dict[str, Any]:
    if imported.parameters_a is None:
        raise CorpusBuildError("Scenario A disappeared after audit")
    raw = _raw_payload(spec, mapping)
    proxy = _proxy_payload(spec, mapping, imported.trips_b)
    return {
        "anonymization_profile": {
            "date_shift_days": DATE_SHIFT_DAYS,
            "excluded_private_fields": [
                "absolute_source_path",
                "free_text_historical_conclusions",
                "operator_or_organization_identity",
                "private_route_identity",
                "private_terminal_identity",
                "vehicle_identifiers",
                "workbook_author_metadata",
            ],
            "profile_id": "route_corpus_v1_relative_terminal_redaction",
            "route_name": spec.public_route_name,
            "terminal_1_name": "Terminal 1",
            "terminal_2_name": "Terminal 2",
        },
        "configuration": {
            "combined_direction_policy": "do_not_infer",
            "final_service_block_minutes": 90,
            "generator_mode": "deterministic",
        },
        "corpus_version": CORPUS_VERSION,
        "demand_observations": {
            "departure_hour_proxy_v1": proxy,
            "raw_trip_observations": raw,
        },
        "excluded_source_sheets": list(HISTORICAL_SHEETS),
        "fixture_id": spec.fixture_id,
        "limitations": [
            "Fleet limits are corpus assumptions, not operator-declared source facts.",
            "The LOW-confidence departure-hour proxy is sensitivity evidence only.",
            "Raw trip observations are never supplied as Contract V1 demand intervals.",
            "Historical optimized sheets are excluded from corpus truth.",
            "No generated timetable in Milestone 4C1 is operationally approved.",
        ],
        "normalization_options": {
            "available_fleet_limit_a": spec.fleet_a,
            "available_fleet_limit_b": spec.fleet_b,
            "demand_confidence": "LOW",
            "demand_dataset_id": proxy["dataset_id"],
            "imported_at": FIXED_IMPORTED_AT,
            "operating_day_type_a": "WEEKDAY",
            "operating_day_type_b": "WEEKDAY",
            "source_id": spec.fixture_id,
            "source_notes": (
                "Anonymized real-route-derived fixture using departure_hour_proxy_v1."
            ),
        },
        "scenario_a": {
            "exact_trips": _trips_payload(imported.trips_a),
            "parameters": _parameters_payload(
                spec,
                _corrected_parameters(imported.parameters_a, imported.trips_a),
            ),
        },
        "scenario_b": {
            "exact_trips": _trips_payload(imported.trips_b),
            "parameters": _parameters_payload(
                spec,
                _corrected_parameters(imported.parameters_b, imported.trips_b),
            ),
        },
        "source_audit_codes": sorted(
            {
                "DEPARTURE_HOUR_PROXY_V1_DERIVED",
                "EXACT_TIMETABLE_ROWS_AUTHORITATIVE",
                "HISTORICAL_OUTPUT_SHEETS_EXCLUDED",
                "RAW_TRIP_OBSERVATION_OVERLAPS_PRESERVED",
                *(correction["correction_code"] for correction in corrections),
            }
        ),
        "source_sha256": source_hash,
    }


def _manifest_entry(
    spec: SourceSpec,
    source_hash: str,
    fixture: dict[str, Any],
    corrections: list[dict[str, Any]],
) -> dict[str, Any]:
    raw = fixture["demand_observations"]["raw_trip_observations"]
    proxy = fixture["demand_observations"]["departure_hour_proxy_v1"]
    return {
        "corrections": corrections,
        "derived_datasets": [
            {
                "classification": "derived_proxy_dataset",
                "confidence": "LOW",
                "dataset_id": proxy["dataset_id"],
                "method": "departure_hour_proxy_v1",
                "proxy_fingerprint": _fingerprint(proxy["blocks"]),
                "source_dataset_id": raw["dataset_id"],
                "status": "PROXY_SENSITIVITY_ONLY",
            }
        ],
        "fixture_file": spec.output_filename,
        "fixture_id": spec.fixture_id,
        "observed_source_facts": [
            {
                "classification": "observed_source_fact",
                "code": "EXACT_SCENARIO_A_TIMETABLE",
                "directional_trip_counts": [spec.directional_a, spec.directional_a],
                "total_trip_count": spec.a_total,
            },
            {
                "classification": "observed_source_fact",
                "code": "EXACT_SCENARIO_B_TIMETABLE",
                "directional_trip_counts": [spec.directional_b, spec.directional_b],
                "runtime_range_minutes": list(spec.b_runtime_range),
                "total_trip_count": spec.b_total,
            },
            {
                "classification": "observed_source_fact",
                "code": "RAW_TRIP_OBSERVATIONS",
                "overlap_pair_count": spec.overlap_pairs,
                "raw_fingerprint": _fingerprint(raw["rows"]),
                "row_count": spec.raw_rows,
            },
            {
                "classification": "observed_source_fact",
                "code": "OPERATING_PARAMETERS",
                "maximum_load_factor": 0.9,
                "minimum_layover_minutes": 5,
                "route_type": "intra_provincial",
                "target_load_factor": 0.85,
                "vehicle_capacity_passengers": 28,
            },
        ],
        "scenario_assumptions": [
            {
                "classification": "corpus_scenario_assumption",
                "field": "available_fleet_limit_a",
                "value": spec.fleet_a,
            },
            {
                "classification": "corpus_scenario_assumption",
                "field": "available_fleet_limit_b",
                "value": spec.fleet_b,
            },
            {
                "classification": "corpus_scenario_assumption",
                "field": "operating_day_type_a",
                "value": "WEEKDAY",
            },
            {
                "classification": "corpus_scenario_assumption",
                "field": "operating_day_type_b",
                "value": "WEEKDAY",
            },
            {
                "classification": "corpus_scenario_assumption",
                "field": "demand_confidence",
                "value": "LOW",
            },
        ],
        "source_label": spec.source_label,
        "source_sha256": source_hash,
    }


def build_outputs() -> dict[str, dict[str, Any]]:
    sources = locate_private_sources()
    outputs: dict[str, dict[str, Any]] = {}
    manifest_entries: list[dict[str, Any]] = []
    for spec in SOURCE_SPECS:
        path = sources[spec]
        source_hash = _sha256(path)
        imported, corrections, mapping = _audit_source(spec, path)
        fixture = _fixture_payload(
            spec,
            source_hash,
            imported,
            corrections,
            mapping,
        )
        outputs[spec.output_filename] = fixture
        manifest_entries.append(_manifest_entry(spec, source_hash, fixture, corrections))
    outputs["manifest.json"] = {
        "anonymization_profile_id": "route_corpus_v1_relative_terminal_redaction",
        "corpus_version": CORPUS_VERSION,
        "date_shift_days": DATE_SHIFT_DAYS,
        "fixtures": manifest_entries,
        "historical_source_sheet_policy": "HISTORICAL_NON_AUTHORITATIVE_REFERENCE",
        "proxy_policy": "PROXY_SENSITIVITY_ONLY",
    }
    return outputs


def json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def write_outputs(outputs: dict[str, dict[str, Any]]) -> None:
    destination = corpus_dir()
    destination.mkdir(parents=True, exist_ok=True)
    for filename, payload in sorted(outputs.items()):
        (destination / filename).write_bytes(json_bytes(payload))


def verify_outputs(outputs: dict[str, dict[str, Any]]) -> None:
    errors: list[str] = []
    for filename, payload in sorted(outputs.items()):
        path = corpus_dir() / filename
        if not path.is_file():
            errors.append(f"missing {filename}")
        elif path.read_bytes() != json_bytes(payload):
            errors.append(f"different {filename}")
    if errors:
        raise CorpusBuildError("Committed corpus verification failed: " + ", ".join(errors))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        outputs = build_outputs()
        if args.write:
            write_outputs(outputs)
            print("Wrote deterministic route corpus v1 JSON.")
        else:
            verify_outputs(outputs)
            print("Verified deterministic route corpus v1 JSON.")
    except (CorpusBuildError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit reader for V3 multi-period workbooks.

The legacy ``import_workbook`` path intentionally continues to read only ``SAN_LUONG``.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from .contracts_v1.models import ContractDirection, VolumeClassification
from .contracts_v1.multi_period_demand import (
    DemandObservationPeriodV1,
    DemandPeriodObservationV1,
    DemandProfileAggregationMethodV1,
    DemandProfileConfigV1,
    MultiPeriodDemandError,
    MultiPeriodDemandInputV1,
    validate_multi_period_demand_input_v1,
)
from .importer import (
    ImportedWorkbook,
    InputDataError,
    WorkbookAuthorityMetadata,
    _authority_metadata,
    _clean,
    _date,
    _direction,
    _key_value_sheet,
    _materialize_workbook_source,
    _parameters,
    _trips,
)
from .models import Direction, VolumeType
from .time_utils import parse_time_to_seconds

V3_MULTI_PERIOD_RUNNER_PROFILE_V1 = "v3_multi_period_runner_v1"

_REQUIRED_V3_SHEETS = {
    "PERIOD_CATALOG",
    "SAN_LUONG_MULTI_PERIOD",
    "DEMAND_PROFILE_CONFIG",
    "THONG_TIN_DU_LIEU",
}
_PERIOD_REQUIRED_COLUMNS = {
    "period_id",
    "period_start",
    "period_end",
    "observation_days",
    "period_role",
    "status",
    "source_dataset_id",
}
_DEMAND_REQUIRED_COLUMNS = {
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
}
_PROFILE_REQUIRED_COLUMNS = {
    "profile_id",
    "included_period_ids",
    "aggregation_method",
    "period_weight",
    "authority_role",
    "status",
    "description",
}


@dataclass(frozen=True, slots=True)
class ImportedV3WorkbookV1:
    base_workbook: ImportedWorkbook
    multi_period_demand: MultiPeriodDemandInputV1


def _required_columns(frame: pd.DataFrame, required: set[str], sheet_name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise InputDataError(f"{sheet_name} thiếu cột: {', '.join(sorted(missing))}")


def _required_text(value: object, *, field: str, sheet: str, row: int) -> str:
    cleaned = _clean(value)
    if cleaned is None or not str(cleaned).strip():
        raise MultiPeriodDemandError(
            f"{field.upper()}_MISSING",
            f"{sheet} row {row} requires {field}",
        )
    return str(cleaned).strip()


def _positive_observation_days(value: object, *, sheet: str, row: int) -> int:
    cleaned = _clean(value)
    if cleaned is None:
        raise MultiPeriodDemandError(
            "OBSERVATION_DAYS_MISSING",
            f"{sheet} row {row} is missing observation_days",
        )
    try:
        days = int(cleaned)
    except (TypeError, ValueError) as exc:
        raise MultiPeriodDemandError(
            "OBSERVATION_DAYS_INVALID",
            f"{sheet} row {row} has invalid observation_days",
        ) from exc
    if days <= 0:
        raise MultiPeriodDemandError(
            "OBSERVATION_DAYS_INVALID",
            f"{sheet} row {row} requires positive observation_days",
        )
    return days


def _contract_direction(value: object) -> ContractDirection:
    direction = _direction(value)
    return {
        Direction.TERMINAL_1_TO_2: ContractDirection.OUTBOUND,
        Direction.TERMINAL_2_TO_1: ContractDirection.INBOUND,
        Direction.COMBINED: ContractDirection.COMBINED,
    }[direction]


def _volume_classification(value: object) -> VolumeClassification:
    try:
        volume_type = VolumeType(str(value).strip())
    except ValueError as exc:
        raise MultiPeriodDemandError(
            "VOLUME_TYPE_UNSUPPORTED",
            f"unsupported volume_type {value!r}",
        ) from exc
    return (
        VolumeClassification.AVERAGE_DAY
        if volume_type == VolumeType.AVERAGE_DAY
        else VolumeClassification.TOTAL_OBSERVATION_PERIOD
    )


def _split_ids(value: object) -> tuple[str, ...]:
    cleaned = _clean(value)
    if cleaned is None:
        return ()
    return tuple(item.strip() for item in str(cleaned).split(",") if item.strip())


def _period_catalog(frame: pd.DataFrame) -> tuple[DemandObservationPeriodV1, ...]:
    _required_columns(frame, _PERIOD_REQUIRED_COLUMNS, "PERIOD_CATALOG")
    periods: list[DemandObservationPeriodV1] = []
    for index, row in frame.iterrows():
        excel_row = index + 2
        if _clean(row.get("period_id")) is None:
            continue
        try:
            periods.append(
                DemandObservationPeriodV1(
                    period_id=_required_text(
                        row.get("period_id"),
                        field="period_id",
                        sheet="PERIOD_CATALOG",
                        row=excel_row,
                    ),
                    period_start=_date(row.get("period_start")),
                    period_end=_date(row.get("period_end")),
                    observation_days=_positive_observation_days(
                        row.get("observation_days"),
                        sheet="PERIOD_CATALOG",
                        row=excel_row,
                    ),
                    observations=(),
                    source_dataset_id=_required_text(
                        row.get("source_dataset_id"),
                        field="source_dataset_id",
                        sheet="PERIOD_CATALOG",
                        row=excel_row,
                    ),
                    period_role=_required_text(
                        row.get("period_role"),
                        field="period_role",
                        sheet="PERIOD_CATALOG",
                        row=excel_row,
                    ),
                    status=_required_text(
                        row.get("status"),
                        field="status",
                        sheet="PERIOD_CATALOG",
                        row=excel_row,
                    ),
                )
            )
        except MultiPeriodDemandError:
            raise
        except (TypeError, ValueError) as exc:
            raise MultiPeriodDemandError(
                "PERIOD_CATALOG_ROW_INVALID",
                f"PERIOD_CATALOG row {excel_row}: {exc}",
            ) from exc
    return tuple(periods)


def _attach_observations(
    periods: tuple[DemandObservationPeriodV1, ...],
    frame: pd.DataFrame,
) -> tuple[DemandObservationPeriodV1, ...]:
    _required_columns(frame, _DEMAND_REQUIRED_COLUMNS, "SAN_LUONG_MULTI_PERIOD")
    catalog = {item.period_id: item for item in periods}
    observations: dict[str, list[DemandPeriodObservationV1]] = {
        item.period_id: [] for item in periods
    }
    for index, row in frame.iterrows():
        excel_row = index + 2
        if _clean(row.get("period_id")) is None:
            continue
        period_id = str(row.get("period_id")).strip()
        period = catalog.get(period_id)
        if period is None:
            raise MultiPeriodDemandError(
                "DEMAND_ROW_UNKNOWN_PERIOD",
                f"SAN_LUONG_MULTI_PERIOD row {excel_row} references {period_id}",
            )
        try:
            row_start = _date(row.get("period_start"))
            row_end = _date(row.get("period_end"))
            row_days = _positive_observation_days(
                row.get("observation_days"),
                sheet="SAN_LUONG_MULTI_PERIOD",
                row=excel_row,
            )
            if row_start != period.period_start or row_end != period.period_end:
                raise MultiPeriodDemandError(
                    "PERIOD_ROW_DATE_MISMATCH",
                    f"period {period_id} row dates differ from PERIOD_CATALOG",
                )
            if row_days != period.observation_days:
                raise MultiPeriodDemandError(
                    "PERIOD_ROW_OBSERVATION_DAYS_MISMATCH",
                    f"period {period_id} row observation_days differs from PERIOD_CATALOG",
                )
            observations[period_id].append(
                DemandPeriodObservationV1(
                    interval_start=parse_time_to_seconds(row.get("time_block_start")),
                    interval_end=parse_time_to_seconds(row.get("time_block_end")),
                    direction=_contract_direction(row.get("direction")),
                    passenger_volume=float(row.get("passenger_volume")),
                    volume_classification=_volume_classification(row.get("volume_type")),
                    source_time_basis=_required_text(
                        row.get("source_time_basis"),
                        field="source_time_basis",
                        sheet="SAN_LUONG_MULTI_PERIOD",
                        row=excel_row,
                    ),
                    source_dataset_id=_required_text(
                        row.get("source_dataset_id"),
                        field="source_dataset_id",
                        sheet="SAN_LUONG_MULTI_PERIOD",
                        row=excel_row,
                    ),
                )
            )
        except MultiPeriodDemandError:
            raise
        except (TypeError, ValueError) as exc:
            raise MultiPeriodDemandError(
                "DEMAND_ROW_INVALID",
                f"SAN_LUONG_MULTI_PERIOD row {excel_row}: {exc}",
            ) from exc
    return tuple(
        DemandObservationPeriodV1(
            period_id=period.period_id,
            period_start=period.period_start,
            period_end=period.period_end,
            observation_days=period.observation_days,
            observations=tuple(observations[period.period_id]),
            source_dataset_id=period.source_dataset_id,
            period_role=period.period_role,
            status=period.status,
        )
        for period in periods
    )


def _profiles(frame: pd.DataFrame) -> tuple[DemandProfileConfigV1, ...]:
    _required_columns(frame, _PROFILE_REQUIRED_COLUMNS, "DEMAND_PROFILE_CONFIG")
    profiles: list[DemandProfileConfigV1] = []
    for index, row in frame.iterrows():
        excel_row = index + 2
        if _clean(row.get("profile_id")) is None:
            continue
        try:
            profiles.append(
                DemandProfileConfigV1(
                    profile_id=_required_text(
                        row.get("profile_id"),
                        field="profile_id",
                        sheet="DEMAND_PROFILE_CONFIG",
                        row=excel_row,
                    ),
                    included_period_ids=_split_ids(row.get("included_period_ids")),
                    aggregation_method=DemandProfileAggregationMethodV1(
                        str(row.get("aggregation_method")).strip()
                    ),
                    period_weight=_required_text(
                        row.get("period_weight"),
                        field="period_weight",
                        sheet="DEMAND_PROFILE_CONFIG",
                        row=excel_row,
                    ),
                    authority_role=_required_text(
                        row.get("authority_role"),
                        field="authority_role",
                        sheet="DEMAND_PROFILE_CONFIG",
                        row=excel_row,
                    ),
                    status=_required_text(
                        row.get("status"),
                        field="status",
                        sheet="DEMAND_PROFILE_CONFIG",
                        row=excel_row,
                    ),
                    description=str(_clean(row.get("description")) or ""),
                )
            )
        except MultiPeriodDemandError:
            raise
        except ValueError as exc:
            raise MultiPeriodDemandError(
                "AGGREGATION_METHOD_UNSUPPORTED",
                f"DEMAND_PROFILE_CONFIG row {excel_row}: {exc}",
            ) from exc
    return tuple(profiles)


def import_v3_multi_period_workbook_v1(
    source: str | Path | bytes | BinaryIO,
) -> ImportedV3WorkbookV1:
    """Load Scenario B through the legacy reader and demand through the explicit V3 path."""
    materialized = _materialize_workbook_source(source)
    workbook_source: str | Path | BytesIO = (
        BytesIO(materialized) if isinstance(materialized, bytes) else materialized
    )
    with pd.ExcelFile(workbook_source, engine="openpyxl") as excel_file:
        missing = _REQUIRED_V3_SHEETS - set(excel_file.sheet_names)
        if missing:
            raise InputDataError("Workbook thiếu sheet V3: " + ", ".join(sorted(missing)))
        parameter_frame = pd.read_excel(excel_file, sheet_name="THONG_SO_B", header=1)
        timetable_frame = pd.read_excel(excel_file, sheet_name="BIEU_DO_B", header=2)
        period_frame = pd.read_excel(excel_file, sheet_name="PERIOD_CATALOG", header=0)
        demand_frame = pd.read_excel(
            excel_file,
            sheet_name="SAN_LUONG_MULTI_PERIOD",
            header=0,
        )
        profile_frame = pd.read_excel(
            excel_file,
            sheet_name="DEMAND_PROFILE_CONFIG",
            header=0,
        )
        metadata_frame = pd.read_excel(
            excel_file,
            sheet_name="THONG_TIN_DU_LIEU",
            header=1,
        )
    parameters_b = _parameters(parameter_frame, "B")
    base = ImportedWorkbook(
        parameters_a=None,
        trips_a=[],
        parameters_b=parameters_b,
        trips_b=_trips(timetable_frame, "B"),
        demand=[],
        configuration={},
        authority_metadata=(
            _authority_metadata(metadata_frame)
            if not metadata_frame.dropna(how="all").empty
            else WorkbookAuthorityMetadata()
        ),
    )
    periods = _attach_observations(_period_catalog(period_frame), demand_frame)
    profiles = _profiles(profile_frame)
    metadata = _key_value_sheet(metadata_frame, "THONG_TIN_DU_LIEU")
    demand_dataset_id = _clean(metadata.get("demand_dataset_id"))
    if demand_dataset_id is None or not str(demand_dataset_id).strip():
        raise MultiPeriodDemandError(
            "DEMAND_DATASET_ID_MISSING",
            "THONG_TIN_DU_LIEU requires demand_dataset_id",
        )
    default_profile = _clean(metadata.get("default_demand_profile"))
    sensitivity_profiles = _split_ids(metadata.get("sensitivity_profiles"))
    demand_input = validate_multi_period_demand_input_v1(
        MultiPeriodDemandInputV1(
            demand_dataset_id=str(demand_dataset_id).strip(),
            periods=periods,
            profiles=profiles,
            default_profile_id=(
                str(default_profile).strip() if default_profile is not None else None
            ),
            sensitivity_profile_ids=sensitivity_profiles,
        )
    )
    return ImportedV3WorkbookV1(
        base_workbook=base,
        multi_period_demand=demand_input,
    )


__all__ = [
    "V3_MULTI_PERIOD_RUNNER_PROFILE_V1",
    "ImportedV3WorkbookV1",
    "import_v3_multi_period_workbook_v1",
]

"""Source-specific ingestion for the T06/T10 trip-level ticketing workbook.

Workbook parsing is kept outside the canonical regime selector.  Multiple trip
rows in one date/direction/bucket are legitimate and are summed.  Empty buckets
are emitted as observed zero only for dates whose trip manifest matches the
deterministic modal daily trip count and has no invalid, duplicate, or off-grid
source rows.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from numbers import Real
from pathlib import Path

import pandas as pd

from .contracts_v1.demand_regimes import DailyDemandObservationV1
from .contracts_v1.models import ContractDirection
from .contracts_v1.multi_period_demand import DemandProfileV1
from .time_utils import parse_time_to_seconds

RAW_T06_T10_ADAPTER_PROFILE_V1 = "raw_t06_t10_daily_demand_adapter_v1"
RAW_T06_T10_SHEET_V1 = "Sheet1"

_REQUIRED_COLUMNS = (
    "Ngày",
    "SHT",
    "Tên tuyến",
    "Đầu bến",
    "Hướng đi",
    "BSX",
    "Giờ đi KH",
    "Giờ về KH",
    "Giờ đi HT",
    "Giờ về HT",
    "Vé lượt",
    "Vé HSSV",
    "Vé bán trước",
    "Vé miễn",
    "Tổng vé",
)

_DIRECTION_MAP = {
    (
        6,
        "Lượt đi: Bến xe buýt Chợ Lớn - Đại học Nông Lâm",
    ): ContractDirection.OUTBOUND,
    (
        6,
        "Lượt về: Đại học Nông Lâm - Bến xe buýt Chợ Lớn",
    ): ContractDirection.INBOUND,
    (
        10,
        "Lượt đi: Bến xe buýt ĐH Quốc gia TPHCM (mới) - Bến xe Miền Tây",
    ): ContractDirection.OUTBOUND,
    (
        10,
        "Lượt về: Bến xe Miền Tây - Bến xe buýt ĐH Quốc gia TPHCM (mới)",
    ): ContractDirection.INBOUND,
}


class RawDailyDemandImportError(ValueError):
    """Fail-closed raw-source error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class RawDailyDemandDirectionAuditV1:
    direction: ContractDirection
    raw_row_count: int
    raw_date_count: int
    minimum_date: date | None
    maximum_date: date | None
    expected_bucket_count_per_date: int
    expected_trip_rows_per_complete_date: int | None
    complete_date_count: int
    incomplete_dates: tuple[date, ...]
    missing_service_dates: tuple[date, ...]
    duplicate_source_row_count: int
    duplicate_canonical_observation_count: int
    invalid_demand_row_count: int
    invalid_time_row_count: int
    fallback_to_planned_time_row_count: int
    off_grid_row_count: int
    multirow_bucket_group_count: int
    observed_zero_bucket_count: int


@dataclass(frozen=True, slots=True)
class RawDailyDemandRouteV1:
    route_id: str
    route_names: tuple[str, ...]
    observed_dates: tuple[date, ...]
    daily_observations: tuple[DailyDemandObservationV1, ...]
    direction_audits: tuple[RawDailyDemandDirectionAuditV1, ...]


@dataclass(frozen=True, slots=True)
class RawDailyDemandImportResultV1:
    adapter_profile: str
    source_file: str
    source_sha256: str
    sheet_name: str
    sheet_row_count: int
    sheet_column_count: int
    source_minimum_date: date
    source_maximum_date: date
    source_route_ids: tuple[str, ...]
    selected_period_start: date
    selected_period_end: date
    raw_time_granularity_seconds: int
    unknown_direction_row_count: int
    routes: tuple[RawDailyDemandRouteV1, ...]


@dataclass(frozen=True, slots=True)
class RawDemandReconciliationBucketV1:
    direction: ContractDirection
    interval_start: int
    interval_end: int
    raw_derived_average: float
    v3_average_day: float
    absolute_difference: float
    relative_difference: float | None


@dataclass(frozen=True, slots=True)
class RawDemandReconciliationV1:
    route_id: str
    compared_bucket_count: int
    raw_complete_date_counts: tuple[tuple[ContractDirection, int], ...]
    maximum_absolute_difference: float
    maximum_relative_difference: float
    mismatched_bucket_count: int
    buckets: tuple[RawDemandReconciliationBucketV1, ...]


def _strict_route_id(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        try:
            numeric = float(str(value).strip())
        except (TypeError, ValueError):
            return None
    else:
        numeric = float(value)
    return int(numeric) if math.isfinite(numeric) and numeric.is_integer() else None


def _source_date(value: object) -> date | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        parsed = pd.to_datetime(value, errors="raise")
    except (TypeError, ValueError):
        return None
    return parsed.date()


def _finite_nonnegative(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) and numeric >= 0 else None


def _optional_time(value: object) -> int | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return parse_time_to_seconds(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=4)
def _read_source(path: str, size: int, modified_ns: int) -> pd.DataFrame:
    del size, modified_ns
    try:
        frame = pd.read_excel(path, sheet_name=RAW_T06_T10_SHEET_V1, dtype=object)
    except (OSError, ValueError) as exc:
        raise RawDailyDemandImportError("RAW_WORKBOOK_READ_FAILED", str(exc)) from exc
    missing = set(_REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise RawDailyDemandImportError(
            "RAW_WORKBOOK_SCHEMA_INVALID",
            "missing required columns: " + ", ".join(sorted(missing)),
        )
    return frame.loc[:, _REQUIRED_COLUMNS]


def _canonical_grid(profile: DemandProfileV1) -> tuple[tuple[int, int], ...]:
    grid = tuple(
        sorted({(item.interval_start, item.interval_end) for item in profile.derived_observations})
    )
    if not grid:
        raise RawDailyDemandImportError(
            "CANONICAL_DEMAND_GRID_MISSING",
            "the V3 profile has no canonical demand buckets",
        )
    for index, (start, end) in enumerate(grid):
        if end <= start or (index and start != grid[index - 1][1]):
            raise RawDailyDemandImportError(
                "CANONICAL_DEMAND_GRID_INVALID",
                "the V3 demand buckets must form one contiguous grid",
            )
    durations = {end - start for start, end in grid}
    if len(durations) != 1:
        raise RawDailyDemandImportError(
            "CANONICAL_DEMAND_GRID_INVALID",
            "the raw adapter requires equal canonical bucket durations",
        )
    return grid


def _calendar_dates(start: date, end: date) -> tuple[date, ...]:
    return tuple(start + timedelta(days=index) for index in range((end - start).days + 1))


def _modal_positive_count(counts: Counter[date]) -> int | None:
    frequencies = Counter(counts.values())
    return min(frequencies, key=lambda value: (-frequencies[value], value)) if frequencies else None


def _bucket_index(grid: tuple[tuple[int, int], ...], seconds: int) -> int | None:
    for index, (start, end) in enumerate(grid):
        if start <= seconds < end:
            return index
    return None


def import_t06_t10_daily_demand_v1(
    source: str | Path,
    profile: DemandProfileV1,
    *,
    period_start: date,
    period_end: date,
    route_ids: tuple[str, ...] = ("6", "10"),
) -> RawDailyDemandImportResultV1:
    """Aggregate complete trip manifests into canonical date-keyed demand buckets."""

    if period_end < period_start:
        raise ValueError("period_end must not precede period_start")
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    stat = path.stat()
    frame = _read_source(str(path), stat.st_size, stat.st_mtime_ns).copy()
    grid = _canonical_grid(profile)
    route_filter = {int(item) for item in route_ids}
    frame["_source_date"] = frame["Ngày"].map(_source_date)
    if frame["_source_date"].isna().any():
        raise RawDailyDemandImportError(
            "RAW_SERVICE_DATE_INVALID",
            f"{int(frame['_source_date'].isna().sum())} source rows have invalid dates",
        )
    frame["_route_id"] = frame["SHT"].map(_strict_route_id)
    source_dates = tuple(frame["_source_date"])
    source_routes = tuple(
        str(item) for item in sorted({item for item in frame["_route_id"] if item is not None})
    )
    selected = frame[
        frame["_route_id"].isin(route_filter)
        & (frame["_source_date"] >= period_start)
        & (frame["_source_date"] <= period_end)
    ].copy()
    selected["_direction"] = [
        _DIRECTION_MAP.get((int(route), str(direction).strip()))
        for route, direction in zip(selected["_route_id"], selected["Hướng đi"], strict=True)
    ]
    selected["_demand"] = selected["Tổng vé"].map(_finite_nonnegative)
    selected["_actual_time"] = selected["Giờ đi HT"].map(_optional_time)
    selected["_planned_time"] = selected["Giờ đi KH"].map(_optional_time)
    selected["_demand_time"] = selected["_actual_time"].where(
        selected["_actual_time"].notna(), selected["_planned_time"]
    )
    selected["_bucket_index"] = [
        _bucket_index(grid, int(value)) if value is not None and not pd.isna(value) else None
        for value in selected["_demand_time"]
    ]
    selected["_exact_duplicate"] = selected.duplicated(subset=list(_REQUIRED_COLUMNS), keep=False)
    unknown_direction_count = int(selected["_direction"].isna().sum())
    calendar = _calendar_dates(period_start, period_end)
    routes: list[RawDailyDemandRouteV1] = []
    for route_id in sorted(route_filter):
        route_frame = selected[selected["_route_id"] == route_id]
        observed_dates = tuple(sorted(set(route_frame["_source_date"])))
        observations: list[DailyDemandObservationV1] = []
        audits: list[RawDailyDemandDirectionAuditV1] = []
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
            group = route_frame[route_frame["_direction"] == direction]
            daily_counts = Counter(group["_source_date"])
            expected_trip_count = _modal_positive_count(daily_counts)
            missing_dates = tuple(item for item in calendar if item not in daily_counts)
            duplicate_dates = set(group.loc[group["_exact_duplicate"], "_source_date"])
            invalid_demand_dates = set(group.loc[group["_demand"].isna(), "_source_date"])
            invalid_time_dates = set(group.loc[group["_demand_time"].isna(), "_source_date"])
            off_grid_dates = set(group.loc[group["_bucket_index"].isna(), "_source_date"])
            complete_dates = tuple(
                item
                for item in calendar
                if expected_trip_count is not None
                and daily_counts[item] == expected_trip_count
                and item not in duplicate_dates
                and item not in invalid_demand_dates
                and item not in invalid_time_dates
                and item not in off_grid_dates
            )
            complete_set = set(complete_dates)
            incomplete_dates = tuple(item for item in calendar if item not in complete_set)
            bucket_group_sizes = Counter(
                (source_date, int(bucket_index))
                for source_date, bucket_index in group[
                    ["_source_date", "_bucket_index"]
                ].itertuples(index=False, name=None)
                if source_date in complete_set and bucket_index is not None
            )
            observed_zero_count = 0
            for observed_date in complete_dates:
                values = [0.0] * len(grid)
                day_rows = group[group["_source_date"] == observed_date]
                for bucket_index, demand in day_rows[["_bucket_index", "_demand"]].itertuples(
                    index=False, name=None
                ):
                    values[int(bucket_index)] += float(demand)
                observed_zero_count += sum(value == 0 for value in values)
                observations.extend(
                    DailyDemandObservationV1(
                        observation_date=observed_date,
                        direction=direction,
                        interval_start=start,
                        interval_end=end,
                        passenger_demand=values[index],
                    )
                    for index, (start, end) in enumerate(grid)
                )
            audits.append(
                RawDailyDemandDirectionAuditV1(
                    direction=direction,
                    raw_row_count=len(group),
                    raw_date_count=len(daily_counts),
                    minimum_date=min(daily_counts) if daily_counts else None,
                    maximum_date=max(daily_counts) if daily_counts else None,
                    expected_bucket_count_per_date=len(grid),
                    expected_trip_rows_per_complete_date=expected_trip_count,
                    complete_date_count=len(complete_dates),
                    incomplete_dates=incomplete_dates,
                    missing_service_dates=missing_dates,
                    duplicate_source_row_count=int(
                        group.duplicated(subset=list(_REQUIRED_COLUMNS)).sum()
                    ),
                    duplicate_canonical_observation_count=0,
                    invalid_demand_row_count=int(group["_demand"].isna().sum()),
                    invalid_time_row_count=int(group["_demand_time"].isna().sum()),
                    fallback_to_planned_time_row_count=int(group["_actual_time"].isna().sum()),
                    off_grid_row_count=int(group["_bucket_index"].isna().sum()),
                    multirow_bucket_group_count=sum(
                        size > 1 for size in bucket_group_sizes.values()
                    ),
                    observed_zero_bucket_count=observed_zero_count,
                )
            )
        routes.append(
            RawDailyDemandRouteV1(
                route_id=str(route_id),
                route_names=tuple(sorted(str(item) for item in route_frame["Tên tuyến"].unique())),
                observed_dates=observed_dates,
                daily_observations=tuple(
                    sorted(
                        observations,
                        key=lambda item: (
                            item.observation_date,
                            item.direction.value,
                            item.interval_start,
                            item.interval_end,
                        ),
                    )
                ),
                direction_audits=tuple(audits),
            )
        )
    demand_times = tuple(int(item) for item in selected["_demand_time"].dropna().tolist())
    time_gcd = 0
    for value in demand_times:
        time_gcd = math.gcd(time_gcd, value)
    return RawDailyDemandImportResultV1(
        adapter_profile=RAW_T06_T10_ADAPTER_PROFILE_V1,
        source_file=path.name,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        sheet_name=RAW_T06_T10_SHEET_V1,
        sheet_row_count=len(frame),
        sheet_column_count=len(frame.columns) - 2,
        source_minimum_date=min(source_dates),
        source_maximum_date=max(source_dates),
        source_route_ids=source_routes,
        selected_period_start=period_start,
        selected_period_end=period_end,
        raw_time_granularity_seconds=time_gcd,
        unknown_direction_row_count=unknown_direction_count,
        routes=tuple(routes),
    )


def reconcile_raw_daily_demand_v1(
    route: RawDailyDemandRouteV1,
    profile: DemandProfileV1,
    *,
    epsilon: float = 1e-9,
) -> RawDemandReconciliationV1:
    """Compare complete raw daily averages with the V3 aggregate profile."""

    complete_counts = {item.direction: item.complete_date_count for item in route.direction_audits}
    sums: dict[tuple[ContractDirection, int, int], float] = defaultdict(float)
    for item in route.daily_observations:
        sums[(item.direction, item.interval_start, item.interval_end)] += item.passenger_demand
    rows: list[RawDemandReconciliationBucketV1] = []
    for item in sorted(
        profile.derived_observations,
        key=lambda value: (value.direction.value, value.interval_start, value.interval_end),
    ):
        count = complete_counts.get(item.direction, 0)
        if count == 0:
            raise RawDailyDemandImportError(
                "RAW_RECONCILIATION_DAYS_MISSING",
                f"route {route.route_id} {item.direction.value} has no complete raw days",
            )
        raw_average = sums[(item.direction, item.interval_start, item.interval_end)] / count
        difference = raw_average - item.average_daily_passengers
        relative = (
            abs(difference) / abs(item.average_daily_passengers)
            if item.average_daily_passengers != 0
            else None
        )
        rows.append(
            RawDemandReconciliationBucketV1(
                direction=item.direction,
                interval_start=item.interval_start,
                interval_end=item.interval_end,
                raw_derived_average=raw_average,
                v3_average_day=item.average_daily_passengers,
                absolute_difference=abs(difference),
                relative_difference=relative,
            )
        )
    return RawDemandReconciliationV1(
        route_id=route.route_id,
        compared_bucket_count=len(rows),
        raw_complete_date_counts=tuple(
            (direction, complete_counts[direction])
            for direction in sorted(complete_counts, key=lambda item: item.value)
        ),
        maximum_absolute_difference=max((item.absolute_difference for item in rows), default=0.0),
        maximum_relative_difference=max(
            (item.relative_difference or 0.0 for item in rows), default=0.0
        ),
        mismatched_bucket_count=sum(item.absolute_difference > epsilon for item in rows),
        buckets=tuple(rows),
    )


def raw_daily_demand_to_dict_v1(value: object) -> dict[str, object]:
    """Stable JSON-ready conversion for raw import and reconciliation evidence."""

    def convert(item: object) -> object:
        if isinstance(item, StrEnum):
            return item.value
        if isinstance(item, date):
            return item.isoformat()
        if isinstance(item, dict):
            return {str(key): convert(nested) for key, nested in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(nested) for nested in item]
        return item

    return convert(asdict(value))  # type: ignore[arg-type,return-value]


__all__ = [
    "RAW_T06_T10_ADAPTER_PROFILE_V1",
    "RAW_T06_T10_SHEET_V1",
    "RawDailyDemandDirectionAuditV1",
    "RawDailyDemandImportError",
    "RawDailyDemandImportResultV1",
    "RawDailyDemandRouteV1",
    "RawDemandReconciliationBucketV1",
    "RawDemandReconciliationV1",
    "import_t06_t10_daily_demand_v1",
    "raw_daily_demand_to_dict_v1",
    "reconcile_raw_daily_demand_v1",
]

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import bus_schedule_engine.raw_daily_demand as raw_module
from bus_schedule_engine.contracts_v1.demand_regimes import (
    DemandRegimeDetectorConfigV1,
    demand_regime_model_selection_to_dict_v1,
    select_demand_regime_model_v1,
)
from bus_schedule_engine.contracts_v1.models import ContractDirection
from bus_schedule_engine.contracts_v1.multi_period_demand import (
    DemandDirectionGrainV1,
    DemandProfileAggregationMethodV1,
    DemandProfileV1,
    DerivedDemandObservationV1,
)
from bus_schedule_engine.raw_daily_demand import (
    import_t06_t10_daily_demand_v1,
    reconcile_raw_daily_demand_v1,
)

RAW_COLUMNS = (
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

DIRECTIONS = {
    (6, ContractDirection.OUTBOUND): (
        "Bến xe buýt Chợ Lớn - Đại học Nông Lâm",
        "Bến xe buýt Chợ Lớn",
        "Lượt đi: Bến xe buýt Chợ Lớn - Đại học Nông Lâm",
    ),
    (6, ContractDirection.INBOUND): (
        "Bến xe buýt Chợ Lớn - Đại học Nông Lâm",
        "BẾN XE BUÝT ĐẠI HỌC NÔNG LÂM",
        "Lượt về: Đại học Nông Lâm - Bến xe buýt Chợ Lớn",
    ),
    (10, ContractDirection.OUTBOUND): (
        "Đại học Quốc Gia - Bến xe Miền Tây",
        "Bến xe buýt Khu A - Đại học Quốc gia TP.HCM",
        "Lượt đi: Bến xe buýt ĐH Quốc gia TPHCM (mới) - Bến xe Miền Tây",
    ),
    (10, ContractDirection.INBOUND): (
        "Đại học Quốc Gia - Bến xe Miền Tây",
        "Bến xe Miền Tây",
        "Lượt về: Bến xe Miền Tây - Bến xe buýt ĐH Quốc gia TPHCM (mới)",
    ),
}


def _row(
    service_date: date,
    route_id: int,
    direction: ContractDirection,
    departure: str,
    demand: float,
    *,
    vehicle: str,
    actual: str | None = None,
) -> dict[str, object]:
    route_name, terminal, source_direction = DIRECTIONS[(route_id, direction)]
    return {
        "Ngày": service_date,
        "SHT": route_id,
        "Tên tuyến": route_name,
        "Đầu bến": terminal,
        "Hướng đi": source_direction,
        "BSX": vehicle,
        "Giờ đi KH": departure,
        "Giờ về KH": "07:00:00",
        "Giờ đi HT": actual if actual is not None else departure,
        "Giờ về HT": "07:00:00",
        "Vé lượt": demand,
        "Vé HSSV": 0,
        "Vé bán trước": 0,
        "Vé miễn": 0,
        "Tổng vé": demand,
    }


def _profile(values: dict[ContractDirection, tuple[float, ...]]) -> DemandProfileV1:
    starts = tuple((4 * 60 + 30 + index * 30) * 60 for index in range(4))
    return DemandProfileV1(
        profile_id="raw-fixture-profile",
        included_period_ids=("raw-fixture-period",),
        aggregation_method=DemandProfileAggregationMethodV1.SINGLE_PERIOD,
        period_weight_method="observation_days",
        total_observation_days=7,
        direction_grain=DemandDirectionGrainV1.DIRECTIONAL,
        derived_observations=tuple(
            DerivedDemandObservationV1(
                direction=direction,
                interval_start=start,
                interval_end=start + 30 * 60,
                average_daily_passengers=demand,
            )
            for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
            for start, demand in zip(starts, values[direction], strict=True)
        ),
        source_period_fingerprints=(("raw-fixture-period", "abc"),),
        limitations=(),
        profile_fingerprint="raw-fixture-profile-fingerprint",
    )


def _source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, object]],
) -> Path:
    frame = pd.DataFrame(rows, columns=RAW_COLUMNS)
    monkeypatch.setattr(raw_module, "_read_source", lambda *_: frame.copy())
    path = tmp_path / "T06&T10_01012025_31072026.xlsx"
    path.write_bytes(b"controlled raw fixture")
    return path


def test_dates_routes_directions_and_multirow_buckets_are_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = date(2026, 3, 1)
    rows = []
    for day_index in range(2):
        observed_date = first + timedelta(days=day_index)
        for route_id in (6, 10):
            for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
                rows.extend(
                    [
                        _row(
                            observed_date,
                            route_id,
                            direction,
                            "04:35:00",
                            route_id + day_index,
                            vehicle=f"{route_id}-{direction.value}-a",
                        ),
                        _row(
                            observed_date,
                            route_id,
                            direction,
                            "04:50:00",
                            1,
                            vehicle=f"{route_id}-{direction.value}-b",
                        ),
                    ]
                )
    profile = _profile(
        {
            ContractDirection.OUTBOUND: (0, 0, 0, 0),
            ContractDirection.INBOUND: (0, 0, 0, 0),
        }
    )
    source = _source(tmp_path, monkeypatch, rows)

    result = import_t06_t10_daily_demand_v1(
        source,
        profile,
        period_start=first,
        period_end=first + timedelta(days=1),
    )

    assert [item.route_id for item in result.routes] == ["6", "10"]
    route_6, route_10 = result.routes
    assert (
        route_6.observed_dates
        == route_10.observed_dates
        == (
            first,
            first + timedelta(days=1),
        )
    )
    route_6_first = [
        item
        for item in route_6.daily_observations
        if item.observation_date == first and item.direction == ContractDirection.OUTBOUND
    ]
    route_10_first = [
        item
        for item in route_10.daily_observations
        if item.observation_date == first and item.direction == ContractDirection.OUTBOUND
    ]
    assert [item.passenger_demand for item in route_6_first] == [7, 0, 0, 0]
    assert [item.passenger_demand for item in route_10_first] == [11, 0, 0, 0]
    assert {item.direction for item in route_6.daily_observations} == {
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
    }
    assert route_6.direction_audits[0].multirow_bucket_group_count == 2


def test_incomplete_or_absent_dates_are_not_silently_zero_filled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = date(2026, 3, 1)
    rows = []
    for day_index, trip_count in enumerate((2, 2, 1)):
        observed_date = first + timedelta(days=day_index)
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
            for trip_index in range(trip_count):
                rows.append(
                    _row(
                        observed_date,
                        6,
                        direction,
                        f"04:{35 + trip_index * 10:02d}:00",
                        10,
                        vehicle=f"6-{direction.value}-{day_index}-{trip_index}",
                    )
                )
    profile = _profile(
        {
            ContractDirection.OUTBOUND: (0, 0, 0, 0),
            ContractDirection.INBOUND: (0, 0, 0, 0),
        }
    )
    source = _source(tmp_path, monkeypatch, rows)

    route = import_t06_t10_daily_demand_v1(
        source,
        profile,
        period_start=first,
        period_end=first + timedelta(days=3),
        route_ids=("6",),
    ).routes[0]

    assert route.observed_dates == tuple(first + timedelta(days=index) for index in range(3))
    assert {item.observation_date for item in route.daily_observations} == {
        first,
        first + timedelta(days=1),
    }
    assert all(item.complete_date_count == 2 for item in route.direction_audits)
    assert all(
        item.incomplete_dates == (first + timedelta(days=2), first + timedelta(days=3))
        for item in route.direction_audits
    )
    assert all(
        item.missing_service_dates == (first + timedelta(days=3),)
        for item in route.direction_audits
    )


def test_controlled_daily_profiles_reconcile_exactly_and_are_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = date(2026, 3, 1)
    rows = []
    outbound = (10.0, 10.0, 100.0, 100.0)
    inbound = (20.0, 20.0, 80.0, 80.0)
    starts = ("04:35:00", "05:05:00", "05:35:00", "06:05:00")
    for day_index in range(7):
        observed_date = first + timedelta(days=day_index)
        for direction, values in (
            (ContractDirection.OUTBOUND, outbound),
            (ContractDirection.INBOUND, inbound),
        ):
            rows.extend(
                _row(
                    observed_date,
                    6,
                    direction,
                    departure,
                    demand,
                    vehicle=f"6-{direction.value}-{day_index}-{trip_index}",
                )
                for trip_index, (departure, demand) in enumerate(zip(starts, values, strict=True))
            )
    profile = _profile(
        {
            ContractDirection.OUTBOUND: outbound,
            ContractDirection.INBOUND: inbound,
        }
    )
    source = _source(tmp_path, monkeypatch, rows)

    serialized = set()
    for _ in range(10):
        route = import_t06_t10_daily_demand_v1(
            source,
            profile,
            period_start=first,
            period_end=first + timedelta(days=6),
            route_ids=("6",),
        ).routes[0]
        reconciliation = reconcile_raw_daily_demand_v1(route, profile)
        assert reconciliation.maximum_absolute_difference == 0
        assert reconciliation.mismatched_bucket_count == 0
        selection = select_demand_regime_model_v1(
            profile,
            route.daily_observations,
            DemandRegimeDetectorConfigV1(
                target_min_regime_minutes=30,
                min_validation_days=7,
            ),
            observed_dates=route.observed_dates,
        )
        serialized.add(
            json.dumps(
                demand_regime_model_selection_to_dict_v1(selection),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    assert len(serialized) == 1

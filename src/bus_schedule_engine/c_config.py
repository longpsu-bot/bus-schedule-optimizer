from __future__ import annotations

from dataclasses import dataclass, fields

FIXED_RESOURCE_STRATEGY_ID = "fixed_resource_redistribution"
SCENARIO_C_DISPLAY_NAME = "C — Tái phân bổ ổn định theo nhu cầu"
SCENARIO_B_DISPLAY_NAME = "B — Biểu đồ giờ đề xuất"


@dataclass(frozen=True)
class ScenarioCConfig:
    direction_trip_lock_mode: str = "fixed_by_direction"
    lock_first_departures: bool = True
    lock_last_departures: bool = True
    headway_rounding_tolerance_minutes: int = 1
    minimum_departures_per_normal_regime: int = 3
    minimum_regime_duration_minutes: int = 60
    maximum_headway_regimes_per_direction: int = 6
    maximum_transition_headways_per_boundary: int = 1
    maximum_transition_deviation_minutes: int = 5
    minimum_sustained_change_intervals: int = 2
    minimum_material_headway_change_minutes: int = 5
    minimum_material_service_rate_change_ratio: float = 0.15
    preferred_max_shift_per_trip_minutes: int = 15
    absolute_max_shift_per_trip_minutes: int = 30
    final_service_block_minutes: int = 90
    configuration_version: str = "scenario_c_regimes_v1"

    @classmethod
    def from_mapping(cls, values: dict[str, object] | None) -> ScenarioCConfig:
        if not values:
            return cls()
        converters = {
            "direction_trip_lock_mode": str,
            "lock_first_departures": _as_bool,
            "lock_last_departures": _as_bool,
            "headway_rounding_tolerance_minutes": int,
            "minimum_departures_per_normal_regime": int,
            "minimum_regime_duration_minutes": int,
            "maximum_headway_regimes_per_direction": int,
            "maximum_transition_headways_per_boundary": int,
            "maximum_transition_deviation_minutes": int,
            "minimum_sustained_change_intervals": int,
            "minimum_material_headway_change_minutes": int,
            "minimum_material_service_rate_change_ratio": float,
            "preferred_max_shift_per_trip_minutes": int,
            "absolute_max_shift_per_trip_minutes": int,
            "final_service_block_minutes": int,
            "configuration_version": str,
        }
        allowed = {item.name for item in fields(cls)}
        overrides = {
            key: converters[key](value)
            for key, value in values.items()
            if key in allowed and value is not None
        }
        config = cls(**overrides)
        if config.direction_trip_lock_mode != "fixed_by_direction":
            raise ValueError(
                "MVP chỉ cho phép direction_trip_lock_mode=total_only khi người dùng bật rõ "
                "và có nhu cầu theo chiều đáng tin cậy."
            )
        return config


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "có", "co"}:
        return True
    if normalized in {"0", "false", "no", "n", "không", "khong"}:
        return False
    raise ValueError(f"Giá trị boolean không hợp lệ: {value}")

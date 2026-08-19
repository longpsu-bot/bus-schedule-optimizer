"""Versioned multi-period demand contracts and deterministic profile derivation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date
from enum import StrEnum

from .models import ContractDirection, VolumeClassification
from .serialization import canonical_sha256
from .solver_problem import jsonable

MULTI_PERIOD_DEMAND_INPUT_PROFILE_V1 = "multi_period_demand_input_v1"
DEMAND_PROFILE_DERIVATION_PROFILE_V1 = "demand_profile_derivation_v1"
DEMAND_PERIOD_FINGERPRINT_PROFILE_V1 = "demand_observation_period_v1"
DEMAND_PROFILE_FINGERPRINT_PROFILE_V1 = "demand_profile_v1"
MULTI_PERIOD_STRUCTURAL_CHANGE_DETECTED = "MULTI_PERIOD_STRUCTURAL_CHANGE_DETECTED"
DEFAULT_SHAPE_DISTANCE_THRESHOLD_V1 = 0.15


class DemandProfileAggregationMethodV1(StrEnum):
    SINGLE_PERIOD = "single_period"
    DAY_WEIGHTED_MEAN = "day_weighted_mean"


class DemandDirectionGrainV1(StrEnum):
    DIRECTIONAL = "directional"
    COMBINED = "combined"


class MultiPeriodDemandError(ValueError):
    """Fail-closed validation or derivation error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class DemandPeriodObservationV1:
    interval_start: int
    interval_end: int
    direction: ContractDirection
    passenger_volume: float
    volume_classification: VolumeClassification
    source_time_basis: str
    source_dataset_id: str

    def average_daily_passengers(self, observation_days: int) -> float:
        if self.volume_classification == VolumeClassification.AVERAGE_DAY:
            return float(self.passenger_volume)
        if observation_days <= 0:
            raise MultiPeriodDemandError(
                "OBSERVATION_DAYS_INVALID",
                "observation_days must be positive before total-period normalization",
            )
        return float(self.passenger_volume) / observation_days


@dataclass(frozen=True, slots=True)
class DemandObservationPeriodV1:
    period_id: str
    period_start: date
    period_end: date
    observation_days: int
    observations: tuple[DemandPeriodObservationV1, ...]
    source_dataset_id: str
    period_role: str
    status: str
    period_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class DemandProfileConfigV1:
    profile_id: str
    included_period_ids: tuple[str, ...]
    aggregation_method: DemandProfileAggregationMethodV1
    period_weight: str
    authority_role: str
    status: str
    description: str


@dataclass(frozen=True, slots=True)
class DerivedDemandObservationV1:
    direction: ContractDirection
    interval_start: int
    interval_end: int
    average_daily_passengers: float


@dataclass(frozen=True, slots=True)
class DemandProfileV1:
    profile_id: str
    included_period_ids: tuple[str, ...]
    aggregation_method: DemandProfileAggregationMethodV1
    period_weight_method: str
    total_observation_days: int
    direction_grain: DemandDirectionGrainV1
    derived_observations: tuple[DerivedDemandObservationV1, ...]
    source_period_fingerprints: tuple[tuple[str, str], ...]
    limitations: tuple[str, ...]
    profile_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class DemandPeriodShapeDiagnosticV1:
    period_id: str
    direction: ContractDirection
    average_daily_passengers: float
    normalized_block_shares: tuple[tuple[int, int, float], ...]
    peak_block_start: int
    peak_block_end: int
    peak_share: float
    compared_period_id: str | None
    maximum_shape_distance: float
    shape_distance_threshold: float
    structural_change_detected: bool


@dataclass(frozen=True, slots=True)
class DemandProfileDerivationResultV1:
    profile: DemandProfileV1
    period_diagnostics: tuple[DemandPeriodShapeDiagnosticV1, ...]
    diagnostic_codes: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MultiPeriodDemandInputV1:
    demand_dataset_id: str
    periods: tuple[DemandObservationPeriodV1, ...]
    profiles: tuple[DemandProfileConfigV1, ...]
    default_profile_id: str | None = None
    sensitivity_profile_ids: tuple[str, ...] = ()
    contract_profile: str = MULTI_PERIOD_DEMAND_INPUT_PROFILE_V1


def _period_payload(period: DemandObservationPeriodV1) -> dict[str, object]:
    payload = jsonable(asdict(period))
    payload.pop("period_fingerprint", None)
    payload["period_start"] = period.period_start.isoformat()
    payload["period_end"] = period.period_end.isoformat()
    payload["observations"] = [
        {
            "interval_start": item.interval_start,
            "interval_end": item.interval_end,
            "direction": item.direction.value,
            "passenger_volume": item.passenger_volume,
            "volume_classification": item.volume_classification.value,
            "source_time_basis": item.source_time_basis,
            "source_dataset_id": item.source_dataset_id,
        }
        for item in period.observations
    ]
    return {
        "fingerprint_profile": DEMAND_PERIOD_FINGERPRINT_PROFILE_V1,
        "period": payload,
    }


def calculate_demand_period_fingerprint_v1(period: DemandObservationPeriodV1) -> str:
    return canonical_sha256(_period_payload(period))


def _validate_period(period: DemandObservationPeriodV1) -> None:
    if not period.period_id.strip():
        raise MultiPeriodDemandError("PERIOD_ID_MISSING", "period_id is required")
    if period.period_end < period.period_start:
        raise MultiPeriodDemandError(
            "PERIOD_DATE_RANGE_INVALID",
            f"period {period.period_id} has period_end before period_start",
        )
    if period.observation_days <= 0:
        raise MultiPeriodDemandError(
            "OBSERVATION_DAYS_INVALID",
            f"period {period.period_id} requires positive observation_days",
        )
    if not period.observations:
        raise MultiPeriodDemandError(
            "PERIOD_OBSERVATIONS_MISSING",
            f"period {period.period_id} has no demand observations",
        )
    if not period.source_dataset_id.strip():
        raise MultiPeriodDemandError(
            "SOURCE_DATASET_ID_MISSING",
            f"period {period.period_id} requires source_dataset_id",
        )

    interval_counts: Counter[tuple[ContractDirection, int, int]] = Counter()
    by_direction: dict[ContractDirection, list[DemandPeriodObservationV1]] = defaultdict(list)
    for observation in period.observations:
        if not (0 <= observation.interval_start < observation.interval_end <= 24 * 3600):
            raise MultiPeriodDemandError(
                "TIME_BLOCK_BOUNDARY_INVALID",
                f"period {period.period_id} contains an invalid time block",
            )
        if not observation.source_time_basis.strip():
            raise MultiPeriodDemandError(
                "SOURCE_TIME_BASIS_MISSING",
                f"period {period.period_id} contains a blank source_time_basis",
            )
        if observation.source_dataset_id != period.source_dataset_id:
            raise MultiPeriodDemandError(
                "PERIOD_SOURCE_DATASET_MISMATCH",
                f"period {period.period_id} row source_dataset_id differs from catalog",
            )
        interval_counts[
            (observation.direction, observation.interval_start, observation.interval_end)
        ] += 1
        by_direction[observation.direction].append(observation)

    if any(count > 1 for count in interval_counts.values()):
        raise MultiPeriodDemandError(
            "DUPLICATE_SOURCE_INTERVAL",
            f"period {period.period_id} contains a duplicate source interval",
        )
    for direction, observations in by_direction.items():
        ordered = sorted(
            observations,
            key=lambda item: (item.interval_start, item.interval_end),
        )
        for left, right in zip(ordered, ordered[1:], strict=False):
            if right.interval_start < left.interval_end:
                raise MultiPeriodDemandError(
                    "OVERLAPPING_DEMAND_INTERVALS",
                    f"period {period.period_id} has overlapping {direction.value} intervals",
                )


def finalize_demand_observation_period_v1(
    period: DemandObservationPeriodV1,
) -> DemandObservationPeriodV1:
    _validate_period(period)
    fingerprint = calculate_demand_period_fingerprint_v1(period)
    if period.period_fingerprint and period.period_fingerprint != fingerprint:
        raise MultiPeriodDemandError(
            "PERIOD_FINGERPRINT_INVALID",
            f"period {period.period_id} fingerprint does not match its authority payload",
        )
    return replace(period, period_fingerprint=fingerprint)


def validate_multi_period_demand_input_v1(
    demand_input: MultiPeriodDemandInputV1,
) -> MultiPeriodDemandInputV1:
    if demand_input.contract_profile != MULTI_PERIOD_DEMAND_INPUT_PROFILE_V1:
        raise MultiPeriodDemandError(
            "MULTI_PERIOD_CONTRACT_PROFILE_INVALID",
            "unsupported multi-period demand contract profile",
        )
    if not demand_input.demand_dataset_id.strip():
        raise MultiPeriodDemandError(
            "DEMAND_DATASET_ID_MISSING",
            "multi-period demand_dataset_id is required",
        )
    period_counts = Counter(item.period_id for item in demand_input.periods)
    duplicate_periods = sorted(key for key, count in period_counts.items() if count > 1)
    if duplicate_periods:
        raise MultiPeriodDemandError(
            "DUPLICATE_PERIOD_ID",
            "duplicate period_id values: " + ", ".join(duplicate_periods),
        )
    profile_counts = Counter(item.profile_id for item in demand_input.profiles)
    duplicate_profiles = sorted(key for key, count in profile_counts.items() if count > 1)
    if duplicate_profiles:
        raise MultiPeriodDemandError(
            "DUPLICATE_PROFILE_ID",
            "duplicate profile_id values: " + ", ".join(duplicate_profiles),
        )

    periods = tuple(finalize_demand_observation_period_v1(item) for item in demand_input.periods)
    period_ids = {item.period_id for item in periods}
    for profile in demand_input.profiles:
        if not profile.included_period_ids:
            raise MultiPeriodDemandError(
                "PROFILE_HAS_NO_PERIODS",
                f"profile {profile.profile_id} has no included periods",
            )
        unknown = sorted(set(profile.included_period_ids) - period_ids)
        if unknown:
            raise MultiPeriodDemandError(
                "PROFILE_REFERENCES_UNKNOWN_PERIOD",
                f"profile {profile.profile_id} references: {', '.join(unknown)}",
            )
        if len(set(profile.included_period_ids)) != len(profile.included_period_ids):
            raise MultiPeriodDemandError(
                "PROFILE_DUPLICATE_PERIOD_REFERENCE",
                f"profile {profile.profile_id} repeats an included period",
            )
    if demand_input.default_profile_id is not None and (
        demand_input.default_profile_id not in profile_counts
    ):
        raise MultiPeriodDemandError(
            "DEFAULT_PROFILE_INVALID",
            f"default profile {demand_input.default_profile_id} is not defined",
        )
    unknown_sensitivity = sorted(set(demand_input.sensitivity_profile_ids) - set(profile_counts))
    if unknown_sensitivity:
        raise MultiPeriodDemandError(
            "SENSITIVITY_PROFILE_INVALID",
            "unknown sensitivity profiles: " + ", ".join(unknown_sensitivity),
        )
    return replace(demand_input, periods=periods)


def _period_grain(period: DemandObservationPeriodV1) -> DemandDirectionGrainV1:
    directions = {item.direction for item in period.observations}
    has_combined = ContractDirection.COMBINED in directions
    has_directional = bool(directions & {ContractDirection.OUTBOUND, ContractDirection.INBOUND})
    if has_combined and has_directional:
        raise MultiPeriodDemandError(
            "MIXED_INCOMPATIBLE_DIRECTION_GRAINS",
            f"period {period.period_id} mixes combined and directional observations",
        )
    return DemandDirectionGrainV1.COMBINED if has_combined else DemandDirectionGrainV1.DIRECTIONAL


def _observation_key(
    observation: DemandPeriodObservationV1,
) -> tuple[ContractDirection, int, int]:
    return (
        observation.direction,
        observation.interval_start,
        observation.interval_end,
    )


def _shape_diagnostics(
    periods: tuple[DemandObservationPeriodV1, ...],
    threshold: float,
) -> tuple[DemandPeriodShapeDiagnosticV1, ...]:
    if not 0 <= threshold <= 1:
        raise MultiPeriodDemandError(
            "SHAPE_DISTANCE_THRESHOLD_INVALID",
            "shape distance threshold must be between zero and one",
        )
    vectors: dict[tuple[str, ContractDirection], dict[tuple[int, int], float]] = {}
    totals: dict[tuple[str, ContractDirection], float] = {}
    for period in periods:
        by_direction: dict[ContractDirection, dict[tuple[int, int], float]] = defaultdict(dict)
        for observation in period.observations:
            by_direction[observation.direction][
                (observation.interval_start, observation.interval_end)
            ] = observation.average_daily_passengers(period.observation_days)
        for direction, values in by_direction.items():
            total = sum(values.values())
            totals[(period.period_id, direction)] = total
            vectors[(period.period_id, direction)] = {
                block: (value / total if total > 0 else 0.0) for block, value in values.items()
            }

    output: list[DemandPeriodShapeDiagnosticV1] = []
    for period in periods:
        directions = sorted(
            {item.direction for item in period.observations},
            key=lambda item: item.value,
        )
        for direction in directions:
            key = (period.period_id, direction)
            vector = vectors[key]
            maximum_distance = 0.0
            compared_period_id: str | None = None
            for other in periods:
                other_key = (other.period_id, direction)
                if other.period_id == period.period_id or other_key not in vectors:
                    continue
                blocks = set(vector) | set(vectors[other_key])
                distance = (
                    sum(
                        abs(vector.get(block, 0.0) - vectors[other_key].get(block, 0.0))
                        for block in blocks
                    )
                    / 2
                )
                if distance > maximum_distance:
                    maximum_distance = distance
                    compared_period_id = other.period_id
            peak_block = max(
                sorted(vector),
                key=lambda block: (vector[block], -block[0], -block[1]),
            )
            output.append(
                DemandPeriodShapeDiagnosticV1(
                    period_id=period.period_id,
                    direction=direction,
                    average_daily_passengers=totals[key],
                    normalized_block_shares=tuple(
                        (start, end, vector[(start, end)]) for start, end in sorted(vector)
                    ),
                    peak_block_start=peak_block[0],
                    peak_block_end=peak_block[1],
                    peak_share=vector[peak_block],
                    compared_period_id=compared_period_id,
                    maximum_shape_distance=maximum_distance,
                    shape_distance_threshold=threshold,
                    structural_change_detected=maximum_distance > threshold,
                )
            )
    return tuple(output)


def _profile_payload(
    profile: DemandProfileV1,
    config: DemandProfileConfigV1,
) -> dict[str, object]:
    return {
        "fingerprint_profile": DEMAND_PROFILE_FINGERPRINT_PROFILE_V1,
        "derivation_profile": DEMAND_PROFILE_DERIVATION_PROFILE_V1,
        "profile_config": jsonable(asdict(config)),
        "profile": {
            "profile_id": profile.profile_id,
            "included_period_ids": list(profile.included_period_ids),
            "aggregation_method": profile.aggregation_method.value,
            "period_weight_method": profile.period_weight_method,
            "total_observation_days": profile.total_observation_days,
            "direction_grain": profile.direction_grain.value,
            "derived_observations": [
                {
                    "direction": item.direction.value,
                    "interval_start": item.interval_start,
                    "interval_end": item.interval_end,
                    "average_daily_passengers": item.average_daily_passengers,
                }
                for item in profile.derived_observations
            ],
            "source_period_fingerprints": [
                list(item) for item in profile.source_period_fingerprints
            ],
            "limitations": list(profile.limitations),
        },
    }


def calculate_demand_profile_fingerprint_v1(
    profile: DemandProfileV1,
    config: DemandProfileConfigV1,
) -> str:
    return canonical_sha256(_profile_payload(profile, config))


def derive_demand_profile_v1(
    demand_input: MultiPeriodDemandInputV1,
    profile_id: str,
    *,
    shape_distance_threshold: float = DEFAULT_SHAPE_DISTANCE_THRESHOLD_V1,
) -> DemandProfileDerivationResultV1:
    validated = validate_multi_period_demand_input_v1(demand_input)
    configs = {item.profile_id: item for item in validated.profiles}
    config = configs.get(profile_id)
    if config is None:
        raise MultiPeriodDemandError(
            "PROFILE_NOT_FOUND",
            f"profile {profile_id} is not defined",
        )
    if config.status.strip().upper() != "READY":
        raise MultiPeriodDemandError(
            "PROFILE_NOT_READY",
            f"profile {profile_id} has status {config.status}",
        )
    period_lookup = {item.period_id: item for item in validated.periods}
    periods = tuple(period_lookup[item] for item in config.included_period_ids)
    for period in periods:
        if period.status.strip().upper() != "READY":
            raise MultiPeriodDemandError(
                "PERIOD_NOT_READY",
                f"requested profile {profile_id} includes period {period.period_id} with status {period.status}",
            )

    grains = {_period_grain(period) for period in periods}
    if len(grains) != 1:
        raise MultiPeriodDemandError(
            "MIXED_INCOMPATIBLE_DIRECTION_GRAINS",
            f"profile {profile_id} combines directional and combined periods",
        )
    direction_grain = next(iter(grains))

    grids = [set(_observation_key(item) for item in period.observations) for period in periods]
    if any(grid != grids[0] for grid in grids[1:]):
        raise MultiPeriodDemandError(
            "PERIOD_OBSERVATION_GRID_MISMATCH",
            f"profile {profile_id} periods do not share the same demand block grid",
        )

    total_days = sum(item.observation_days for item in periods)
    if config.aggregation_method == DemandProfileAggregationMethodV1.SINGLE_PERIOD:
        if len(periods) != 1:
            raise MultiPeriodDemandError(
                "SINGLE_PERIOD_PROFILE_INVALID",
                f"profile {profile_id} must include exactly one period",
            )
        source = periods[0]
        derived = tuple(
            DerivedDemandObservationV1(
                direction=item.direction,
                interval_start=item.interval_start,
                interval_end=item.interval_end,
                average_daily_passengers=item.average_daily_passengers(source.observation_days),
            )
            for item in sorted(source.observations, key=_observation_key)
        )
    elif config.aggregation_method == DemandProfileAggregationMethodV1.DAY_WEIGHTED_MEAN:
        if config.period_weight.strip().lower() != "observation_days":
            raise MultiPeriodDemandError(
                "PERIOD_WEIGHT_UNSUPPORTED",
                f"profile {profile_id} must use observation_days weighting in V1",
            )
        values_by_period = {
            period.period_id: {
                _observation_key(item): item.average_daily_passengers(period.observation_days)
                for item in period.observations
            }
            for period in periods
        }
        derived = tuple(
            DerivedDemandObservationV1(
                direction=key[0],
                interval_start=key[1],
                interval_end=key[2],
                average_daily_passengers=sum(
                    values_by_period[period.period_id][key] * period.observation_days
                    for period in periods
                )
                / total_days,
            )
            for key in sorted(grids[0], key=lambda item: (item[1], item[2], item[0].value))
        )
    else:  # pragma: no cover - the enum rejects unsupported workbook values
        raise MultiPeriodDemandError(
            "AGGREGATION_METHOD_UNSUPPORTED",
            str(config.aggregation_method),
        )

    limitations = (
        "V1 uses only the profile's explicitly included periods and never applies hidden recency weights.",
    )
    provisional = DemandProfileV1(
        profile_id=config.profile_id,
        included_period_ids=config.included_period_ids,
        aggregation_method=config.aggregation_method,
        period_weight_method=config.period_weight,
        total_observation_days=total_days,
        direction_grain=direction_grain,
        derived_observations=derived,
        source_period_fingerprints=tuple(
            (item.period_id, item.period_fingerprint) for item in periods
        ),
        limitations=limitations,
    )
    profile = replace(
        provisional,
        profile_fingerprint=calculate_demand_profile_fingerprint_v1(provisional, config),
    )
    diagnostics = _shape_diagnostics(periods, shape_distance_threshold)
    codes = (
        (MULTI_PERIOD_STRUCTURAL_CHANGE_DETECTED,)
        if any(item.structural_change_detected for item in diagnostics)
        else ()
    )
    diagnostic_limitations = (
        (
            "Structural-change diagnostics use pairwise L1 distance divided by two on "
            "normalized time-block shares; they inform review and do not change weights."
        ),
    )
    return DemandProfileDerivationResultV1(
        profile=profile,
        period_diagnostics=diagnostics,
        diagnostic_codes=codes,
        limitations=diagnostic_limitations,
    )


__all__ = [
    "DEFAULT_SHAPE_DISTANCE_THRESHOLD_V1",
    "DEMAND_PERIOD_FINGERPRINT_PROFILE_V1",
    "DEMAND_PROFILE_DERIVATION_PROFILE_V1",
    "DEMAND_PROFILE_FINGERPRINT_PROFILE_V1",
    "MULTI_PERIOD_DEMAND_INPUT_PROFILE_V1",
    "MULTI_PERIOD_STRUCTURAL_CHANGE_DETECTED",
    "DemandDirectionGrainV1",
    "DemandObservationPeriodV1",
    "DemandPeriodObservationV1",
    "DemandPeriodShapeDiagnosticV1",
    "DemandProfileAggregationMethodV1",
    "DemandProfileConfigV1",
    "DemandProfileDerivationResultV1",
    "DemandProfileV1",
    "DerivedDemandObservationV1",
    "MultiPeriodDemandError",
    "MultiPeriodDemandInputV1",
    "calculate_demand_period_fingerprint_v1",
    "calculate_demand_profile_fingerprint_v1",
    "derive_demand_profile_v1",
    "finalize_demand_observation_period_v1",
    "validate_multi_period_demand_input_v1",
]

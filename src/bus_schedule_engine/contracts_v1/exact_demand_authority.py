"""Internal exact rational demand authority for canonical quality optimization."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from .demand_resolution import AggregationMethod
from .evaluation import ScenarioBEvaluationBundleV1, ScenarioBEvaluationPolicyV1
from .models import (
    ContractDirection,
    DemandResolutionType,
    NormalizedInputBundleV1,
    VolumeClassification,
)
from .solver_models import ScheduleProblemV1

_SAFE_CP_SAT_INTEGER = (1 << 62) - 1


class _ExactDemandAuthorityError(ValueError):
    """Stable fail-closed error raised while constructing exact internal authority."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _ExactBlockDemand:
    block_id: str
    numerator: int
    denominator: int

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)


@dataclass(frozen=True, slots=True)
class _ExactDemandAuthority:
    blocks: tuple[_ExactBlockDemand, ...]
    authority_fingerprint: str

    def fraction_by_block_id(self) -> dict[str, Fraction]:
        return {block.block_id: block.fraction for block in self.blocks}


@dataclass(frozen=True, slots=True)
class _ExactScaledDemand:
    common_denominator: int
    reduction_gcd: int
    weight_by_block_id: dict[str, int]
    total_by_direction: dict[ContractDirection, int]
    total_alignment_upper_bound: int

    @property
    def scale(self) -> int:
        """Backward-compatible descriptive scale before global GCD reduction."""

        return self.common_denominator


def _decimal_fraction(value: object, *, code: str) -> Fraction:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise _ExactDemandAuthorityError(code) from exc
    if not decimal_value.is_finite():
        raise _ExactDemandAuthorityError(code)
    return Fraction(decimal_value)


def _source_daily_fraction(
    passenger_count: object,
    volume_classification: VolumeClassification,
    observation_days: int,
) -> Fraction:
    value = _decimal_fraction(
        passenger_count,
        code="EXACT_DEMAND_SOURCE_VALUE_INVALID",
    )
    if value < 0:
        raise _ExactDemandAuthorityError("EXACT_DEMAND_NEGATIVE")
    if volume_classification == VolumeClassification.AVERAGE_DAY:
        return value
    if observation_days <= 0:
        raise _ExactDemandAuthorityError("EXACT_DEMAND_OBSERVATION_DAYS_INVALID")
    return value / observation_days


def _canonical_authority_fingerprint(
    blocks: tuple[_ExactBlockDemand, ...],
) -> str:
    rows = [
        [block.block_id, block.numerator, block.denominator]
        for block in sorted(blocks, key=lambda item: item.block_id)
    ]
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _exact_required_trips(
    demand: Fraction,
    *,
    capacity: int,
    ceiling: float,
) -> int:
    if demand <= 0:
        return 0
    if capacity <= 0:
        raise _ExactDemandAuthorityError("EXACT_DEMAND_THRESHOLD_CONTEXT_INVALID")
    ceiling_fraction = _decimal_fraction(
        ceiling,
        code="EXACT_DEMAND_THRESHOLD_CONTEXT_INVALID",
    )
    if ceiling_fraction <= 0:
        raise _ExactDemandAuthorityError("EXACT_DEMAND_THRESHOLD_CONTEXT_INVALID")
    return _ceil_fraction(demand / (capacity * ceiling_fraction))


def _build_exact_demand_authority(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    *,
    evaluation_policy: ScenarioBEvaluationPolicyV1,
) -> _ExactDemandAuthority:
    observed = normalized_inputs.observed_demand
    resolution = b_evaluation.demand_resolution
    if observed is None or resolution is None:
        raise _ExactDemandAuthorityError("EXACT_DEMAND_AUTHORITY_MISSING")

    source_by_id = {}
    for observation in observed.observations:
        if observation.observation_id in source_by_id:
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_DUPLICATE_SOURCE_OBSERVATION",
                observation.observation_id,
            )
        source_by_id[observation.observation_id] = observation

    supply_by_block_id = {}
    for requirement in b_evaluation.b_block_supply:
        if requirement.block_id in supply_by_block_id:
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_DUPLICATE_BLOCK_REQUIREMENT",
                requirement.block_id,
            )
        supply_by_block_id[requirement.block_id] = requirement

    assigned_source_ids: dict[str, str] = {}
    exact_blocks: list[_ExactBlockDemand] = []
    seen_block_ids: set[str] = set()
    for block in resolution.blocks:
        if block.block_id in seen_block_ids:
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_DUPLICATE_BLOCK_ID",
                block.block_id,
            )
        seen_block_ids.add(block.block_id)
        if not block.source_interval_ids:
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_BLOCK_SOURCE_IDS_MISSING",
                block.block_id,
            )
        if block.aggregation_method not in {
            AggregationMethod.NONE,
            AggregationMethod.SUM,
        }:
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_AGGREGATION_UNSUPPORTED",
                block.block_id,
            )
        if len(block.source_interval_ids) > 1 and block.aggregation_method != AggregationMethod.SUM:
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_AGGREGATION_INCONSISTENT",
                block.block_id,
            )

        exact_value = Fraction(0, 1)
        local_source_ids: set[str] = set()
        for source_id in block.source_interval_ids:
            if source_id in local_source_ids:
                raise _ExactDemandAuthorityError(
                    "EXACT_DEMAND_DUPLICATE_SOURCE_MAPPING",
                    source_id,
                )
            local_source_ids.add(source_id)
            source = source_by_id.get(source_id)
            if source is None:
                raise _ExactDemandAuthorityError(
                    "EXACT_DEMAND_UNKNOWN_SOURCE_OBSERVATION",
                    source_id,
                )
            previous_block_id = assigned_source_ids.get(source_id)
            if previous_block_id is not None and previous_block_id != block.block_id:
                raise _ExactDemandAuthorityError(
                    "EXACT_DEMAND_SOURCE_ASSIGNED_INCONSISTENTLY",
                    source_id,
                )
            assigned_source_ids[source_id] = block.block_id
            exact_value += _source_daily_fraction(
                source.passenger_count,
                source.volume_classification,
                observed.observation_days,
            )

        if exact_value < 0:
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_NEGATIVE",
                block.block_id,
            )
        if not math.isclose(
            float(exact_value),
            float(block.observed_passengers),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_FLOAT_COMPATIBILITY_MISMATCH",
                block.block_id,
            )
        if (exact_value > 0) != (block.observed_passengers > 0):
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_POSITIVE_CLASSIFICATION_MISMATCH",
                block.block_id,
            )

        requirement = supply_by_block_id.get(block.block_id)
        if requirement is None:
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_BLOCK_REQUIREMENT_MISSING",
                block.block_id,
            )
        if not math.isclose(
            float(exact_value),
            float(requirement.passenger_demand),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_REQUIREMENT_COMPATIBILITY_MISMATCH",
                block.block_id,
            )
        required_85 = _exact_required_trips(
            exact_value,
            capacity=requirement.vehicle_capacity,
            ceiling=evaluation_policy.planning_load_factor_ceiling,
        )
        required_90 = _exact_required_trips(
            exact_value,
            capacity=requirement.vehicle_capacity,
            ceiling=evaluation_policy.critical_load_factor_ceiling,
        )
        if (
            required_85 != requirement.required_trips_85
            or required_90 != requirement.required_trips_90
        ):
            raise _ExactDemandAuthorityError(
                "EXACT_DEMAND_SERVICE_THRESHOLD_MISMATCH",
                block.block_id,
            )
        exact_blocks.append(
            _ExactBlockDemand(
                block_id=block.block_id,
                numerator=exact_value.numerator,
                denominator=exact_value.denominator,
            )
        )

    if len(exact_blocks) != len(resolution.blocks):
        raise _ExactDemandAuthorityError("EXACT_DEMAND_BLOCK_AUTHORITY_INCOMPLETE")

    intraday_source_ids = {
        observation.observation_id
        for observation in observed.observations
        if observation.source_resolution_type != DemandResolutionType.DAILY_TOTAL
    }
    if set(assigned_source_ids) != intraday_source_ids:
        raise _ExactDemandAuthorityError("EXACT_DEMAND_SOURCE_MAPPING_INCOMPLETE")

    ordered = tuple(sorted(exact_blocks, key=lambda item: item.block_id))
    return _ExactDemandAuthority(
        blocks=ordered,
        authority_fingerprint=_canonical_authority_fingerprint(ordered),
    )


def _scale_exact_demand_authority(
    authority: _ExactDemandAuthority,
    problem: ScheduleProblemV1,
) -> _ExactScaledDemand:
    block_ids = [block.block_id for block in authority.blocks]
    if len(block_ids) != len(set(block_ids)):
        raise _ExactDemandAuthorityError("EXACT_DEMAND_DUPLICATE_BLOCK_ID")
    problem_block_ids = {block.block_id for block in problem.analysis_blocks}
    if set(block_ids) != problem_block_ids:
        raise _ExactDemandAuthorityError("EXACT_DEMAND_BLOCK_AUTHORITY_INCOMPLETE")

    common_denominator = 1
    for block in authority.blocks:
        if block.denominator <= 0 or block.numerator < 0:
            raise _ExactDemandAuthorityError("EXACT_DEMAND_AUTHORITY_INVALID")
        common_denominator = math.lcm(common_denominator, block.denominator)
        if common_denominator > _SAFE_CP_SAT_INTEGER:
            raise _ExactDemandAuthorityError("ORTOOLS_QUALITY_DEMAND_INTEGER_UNSAFE")

    raw_weights: dict[str, int] = {}
    for block in authority.blocks:
        weight = block.numerator * (common_denominator // block.denominator)
        if weight < 0 or weight > _SAFE_CP_SAT_INTEGER:
            raise _ExactDemandAuthorityError("ORTOOLS_QUALITY_DEMAND_INTEGER_UNSAFE")
        raw_weights[block.block_id] = weight

    reduction_gcd = 0
    for weight in raw_weights.values():
        reduction_gcd = math.gcd(reduction_gcd, weight)
    if reduction_gcd <= 0:
        reduction_gcd = 1
    weights = {block_id: weight // reduction_gcd for block_id, weight in raw_weights.items()}

    total_by_direction: dict[ContractDirection, int] = {}
    total_alignment_upper_bound = 0
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        directional_weights = [
            weights[block.block_id]
            for block in problem.analysis_blocks
            if block.direction == direction
        ]
        total_weight = sum(directional_weights)
        trip_count = (
            problem.scenario_b.trips_by_direction.outbound
            if direction == ContractDirection.OUTBOUND
            else problem.scenario_b.trips_by_direction.inbound
        )
        cross_product = trip_count * total_weight
        alignment_bound = 2 * cross_product
        if (
            total_weight > _SAFE_CP_SAT_INTEGER
            or any(trip_count * weight > _SAFE_CP_SAT_INTEGER for weight in directional_weights)
            or cross_product > _SAFE_CP_SAT_INTEGER
            or alignment_bound > _SAFE_CP_SAT_INTEGER
            or total_alignment_upper_bound + alignment_bound > _SAFE_CP_SAT_INTEGER
        ):
            raise _ExactDemandAuthorityError("ORTOOLS_QUALITY_DEMAND_INTEGER_UNSAFE")
        total_by_direction[direction] = total_weight
        total_alignment_upper_bound += alignment_bound

    return _ExactScaledDemand(
        common_denominator=common_denominator,
        reduction_gcd=reduction_gcd,
        weight_by_block_id=weights,
        total_by_direction=total_by_direction,
        total_alignment_upper_bound=total_alignment_upper_bound,
    )

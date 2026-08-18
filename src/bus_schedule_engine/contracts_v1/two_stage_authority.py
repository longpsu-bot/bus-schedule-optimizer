"""Demand-authority routing for explicit B-anchored two-stage optimization."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .demand_coverage import DemandCoverageModeV1
from .evaluation import ScenarioBEvaluationBundleV1
from .models import (
    DemandAllocationAuthorityModeV1,
    NormalizedInputBundleV1,
    ScenarioCOptimizationModeV1,
)
from .serialization import canonical_sha256
from .solver_problem import jsonable

TWO_STAGE_DEMAND_AUTHORITY_PROFILE_V1 = "scenario_c_two_stage_demand_authority_v1"
TWO_STAGE_REQUIRES_B_ANCHORED_MODE = "TWO_STAGE_REQUIRES_B_ANCHORED_MODE"
TWO_STAGE_DEMAND_AUTHORITY_MISSING = "TWO_STAGE_DEMAND_AUTHORITY_MISSING"
TWO_STAGE_DEMAND_COVERAGE_UNSUPPORTED = "TWO_STAGE_DEMAND_COVERAGE_UNSUPPORTED"


class TwoStageDemandAuthorityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class TwoStageDemandAuthorityV1:
    authority_mode: DemandAllocationAuthorityModeV1
    observed_demand_fingerprint: str
    source_b_fingerprint: str
    supports_directional_passenger_inference: bool
    limitations: tuple[str, ...]
    authority_fingerprint: str


def _authority_payload(authority: TwoStageDemandAuthorityV1) -> dict[str, object]:
    payload = jsonable(asdict(authority))
    payload.pop("authority_fingerprint", None)
    return {
        "fingerprint_profile": TWO_STAGE_DEMAND_AUTHORITY_PROFILE_V1,
        "optimization_mode": ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE.value,
        "authority": payload,
    }


def calculate_two_stage_demand_authority_fingerprint_v1(
    authority: TwoStageDemandAuthorityV1,
) -> str:
    return canonical_sha256(_authority_payload(authority))


def build_two_stage_demand_authority_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
) -> TwoStageDemandAuthorityV1:
    if normalized_inputs.optimization_mode != (
        ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE
    ):
        raise TwoStageDemandAuthorityError(
            TWO_STAGE_REQUIRES_B_ANCHORED_MODE,
            "legacy A-bound normalization cannot authorize the V3 two-stage workflow",
        )
    if (
        normalized_inputs.observed_demand is None
        or normalized_inputs.observed_demand_fingerprint is None
        or b_evaluation.demand_resolution is None
        or b_evaluation.demand_resolution.coverage_assessment is None
    ):
        raise TwoStageDemandAuthorityError(
            TWO_STAGE_DEMAND_AUTHORITY_MISSING,
            "observed demand, its fingerprint, and evaluated coverage are required",
        )

    coverage = b_evaluation.demand_resolution.coverage_assessment
    if coverage.directional_c_generation_supported:
        mode = DemandAllocationAuthorityModeV1.DIRECTIONAL_FIXED_DIRECTION_COUNTS
        supports_directional = True
        limitations: tuple[str, ...] = ()
    elif (
        coverage.mode == DemandCoverageModeV1.COMBINED_ONLY
        and coverage.whole_b_suitability_supported
    ):
        mode = DemandAllocationAuthorityModeV1.COMBINED_FIXED_DIRECTION_COUNTS
        supports_directional = False
        limitations = (
            "The demand source is combined across directions. V3 optimizes total service by "
            "time block while preserving Scenario B directional daily counts; it does not "
            "claim directional passenger inference.",
        )
    else:
        raise TwoStageDemandAuthorityError(
            TWO_STAGE_DEMAND_COVERAGE_UNSUPPORTED,
            "demand coverage supports neither directional allocation nor combined total-service allocation",
        )

    provisional = TwoStageDemandAuthorityV1(
        authority_mode=mode,
        observed_demand_fingerprint=normalized_inputs.observed_demand_fingerprint,
        source_b_fingerprint=normalized_inputs.scenario_b_fingerprint,
        supports_directional_passenger_inference=supports_directional,
        limitations=limitations,
        authority_fingerprint="",
    )
    return TwoStageDemandAuthorityV1(
        authority_mode=provisional.authority_mode,
        observed_demand_fingerprint=provisional.observed_demand_fingerprint,
        source_b_fingerprint=provisional.source_b_fingerprint,
        supports_directional_passenger_inference=(
            provisional.supports_directional_passenger_inference
        ),
        limitations=provisional.limitations,
        authority_fingerprint=(calculate_two_stage_demand_authority_fingerprint_v1(provisional)),
    )


__all__ = [
    "TWO_STAGE_DEMAND_AUTHORITY_MISSING",
    "TWO_STAGE_DEMAND_AUTHORITY_PROFILE_V1",
    "TWO_STAGE_DEMAND_COVERAGE_UNSUPPORTED",
    "TWO_STAGE_REQUIRES_B_ANCHORED_MODE",
    "TwoStageDemandAuthorityError",
    "TwoStageDemandAuthorityV1",
    "build_two_stage_demand_authority_v1",
    "calculate_two_stage_demand_authority_fingerprint_v1",
]

from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Any

from .evaluation import ScenarioBEvaluationBundleV1, ScenarioBEvaluationPolicyV1
from .evaluation_serialization import (
    block_supply_plan_to_contract_dict,
    demand_analysis_block_to_contract_dict,
    demand_resolution_to_contract_dict,
    schedule_evaluation_to_contract_dict,
)
from .models import NormalizedInputBundleV1
from .serialization import canonical_sha256

EVALUATION_FINGERPRINT_PROFILE = "contract_v1_h1_evaluation"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _fleet_assessment_payload(evaluation: ScenarioBEvaluationBundleV1) -> dict[str, object]:
    fleet = evaluation.fleet_assessment
    return {
        "available_fleet_limit": fleet.available_fleet_limit,
        "minimum_required_fleet": fleet.minimum_required_fleet,
        "recommended_initial_fleet_terminal_1": (fleet.recommended_initial_fleet_terminal_1),
        "recommended_initial_fleet_terminal_2": (fleet.recommended_initial_fleet_terminal_2),
        "fleet_margin": fleet.fleet_margin,
        "feasible": fleet.feasible,
        "terminal_1_events": _jsonable([asdict(item) for item in fleet.terminal_1_events]),
        "terminal_2_events": _jsonable([asdict(item) for item in fleet.terminal_2_events]),
    }


def evaluation_fingerprint_payload(
    normalized_inputs: NormalizedInputBundleV1,
    evaluation: ScenarioBEvaluationBundleV1,
    policy: ScenarioBEvaluationPolicyV1,
) -> dict[str, object]:
    resolution = evaluation.demand_resolution
    resolution_payload: dict[str, object] | None = None
    if resolution is not None:
        resolution_payload = {
            "contract": demand_resolution_to_contract_dict(resolution.contract),
            "blocks": [demand_analysis_block_to_contract_dict(item) for item in resolution.blocks],
            "warnings": list(resolution.warnings),
            "limitations": list(resolution.limitations),
        }
    return {
        "fingerprint_profile": EVALUATION_FINGERPRINT_PROFILE,
        "contract_version": normalized_inputs.scenario_b.contract_version,
        "scenario_a_fingerprint": normalized_inputs.scenario_a_fingerprint,
        "scenario_b_fingerprint": normalized_inputs.scenario_b_fingerprint,
        "observed_demand_fingerprint": normalized_inputs.observed_demand_fingerprint,
        "evaluation_policy": _jsonable(asdict(policy)),
        "demand_resolution": resolution_payload,
        "a_block_supply": [
            block_supply_plan_to_contract_dict(item) for item in evaluation.a_block_supply
        ],
        "b_block_supply": [
            block_supply_plan_to_contract_dict(item) for item in evaluation.b_block_supply
        ],
        "fleet_assessment": _fleet_assessment_payload(evaluation),
        "evaluation": schedule_evaluation_to_contract_dict(evaluation.evaluation),
    }


def evaluation_fingerprint(
    normalized_inputs: NormalizedInputBundleV1,
    evaluation: ScenarioBEvaluationBundleV1,
    policy: ScenarioBEvaluationPolicyV1,
) -> str:
    return canonical_sha256(evaluation_fingerprint_payload(normalized_inputs, evaluation, policy))

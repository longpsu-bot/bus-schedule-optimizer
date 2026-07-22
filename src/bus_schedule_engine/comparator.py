from __future__ import annotations

import json
from pathlib import Path

from .models import (
    EvaluationStatus,
    FleetResult,
    ScenarioEvaluation,
    ScenarioParameters,
    ValidationReport,
)


def load_scoring_config(path: str | Path | None = None) -> dict[str, object]:
    config_path = Path(path) if path else Path(__file__).parents[2] / "config" / "scoring.json"
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def score_scenario(
    evaluation: ScenarioEvaluation,
    fleet: FleetResult,
    validation: ValidationReport,
    parameters: ScenarioParameters,
    config: dict[str, object],
) -> float | None:
    """Score only technically valid scenarios; hard-constraint failures remain visible."""
    if not validation.passed:
        return None
    weights = config["weights"]
    penalties = config["penalties"]
    thresholds = config["thresholds"]

    block_scores: list[float] = []
    for block in evaluation.blocks:
        if block.status == EvaluationStatus.NO_SERVICE_WITH_DEMAND:
            block_scores.append(0.0)
        elif block.load_factor is None:
            continue
        elif block.load_factor <= parameters.maximum_load_factor:
            distance = abs(block.load_factor - parameters.target_load_factor)
            block_scores.append(max(0.0, 1 - distance / parameters.target_load_factor))
        else:
            overload = block.load_factor - parameters.maximum_load_factor
            block_scores.append(max(0.0, 1 - overload / parameters.maximum_load_factor))
    demand_component = (
        float(weights["demand_fit"]) * sum(block_scores) / len(block_scores)
        if block_scores
        else 0.0
    )

    coefficient = evaluation.headway.coefficient_of_variation
    if coefficient is None:
        regularity_ratio = 0.5
    else:
        good = float(thresholds["good_headway_cv"])
        poor = float(thresholds["poor_headway_cv"])
        regularity_ratio = 1 - min(1.0, max(0.0, coefficient - good) / (poor - good))
    headway_component = float(weights["headway_regularity"]) * regularity_ratio

    total_active = sum(float(item["active_minutes"]) for item in fleet.vehicle_summaries)
    total_travel = sum(float(item["travel_minutes"]) for item in fleet.vehicle_summaries)
    utilization = total_travel / total_active if total_active else 0
    fleet_component = float(weights["fleet_efficiency"]) * min(1.0, utilization)

    tolerance = float(thresholds["final_trip_tolerance_minutes"])
    coverage_gap = max(evaluation.early_coverage_gap_minutes, evaluation.late_coverage_gap_minutes)
    coverage_ratio = max(0.0, 1 - coverage_gap / max(1, tolerance * 4))
    coverage_component = float(weights["service_coverage"]) * coverage_ratio

    penalty = evaluation.blocks_over_maximum * float(penalties["block_over_maximum"])
    penalty += sum(
        block.status == EvaluationStatus.NO_SERVICE_WITH_DEMAND for block in evaluation.blocks
    ) * float(penalties["no_service_with_demand"])
    if evaluation.late_coverage_gap_minutes > tolerance:
        penalty += float(penalties["final_trip_too_early"])
    mean_headway = evaluation.headway.mean_minutes
    max_headway = evaluation.headway.maximum_minutes
    if (
        mean_headway
        and max_headway
        and max_headway > mean_headway * float(thresholds["abnormal_gap_multiplier"])
    ):
        penalty += float(penalties["abnormal_service_gap"])
    total = demand_component + headway_component + fleet_component + coverage_component - penalty
    return round(max(0.0, min(100.0, total)), 1)

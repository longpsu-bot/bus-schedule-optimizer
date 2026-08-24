from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts/run_pr62_e_closed_loop_pilot.py"
    spec = importlib.util.spec_from_file_location("run_pr62_e_closed_loop_pilot", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pilot = _load_script()


def test_neighbor_explosion_classifications_cover_material_and_none() -> None:
    assert (
        pilot.classify_neighbor_explosion(
            generated=1_209_043,
            evaluated=24,
            pruned=1_000_000,
            duplicates=100_000,
            open_limit=512,
        )
        == "MATERIAL_NEIGHBOR_GENERATION_EXPLOSION"
    )
    assert (
        pilot.classify_neighbor_explosion(
            generated=100,
            evaluated=24,
            pruned=0,
            duplicates=0,
            open_limit=512,
        )
        == "NO_NEIGHBOR_EXPLOSION_EVIDENCE"
    )


def test_queue_classification_has_no_starvation_when_search_completed() -> None:
    assert (
        pilot.classify_queue_starvation(
            budget_exhausted=False,
            queue_rows=[{"ancestry_codes": ["DEMAND_UNDERSERVED_INTERVAL"]}],
            evaluated=[SimpleNamespace()],
        )
        == "NO_QUEUE_STARVATION_EVIDENCE"
    )


def test_route_markdown_states_no_policy_change() -> None:
    payload = {
        "route_id": "6",
        "status": "SEARCH_BUDGET_EXHAUSTED",
        "authority": {
            "runtime_minutes_each_direction": 70,
            "minimum_layover_minutes": 5,
            "fleet_ceiling": 20,
            "directions": {
                "outbound": {
                    "fixed_first_departure_hhmm": "04:55",
                    "fixed_last_departure_hhmm": "21:00",
                },
                "inbound": {
                    "fixed_first_departure_hhmm": "04:55",
                    "fixed_last_departure_hhmm": "21:00",
                },
            },
        },
        "search_budget": {"max_service_plan_evaluations": 24},
        "search_audit": {
            "states_generated": 10,
            "states_evaluated": 2,
            "duplicate_states_skipped": 1,
            "states_pruned": 2,
            "search_iterations": 2,
            "compile_variants_evaluated": 4,
            "protected_compile_variants_rejected": 0,
            "fleet_validations_run": 3,
            "final_directional_archive_sizes": {"outbound": 2, "inbound": 2},
            "final_pareto_size": 1,
            "active_open_queue_size_at_stop": 1,
            "generation_to_evaluation_ratio": 5.0,
            "pruned_generation_share": 0.2,
            "duplicate_generation_share": 0.1,
        },
        "queue_starvation_classification": "QUEUE_STARVATION_INCONCLUSIVE",
        "neighbor_generation_explosion_classification": "NEIGHBOR_EXPLOSION_INCONCLUSIVE",
        "metric_ranges": {
            "observed_demand_mismatch": {"minimum": 0.1, "maximum": 0.2},
            "demand_weighted_expected_passenger_wait_minutes": {
                "minimum": 5.0,
                "maximum": 6.0,
            },
            "fleet_required": {"minimum": 10, "maximum": 11},
        },
        "exact_wait_frontier_effect": {
            "membership_changed": True,
            "production_pareto_size_with_exact_wait": 1,
            "counterfactual_pareto_size_without_wait": 2,
        },
        "demand_response_audit": {
            direction: {
                "candidates": [
                    {
                        "service_frequency_max_min_ratio": 1.5,
                        "direction_accuracy": 1.0,
                    }
                ],
                "exact_flat_compilations": [],
            }
            for direction in ("outbound", "inbound")
        },
        "representative_candidate": {
            "pair_fingerprint": "pair",
            "metrics": {
                "demand_weighted_expected_passenger_wait_minutes": 5.0,
                "observed_demand_mismatch": 0.1,
                "fleet_required": 10,
                "max_frequency_jump": 0.2,
            },
            "outbound_service_regimes": [],
            "inbound_service_regimes": [],
        },
        "clean_boundary_blockers": [],
        "settlement_classification": "SETTLEMENT_NOT_CURRENTLY_NEEDED",
        "feedback_effectiveness": {},
        "route_6_expert_reference": None,
    }
    assert "No production scheduling policy changed." in pilot.render_route_markdown(payload)

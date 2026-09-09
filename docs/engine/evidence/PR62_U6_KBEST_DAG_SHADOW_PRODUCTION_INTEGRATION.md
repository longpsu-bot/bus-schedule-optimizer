# PR62-U6 k-best DAG shadow integration

## PORT

```json
{
  "comparison_base": "59b892d3b367182b20734ad4e4405e264ba14024",
  "implementation_authority_sha256": "0be8acde71bead9486e99936c48fea897d199d82d11db62b4b595d9c91a151eb",
  "port_audit_sha256": "fca7051c8d478e0d53350a29abdf383bcd92f2695a67efb58cfb5a89a5600100",
  "production_file_sha256": {
    "app_pages/01_nhap_du_lieu.py": "215c06bedd296312ef1e96142e44cba229f78dc7dbbe50a39918cc16fed17544",
    "app_pages/02_kiem_tra.py": "11ab809e85c1ad028431f230156b213b67a56bc15dba06a7a00c86d17fc2e8c6",
    "app_pages/03_nhu_cau.py": "29fcc784152337584427323e666b52c26251d8100915520981797b2585ed671f",
    "app_pages/04_khuyen_nghi.py": "d3737bb873b043b492bb6e5a5111aa383c4f2d0bc0a631815a724d8bcc6e82e5",
    "app_pages/05_xuat_file.py": "599bb1b45873df4e2e49d6a5f50348b18120453014e0fc45778e89260e45bcd4",
    "outputs/final_pilot/PR62_P_FINAL_PILOT_DATA.json": "ee5b90525d4e4411a8399b684e41a863cd53ce5dac8ef8ebf47c73861c7899c8",
    "outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx": "d84dd2e873d3ba30275463a5eff67277a22467839af0f0125e69160a891fc3db",
    "outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx": "13454026722f996d8b06e5305b3b6ab2d57ea6126734f4deeb23c3e7dbafd02c",
    "outputs/final_pilot/archive/pr62_g/Route_10_Final_Pilot_Timetable.xlsx": "e49031892388714850001c0a97f91db9e3380b2dc0808d45095ce9825abf9da0",
    "outputs/final_pilot/archive/pr62_g/Route_6_Final_Pilot_Timetable.xlsx": "35a4ef65b0bc64cc8e18397c27bc7a135d5039857321f06e5ec5aadf15bf8879",
    "pyproject.toml": "30fed6237a06b2d2485d5acc6bf8afbe1cc171370f5bcb76e3964823f648191c",
    "scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py": "9b5d036b86e10415ef09befe83094cc93a892c15d0c6577e42a457f3d57a7454",
    "src/bus_schedule_engine/contracts_v1/clean_boundary_compiler.py": "e36950284e7d2bea1f7ff15dc1bb016d360b8b3dd6ff3ce0299cfcbdb3952490",
    "src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py": "ed770bf575d9a426d6f8f32f9524694bb54a56d8d0f1147b35b07134ea602be3",
    "src/bus_schedule_engine/contracts_v1/closed_loop_service_protection.py": "c5a7e1329454c552008acd324c1fe10391181221836c0564fd36954651fc2a94",
    "src/bus_schedule_engine/contracts_v1/end_tail_settlement.py": "018232a94600d4ce0773402f8de15087c6e4fd152fa8949a82f9edb3828bae03",
    "src/bus_schedule_engine/contracts_v1/fleet_assignment.py": "3f2f336fcac16477f167cd96d7c7b2a0c7401784018a0d0ff631f59158e096d2",
    "src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py": "dd7397097d733703220b420a777e794631b7aed1c52bf47130df63f43532d063",
    "src/bus_schedule_engine/contracts_v1/operational_selection_policy_v3.py": "b36390de2737cf344a26621f7de03f399eac34d730d895ef162f4913bf4eb4d3",
    "src/bus_schedule_engine/kbest_shadow_refinement.py": "0198247b8eb999cc18f17c7913dc4c0c83071332ec863a0300c6c0f41a93a672",
    "src/bus_schedule_engine/local_rhythm_refinement.py": "0e0c27c5d4e12ef1aa15bf38f0227cb7594dee6bde9b509763ad2d53b3b19b38",
    "src/bus_schedule_engine/service_plan_coordinator.py": "99da83840f30d5ff7781b1525ec5202074641f1c01203ad46ddc42200a24bfc0",
    "streamlit_app.py": "24a92a814ec54cc4a9b9eef1d2179aae96b98a1fdfc6d7e10e4500caf53e0243"
  },
  "protected_authority_unchanged": true,
  "u5_parity": {
    "classification": "U5_EXACT_PRODUCTION_PORT_PARITY",
    "family_manifest_sha256": "465c0800be66ce991af017ecea6dc87cdd4db7342d8ac9adb30ba1b5678fa905",
    "first_distinct_objective_tiers": [
      [
        8214,
        7,
        74
      ],
      [
        9264,
        7,
        51
      ],
      [
        10734,
        7,
        58
      ]
    ],
    "fixture_sha256": "1b65a2f34c6bf06e9e2b94a8371e1e2d447b1e1b6fd2464510e7cd9066294a0f",
    "raw_count": 256,
    "raw_top256_sha256": "71092c883923e6d5460980a8c528f263a275255986e887bb03c3c1ef16c17601",
    "state_count": 49,
    "top1_fingerprint": "8e06dbcafc0194e5d338bc96b28569825bff30a79f96eaec8b5eda3c778ca7f6",
    "top_objective": [
      8214,
      7,
      74
    ]
  }
}
```

## ROUTE 10

Route 10 has no selected timetable under unchanged V3. The diagnostic repeat and cap comparison cannot authorize Route 6 or production use.

U6_ROUTE10_FINAL_V3_SELECTION_UNAVAILABLE

Canonical semantic SHA-256: `46cd605e4ffb0a9aa00bb9376002b2001ada60760d460e1cbf38ba69aa549d99`

### Canonical

```json
{
  "pareto_sha256": "d6c7cab9f86fa5ba498c83ff3d3316467b759acbc67737cd935ed5ccd7d14d94",
  "selected": null,
  "statistics": {
    "base_frontier_count": 11,
    "directional_strict_progress_rejects": 343,
    "duplicate_pair_rejects": 38,
    "endpoint_preflight_rejects": 0,
    "families_processed": 17,
    "final_frontier_count": 123,
    "fleet_rejects": 2448,
    "global_coordinator_executions": 0,
    "hard_eligible_paths": 1688,
    "pair_cross_products_evaluated": 2816,
    "pareto_admitted_generated_pairs": 159,
    "processed_source_count": 6,
    "protection_rejects": 0,
    "raw_paths_produced": 3058,
    "refinement_iterations": 6,
    "retained_directional_candidates": 280,
    "source_materiality_pair_count": 6,
    "strict_rhythm_rejects": 31,
    "structural_rejects": 0,
    "tail_rejects": 1370
  },
  "timings": {
    "dag_seconds": 96.56674499996006,
    "diversity_seconds": 4.035865099984221,
    "family_generation_seconds": 0.020663199946284294,
    "global_coordinator_executions": 0,
    "hard_eligibility_seconds": 3.3377881000051275,
    "max_family_dag_seconds": 20.72514009999577,
    "pair_fleet_seconds": 4.001905404962599,
    "pareto_v3_seconds": 3.671616200823337,
    "total_seconds": 118.23606399993878
  },
  "v3_classification": "DEMAND_FIT_ANCHOR_CONFLICT"
}
```

### Repeat

```json
{
  "pareto_sha256": "d6c7cab9f86fa5ba498c83ff3d3316467b759acbc67737cd935ed5ccd7d14d94",
  "selected": null,
  "statistics": {
    "base_frontier_count": 11,
    "directional_strict_progress_rejects": 343,
    "duplicate_pair_rejects": 38,
    "endpoint_preflight_rejects": 0,
    "families_processed": 17,
    "final_frontier_count": 123,
    "fleet_rejects": 2448,
    "global_coordinator_executions": 0,
    "hard_eligible_paths": 1688,
    "pair_cross_products_evaluated": 2816,
    "pareto_admitted_generated_pairs": 159,
    "processed_source_count": 6,
    "protection_rejects": 0,
    "raw_paths_produced": 3058,
    "refinement_iterations": 6,
    "retained_directional_candidates": 280,
    "source_materiality_pair_count": 6,
    "strict_rhythm_rejects": 31,
    "structural_rejects": 0,
    "tail_rejects": 1370
  },
  "timings": {
    "dag_seconds": 95.90748349984642,
    "diversity_seconds": 4.046877499902621,
    "family_generation_seconds": 0.020981799927540123,
    "global_coordinator_executions": 0,
    "hard_eligibility_seconds": 3.366902699926868,
    "max_family_dag_seconds": 20.43490849994123,
    "pair_fleet_seconds": 4.001751002157107,
    "pareto_v3_seconds": 3.74549209990073,
    "total_seconds": 117.62657469999976
  },
  "v3_classification": "DEMAND_FIT_ANCHOR_CONFLICT"
}
```

Full source, family, raw/eligible/retained, pair, Pareto, and V3 histories are in the companion JSON.

### Independent cap sensitivity

| Cap | Sources | Families | Raw | Eligible | Retained | Pairs | Pareto | V3 | Local seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 11 | 29 | 5632 | 2930 | 247 | 1136 | 88 | DEMAND_FIT_ANCHOR_CONFLICT | 151.213192 |
| 32 | 6 | 17 | 3058 | 1688 | 280 | 2816 | 123 | DEMAND_FIT_ANCHOR_CONFLICT | 18.370357 |
| 64 | 6 | 17 | 3058 | 1688 | 476 | 5888 | 228 | DEMAND_FIT_ANCHOR_CONFLICT | 42.272322 |

```json
{
  "binding": false,
  "canonical_cap32_semantic_sha256": "46cd605e4ffb0a9aa00bb9376002b2001ada60760d460e1cbf38ba69aa549d99",
  "classification": "U6_DIRECTIONAL_FRONTIER_32_CAP_NON_BINDING",
  "normalized_union_winner_cap32_present": false,
  "normalized_union_winner_cap64_only": false
}
```

## ROUTE 6

```json
{
  "global_coordinator_executions": 0,
  "state": "NOT_RUN_ROUTE10_GATE_FAILED"
}
```

## Q

```json
{
  "classification_effect": false,
  "policy": "HISTORICAL_REFERENCE_ONLY",
  "state": "NOT_OBSERVED_ROUTE6_CANONICAL_PENDING"
}
```

## READINESS

```json
{
  "DAG shadow backend authoritative": false,
  "READY_FOR_FINAL_PILOT_USE": false,
  "READY_FOR_PR62_COMPLETION_REVIEW": false,
  "legacy backend removed": false,
  "production default changed": false
}
```

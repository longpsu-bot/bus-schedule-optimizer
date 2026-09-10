# PR62-U7 — Demand-Fit Authority Rehearsal

Policy-evidence experiment only. No production timetable is selected.

## 1. Review authority

- Base SHA: `a1b96c779c50318af8c4b2db6b1aacd2ab49d3cb`
- Canonical U6 semantic SHA-256: `46cd605e4ffb0a9aa00bb9376002b2001ada60760d460e1cbf38ba69aa549d99`
- Numerical epsilon: `1e-12` from hash-locked `src/bus_schedule_engine/contracts_v1/operational_selection_policy.py`
- Route 6 global executions: `0`

### Source artifacts

| Artifact | Commit | SHA-256 | Bytes |
|---|---:|---:|---:|
| `docs/engine/evidence/PR62_E_ROUTE10_CLOSED_LOOP_PILOT.json` | `c1a741d4b62b9f23fd46a5ee4b80cfc956e2bcfe` | `0589b36a1c92b0e1c0c390eb38adc97702137bf413a7bd1656623605333f6aa2` | 1136804 |
| `docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json` | `3d6ebb9c4126aca833f5d7ddce12e2fa4755442a` | `f9c5438c3d4b0b871b8fc1ec24a9dcd3a392efd76e85e7ab9ec385532c98c0c9` | 525934 |
| `docs/engine/evidence/PR62_M1_RANK_CONCORDANCE_CLARIFICATION.json` | `1902ac4e4b4d523d81a5a3d6d527c91fc8077b54` | `fcb77df73cc5bdf39738a7e81300456870938cab489144fbe2f59a414fbffcda` | 99878 |
| `docs/engine/evidence/PR62_N_ONE_TRIP_POLICY_REHEARSAL.json` | `c956284102eb307e10068c1128151943da5246d7` | `6e15939240963171e80e20b95a4d728df8ec6ccecb3f0b6b192135fb56ad371b` | 20224 |
| `docs/engine/evidence/PR62_O_PRODUCTION_POLICY_FREEZE.json` | `91702bae7d9b2a93afa6f470b3838f8b51e5a6df` | `91a93fa7e7abd4ede3e6848b241b0a3aa22f8f4942aa202c93dad6631df46346` | 133912 |
| `docs/engine/evidence/PR62_R_DEMAND_FIT_METRIC_VALIDITY.json` | `702e0fe494f340d27b862cd4ffbca64366f2df03` | `7f6b238981024ede96905072a6445f55df5fca09d41539088fdd1579b15840fd` | 273425 |
| `docs/engine/evidence/PR62_S_PHASE_ROBUST_MATERIALITY_POLICY_EXPERIMENT.json` | `b45a7317de9f8142da8d5976280b1503964ee054` | `e54ab2a5d366c3d76613a93e73fae0a722cd642f64dbc1f077618d51c6472c2a` | 268759 |
| `docs/engine/evidence/PR62_T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE.json` | `d497748e8141195eb97c7a3dc6ad026ad689ce3b` | `23d472e751d7811707f9b10dd3c1b8133a94ab0c7447356f06f14c7853ca2198` | 115723 |
| `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json` | `e9bcfec96470cbb6250a6bc82c3c3de65e967d49` | `0dcb75205c329a3fc512f475cb619eee61be9b3d25342ae6e12fa923a9bf6877` | 54651797 |
| `docs/engine/evidence/PR62_U6_V3_ANCHOR_CONFLICT_REVIEW.json` | `a1b96c779c50318af8c4b2db6b1aacd2ab49d3cb` | `2f1e40faca338cb799801667c02d949b34c4ee5f71658e005e6267e3afefb426` | 106376 |

## 2. Route 10 policy rehearsal

### Cap-final authorities

| Cap | Access-safe | A: SSE | B: TE | C: continuous | D: SSE/TE frontier |
|---:|---:|---|---|---|---|
| 16 | 55 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `9da4067ec1f7f7e7372cc9ea1062317c2f37ef6d72d4f556324833c8b59c5eec` | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 3: `9da4067ec1f7f7e7372cc9ea1062317c2f37ef6d72d4f556324833c8b59c5eec, bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c, da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` |
| 32 | 83 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | `1d3e0a6bf5508c30a45f919c37e30f81ea4857de806947288014c8d549f7d241` | 2: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c, da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` |
| 64 | 154 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `47230f4b711a8d9d36213e62e93ff507ac28258ba494fea0b569edc44495317f` | `08937da28a0d515dd72f6258d2515a3b2e2dd0055222fb9023994b7d184028c5` | 2: `47230f4b711a8d9d36213e62e93ff507ac28258ba494fea0b569edc44495317f, bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` |

### Source-batch evolution (canonical cap 32)

| Batch | Completed source | Access-safe | A | B | C | D size |
|---:|---|---:|---|---|---|---:|
| 0 | `BASE_FRONTIER` | 7 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 1 |
| 1 | `2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3` | 23 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 2 |
| 2 | `6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16` | 35 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 2 |
| 3 | `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0` | 55 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 2 |
| 4 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 60 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | `1d3e0a6bf5508c30a45f919c37e30f81ea4857de806947288014c8d549f7d241` | 2 |
| 5 | `c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7` | 66 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | `1d3e0a6bf5508c30a45f919c37e30f81ea4857de806947288014c8d549f7d241` | 2 |
| 6 | `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24` | 83 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | `1d3e0a6bf5508c30a45f919c37e30f81ea4857de806947288014c8d549f7d241` | 2 |

### Scalar growth summary

| Policy | Anchor changes | First change batch | Final anchor | Cap 16/32/64 agree | Classification |
|---|---:|---|---|---|---|
| A | 0 | `none` | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | True | `AUTHORITY_TOP_STABLE` |
| B | 2 | `1: 2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3` | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | False | `AUTHORITY_TOP_UNIVERSE_SENSITIVE` |
| C | 1 | `4: bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `1d3e0a6bf5508c30a45f919c37e30f81ea4857de806947288014c8d549f7d241` | False | `AUTHORITY_TOP_UNIVERSE_SENSITIVE` |

### D boundedness audit

No arbitrary frontier-size ceiling is applied.

| Cap | Access-safe | Frontier size/proportion | Exact frontier | Rhythm diversity | Continuous range | Wait range (min) | Fleet range |
|---:|---:|---|---|---|---|---|---|
| 16 | 55 | 3 / 0.054545 | `9da4067ec1f7f7e7372cc9ea1062317c2f37ef6d72d4f556324833c8b59c5eec, bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c, da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | `[(6, 8, 5, 0), (8, 11, 6, 0), (11, 12, 7, 0)]` | 12.905528866964–14.545320306779 | 9.592579549111–9.701359259870 | 12–13 |
| 32 | 83 | 2 / 0.024096 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c, da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | `[(8, 11, 6, 0), (11, 12, 7, 0)]` | 12.905528866964–14.157160266920 | 9.592579549111–9.649154876527 | 12–13 |
| 64 | 154 | 2 / 0.012987 | `47230f4b711a8d9d36213e62e93ff507ac28258ba494fea0b569edc44495317f, bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `[(9, 10, 8, 0), (11, 12, 7, 0)]` | 12.905528866964–14.289696048290 | 9.592579549111–9.707750260913 | 12–13 |

D stability: `AUTHORITY_SET_UNIVERSE_SENSITIVE`; boundedness: `MULTI_METRIC_FRONTIER_COHERENT_BUT_DOWNSTREAM_POLICY_REQUIRED`.

#### D source-batch entries and exits

| Batch | Frontier size | Entries | Exits |
|---:|---:|---|---|
| 0 | 1 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `none` |
| 1 | 2 | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | `none` |
| 2 | 2 | `none` | `none` |
| 3 | 2 | `none` | `none` |
| 4 | 2 | `none` | `none` |
| 5 | 2 | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` |
| 6 | 2 | `none` | `none` |

#### D cap-set overlaps

| Caps | Intersection / union | Intersection fingerprints |
|---|---|---|
| cap16_cap32 | 2 / 3 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c, da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` |
| cap16_cap64 | 1 / 4 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` |
| cap32_cap64 | 1 / 3 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` |

## 3. Phase / edge sensitivity and passenger/service context

The metrics below are contextual outcomes, not a hidden reranking and not actual onboard passenger delay.

| Fingerprint | SSE rank/value | TE rank/value | Continuous rank/value | Bucket exposure SSE rank/value | Bucket exposure TE-eq rank/value | Avg scheduled wait | Out max | In max | Rhythm | Fleet | Terminal excess total/max | Lineage | In D |
|---|---|---|---|---|---|---:|---:|---:|---|---:|---|---|---|
| `1d3e0a6bf5508c30a45f919c37e30f81ea4857de806947288014c8d549f7d241` | 44/0.012032576567 | 53/19.231650945837 | 1/12.762989322347 | 2/0.005539276720 | 1/12.486050797432 | 9.522948123386 | 12.900000000000 | 13.366666666667 | `[9, 9, 6, 0]` | 13 | 2414/68 | `PR62_U6_GENERATED from bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | False |
| `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 1/0.009369737096 | 5/16.957200065675 | 2/12.905528866964 | 1/0.005534496764 | 2/12.562560180023 | 9.592579549111 | 12.900000000000 | 13.366666666667 | `[11, 12, 7, 0]` | 13 | 2432/71 | `PR62_E_BASE_FRONTIER` | True |
| `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | 2/0.009503607918 | 1/16.582604218230 | 26/14.157160266920 | 27/0.006720273975 | 27/14.157160266920 | 9.649154876527 | 13.800000000000 | 14.066666666667 | `[8, 11, 6, 0]` | 12 | 2035/59 | `PR62_U6_GENERATED from c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7` | True |

### Exact bucket-edge comparison summary

| Pair | Direction | Changed departures | Bucket crossings | Total bucket edges crossed |
|---|---|---:|---:|---:|
| A_vs_B | outbound | 49 | 21 | 21 |
| A_vs_B | inbound | 48 | 22 | 23 |
| A_vs_C | outbound | 42 | 12 | 12 |
| A_vs_C | inbound | 0 | 0 | 0 |
| B_vs_C | outbound | 49 | 32 | 33 |
| B_vs_C | inbound | 48 | 22 | 23 |

Exact crossing departure positions are retained in the compact JSON evidence.

## 4. Historical Route 6

- Result: `HISTORICAL_ROUTE6_AUTHORITY_PRESERVED`
- Snapshot-only access-safe universe: 41 candidates
- A/B/C authority and D singleton: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`
- Route 6 global executions by U7: `0`

## 5. Criterion matrix (no weighted score)

| Criterion | A | B | C | D |
|---|---|---|---|---|
| C1 | PASS — finite unique SSE minimum with AUTHORITY_NOT_UNIQUE fail-closed semantics. | PASS — finite unique TE minimum with AUTHORITY_NOT_UNIQUE fail-closed semantics. | PASS — finite unique exact continuous-exposure minimum with AUTHORITY_NOT_UNIQUE fail-closed semantics. | PASS — finite nonempty SSE/TE sets using transitive strict Pareto: exact componentwise no-worse and improvement beyond epsilon in at least one dimension. |
| C2 | PASS — no weights, percentages, normalized composite, preferred identity, or historical-Q rule. | PASS — no weights, percentages, normalized composite, preferred identity, or historical-Q rule. | PASS — no weights, percentages, normalized composite, preferred identity, or historical-Q rule. | PASS — no weights, percentages, normalized composite, preferred identity, or historical-Q rule. |
| C3 | PASS — AUTHORITY_TOP_STABLE across completed batches and caps 16/32/64. | PASS WITH EVIDENCE — AUTHORITY_TOP_UNIVERSE_SENSITIVE; changes are descriptive, not rejection. | PASS WITH EVIDENCE — AUTHORITY_TOP_UNIVERSE_SENSITIVE; changes are descriptive, not rejection. | PASS WITH EVIDENCE — AUTHORITY_SET_UNIVERSE_SENSITIVE with explicit entries, exits, and overlaps. |
| C4 | CAUTION — point-count SSE retains bucket-edge sensitivity; exposure ranks are reported independently. | CAUTION — point-count TE retains bucket-edge sensitivity; exposure ranks are reported independently. | PASS WITH SCOPE — phase-robust to departure point buckets, while demand support remains bucket-defined. | CAUTION — primary frontier remains point-bucket-sensitive; continuous ranks stay diagnostic. |
| C5 | PASS — contextual wait/access/operations are reported without reranking; metric is not passenger welfare. | PASS — contextual wait/access/operations are reported without reranking; metric is not passenger welfare. | PASS — contextual wait/access/operations are reported without reranking; metric is not passenger welfare. | PASS — contextual wait/access/operations are reported without reranking; metric is not passenger welfare. |
| C6 | PASS — committed Route 6 snapshots preserve the historical authority; U7 executions remain zero. | PASS — committed Route 6 snapshots preserve the historical authority; U7 executions remain zero. | PASS — committed Route 6 snapshots preserve the historical authority; U7 executions remain zero. | PASS — committed Route 6 snapshots preserve the historical authority; U7 executions remain zero. |
| C7 | PASS — Route 10 result is an SSE authority fingerprint only, not a timetable selection. | PASS — Route 10 result is a TE authority fingerprint only, not a timetable selection. | PASS — Route 10 result is a continuous authority fingerprint only, not a timetable selection. | PASS — Route 10 result is an SSE/TE authority set only, not a timetable selection. |
| C8 | PASS — empty, malformed, nonfinite, epsilon ties, equality, transitivity-sensitive dominance, and nondominance fail or resolve deterministically. | PASS — empty, malformed, nonfinite, epsilon ties, equality, transitivity-sensitive dominance, and nondominance fail or resolve deterministically. | PASS — empty, malformed, nonfinite, epsilon ties, equality, transitivity-sensitive dominance, and nondominance fail or resolve deterministically. | PASS — empty, malformed, nonfinite, epsilon ties, equality, transitivity-sensitive dominance, and nondominance fail or resolve deterministically. |
| C9 | LOWEST CONTRACT CHANGE — remove concordance and preserve SSE authority; not sufficient alone. | MODERATE CONTRACT CHANGE — primary demand-fit authority changes from SSE to TE. | LARGER CONTRACT CHANGE — promotes continuous exposure from materiality to anchor authority. | UNRESOLVED — replacing one anchor with a set requires a separately designed downstream admissibility contract. |

## 6. Policy classifications

- A: `SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT`
- B: `SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT`
- C: `SUPPORTED_FOR_PRODUCTION_POLICY_EXPERIMENT`
- D: `SUPPORTED_WITH_UNRESOLVED_POLICY_QUESTION`

## 7. Primary U7 classification

`MULTIPLE_DEMAND_FIT_AUTHORITIES_REMAIN_PLAUSIBLE`

## 8. Exactly one next decision

Run one narrowed review-only A-versus-C downstream-admissibility rehearsal on the preserved Route 10 candidates; do not execute either route or change production selection.

## 9. Longer-term service-quality boundary

A/B/C/D concern demand-fit authority only. None resolves crowding, timetable-aware passenger arrival, expected-wait/access evidence, or operational reliability validation.

## 10. Final invariants

`production selector changed = false`
`U6 changed = false`
`Route 10 production timetable selected = false`
`Route 6 global executions = 0`
`final pilot workbooks changed = false`
`PR #62 modified = false`

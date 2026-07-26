# Route Corpus Characterization Draft V1

**DRAFT — NOT AN APPROVED OPERATIONAL TIMETABLE**

**Milestone:** 4C1 source audit, anonymization, corpus construction, structural validation, and
draft characterization only

This document reports current behavior. It does not approve a generated timetable, declare an
operational demand baseline, or freeze solver recommendations as permanent regression
expectations.

## Source identity and anonymization

The two approved workbooks remain private, external to the Git worktree, and uncommitted. Public
identity is limited to:

| Fixture | Public route name | Source SHA-256 |
|---|---|---|
| `CORPUS-ALPHA-80` | Anonymized Route Alpha | `085608bc9a326b1fe68e41aa9488c8382d27e2a83307b1d97fb66953c4b30c3f` |
| `CORPUS-BETA-46` | Anonymized Route Beta | `0b886ad7670eeb47bda53690ae905d473a1b0397fc4817ca0c674675650fd159` |

Private route and terminal identities are replaced with the fixture ID, public route name,
`Terminal 1`, and `Terminal 2`. Generic `A-###` and `B-###` trip IDs are retained. Workbook
metadata, organization/operator identity, vehicle identity, local paths, and historical free-text
conclusions are excluded. Observation dates use one deterministic −365-day shift, from the
private 15-day period to 2025-07-01 through 2025-07-15.

The historical diagnostic, hourly-allocation, and optimized-timetable sheets are excluded from
corpus truth. They are not engine input or exact solver oracles.

## Raw trip-observation evidence and proxy

The private `SAN_LUONG` rows are not non-overlapping demand blocks. Every row maps one-to-one to a
Scenario A trip and its interval exactly equals that trip's departure-to-arrival span. The corpus
therefore preserves these rows as `raw_trip_observations`, including their overlaps, but never
supplies them to Contract V1 demand normalization.

`departure_hour_proxy_v1` is a separate derived dataset:

- passenger volumes are grouped by direction and Scenario A departure hour;
- every block lists all contributing Scenario A trip IDs;
- directional and total 15-day passenger volumes are conserved exactly;
- blocks are contiguous and non-overlapping;
- no empty hour is fabricated as zero demand; and
- a nonempty block may extend to the next observed departure hour or through the Scenario B
  endpoint to provide complete fixed-resource solver coverage.

The proxy has LOW confidence and status `PROXY_SENSITIVITY_ONLY`. To avoid rounding repeating
15-day-to-daily fractions, Contract V1 receives the exactly conserved 15-day totals as unscaled
proxy weights through the existing `average_day` transport classification. The original
`total_observation_period` classification remains on every raw row and is also recorded as
`source_volume_type` on derived blocks. These weights are not observed average-day passenger
counts.

## Source-audit discrepancies and corrections

Exact timetable rows are authoritative over the following summary cells. No other
parameter-versus-exact-timetable contradiction was observed.

| Fixture | Sheet and field | Source | Exact-row value | Evidence | Correction |
|---|---|---:|---:|---|---|
| Alpha | `THONG_SO_A.total_daily_trips` | 80 | 52 | `A-001`–`A-052` | `A_TOTAL_FROM_EXACT_TIMETABLE` |
| Beta | `THONG_SO_A.terminal_1_first_departure` | 04:30 | 05:30 | `A-001` | `A_ENDPOINT_FROM_EXACT_TIMETABLE` |
| Beta | `THONG_SO_A.terminal_1_last_departure` | 18:25 | 18:15 | `A-013` | `A_ENDPOINT_FROM_EXACT_TIMETABLE` |
| Beta | `THONG_SO_A.terminal_2_first_departure` | 05:35 | 05:30 | `A-014` | `A_ENDPOINT_FROM_EXACT_TIMETABLE` |
| Beta | `THONG_SO_A.terminal_2_last_departure` | 19:40 | 17:20 | `A-026` | `A_ENDPOINT_FROM_EXACT_TIMETABLE` |

Each correction is approved for corpus construction only and is classified separately from
observed source facts and scenario assumptions.

## Corpus scenario assumptions

The private sources do not declare Contract V1 fleet limits. The following remain explicit corpus
assumptions:

| Fixture | A fleet limit | B fleet limit | A/B day type | Proxy confidence |
|---|---:|---:|---|---|
| Alpha | 5 | 8 | WEEKDAY | LOW |
| Beta | 4 | 7 | WEEKDAY | LOW |

The proxy confidence supersedes the earlier proposed MEDIUM value following expert direction. A
fleet limit is never described as an operator-declared fleet fact.

## Exact structural facts

| Fact | Alpha | Beta |
|---|---:|---:|
| Scenario A trips | 52 (26/26) | 26 (13/13) |
| Scenario B trips | 80 (40/40) | 46 (23/23) |
| Scenario B runtime | exact 55–65 minutes by trip | exact 100 minutes |
| Raw trip-observation rows | 52 (26/26) | 26 (13/13) |
| Adjacent raw overlap pairs | 50; 20–40 minutes | 24; 10–55 minutes |
| Proxy blocks | 30 (15/15) | 26 (13/13) |
| Terminal 1-direction passenger total | 5,707 | 3,052 |
| Terminal 2-direction passenger total | 5,991 | 2,887 |
| Overall passenger total | 11,698 | 5,939 |
| Vehicle capacity | 28 | 28 |
| Route type | intra-provincial | intra-provincial |
| Minimum turnaround | 5 minutes | 5 minutes |
| Load-factor policy | 0.85 / 0.90 | 0.85 / 0.90 |

Alpha's final Terminal 2-direction proxy block extends one additional hour through the Scenario B
endpoint. Beta has one interior nonempty block extended across the absent departure hour and one
final block extended through the Scenario B endpoint. No zero-volume row is introduced.

## Natural unified-service behavior

The default `ScenarioBEvaluationPolicyV1` requires MEDIUM confidence. Because the proxy is LOW
confidence, all three solver selections behave identically for both fixtures:

| Fixture | Solver choice | B disposition | Adjustment decision/action | Solver attempted | Outcome/recommendation |
|---|---|---|---|---:|---|
| Alpha | HEURISTIC | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Alpha | OR_TOOLS | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Alpha | BOTH | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | HEURISTIC | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | OR_TOOLS | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | BOTH | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |

The natural business result is therefore no solver run, not a forced fixed-resource timetable.
The common reason set includes block shortage evidence, unproven joint donor capacity, headway
imbalance, and `ADJUSTMENT_DECISION_DATA_INSUFFICIENT`.

## `PROXY_SENSITIVITY_ONLY` fixed-resource diagnostic

This separate diagnostic lowers only the minimum accepted demand confidence to LOW. It normalizes
once, evaluates B once, constructs the existing canonical heuristic and OR-Tools
service-quality requests, runs both through `run_schedule_solver_v1()`, and compares accepted
solutions under the common quality problem.

### Alpha

| Solver | Native status | Generation result | Accepted | Vector eligible | Recommendation |
|---|---|---|---:|---:|---|
| Heuristic | `UNKNOWN` | `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | No | No | None |
| OR-Tools | `UNKNOWN` | `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | No | No | None |

The comparison reason is `NO_ACCEPTED_SOLUTION`. `UNKNOWN` is not infeasibility. No Scenario C,
fleet recommendation, objective vector, or solver recommendation is reported. The pre-solve B
fleet assessment is feasible at the assumed limit of 8, with minimum required fleet 8 and an 8/0
initial split, but that assessment is not a generated-solution result.

### Beta

Both candidates were independently accepted with native `FEASIBLE` status. Neither solver proved
global optimality.

| Result | Heuristic | OR-Tools |
|---|---:|---:|
| Available/minimum fleet | 7 / 7 | 7 / 7 |
| Initial Terminal 1/2 split | 3 / 4 | 3 / 4 |
| Shifted trips | 42 | 0 |
| Total shift minutes | 484 | 0 |
| Maximum shift minutes | 23 | 0 |
| Regime count | 5 | 22 |

The heuristic vector is lexicographically better at stage 6, so the diagnostic comparison reports
`HEURISTIC_VECTOR_BETTER`. This is a proxy-sensitivity recommendation only.

| Stage | Objective | Heuristic | OR-Tools |
|---:|---|---:|---:|
| 1 | `no_service_block_count` | 0 | 0 |
| 2 | `critical_block_count` | 26 | 26 |
| 3 | `total_critical_shortage_trips` | 205 | 205 |
| 4 | `planning_warning_block_count` | 26 | 26 |
| 5 | `total_planning_shortage_trips` | 217 | 217 |
| 6 | `maximum_positive_demand_headway_minutes` | 39 | 40 |
| 7 | `total_positive_demand_block_max_gap_minutes` | 910 | 920 |
| 8 | `directional_demand_alignment_error` | 408,920 | 440,920 |
| 9 | `maximum_within_regime_headway_change_minutes` | 1 | 5 |
| 10 | `total_within_regime_headway_change_minutes` | 2 | 10 |
| 11 | `maximum_regime_transition_headway_jump_minutes` | 7 | 15 |
| 12 | `total_regime_transition_headway_jump_minutes` | 26 | 90 |
| 13 | `shifted_trip_count` | 42 | 0 |
| 14 | `total_shift_minutes` | 484 | 0 |
| 15 | `maximum_shift_minutes` | 23 | 0 |

The comparison stops at the first differing objective. OR-Tools' zero-shift advantage is
lower-priority and cannot override the heuristic's stage-6 advantage. OR-Tools returned
`FEASIBLE`, so no optimality claim is available.

## Repeatability and benchmark controls

Characterization ran against source tree based on
`ba2df18a6e20b184776da05f0c4c592b4f266aaf`, using Python 3.13.5 and OR-Tools 9.15.6755 on
Windows. Ignored machine-readable outputs record the exact Git commit and dirty-worktree marker.

Requested controls were one worker, random seed 0, and 30 seconds per solver invocation. The
OR-Tools adapter applied all three. The canonical heuristic is deterministic but does not
implement generic worker, seed, or time-limit controls; its effective values are recorded as
unsupported rather than falsely claimed.

| Fixture | Solver | Cold | Warm 1 | Warm 2 |
|---|---|---:|---:|---:|
| Alpha | Heuristic | 0.020 s | 0.019 s | 0.017 s |
| Alpha | OR-Tools | 26.310 s | 30.264 s | 30.249 s |
| Beta | Heuristic | 0.105 s | 0.140 s | 0.163 s |
| Beta | OR-Tools | 30.091 s | 30.048 s | 30.052 s |

Alpha's heuristic and OR-Tools repetitions and Beta's heuristic repetitions agreed on acceptance,
candidate fingerprint, generation status, native status, objective vector eligibility/value,
outcome fingerprint, problem fingerprint, and solution fingerprint.

Beta OR-Tools agreed on accepted `FEASIBLE` status, problem fingerprint, candidate fingerprint,
and the full objective vector in all three runs. Its cold and second warm runs shared solution
fingerprint
`3b4f3b3d2903be117075da3eedc137b4d83ef94365f0805171434f5e1d26b69e`
and outcome fingerprint
`03856480e4fbf9ae48c86c7f032ce6beeccf8b0813e24ed2afdf5552c438d60e`; the first warm run
reported solution fingerprint
`c245db1c97941f310e685d653c308eb48b4d3b56550568c9487e9db1c99aa6fa`
and outcome fingerprint
`e86489859923115325735d277332599baa2758620fa5eb8e0c3ebdb703e9de37`.
The difference is preserved as observed solver nondeterminism even though the public quality
vector and recommendation were unchanged. Wall-clock duration varied and is not a test
assertion.

## Historical non-authoritative reference

The private historical optimized sheet was read only as
`HISTORICAL_NON_AUTHORITATIVE_REFERENCE`. It remains excluded from fixtures and tests.

- Alpha's historical reference contains 80 trips (40/40) and eight vehicle labels, matching the
  corpus B total/directional counts and assumed fleet limit. Only 22 historical departure times
  exactly match B within the same direction. A positional, non-authoritative comparison indicates
  66 changed departures, 780 total shift minutes, and a 25-minute maximum shift. The current
  proxy sensitivity produced no accepted candidate, so it cannot reproduce or replace that
  reference.
- Beta's historical reference contains 46 trips (23/23) and seven vehicle labels. It has 21 exact
  directional departure-time matches with B; a positional, non-authoritative comparison indicates
  34 changed departures, 675 total shift minutes, and a 40-minute maximum shift. The current
  OR-Tools sensitivity candidate retains B exactly, while the heuristic shifts 42 trips by 484
  minutes in total with a 23-minute maximum.

These comparisons are descriptive only. Historical `OPT-*` rows do not carry the canonical
one-to-one B trace and were produced under a different expert-assist method, so positional shift
figures are not regression expectations.

## Status and proof qualifications

- Default-policy no-run results are valid business decisions under LOW proxy confidence.
- Heuristic `FEASIBLE` means independently validated feasibility, not optimality.
- OR-Tools `FEASIBLE` means an independently validated candidate without an optimality proof.
- `UNKNOWN` means no accepted candidate within the invocation, not infeasibility.
- Proxy weights, vectors, recommendations, timings, and historical differences are draft
  characterization evidence only.
- No result is approved for operation or frozen as a Milestone 4C2 baseline.

## Questions requiring expert approval

1. Are fleet assumptions 5/8 and 4/7 acceptable for the corpus scenarios?
2. Are exact timetable rows correctly treated as authority over inconsistent summary cells?
3. Is LOW confidence appropriate for `departure_hour_proxy_v1`, including its use of conserved
   15-day totals as unscaled sensitivity weights?
4. Should the historical optimized sheet remain diagnostic-only?
5. Are the reported native statuses and eligible Beta vectors acceptable candidates for later
   regression baselines?
6. Which outcomes, if any, should be frozen in Milestone 4C2?
7. Are the measured solve times acceptable for future CI?
8. Are the documented nonempty block extensions acceptable for contiguous solver coverage without
   fabricated zero-demand hours?

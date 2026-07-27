# Route Corpus Characterization Draft V1

**DRAFT — NOT AN APPROVED OPERATIONAL TIMETABLE**

**Milestone:** 4C1 source audit, anonymization, corrected corpus construction, structural
validation, and draft characterization only

This document reports current behavior. It does not approve a generated timetable, establish an
operational demand baseline, or freeze a solver result for Milestone 4C2.

## Source identity and anonymization

The approved workbooks remain private, external to the Git worktree, and uncommitted.

| Fixture | Public route name | Source SHA-256 |
|---|---|---|
| `CORPUS-ALPHA-80` | Anonymized Route Alpha | `085608bc9a326b1fe68e41aa9488c8382d27e2a83307b1d97fb66953c4b30c3f` |
| `CORPUS-BETA-46` | Anonymized Route Beta | `0b886ad7670eeb47bda53690ae905d473a1b0397fc4817ca0c674675650fd159` |

Private route and terminal identities are replaced with the fixture ID, public route name,
`Terminal 1`, and `Terminal 2`. Generic `A-###` and `B-###` trip IDs are retained. Workbook
metadata, organization/operator identity, vehicle identity, local paths, and historical free-text
conclusions are excluded. Both fixtures use a deterministic −365-day date shift, preserving the
15-day observation period as 2025-07-01 through 2025-07-15.

Historical diagnostic, hourly-allocation, and optimized-timetable sheets remain
`HISTORICAL_NON_AUTHORITATIVE_REFERENCE`. They are excluded from corpus truth, engine input, and
exact regression expectations.

## Raw trip-observation evidence

Every private `SAN_LUONG` row maps one-to-one to a Scenario A trip. Its raw interval exactly
equals that trip's departure-to-arrival span. Those intervals overlap because they are
trip-observation evidence, not non-overlapping demand blocks.

The corpus preserves every row, passenger total, direction, source trip ID, observation day,
volume classification, shifted date, and overlap as `raw_trip_observations`.
`contract_v1_demand_interval_eligible` is false, and test support never supplies these raw
intervals to Contract V1.

## Corrected `departure_hour_proxy_v1`

The separate proxy groups raw passenger totals by direction and the clock hour containing each
Scenario A departure. Every derived block records all contributing source trip IDs.

Each proxy block retains:

```text
passenger_volume = exact sum of source 15-day totals
volume_type = TOTAL_OBSERVATION_PERIOD
observation_days = 15
source_volume_type = TOTAL_OBSERVATION_PERIOD
```

Contract V1 therefore computes:

```text
average_daily_passenger_count = passenger_volume / observation_days
```

The normalization authority receives `observation_days=15` for every proxy block.
For example, Alpha block `PROXY-TERMINAL_1_TO_2-04` retains 264 passengers and normalizes to
264 / 15 = 17.6 passengers per average day. Alpha block
`PROXY-TERMINAL_2_TO_1-05` retains 146 and normalizes to 146 / 15 =
9.733333333333… . The source-period values are not rounded, truncated, multiplied, rescaled, or
relabeled as daily observations.

### Boundary method

- An ordinary observed hour H uses `[H:00, H+1:00)`.
- The first block starts at the later of H:00 and the exact Scenario B first departure.
- The final block ends one minute after the exact Scenario B last departure, so the locked final
  departure belongs to the half-open interval.
- A populated block never extends to the next observed hour.
- An unobserved interior hour is not filled, interpolated, or absorbed by a neighboring block.

Exact corrected boundaries are:

| Fixture | Direction | First block | Final block | Coverage |
|---|---|---|---|---|
| Alpha | Terminal 1→2 | `04:30–05:00` | `18:00–18:31` | `COMPLETE` |
| Alpha | Terminal 2→1 | `05:35–06:00` | `19:00–20:01` | `COMPLETE` |
| Beta | Terminal 1→2 | `05:30–06:00` | `18:00–18:26` | `PROXY_COVERAGE_INCOMPLETE` |
| Beta | Terminal 2→1 | `05:00–06:00` | `17:00–18:11` | `COMPLETE` |

The only interior coverage issue is:

| Fixture | Direction | Missing interval | Surrounding observed hours | Code |
|---|---|---|---|---|
| Beta | Terminal 1→2 | `17:00–18:00` | `16:00`, `18:00` | `PROXY_INTERIOR_HOUR_UNOBSERVED` |

No zero-demand row represents this hour, and no populated block crosses it. Beta's overall proxy
status is `PROXY_COVERAGE_INCOMPLETE`, so its
`contract_v1_demand_interval_eligible` value is false. Alpha's overall coverage is complete.

## Source-audit discrepancies and corrections

Exact timetable rows remain authoritative over the following summary cells:

| Fixture | Sheet and field | Source | Exact-row value | Evidence | Correction |
|---|---|---:|---:|---|---|
| Alpha | `THONG_SO_A.total_daily_trips` | 80 | 52 | `A-001`–`A-052` | `A_TOTAL_FROM_EXACT_TIMETABLE` |
| Beta | `THONG_SO_A.terminal_1_first_departure` | 04:30 | 05:30 | `A-001` | `A_ENDPOINT_FROM_EXACT_TIMETABLE` |
| Beta | `THONG_SO_A.terminal_1_last_departure` | 18:25 | 18:15 | `A-013` | `A_ENDPOINT_FROM_EXACT_TIMETABLE` |
| Beta | `THONG_SO_A.terminal_2_first_departure` | 05:35 | 05:30 | `A-014` | `A_ENDPOINT_FROM_EXACT_TIMETABLE` |
| Beta | `THONG_SO_A.terminal_2_last_departure` | 19:40 | 17:20 | `A-026` | `A_ENDPOINT_FROM_EXACT_TIMETABLE` |

No other parameter-versus-exact-timetable contradiction was observed. Each correction is
approved for corpus construction only and remains distinct from observed facts and assumptions.

## Corpus assumptions and exact structural facts

Fleet limits are explicit corpus assumptions, not operator-declared facts.

| Fixture | A fleet | B fleet | A/B day type | Proxy confidence |
|---|---:|---:|---|---|
| Alpha | 5 | 8 | WEEKDAY | LOW |
| Beta | 4 | 7 | WEEKDAY | LOW |

| Fact | Alpha | Beta |
|---|---:|---:|
| Scenario A trips | 52 (26/26) | 26 (13/13) |
| Scenario B trips | 80 (40/40) | 46 (23/23) |
| Scenario B runtime | exact 55–65 minutes | exact 100 minutes |
| Raw observation rows | 52 (26/26) | 26 (13/13) |
| Adjacent raw overlap pairs | 50; 20–40 minutes | 24; 10–55 minutes |
| Proxy blocks | 30 (15/15) | 26 (13/13) |
| Terminal 1-direction passengers | 5,707 | 3,052 |
| Terminal 2-direction passengers | 5,991 | 2,887 |
| Overall passengers | 11,698 | 5,939 |
| Vehicle capacity | 28 | 28 |
| Minimum turnaround | 5 minutes | 5 minutes |
| Load-factor policy | 0.85 / 0.90 | 0.85 / 0.90 |

Directional and overall 15-day passenger totals are exactly conserved.

## Natural unified-service characterization

The default `ScenarioBEvaluationPolicyV1` requires MEDIUM demand confidence. Both proxies remain
LOW confidence. Executing the normal unified service produces the same authoritative business
result for every solver selection:

| Fixture | Solver choice | B disposition | Decision/action | Solver attempted | Recommendation |
|---|---|---|---|---:|---|
| Alpha | HEURISTIC | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Alpha | OR_TOOLS | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Alpha | BOTH | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | HEURISTIC | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | OR_TOOLS | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | BOTH | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |

No heuristic outcome, OR-Tools outcome, comparison, or recommended outcome is produced.

## `PROXY_SENSITIVITY_ONLY` readiness

The diagnostic lowers only the minimum accepted confidence to LOW. It runs neither solver unless
both canonical requests can share a canonical quality problem.

| Fixture | Coverage gate | Quality builder | Diagnostic | Reason |
|---|---|---|---|---|
| Alpha | Passed | Rejected | `NOT_RUN` | `QUALITY_REQUEST_UNREPRESENTABLE_DEMAND_PRECISION` |
| Beta | Failed | Not attempted | `NOT_RUN` | `PROXY_COVERAGE_INCOMPLETE` |

For Alpha, normalization and LOW-confidence evaluation each ran once. The canonical quality
builder then returned:

- primary code: `ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY`;
- exact nested code: `ORTOOLS_QUALITY_DEMAND_PRECISION_UNSUPPORTED`.

The repeating normalized daily values exceed the quality model's current six-decimal exact
authority. This is a proxy data-representation limitation—not infeasibility, `UNKNOWN`,
insufficient fleet, or a failed optimization. The heuristic request was not constructed because
no common quality problem existed.

For Beta, the explicit `17:00–18:00` gap fails proxy eligibility before normalization for the
diagnostic. Neither canonical request is constructed.

Both fixtures therefore have:

```text
heuristic_outcome = null
ortools_outcome = null
comparison = null
recommendation = null
benchmark_run_count = 0
```

No diagnostic solver timing is reported because no diagnostic solver ran.

## Invalid earlier characterization discarded

An earlier unmerged characterization transported exact 15-day totals as `AVERAGE_DAY` and
stretched populated blocks across unobserved or endpoint hours. Its sensitivity outcomes,
vectors, comparison, shift interpretation, and timings are invalid and have been removed as
current evidence. They are not candidate baselines and must not be used in Milestone 4C2.

## Determinism and proof qualifications

- Rebuilding from the unchanged private hashes is byte-identical under `--write` and `--verify`.
- Raw fact fingerprints remain unchanged; proxy fingerprints change because volume
  classification and block boundaries were corrected.
- Default-policy no-run results are valid business decisions under LOW proxy confidence.
- `PROXY_COVERAGE_INCOMPLETE` is missing evidence, not zero demand.
- Unsupported decimal precision is a representation limitation, not a solver status.
- No operational timetable, vector, recommendation, or performance baseline is approved.

## Questions requiring expert approval

1. Are fleet assumptions 5/8 and 4/7 acceptable for corpus scenarios?
2. Are exact timetable rows correctly authoritative over the inconsistent summary cells?
3. Is LOW confidence appropriate for `departure_hour_proxy_v1`?
4. Are the first/final boundary method and explicit Beta interior gap correctly represented?
5. Should the exact normalized decimal limitation remain a not-run gate until a separately
   approved precision policy exists?
6. Should the historical optimized sheet remain diagnostic-only?
7. Which outcomes, if any, should be designed and approved as Milestone 4C2 baselines?

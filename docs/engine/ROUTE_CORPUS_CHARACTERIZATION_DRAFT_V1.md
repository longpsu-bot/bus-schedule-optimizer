# Route Corpus Characterization Draft V1

**DRAFT — NOT AN APPROVED OPERATIONAL TIMETABLE**

**Milestone:** 4C2A exact rational demand authority, hard uniform headways inside adaptive
demand-derived regimes, and real-route-derived differential characterization.

This document reports diagnostic behavior. It does not approve a timetable, establish an
operational demand baseline, or freeze an objective vector or recommendation.

## Corpus and evidence boundary

The approved source workbooks remain private, external to the Git worktree, and uncommitted.
Their public fixtures retain anonymized route/terminal names, generic trip IDs, a deterministic
365-day date shift, and the exact 15-day observation period.

| Fixture | Public route name | Source SHA-256 |
|---|---|---|
| `CORPUS-ALPHA-80` | Anonymized Route Alpha | `085608bc9a326b1fe68e41aa9488c8382d27e2a83307b1d97fb66953c4b30c3f` |
| `CORPUS-BETA-46` | Anonymized Route Beta | `0b886ad7670eeb47bda53690ae905d473a1b0397fc4817ca0c674675650fd159` |

Raw `SAN_LUONG` rows remain overlapping trip-observation evidence and are never supplied as
Contract V1 demand intervals. The separate `departure_hour_proxy_v1` groups exact passenger
totals by direction and departure hour. It retains:

```text
passenger_volume = exact sum of source 15-day totals
volume_type = TOTAL_OBSERVATION_PERIOD
observation_days=15
source_volume_type = TOTAL_OBSERVATION_PERIOD
```

An ordinary observed hour uses `[H:00, H+1:00)`. The first block starts at the later of the
observed hour and Scenario B's first departure. The final block ends one minute after Scenario
B's locked final departure. No populated block is stretched across an unobserved hour.

## Exact rational authority

The quality request now builds an internal frozen, slotted authority:

```text
_ExactBlockDemand(block_id, numerator, denominator)
_ExactDemandAuthority(blocks, authority_fingerprint)
```

`AVERAGE_DAY` converts `Decimal(str(passenger_count))` directly to a `Fraction`.
`TOTAL_OBSERVATION_PERIOD` divides that exact fraction by `observation_days`. Source IDs are
resolved through each analysis block's `source_interval_ids` and native, adaptive `SUM`, and
manual `SUM` blocks are aggregated exactly.

For Alpha:

```text
146 / 15 = 146/15
264 / 15 = 88/5
authority fingerprint =
eeda98388bb56a340ab9d093243070e9b538fa0d4c1c5191429e26b69ffb0ac7
problem adapter_context_fingerprint =
eeda98388bb56a340ab9d093243070e9b538fa0d4c1c5191429e26b69ffb0ac7
```

Scaling uses one denominator across both directions. Alpha's global LCM is `15`; its global
weight GCD is `1`. Thus `146/15 -> 146` and `88/5 -> 264`. The scaled directional totals are
`5,707` outbound and `5,991` inbound, preserving the exact 15-day totals. Other focused
fixtures prove global GCD reduction while retaining proportional weights. No rational value is
rounded, truncated, or capped; unsafe integer cross-products fail closed.

## Adaptive regimes with exact internal regularity

Regimes are derived independently from authoritative directional demand blocks. Adjacent blocks
merge only when their exact planning service rates match. The solver creates a separate
integer-minute decision variable `H_R >= 1` for each regime. For each chronological adjacent
pair, it proves whether both trips are members of the same authoritative regime and conditionally
enforces:

```text
same_regime_pair(i, R) -> departure[i+1] - departure[i] == H_R
```

No route-wide or direction-wide headway is fixed. Different regimes may receive different
solver-derived `H_R` values. A pair crossing two regimes is a transition; it is excluded from
both internal sequences and remains controlled by technical feasibility and objective stages
11–12. Objective stages 9–10 remain in the unchanged 15-stage vector and must both be zero for
every accepted candidate.

Independent validation re-derives half-open block membership, regime membership, internal
pairs, transitions, and headways from solved departures. It does not trust solver variables or
candidate labels. Unequal, non-positive, non-whole-minute, missing, multiple, or mislabeled
within-regime evidence fails closed. Balanced floor/ceiling rounding is not accepted.

The internal characterization statuses are `UNIFORM`,
`SINGLE_TRIP_HEADWAY_NOT_MEASURABLE`, `NO_TRIPS`, and `INVALID_NON_UNIFORM`. The frozen public V1
schema is unchanged: accepted measurable `UNIFORM` rows serialize through its existing
`REGULAR` value. A candidate containing a zero-trip, one-trip, or invalid non-uniform
authoritative regime is rejected with
`HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1`; the regime remains explicit in raw candidate
and characterization evidence and is never silently omitted or assigned a fabricated positive
target. Supporting accepted zero-trip or one-trip regimes requires a future, separately
authorized Contract revision.

## Terminal physical-occupancy constraint and corpus limitation

TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED

Contract V1 supports optional authoritative per-terminal physical vehicle-occupancy capacities
in Scenario B. When supplied, arrivals count before same-minute departures and the constraint is
enforced in Scenario B evaluation, canonical OR-Tools hard models, and independent candidate
validation. This physical state remains separate from circulation ready stock.

This limitation applies to both Alpha and Beta characterization. No per-terminal physical
occupancy value was supplied or inferred, so terminal-capacity feasibility cannot be claimed for
either fixture. The missing limits did not cause Alpha's solver statuses or Beta's proxy-coverage
gap.

## Natural unified-service execution

The default policy requires MEDIUM demand confidence, while both proxies are LOW. Execution for
all three solver selections remains:

| Fixture | Solver choice | B disposition | Action | Solver attempted | Recommendation |
|---|---|---|---|---:|---|
| Alpha | HEURISTIC | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Alpha | OR_TOOLS | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Alpha | BOTH | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | HEURISTIC | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | OR_TOOLS | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |
| Beta | BOTH | `B_INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | No | None |

## Alpha LOW-confidence sensitivity

Alpha has complete directional proxy coverage. One normalization and one evaluation constructed
both canonical requests before either solver ran. The heuristic ran first and OR-Tools second.
Controls were 30 seconds, one worker, and seed 0 for one cold and two warm repetitions.

| Marker | Solver | Native status | Business result | Accepted | Eligible vector | Seconds |
|---|---|---|---|---:|---|---:|
| COLD | HEURISTIC | `UNKNOWN` | `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | No | None | 0.010835 |
| COLD | OR_TOOLS | `UNKNOWN` | `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | No | None | 30.035635 |
| WARM_1 | HEURISTIC | `UNKNOWN` | `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | No | None | 0.010841 |
| WARM_1 | OR_TOOLS | `UNKNOWN` | `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | No | None | 30.031709 |
| WARM_2 | HEURISTIC | `UNKNOWN` | `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | No | None | 0.010880 |
| WARM_2 | OR_TOOLS | `UNKNOWN` | `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | No | None | 30.038963 |

Neither solver emitted a candidate. Therefore:

- the heuristic was not accepted and was not validator-rejected on uniformity—there was no
  candidate to validate;
- no regime representability rejection occurred in the corpus run because there was no
  candidate;
- OR-Tools was not accepted, did not prove infeasibility, and did not prove optimality;
- exact uniformity remains part of the model, but `UNKNOWN` must not be described as caused by
  uniformity alone;
- no result is `FEASIBLE` or `OPTIMAL`;
- both eligible vectors are `None`;
- comparison returned `NO_ACCEPTED_SOLUTION`;
- no recommendation was emitted.

The compared status/fingerprint/vector fields were identical across all three repetitions for
each solver. Durations are diagnostic measurements and do not participate in recommendation.

### Alpha authoritative regime characterization

The following table reports every demand-derived regime. Because neither solver emitted a
candidate, solved trip count, internal sequence, `H_R`, minimum/maximum headway, entering/leaving
transition, and endpoint/fleet/turnaround binding status are all **not measurable / not
determinable** for every row. This is missing solver evidence, not a zero-trip solution.

| Direction | Regime | Window | Blocks and exact demand → scaled weight |
|---|---|---|---|
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0001` | 04:30–05:00 | `DB-OUTBOUND-0001` 88/5 → 264 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0002` | 05:00–06:00 | `DB-OUTBOUND-0002` 117/5 → 351 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0003` | 06:00–07:00 | `DB-OUTBOUND-0003` 65/1 → 975 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0004` | 07:00–09:00 | `DB-OUTBOUND-0004` 211/5 → 633; `DB-OUTBOUND-0005` 146/5 → 438 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0005` | 09:00–10:00 | `DB-OUTBOUND-0006` 56/5 → 168 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0006` | 10:00–11:00 | `DB-OUTBOUND-0007` 491/15 → 491 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0007` | 11:00–13:00 | `DB-OUTBOUND-0008` 44/3 → 220; `DB-OUTBOUND-0009` 114/5 → 342 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0008` | 13:00–14:00 | `DB-OUTBOUND-0010` 121/5 → 363 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0009` | 14:00–16:00 | `DB-OUTBOUND-0011` 331/15 → 331; `DB-OUTBOUND-0012` 124/15 → 124 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0010` | 16:00–18:00 | `DB-OUTBOUND-0013` 404/15 → 404; `DB-OUTBOUND-0014` 427/15 → 427 |
| outbound | `ORTOOLS-QUALITY-OUTBOUND-0011` | 18:00–18:31 | `DB-OUTBOUND-0015` 176/15 → 176 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0001` | 05:35–06:00 | `DB-INBOUND-0001` 146/15 → 146 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0002` | 06:00–07:00 | `DB-INBOUND-0002` 62/3 → 310 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0003` | 07:00–08:00 | `DB-INBOUND-0003` 25/1 → 375 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0004` | 08:00–09:00 | `DB-INBOUND-0004` 313/15 → 313 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0005` | 09:00–11:00 | `DB-INBOUND-0005` 491/15 → 491; `DB-INBOUND-0006` 134/5 → 402 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0006` | 11:00–12:00 | `DB-INBOUND-0007` 296/15 → 296 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0007` | 12:00–13:00 | `DB-INBOUND-0008` 125/3 → 625 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0008` | 13:00–14:00 | `DB-INBOUND-0009` 17/1 → 255 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0009` | 14:00–18:00 | `DB-INBOUND-0010` 136/5 → 408; `DB-INBOUND-0011` 623/15 → 623; `DB-INBOUND-0012` 502/15 → 502; `DB-INBOUND-0013` 643/15 → 643 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0010` | 18:00–19:00 | `DB-INBOUND-0014` 254/15 → 254 |
| inbound | `ORTOOLS-QUALITY-INBOUND-0011` | 19:00–20:01 | `DB-INBOUND-0015` 116/5 → 348 |

No headway sequence, transition headway, or repeated `H_R` is claimed. Whether different Alpha
regimes receive different `H_R` values remains unresolved. **No externally fixed headway was
imposed.**

## Beta LOW-confidence sensitivity

Beta retains an actual unobserved outbound interval from `17:00` to `18:00` with
`PROXY_INTERIOR_HOUR_UNOBSERVED`. No zero-demand row, interpolation, smoothing, or neighboring
block extension was introduced.

```text
coverage_status = PROXY_COVERAGE_INCOMPLETE
quality request constructed = false
heuristic request constructed = false
solver runs = 0
vectors = null
recommendation = null
```

## Evidence that the solver layer is doing its job

1. Small quality instances are exhaustively enumerated.
2. Enumeration independently excludes non-uniform within-regime candidates.
3. CP-SAT vectors match the true enumerated lexicographic optimum on feasible small fixtures.
4. Solver-proven values match independent exact-authority vector recomputation.
5. Independent validation checks runtime, terminal-specific turnaround, fleet, continuous stock,
   trip traceability, and exact regime uniformity.
6. Heuristic and OR-Tools comparison uses the same exact demand weights and regime authority.
7. Alpha is the first real-route-derived differential characterization under these rules.
8. Operational approval still requires expert review.

Passing tests and matching small exhaustive instances establish implementation evidence; they do
not by themselves establish operational timetable quality.

## Proof and interpretation qualifications

- `UNKNOWN` is neither infeasibility nor feasibility.
- A `FEASIBLE` future result must not be called optimal.
- A candidate with non-uniform internal headways cannot receive a comparison vector or
  recommendation.
- Transition headways may legitimately differ from both neighboring `H_R` values.
- Endpoint, fleet, and turnaround binding evidence can be reported only from an emitted
  independently validated solution.
- The earlier average-day/unscaled characterization remains discarded.
- UI, charts, and XLSX export do not consume these unified results.

## Questions requiring expert approval

1. Are fleet assumptions 5/8 and 4/7 acceptable corpus assumptions?
2. Is LOW confidence appropriate for `departure_hour_proxy_v1`?
3. Are the first/final half-open boundary method and Beta gap correctly represented?
4. Is a longer or differently bounded Alpha solve warranted after this deterministic 30-second
   `UNKNOWN` characterization?
5. Which future accepted outcomes, if any, should become reviewed corpus baselines?
6. Should the historical optimized workbook sheet remain diagnostic-only?

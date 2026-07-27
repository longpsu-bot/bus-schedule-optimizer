# Route Corpus Reviewed Baseline V1

**REVIEWED DIAGNOSTIC BASELINE**

**NOT AN APPROVED OPERATIONAL TIMETABLE**

## 1. Status and purpose

Milestone 4C2C approves route corpus v1 as a diagnostic regression baseline. The baseline protects
source-fact preservation, anonymization, normalization, demand-proxy construction, coverage and
gap handling, exact rational demand conversion, canonical request eligibility, honest
solver-status interpretation, and the prohibition on fabricated operational facts.

This approval does not establish a ridership forecast, optimal schedule, recommended-solver
baseline, solver-performance benchmark, terminal-capacity result, or operational timetable.

## 2. Approved evidence boundary

The corpus fixtures and `manifest.json` remain authoritative for fixture facts and deterministic
source SHA-256 references. `reviewed_baseline.json` records review policy and regression scope; it
does not duplicate trips or demand rows. Private source workbooks remain external and uncommitted.

The detailed timings, regime tables, and historical solver evidence remain in
[Route Corpus Characterization Draft V1](ROUTE_CORPUS_CHARACTERIZATION_DRAFT_V1.md).

## 3. Approved corpus assumptions

Fleet values are explicit `corpus_scenario_assumption` values only:

- Alpha: Scenario A `5`; Scenario B `8`.
- Beta: Scenario A `4`; Scenario B `7`.

They are not observed facts, actual fleets, minimum required fleets, approved operational fleet
requirements, or terminal occupancy limits.

`departure_hour_proxy_v1` remains `LOW` confidence and `PROXY_SENSITIVITY_ONLY`. Exact totals,
15 observation days, conservation by direction, and Alpha's complete temporal coverage do not
make departure-hour allocation directly observed. Raw trip observations remain ineligible for
Contract V1 demand intervals.

The approved boundary convention is half-open. Ordinary hours use `[H:00, H+1:00)`. A first block
starts at the later of the observed hour start and Scenario B's first departure. A final block ends
one minute after Scenario B's locked final departure. An unobserved interior hour remains a gap;
no neighboring block is stretched and no zero-demand row is fabricated.

## 4. Frozen regression invariants

Frozen categories are fixture identity and source SHA-256; anonymization; exact timetable row and
directional trip counts; runtime facts; raw-observation counts and overlap preservation; 15-day
`total_observation_period` classification; proxy directional-volume conservation; `LOW`
confidence; exact rational demand conversion; boundary policy; coverage and gap handling;
canonical request eligibility; historical-sheet exclusion; honest solver-status interpretation;
the absence of supplied terminal occupancy limits; and
`TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED`.

## 5. Explicitly non-frozen solver observations

Solver duration, native status, candidate existence, candidate and outcome fingerprints, accepted
solution, objective vector, recommendation, exact `H_R` values, active or binding fleet and
turnaround constraints, terminal occupancy feasibility, and operational timetable quality are
not regression expectations. A future solver improvement may legitimately change them.

## 6. Alpha disposition

Alpha proxy coverage is `COMPLETE`. Both canonical heuristic and OR-Tools quality requests are
constructible under the approved `LOW`-confidence sensitivity policy, with exact demand authority
preserved. Any future candidate must pass independent validation before it can become an accepted
solution. The historical 30-second solver characterization is diagnostic evidence only and no
longer solve is required for this review.

## 7. Beta disposition

Beta retains outbound `17:00`-`18:00` as
`PROXY_INTERIOR_HOUR_UNOBSERVED` and `PROXY_COVERAGE_INCOMPLETE`. No canonical heuristic or
OR-Tools quality request may be constructed; no solver, vector, or recommendation follows.
Interpolation, smoothing, duplication, block stretching, and fabricated zero demand remain
prohibited.

## 8. Terminal occupancy limitation

Neither fixture supplies a terminal occupancy limit. Available fleet, approved fleet, timetable
occupancy, terminal names, and current vehicle positioning cannot be used to infer one. Both
fixtures retain `TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED`; this review makes no
terminal-capacity-feasibility approval.

## 9. Historical optimized-sheet policy

`DANH_GIA_TOI_UU`, `PHAN_BO_THEO_GIO`, and `BIEU_DO_TOI_UU` are diagnostic-only historical
references. They remain excluded from authoritative corpus construction and cannot supply
Scenario C, demand intervals, accepted objective vectors, recommended schedules, or solver
validation evidence.

## 10. Gate to Milestone 5

Milestone 4C2C closes the corpus review gate for its diagnostic scope. The next task is Milestone
5A: build a side-by-side legacy-versus-unified result adapter and validate charts and XLSX against
authoritative unified facts. Streamlit, charts, and XLSX may cut over only after discrepancies are
reviewed; no presentation cutover is claimed here.

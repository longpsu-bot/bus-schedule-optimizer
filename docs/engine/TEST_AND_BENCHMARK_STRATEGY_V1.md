# Test and Benchmark Strategy V1

The acceptance rules come from [Engine Contract V1](ENGINE_CONTRACT_V1.md). This strategy is for later implementation; no OR-Tools tests are introduced by the documentation task.

## Test layers

1. Schema examples and invalid-contract fixtures.
2. Pure domain unit tests for normalization, demand blocks, LF, headways, and locks.
3. Validator property/invariant tests.
4. Solver-adapter tests with tiny provable instances.
5. Cross-adapter integration tests from workbook/UI normalization to solution.
6. Visualization/XLSX reconciliation and golden-structure tests.
7. Regression corpus and performance benchmarks.

## Required fixture families

### Input and normalization

Missing A/B fields, blocking missing capacity, required positive available fleet limit, optional/nullable approved fleet metadata, invalid times/directions, duplicate IDs, multi-day totals, average-day data, combined vs directional demand, source-resolution detection, irregular/timestamp/trip-level data, and unsupported finer-than-source splitting.

### B evaluation

Declared total mismatch, directional mismatch, first/last mismatch, turnaround/location violation, insufficient fleet, demand-unsuitable but technically feasible B, technically invalid B whose parameter set is feasible, and parameter-level infeasibility.

### C invariants

Property tests assert all locked parameters equal B; total trips equal B; default directional totals equal B; default `available_upper_bound`; default solver-determined initial positioning; fixed/bounded configuration validity; first/last locks; one-to-one trace; exact timetable/block-plan reconciliation; and independent validation rejection of a deliberately corrupted solver candidate.

### Fleet and terminal stock

Test `minimum_required_fleet` below, equal to, and above the available limit; correct fleet margin; initial terminal counts summing to the calculated minimum; fixed mode requiring both values; bounded mode honoring both terminal ranges; ready-before-departure ordering at equal timestamps; negative-stock rejection; and continuity across demand-block boundaries. Verify unused available/approved vehicles need not perform trips and fleet minimization is only a late tie-breaker.

### Load factor

Boundary cases at 0, below 85%, exactly 85%, between ceilings, exactly 90%, above 90%, and demand/no trips. A metamorphic test adds surplus trips in a low-LF period and verifies that no symmetric-to-85 penalty makes the result worse. Static/code-policy tests reject `abs(load_factor - 0.85)` or equivalent objective construction in authoritative planning.

### Demand blocks

Native 15/30/60, daily-only, adaptive sustained changes, insignificant fluctuation merging, no unsupported split, variable duration/rate calculations, critical/no-service preservation, direction divergence, manual boundary validation, and proof that a block boundary does not create a headway regime boundary.

### Diagrams

Combined one-polygon case; directional envelope/components without double count; outbound/inbound/total trip lines; B/C six-line compare; non-vehicle terminology; proportional interval widths; default normalized rates; reference lines; hover completeness; A/B/C small-multiple reconciliation; and exact-departure trace count.

### XLSX

Required sheet names/order, Vietnamese headings, frozen/filterable headers, time/percentage formats, source not overwritten, fingerprints consistent, no missing/duplicate C trace, and values equal authoritative domain rows.

## Tiny solver proofs

Maintain hand-solvable cases with 4–12 trips for: one feasible chain; unavoidable second vehicle; solver-determined initial split; fixed/bounded split; terminal imbalance; exact first/last locks; no-service priority; overload tradeoff; regularity tie; and infeasible available fleet limit. Compare CP-SAT status/objective to exhaustive enumeration where practical.

## Regression and differential validation

For every approved route fixture, compare current heuristic C, CP-SAT C, and expert-reviewed timetable on feasibility, lock invariants, overload vector, gaps, regularity, shift metrics, fleet, and explanation. The heuristic may be better on a lower-priority metric but must never pass when a hard rule fails.

## Performance matrix

Use 40–80, 150, 300, and 400–500 trip tiers. Each tier includes balanced and asymmetric directions, uniform and peaky demand, tight/loose fleet, and feasible/infeasible variants. Report the metrics and targets in the OR-Tools design document.

Run at least five warm repetitions plus one cold start on a pinned machine. Store median, p95, maximum memory, solver version, Python version, CPU, worker count, seed, and commit. Retain instance/problem fingerprints.

## Determinism and flake policy

Run identical cases repeatedly. Optimal cases require identical objective and canonical solution fingerprints. Time-limited cases require identical validity and higher-priority objectives in deterministic mode; production parallel mode records allowed variance. No test may pass by increasing timeouts without a benchmark review.

## Stage gates

- Domain cutover: normalization and evaluator contract suite green.
- Solver feasibility: all hard-invariant/proof cases green.
- Allocation: no-service/overload priority suite green.
- Regularity: headway and traceability suite green.
- Export/UI: reconciliation and fingerprint suite green.
- Final cutover: regression corpus approved and all performance tiers meet agreed gates or carry signed exceptions.

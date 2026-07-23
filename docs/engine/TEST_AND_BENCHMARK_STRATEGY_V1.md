# Test and Benchmark Strategy V1

The acceptance rules come from [Engine Contract V1](ENGINE_CONTRACT_V1.md) and [Amendment V1-A1](EXTREME_SERVICE_CHANGE_AND_DEMAND_SCENARIO_AMENDMENT_V1.md). This strategy is for later implementation; no OR-Tools tests are introduced by the documentation task.

## Test layers

1. Schema examples and invalid-contract fixtures.
2. Pure domain unit tests for normalization, demand blocks, LF, headways, locks, service-change metrics, support classification, and scenario assumptions.
3. Validator property/invariant tests.
4. Solver-adapter tests with tiny provable instances.
5. Cross-adapter integration tests from workbook/UI normalization to solution or unresolved-demand outcome.
6. Visualization/XLSX reconciliation and golden-structure tests.
7. Regression corpus and performance benchmarks.

## Required fixture families

### Input and normalization

Missing A/B fields, blocking missing capacity, required positive available fleet limit, optional/nullable approved fleet metadata, invalid times/directions, duplicate IDs, multi-day totals, average-day data, combined vs directional demand, source-resolution detection, irregular/timestamp/trip-level data, and unsupported finer-than-source splitting.

Trip-count fixtures MUST prove that total trips are across both directions and that actual directional counts remain authoritative. Include symmetric examples such as 80 total = 40/40 and 40 total = 20/20, plus asymmetric examples such as 41/39 that MUST NOT be replaced by an even split. Headway assertions use exact departures separately by direction.

### B evaluation

Declared total mismatch, directional mismatch, first/last mismatch, turnaround/location violation, insufficient fleet, demand-unsuitable but technically feasible B, technically invalid B whose parameter set is feasible, parameter-level infeasibility, and technically feasible structural changes whose demand response is unresolved.

### Structural service change and scenario analysis

Required fixtures include:

- routine changes below a review signal with source-supported demand;
- material but supportable changes with high-resolution demand;
- 10-to-40 and 20-to-80 total-trip structural changes under symmetric and asymmetric directions;
- a small whole-day change concentrated into one interval and therefore structural locally;
- coarse 60/120/150-minute demand intervals containing several B departures;
- major directional headway compression from a low-frequency baseline;
- operating-span extension and contraction;
- combined demand that remains combined under all scenarios;
- no demand dataset, which permits technical results and passenger thresholds only;
- calibrated-model available versus scenario-analysis-required paths.

Assertions require:

- no fabricated passenger value per proposed departure;
- deterministic total/directional/local change metrics;
- classification from multiple signals rather than one fixed percentage;
- correct `demand_temporal_support`, `frequency_change_support`, and `demand_response_support`;
- unresolved structural cases cannot return binary demand suitability;
- target disposition `B_TECHNICALLY_FEASIBLE_DEMAND_RESPONSE_UNRESOLVED`;
- target generation result `C_NOT_GENERATED_DEMAND_RESPONSE_UNRESOLVED` with `NOT_RUN`, null solver fields, zero duration, and null solution;
- technical/fleet results remain invariant across demand scenarios when the timetable is unchanged;
- scenario assumptions, units, provenance, confidence, and selection fingerprints are complete;
- post-implementation monitoring requirements are present.

### C invariants

Property tests assert all locked parameters equal B; total trips equal B; default directional totals equal B; default `available_upper_bound`; default solver-determined initial positioning; fixed/bounded configuration validity; first/last locks; one-to-one trace; exact timetable/block-plan reconciliation; and independent validation rejection of a deliberately corrupted solver candidate.

A structural-change case without an approved scenario or calibrated model MUST NOT produce an authoritative demand-optimized C. Hard-feasibility candidates, if tested, remain explicitly technical/non-authoritative.

### Fleet and terminal stock

Test `minimum_required_fleet` below, equal to, and above the available limit; correct fleet margin; initial terminal counts summing to the calculated minimum; fixed mode requiring both values; bounded mode honoring both terminal ranges; ready-before-departure ordering at equal timestamps; negative-stock rejection; and continuity across demand-block boundaries. Verify unused available/approved vehicles need not perform trips and fleet minimization is only a late tie-breaker.

### Load factor

Boundary cases at 0, below 85%, exactly 85%, between ceilings, exactly 90%, above 90%, and demand/no trips. A metamorphic test adds surplus trips in a low-LF period and verifies that no symmetric-to-85 penalty makes the result worse. Static/code-policy tests reject `abs(load_factor - 0.85)` or equivalent objective construction in authoritative planning.

For scenario analysis, calculate LF only at authoritative source-demand grain. A metamorphic test increases the number of B departures inside a coarse source interval and proves the engine changes aggregate interval supply without inventing a finer demand series.

### Demand blocks

Native 15/30/60, daily-only, adaptive sustained changes, insignificant fluctuation merging, no unsupported split, variable duration/rate calculations, critical/no-service preservation, direction divergence, manual boundary validation, and proof that a block boundary does not create a headway regime boundary.

Add cross-grain fixtures where B has multiple departures per source interval. The demand total/rate and source IDs remain unchanged while A/B trip counts and supply rates change.

### Diagrams and UI workflow

Combined one-polygon case; directional envelope/components without double count; outbound/inbound/total trip lines; B/C six-line compare; non-vehicle terminology; proportional interval widths; default normalized rates; reference lines; hover completeness; A/B/C small-multiple reconciliation; and exact-departure trace count.

Structural-change acceptance adds total versus actual directional counts, per-direction A/B headways, trigger metrics, support classifications, scenario cards, observed-versus-assumed visual distinction, assumptions/provenance, unresolved-demand language, and post-implementation monitoring notice. The base workflow MUST NOT require re-entry of passenger rows.

### XLSX

Required sheet names/order, Vietnamese headings, frozen/filterable headers, time/percentage formats, source not overwritten, fingerprints consistent, no missing/duplicate C trace, and values equal authoritative domain rows.

The `1.1.0` target additionally validates `KICH_BAN_NHU_CAU` and `KE_HOACH_HAU_KIEM`, scenario provenance, observed-versus-assumed labels, actual directional reconciliation, unresolved-demand statuses, and absence of fabricated trip-level demand or C rows.

## Tiny solver proofs

Maintain hand-solvable cases with 4–12 trips for: one feasible chain; unavoidable second vehicle; solver-determined initial split; fixed/bounded split; terminal imbalance; exact first/last locks; no-service priority; overload tradeoff; regularity tie; and infeasible available fleet limit. Compare CP-SAT status/objective to exhaustive enumeration where practical.

Hard-feasibility proofs are independent of demand-response scenario selection. Demand-allocation proofs run only after Stage 3A contracts and fixtures are green.

## Regression and differential validation

For every approved route fixture, compare current heuristic C, CP-SAT C, and expert-reviewed timetable on feasibility, lock invariants, overload vector, gaps, regularity, shift metrics, fleet, and explanation. The heuristic may be better on a lower-priority metric but must never pass when a hard rule fails.

Structural-change fixtures compare technical results across scenario selections and demand results across configured assumptions. Reports MUST distinguish observed A evidence, sensitivity scenarios, calibrated forecasts, and post-implementation B evidence.

## Performance matrix

Use 40–80, 150, 300, and 400–500 trip tiers. Each tier includes balanced and asymmetric directions, uniform and peaky demand, tight/loose fleet, and feasible/infeasible variants. Report the metrics and targets in the OR-Tools design document.

Add extreme service-change cases whose A and B trip totals differ materially. Runtime reporting separates deterministic technical computation from scenario-count-dependent demand evaluation.

Run at least five warm repetitions plus one cold start on a pinned machine. Store median, p95, maximum memory, solver version, Python version, CPU, worker count, seed, and commit. Retain instance/problem fingerprints.

## Determinism and flake policy

Run identical cases repeatedly. Optimal cases require identical objective and canonical solution fingerprints. Time-limited cases require identical validity and higher-priority objectives in deterministic mode; production parallel mode records allowed variance. No test may pass by increasing timeouts without a benchmark review.

Scenario catalogues and selections require deterministic assumption and evaluation fingerprints. Generated timestamps and solve durations are excluded from identity hashes where the governing contract excludes them.

## Stage gates

- Domain cutover: normalization and evaluator contract suite green.
- Structural-change boundary: V1-A1 schema/domain/fixture/UI/export suite green.
- Solver feasibility: all hard-invariant/proof cases green.
- Allocation: no-service/overload priority suite green and structural-change boundary complete.
- Regularity: headway and traceability suite green.
- Export/UI: reconciliation and fingerprint suite green.
- Final cutover: regression corpus approved and all performance tiers meet agreed gates or carry signed exceptions.

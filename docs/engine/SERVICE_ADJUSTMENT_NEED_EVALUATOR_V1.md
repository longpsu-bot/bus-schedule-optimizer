# Quantitative Service Adjustment Need Evaluator V1

**Status:** Approved implementation design

**Design ID:** `V1-D1`

**Base:** `main@31f098302b9d367b03007cba3b0342b5cba1ed3b`

**Applies to:** the decision layer that determines whether a submitted bus timetable should be retained, re-spaced, redistributed, increased, reduced, or technically corrected before timetable optimization is attempted

**Does not implement:** OR-Tools, V1-A1 / Contract `1.1.0`, production runtime cutover, UI, diagrams, XLSX, qualitative service scoring, passenger-satisfaction scoring, accessibility weighting, route-network redesign, or automatic modification of the published timetable

This design introduces a quantitative decision service before Scenario C optimization. Its purpose is to answer:

> Does the current/proposed timetable need adjustment, and what category of adjustment is quantitatively justified?

The evaluator deliberately uses only measurable variables closely related to operating parameters:

- passenger demand;
- trip supply;
- vehicle capacity;
- directional and temporal allocation;
- consecutive headways;
- exact runtime and terminal turnaround;
- minimum required fleet and continuous terminal stock.

It does not create a weighted composite score.

## 1. Governing principles

### 1.1 Decision before optimization

The engine MUST separate two questions:

1. `ServiceAdjustmentNeedEvaluator` — whether adjustment is required and what type;
2. timetable generator/optimizer — how to construct an authorized adjustment.

A generator MUST NOT be invoked merely because an alternative timetable can be produced.

### 1.2 Quantitative evidence only

The first implementation MUST NOT include subjective or difficult-to-normalize criteria such as:

- passenger satisfaction;
- perceived comfort;
- service attitude;
- qualitative network importance;
- accessibility or equity weights;
- complaint counts without a separate validated contract;
- manually assigned strategic scores.

These may remain external expert-review considerations. They do not participate in the V1-D1 decision.

### 1.3 No weighted score

The evaluator MUST NOT calculate a result such as:

`0.40 × demand score + 0.25 × headway score + 0.20 × fleet score + ...`

Hard feasibility cannot be offset by another metric. Demand shortage cannot be hidden by a good headway score. The decision uses ordered gates and explicit rules.

### 1.4 Low load is review evidence, not an automatic reduction order

A low load factor MAY identify possible surplus supply. It MUST NOT independently produce `REDUCE_TOTAL_TRIPS`.

Reduction requires all approved surplus, repeatability, minimum-service, endpoint-lock, and technical-feasibility checks in this design.

### 1.5 Direction and time remain explicit

Demand and supply are evaluated by:

`operating day type × direction × authoritative analysis block`.

A whole-day average such as total passengers divided by total trips MUST NOT replace directional/block analysis.

### 1.6 Existing Contract V1 authority remains controlling

V1-D1 depends on and MUST preserve:

- H1 solver-boundary integrity;
- H2 exact per-trip runtime and arrival-terminal turnaround;
- H3 demand-coverage and directional-grain authority;
- continuous terminal-stock and available-fleet hard constraints;
- one-sided load-factor ceilings.

## 2. Decision outputs

The evaluator returns exactly one primary decision:

- `INSUFFICIENT_DATA`;
- `TECHNICAL_ADJUSTMENT_REQUIRED`;
- `INCREASE_TOTAL_TRIPS`;
- `REDISTRIBUTE_TRIPS`;
- `REDUCE_TOTAL_TRIPS`;
- `REDISTRIBUTE_DEPARTURE_TIMES`;
- `KEEP_CURRENT_TIMETABLE`.

The primary decision is accompanied by deterministic reason codes and quantitative evidence. It is a recommendation/authorization classification, not an automatic timetable mutation.

## 3. Required inputs

The evaluator consumes authoritative Contract V1 facts only.

### 3.1 Timetable and operating inputs

Required:

- exact Scenario B timetable;
- declared total daily trips;
- derived trips by direction;
- first and last departures at both terminals;
- vehicle capacity;
- exact per-trip runtimes;
- terminal-specific turnaround values;
- available fleet limit;
- approved active fleet when applicable;
- operating-day type;
- existing operating locks and modes.

Scenario A is optional and may be used as comparison evidence. It is not required to evaluate Scenario B internally.

### 3.2 Demand inputs

Demand calculations require authoritative H3 intraday evidence.

For directional block decisions and current Scenario C generation, full directional support is required:

- outbound stream present;
- inbound stream present;
- required directional spans covered;
- exact departures covered;
- no unexplained gaps;
- no mixed-grain ambiguity;
- confidence at or above the configured minimum.

Combined-only demand may support an aggregate total-supply review, but it MUST NOT authorize directional redistribution or directional Scenario C optimization.

### 3.3 Repeatability inputs for reduction

`REDUCE_TOTAL_TRIPS` requires repeatability evidence across valid observed service days or approved representative day types.

The implementation MUST expose:

- valid observed day count;
- configured minimum valid day count;
- surplus-consistency rate;
- configured minimum surplus-consistency rate.

When only a single average-day aggregate exists and repeatability cannot be calculated, low load remains `LOW_LOAD_REVIEW_ONLY`; the evaluator MUST NOT return `REDUCE_TOTAL_TRIPS` solely from that aggregate.

## 4. Data gate

The evaluator first determines whether the available data can support the requested level of decision.

### 4.1 Full directional support

Full directional support permits every V1-D1 decision, subject to later gates.

### 4.2 Combined-only support

Combined-only evidence may support:

- aggregate daily supply shortage/surplus evidence;
- aggregate `INCREASE_TOTAL_TRIPS` or reduction review evidence;
- timetable-only technical and headway findings.

It does not support:

- authoritative transfer of trips between directions;
- demand-guided directional departure placement;
- authoritative directional Scenario C generation.

Any aggregate conclusion MUST carry:

`DIRECTIONAL_ACTION_NOT_SUPPORTED_BY_COMBINED_DEMAND`.

### 4.3 Incomplete demand support

When H3 coverage is incomplete, the evaluator may retain known local adverse findings but MUST NOT return a whole-window demand-suitable conclusion.

When the missing evidence prevents the primary decision from being determined, return:

`INSUFFICIENT_DATA`.

Required data reason codes include, as applicable:

- `DEMAND_TEMPORAL_COVERAGE_GAP`;
- `DEMAND_SERVICE_WINDOW_NOT_COVERED`;
- `DEMAND_DEPARTURE_NOT_COVERED`;
- `DEMAND_DIRECTION_STREAM_MISSING`;
- `MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT`;
- `COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE`;
- `INSUFFICIENT_DAYS_FOR_REDUCTION_DECISION`.

## 5. Supply-demand metrics

All formulas use authoritative average-day demand at the supported source grain.

For each authoritative block `b` and direction `d`:

### 5.1 Current trip count

`current_trips[b,d]`

is the number of exact B departures whose departure time belongs to the half-open block:

`block_start <= departure_time < block_end`.

### 5.2 Nominal capacity

`nominal_capacity[b,d] = current_trips[b,d] × vehicle_capacity`

Where trip-specific capacity exists under an approved contract, nominal capacity is the sum of authoritative trip capacities. The first implementation may use the Scenario B vehicle capacity when no trip-specific capacity exists.

### 5.3 Load factor

`load_factor[b,d] = passenger_demand[b,d] / nominal_capacity[b,d]`

When demand is positive and `current_trips = 0`, load factor is undefined and the block status is `NO_SERVICE_WITH_DEMAND`.

### 5.4 Required trips

At the planning ceiling:

`required_trips_85[b,d] = ceil(passenger_demand[b,d] / (vehicle_capacity × planning_load_factor_ceiling))`

At the critical ceiling:

`required_trips_90[b,d] = ceil(passenger_demand[b,d] / (vehicle_capacity × critical_load_factor_ceiling))`

The existing defaults remain:

- planning ceiling: `0.85`;
- critical ceiling: `0.90`.

These values are configuration/contract values and MUST NOT be hard-coded in multiple services.

### 5.5 Shortage and surplus trips

`shortage_trips[b,d] = max(0, required_trips_85[b,d] - current_trips[b,d])`

`surplus_trips[b,d] = max(0, current_trips[b,d] - required_trips_85[b,d])`

Surplus is potential donor evidence only. A block is not an authorized donor merely because `surplus_trips > 0`.

### 5.6 Daily totals

For non-overlapping authoritative blocks that fully cover both directional comparison spans:

`required_daily_trips = sum(required_trips_85[b,d])`

`current_daily_trips = ScenarioB.total_daily_trips`

`daily_trip_gap = required_daily_trips - current_daily_trips`

Interpretation:

- `daily_trip_gap > 0`: total supply is quantitatively insufficient;
- `daily_trip_gap = 0`: total supply may be adequate, but allocation may still be wrong;
- `daily_trip_gap < 0`: potential whole-day surplus, subject to reduction gates.

The daily sum MUST NOT double-count overlapping combined and directional demand evidence.

## 6. Block allocation metrics

### 6.1 Demand share

For a supported direction:

`demand_share[b,d] = passenger_demand[b,d] / total_directional_demand[d]`

### 6.2 Trip share

`trip_share[b,d] = current_trips[b,d] / total_directional_trips[d]`

### 6.3 Allocation mismatch index

For each supported direction:

`allocation_mismatch[d] = 0.5 × sum(abs(demand_share[b,d] - trip_share[b,d]))`

The value lies between `0` and `1`:

- `0`: trip share exactly matches demand share at the evaluated grain;
- larger values: greater temporal misallocation.

This metric is explanatory evidence. It MUST NOT independently determine the decision. The authoritative redistribution trigger is the coexistence of shortage blocks and feasible donor/surplus blocks under the same locked daily resources.

### 6.4 Donor eligibility

A surplus block is eligible to donate one or more trips only when all of the following remain true after the proposed removal:

- resulting trips remain at or above `required_trips_85`;
- no `NO_SERVICE_WITH_DEMAND` condition is created;
- no block becomes `CRITICAL_ABOVE_90`;
- minimum-service rules remain satisfied;
- locked first and last departures remain satisfied;
- directional trip-lock mode remains satisfied;
- technical fleet/runtime/turnaround feasibility is preserved.

Donor eligibility is a hard validation result, not a score.

## 7. Headway regularity metrics

Headway is evaluated separately by direction within continuous headway regimes. Demand-analysis block boundaries MUST NOT automatically create or reset a headway regime.

### 7.1 Actual headway sequence

Trips are ordered by:

`(departure_time, trip_id)`.

For consecutive trips:

`headway[i] = (departure[i+1] - departure[i]) / 60`.

Zero-minute gaps remain representable under H1 Erratum 1 and are classified exceptional.

### 7.2 Balanced target sequence

For a regime with first departure `s`, last departure `e`, and `n` trips:

- interval count: `n - 1`;
- total available minutes: `(e - s) / 60`;
- expected gaps are the deterministic balanced floor/ceiling allocation of that total across the intervals.

Examples:

- `22,22,22,22`;
- `22,23,22,23`.

The evaluator MUST NOT force gaps to a standard multiple such as 30 or 60 minutes.

### 7.3 Headway range

`headway_range = max(headway) - min(headway)`

Interpretation under the current minute-granularity rule:

- `0`: exactly regular;
- `1`: balanced rounding;
- greater than `1`: irregularity requiring review.

### 7.4 Regular headway rate

`regular_headway_rate = conforming_gap_count / total_gap_count`

A gap conforms when it equals one of the validator-derived balanced floor/ceiling values for the regime.

A regime containing a zero gap has regular headway rate evidence but remains `EXCEPTIONAL` under H1.

### 7.5 Headway decision role

Headway metrics may produce `REDISTRIBUTE_DEPARTURE_TIMES` only when:

- block trip counts are demand-adequate;
- total trips are demand-adequate;
- no higher-priority technical correction is required;
- at least one regime has `headway_range > 1` or `regular_headway_rate < 1`;
- re-spacing can preserve all operating locks and technical constraints.

## 8. Technical feasibility metrics

Technical feasibility is a hard gate and takes precedence over demand allocation decisions.

### 8.1 Fleet ratio

`fleet_ratio = minimum_required_fleet / available_fleet_limit`

Interpretation:

- `fleet_ratio <= 1`: feasible under the available upper bound;
- `fleet_ratio > 1`: infeasible.

The evaluator also returns fleet margin:

`fleet_margin = available_fleet_limit - minimum_required_fleet`.

### 8.2 Turnaround margin

For each actual or assigned vehicle connection:

`turnaround_margin = next_departure - previous_arrival - required_turnaround_at_arrival_terminal`.

Interpretation:

- negative: violation;
- zero: exactly feasible;
- positive: available technical margin.

The evaluator returns:

- minimum turnaround margin;
- turnaround violation count;
- affected trip/vehicle references.

### 8.3 Terminal stock

For every event time at each terminal:

`terminal_stock >= 0`.

The evaluator returns:

- minimum stock at terminal 1;
- minimum stock at terminal 2;
- first negative-stock event when any;
- independently calculated initial terminal fleet;
- minimum required fleet.

### 8.4 Technical failure decision

Any of the following produces `TECHNICAL_ADJUSTMENT_REQUIRED` unless fixed-parameter infeasibility has already been independently proven under another approved outcome contract:

- negative terminal stock;
- minimum required fleet above the available limit;
- runtime inconsistency;
- turnaround violation;
- vehicle location conflict;
- first/last departure lock failure;
- invalid service window;
- trip-count or directional-count inconsistency.

Quantitative demand evidence remains attached but does not override the technical decision.

## 9. Surplus repeatability metrics

Reduction must be supported by repeated quantitative evidence.

For each valid observed day `k`:

`required_daily_trips[k] = sum(required_trips_85[b,d,k])`.

A day is a surplus day when:

`required_daily_trips[k] < current_daily_trips`

and no authoritative block has shortage or no-service demand.

`surplus_consistency_rate = surplus_day_count / valid_observed_day_count`.

`REDUCE_TOTAL_TRIPS` requires:

- valid observed day count at or above the configured minimum;
- surplus-consistency rate at or above the configured minimum;
- no shortage block after optimal redistribution;
- no critical or no-service block;
- residual whole-day surplus of at least one trip;
- endpoint, minimum-service and directional locks preserved;
- technical feasibility after reduction.

The initial thresholds MUST be explicit configuration. They are not universal policy constants and MUST participate in decision fingerprint identity.

## 10. Decision precedence

The evaluator applies the following order.

### Gate 1 — Data authority

When data cannot support the required decision:

`INSUFFICIENT_DATA`.

Known local findings remain evidence but do not create unsupported whole-window conclusions.

### Gate 2 — Technical feasibility

When any hard technical rule fails:

`TECHNICAL_ADJUSTMENT_REQUIRED`.

### Gate 3 — Total supply shortage

When:

`required_daily_trips > current_daily_trips`

return:

`INCREASE_TOTAL_TRIPS`.

This recommendation identifies a total-resource shortage. The current fixed-resource heuristic is not authorized to implement it.

### Gate 4 — Temporal/directional misallocation

When at least one authoritative block has shortage and sufficient eligible donor supply exists elsewhere under the same locked total trips:

`REDISTRIBUTE_TRIPS`.

This decision includes local re-spacing of affected neighboring departures.

### Gate 5 — Stable residual surplus

When:

- no authoritative block remains short;
- `required_daily_trips < current_daily_trips`;
- repeatability and reduction gates pass;

return:

`REDUCE_TOTAL_TRIPS`.

When repeatability is not established, retain `LOW_LOAD_REVIEW_ONLY` evidence and continue to later gates; do not return reduction.

### Gate 6 — Departure-time irregularity

When trip counts are adequate but headway regularity fails:

`REDISTRIBUTE_DEPARTURE_TIMES`.

### Gate 7 — No justified change

When supply, allocation, regularity, and technical feasibility all conform:

`KEEP_CURRENT_TIMETABLE`.

## 11. Decision pseudocode

```text
IF data authority is insufficient for the applicable decision
    RETURN INSUFFICIENT_DATA

IF any hard technical rule fails
    RETURN TECHNICAL_ADJUSTMENT_REQUIRED

IF required_daily_trips > current_daily_trips
    RETURN INCREASE_TOTAL_TRIPS

IF shortage blocks exist AND eligible donor trips exist
    RETURN REDISTRIBUTE_TRIPS

IF no shortage blocks
   AND required_daily_trips < current_daily_trips
   AND surplus repeatability passes
   AND reduced timetable can preserve all locks
    RETURN REDUCE_TOTAL_TRIPS

IF block counts are adequate
   AND any headway regime is not regular/balanced
   AND re-spacing is technically feasible
    RETURN REDISTRIBUTE_DEPARTURE_TIMES

RETURN KEEP_CURRENT_TIMETABLE
```

## 12. Solver-capability routing

The decision evaluator does not imply every decision can be implemented by the current solver.

### 12.1 Current fixed-resource heuristic capability

The current heuristic may be invoked only for:

- `REDISTRIBUTE_TRIPS` when total and directional trip locks remain unchanged and H3 directional demand support is complete;
- `REDISTRIBUTE_DEPARTURE_TIMES` under the same locked resources.

### 12.2 Decisions not implemented by the current heuristic

The current heuristic MUST NOT be used to implement:

- `INCREASE_TOTAL_TRIPS`;
- `REDUCE_TOTAL_TRIPS`;
- changes in trips by direction;
- technical parameter changes;
- combined-demand directional allocation.

These decisions are authoritative recommendations for a future authorized solver/workflow or expert action.

### 12.3 No-generation decisions

No Scenario C is generated for:

- `INSUFFICIENT_DATA`;
- `KEEP_CURRENT_TIMETABLE`;
- `TECHNICAL_ADJUSTMENT_REQUIRED` unless a separately approved technical-correction capability exists.

## 13. Output evidence

The evaluator result MUST include at least:

### 13.1 Identity

- decision ID;
- evaluation fingerprint;
- Scenario B fingerprint;
- observed-demand fingerprint when present;
- policy/configuration fingerprint;
- generated decision fingerprint.

### 13.2 Primary result

- primary decision;
- deterministic reason codes;
- explanation;
- limitations;
- whether current solver capability can implement the decision.

### 13.3 Daily evidence

- current daily trips;
- required daily trips at 85%;
- required daily trips at 90%;
- daily trip gap;
- total shortage trips;
- total potential surplus trips;
- valid observed day count;
- surplus-consistency rate when calculable.

### 13.4 Block evidence

For each authoritative direction/block:

- passenger demand;
- current trips;
- required trips at 85%;
- required trips at 90%;
- load factor;
- shortage trips;
- surplus trips;
- donor eligibility;
- block status;
- confidence and source references.

### 13.5 Allocation evidence

- demand share;
- trip share;
- allocation mismatch by direction;
- shortage blocks;
- eligible donor blocks.

### 13.6 Headway evidence

For each regime:

- direction;
- first/last departure;
- trip count;
- actual sequence;
- balanced expected sequence;
- headway range;
- regular headway rate;
- regularity status.

### 13.7 Technical evidence

- available fleet limit;
- minimum required fleet;
- fleet ratio;
- fleet margin;
- recommended initial fleet at each terminal;
- minimum terminal stock;
- minimum turnaround margin;
- turnaround violation count;
- technical issue codes.

## 14. Stable reason codes

The first implementation uses stable codes including:

### Data authority

- `ADJUSTMENT_DECISION_DATA_INSUFFICIENT`;
- `DIRECTIONAL_ACTION_NOT_SUPPORTED_BY_COMBINED_DEMAND`;
- `INSUFFICIENT_DAYS_FOR_REDUCTION_DECISION`.

### Demand and allocation

- `TOTAL_TRIP_SUPPLY_SHORTAGE`;
- `BLOCK_TRIP_SHORTAGE`;
- `ELIGIBLE_DONOR_SUPPLY_AVAILABLE`;
- `TEMPORAL_TRIP_ALLOCATION_MISMATCH`;
- `STABLE_RESIDUAL_TRIP_SURPLUS`;
- `LOW_LOAD_REVIEW_ONLY`.

### Headway

- `HEADWAY_RANGE_ABOVE_BALANCED_TOLERANCE`;
- `REGULAR_HEADWAY_RATE_BELOW_REQUIRED`;
- `ZERO_HEADWAY_EXCEPTION_PRESENT`.

### Technical

- existing normalized/fleet/runtime/turnaround issue codes;
- `FLEET_RATIO_ABOVE_ONE`;
- `NEGATIVE_TERMINAL_STOCK`;
- `TURNAROUND_MARGIN_NEGATIVE`.

### Routing

- `CURRENT_SOLVER_CAN_IMPLEMENT`;
- `CURRENT_SOLVER_CAPABILITY_INSUFFICIENT`.

## 15. Configuration

The decision policy MUST be a typed immutable configuration and participate in decision fingerprint identity.

It includes at least:

- planning load-factor ceiling;
- critical load-factor ceiling;
- low-load review threshold;
- minimum authoritative demand confidence;
- headway rounding tolerance minutes;
- required regular headway rate;
- minimum valid observed days for reduction;
- minimum surplus-consistency rate;
- minimum residual surplus trips for reduction;
- supported decision-to-solver routing.

No threshold may be hidden in UI code or duplicated across services.

## 16. Domain service boundary

The target workflow is:

```text
Normalized A/B/demand inputs
→ H3 demand coverage assessment
→ authoritative Scenario B evaluation
→ ServiceAdjustmentNeedEvaluator
→ quantitative decision
→ capability router
→ optional timetable generator/optimizer
→ independent solution validator
→ outcome
```

The decision service is framework-neutral. UI and export layers display its evidence but MUST NOT recalculate decisions.

## 17. Relationship to V1-H4

V1-D1 is designed independently from the ongoing V1-H4 canonical ScheduleProblem refactor.

After V1-H4 is merged:

- the adjustment decision belongs in the authoritative generation context, not hidden adapter state;
- the decision fingerprint and authorized solver capability must be bound into problem identity before solver invocation;
- a canonical problem for fixed-resource redistribution may be built only after the decision authorizes that capability;
- no problem should be built merely to discover whether a change is needed.

V1-D1 MUST NOT modify the V1-H4 branch or implementation until both designs are separately reviewed.

## 18. Implementation boundary for Codex

Expected implementation files after approval may include:

- a new `contracts_v1/adjustment_need.py` pure domain module;
- typed policy/result models;
- integration with authoritative B evaluation;
- a capability router between decision and solver orchestration;
- evaluation/result serialization only after a separately reviewed external-shape decision;
- dedicated tests.

The first implementation MUST NOT modify:

- legacy demand, fleet, or generator algorithms;
- production Streamlit/UI;
- diagrams or XLSX exporters;
- workbook formats;
- OR-Tools;
- V1-A1 / Contract `1.1.0`;
- H1/H2/H3 semantics;
- H4 canonical-problem work before H4 is merged.

## 19. Mandatory regression suite

At minimum, tests MUST prove:

1. insufficient H3 coverage returns `INSUFFICIENT_DATA` when no stronger supported decision exists;
2. a technical fleet violation returns `TECHNICAL_ADJUSTMENT_REQUIRED` even when demand appears adequate;
3. `required_daily_trips > current_daily_trips` returns `INCREASE_TOTAL_TRIPS`;
4. total trips equal required trips but shortage and eligible surplus blocks coexist returns `REDISTRIBUTE_TRIPS`;
5. allocation mismatch alone does not trigger redistribution without shortage/donor evidence;
6. low load in one block does not independently trigger reduction;
7. average-day-only surplus without repeatability does not trigger reduction;
8. repeated surplus above the configured consistency threshold can support `REDUCE_TOTAL_TRIPS`;
9. a shortage block prevents reduction;
10. a critical or no-service block prevents reduction;
11. first/last locks prevent removal of protected trips;
12. adequate block counts with irregular headways returns `REDISTRIBUTE_DEPARTURE_TIMES`;
13. balanced sequences such as `22,23,22,23` are accepted;
14. chaotic sequences such as `15,31,19,27,18` are flagged;
15. zero headway remains representable and exceptional;
16. technically feasible, demand-adequate and regular timetable returns `KEEP_CURRENT_TIMETABLE`;
17. combined-only demand never authorizes directional redistribution;
18. combined-only aggregate evidence may identify a total shortage with an explicit directional limitation;
19. current heuristic capability is true only for locked-resource redistribution/re-spacing decisions;
20. increase/reduce/technical decisions do not invoke the current heuristic;
21. changing any decision threshold changes the decision-policy fingerprint;
22. changing demand, timetable or technical evidence changes the decision fingerprint;
23. UI/export code is not required to calculate the decision;
24. full H1/H2/H3 regression suites remain green.

## 20. Acceptance gate

V1-D1 is complete only when:

- adjustment necessity is evaluated before optimization;
- only quantitative operating metrics participate;
- no weighted composite score exists;
- data, technical, total-supply, allocation, reduction and headway gates are deterministic;
- low load alone cannot reduce service;
- directional/combined demand authority remains compliant with H3;
- exact runtime, turnaround and fleet evidence remain compliant with H2;
- current solver capability is not overstated;
- every decision is traceable to quantitative evidence and fingerprints;
- all mandatory regressions pass;
- full Pytest, Ruff lint, Contract V1 format and schema suites remain green;
- no prohibited UI, export, OR-Tools or V1-A1 scope drift occurs.

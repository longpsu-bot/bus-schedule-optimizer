# Bus Schedule Engine Contract V1

**Status:** Draft for review

**Contract version:** `1.0.0`

**Normative source of truth:** this file, together with the incorporated [Schedule Generation Outcome Contract V1](RESULT_ENVELOPE_CONTRACT_V1.md)

**Scope:** business rules, normalized domain contracts, scenario evaluation, Scenario C generation, fleet feasibility, output reconciliation, and solver boundaries

## 0. Conformance and interpretation

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are normative. Contract V1 governs the future rebuilt engine even where the current MVP differs. A conflict with this contract is a migration gap, not permission to reinterpret the rule.

Contract V1 is solver-independent. It defines what a conforming engine accepts, proves, returns, explains, visualizes, and exports. It does not define a concrete OR-Tools implementation.

All timestamps belong to one declared operating day and use local service time. A future cross-midnight representation MAY use an offset beyond 24:00 internally, but adapters MUST preserve chronological service-day order and display an unambiguous date or day offset.

## 1. Governing flow and scenario semantics

The authoritative flow is:

> Current operating parameters and exact timetable A + proposed operating parameters and exact timetable B + passenger demand observed under A → normalize and validate → evaluate B technical feasibility → evaluate B demand suitability → decide whether C is required → if appropriate, redistribute B into C → validate C under B's locked parameters → return `ScheduleGenerationOutcomeV1` → produce reconciled comparisons, diagrams, and XLSX → expose status, limitations, confidence, and explanation.

### 1.1 Scenario A — Biểu đồ giờ hiện tại

A is the currently operated timetable and operational baseline. It contains current parameters, exact departures, capacity, fleet information, and operating span. Passenger-production observations are associated with A. The engine MUST NOT silently modify A.

Display name: **A — Biểu đồ giờ hiện tại**.

### 1.2 Scenario B — Biểu đồ giờ đề xuất

B is the timetable proposed by a user, operator, or transport authority. It contains proposed parameters and exact departures. B MUST be evaluated separately for input validity, parameter consistency, technical feasibility, timetable quality, fleet feasibility, and demand suitability.

Display name: **B — Biểu đồ giờ đề xuất**.

### 1.3 Scenario C — Biểu đồ giờ tái phân bổ theo nhu cầu

C is derived from B. It preserves B's locked operating parameters and changes only departure distribution. It is not an independent schedule and MUST NOT silently add or remove trips, add vehicles, shorten runtime or turnaround, change first/last departures, optimize demand blocks independently, or reduce service merely because load factor is low.

Display name: **C — Biểu đồ giờ tái phân bổ theo nhu cầu**.

C exists as an authoritative scenario only when a candidate has passed independent domain validation and the outcome status is `SOLUTION_ACCEPTED`.

## 2. Authoritative normalized inputs

Machine-readable drafts are in `contracts/v1/`. Adapters MAY accept legacy UI or workbook shapes, but the business validator MUST receive normalized contracts.

### 2.1 Common timetable concepts

Directions are `outbound`, `inbound`, or, for demand only, `combined`. A timetable departure MUST be directional. Each trip has a unique trip ID, direction, departure terminal, exact departure time, runtime or exact arrival consistent with runtime, and optional existing vehicle assignment.

Route type is `intra_provincial` or `inter_provincial`. Operating-day type is an explicit controlled value or documented operator code; it MUST NOT be inferred from dates alone.

Source metadata MUST identify at least source type, source ID or file fingerprint, extraction/import timestamp, and optional notes. Sensitive personal information MUST NOT be embedded in fingerprints or examples.

### 2.2 `ScenarioAInput`

`ScenarioAInput` MUST contain:

- `contract_version`, scenario ID, route ID and route name;
- route type and terminal names;
- trip runtime;
- minimum turnaround at each terminal;
- total daily trips and trips by direction;
- first and last departure at each terminal;
- vehicle capacity;
- required `available_fleet_limit` as the maximum assignable route fleet;
- optional `approved_active_fleet` governance metadata;
- exact departure timetable;
- optional existing vehicle assignment on each trip;
- operating-day type and source metadata.

### 2.3 `ScenarioBInput`

`ScenarioBInput` contains the same operating concepts as A but represents the proposed plan. Proposed total trips, directional totals, `available_fleet_limit`, vehicle capacity, first/last departures, runtime, turnaround, and exact timetable MUST be explicit. `approved_active_fleet` MAY record an approved, contracted, or currently scheduled fleet value, but it is optional governance metadata and is not the default technical equality constraint.

Vehicle capacity is REQUIRED and blocking. No adapter or engine component may infer it.

### 2.4 `ObservedDemandInput`

Observed demand is passenger production observed under A. Every observation record MUST expose:

- observation period start/end and observation days;
- direction;
- interval start/end or actual timestamp/trip identity when finer data exists;
- passenger count;
- source resolution, source type, and source metadata;
- classification `total_observation_period` or `average_day`;
- demand confidence.

If values are totals for multiple observation days, normalization MUST divide by the valid observation-day denominator before one-day timetable evaluation. A multi-day total MUST NOT be compared directly with one day of trips.

Demand direction values are `outbound`, `inbound`, and `combined`. Combined observations MUST NOT be fabricated into directional observations.

### 2.5 Demand-response mode

Contract V1 authoritative mode is `static`. The same normalized observations are used to compare A, B, and C. This is a comparison assumption, not a ridership forecast. Outputs MUST state that the engine does not claim demand will remain unchanged, added service will create ridership, or reduced service will preserve ridership.

The enum reserves `elasticity_scenario` and `calibrated`. They are non-authoritative placeholders until a reviewed model, calibration provenance, and uncertainty contract exist. Contract V1 defines no uncalibrated elasticity formula.

## 3. Operating parameter locks for C

`OperatingParameterLock` records the value inherited from B, lock status, source fingerprint, and any explicitly authorized exception. By default C MUST lock:

- route ID, route type, route name, and terminal names;
- trip runtime;
- minimum turnaround at terminal 1 and terminal 2;
- vehicle capacity;
- total daily trips;
- trips by direction;
- first and last departure at both terminals;
- available fleet limit;
- fleet constraint mode and any explicitly authorized exact scheduled fleet value;
- initial fleet positioning mode and any explicit fixed/bounded positioning constraints;
- operating-day type.

Mandatory invariant: `C.total_daily_trips == B.total_daily_trips`.

Default invariant: `C.trips_by_direction == B.trips_by_direction`.

`direction_trip_lock_mode` values are:

- `fixed_by_direction` — Contract V1 default; each directional total is locked.
- `total_only` — MAY be enabled only when reliable directional demand exists and the user explicitly authorizes redistribution between directions. The authorization and confidence evidence MUST be returned.

### 3.1 Fleet constraint mode

`fleet_constraint_mode` values are:

- `available_upper_bound` — Contract V1 default. The timetable is feasible only when its independently calculated `minimum_required_fleet` is less than or equal to B's `available_fleet_limit`.
- `exact_scheduled_fleet` — optional and explicitly authorized. `approved_active_fleet` records the exact fleet scheduled or reserved for the route and MUST be present. This fixes the governance/roster value, not the number of vehicles that must move; idle time and reserve vehicles remain permissible, and the solver MUST NOT distort service merely to make every scheduled vehicle perform a trip.

In `exact_scheduled_fleet` mode, `minimum_required_fleet <= approved_active_fleet <= available_fleet_limit`; the minimum is still derived from the timetable rather than forced to equal the scheduled/reserved roster.

The mandatory C fleet invariant is:

`minimum_required_fleet_C <= available_fleet_limit_B`.

The engine MUST NOT silently add vehicles and MUST NOT require every approved or available vehicle to perform a trip. Unused capacity is fleet margin or reserve:

`fleet_margin = available_fleet_limit - minimum_required_fleet`.

The contract MUST distinguish required `available_fleet_limit`, optional `approved_active_fleet`, and calculated `minimum_required_fleet`. The ambiguous standalone field `number_of_vehicles` is prohibited in normalized contracts.

### 3.2 Initial fleet positioning

`initial_fleet_positioning_mode` values are:

- `solver_determined` — Contract V1 default. The solver calculates non-negative `recommended_initial_fleet_terminal_1` and `recommended_initial_fleet_terminal_2`, whose sum equals `minimum_required_fleet`.
- `fixed` — only when the operator explicitly requires exact starting counts at both terminals. Both values are required inputs.
- `bounded` — when terminal/depot conditions impose explicit minimum and/or maximum starting counts at each terminal. The solver selects values inside both validated ranges.

Initial terminal allocation MUST NOT be treated as fixed unless `fixed` is explicitly selected. Fixed/bounded positioning constraints participate in the constrained timetable's fleet calculation but do not require every vehicle to perform a trip.

## 4. Hard technical constraints

Minimum turnaround is a hard constraint. Default minimums are 5 minutes for intra-provincial routes and 15 minutes for inter-provincial routes. A user-configured larger value MUST be respected separately at each terminal.

A vehicle may operate the next trip only at or after:

`previous departure + actual/contract runtime + minimum turnaround at arrival terminal`

and only from the terminal where that vehicle is then located.

For every operational event time `t`, the two-terminal stock balance is:

`stock_terminal_1(t) = recommended_initial_fleet_terminal_1 - departures_from_terminal_1_up_to_t + vehicles_ready_from_terminal_2_up_to_t`.

`stock_terminal_2(t) = recommended_initial_fleet_terminal_2 - departures_from_terminal_2_up_to_t + vehicles_ready_from_terminal_1_up_to_t`.

A vehicle enters the ready stock at the opposite terminal only after departure time plus runtime plus minimum turnaround at that arrival terminal. Ready events at an identical timestamp are applied before departures that may use those vehicles. Both terminal stocks MUST remain non-negative at every event. Demand-analysis block boundaries do not reset vehicle stock or chronology.

Unless a future contract explicitly adds them, a solver MUST NOT assume deadhead, empty repositioning, shortened runtime, shortened turnaround, teleportation, or simultaneous departures by one vehicle. Exact timetable chronology, operating windows, first/last locks, trip order, minimum service, fleet mode, and terminal balance are hard constraints.

Every solver-generated candidate MUST be checked by an independent domain validator after solving. An otherwise demand-improved candidate is rejected if either terminal stock becomes negative or `minimum_required_fleet` exceeds `available_fleet_limit`. Solver feasibility alone is not conformance.

## 5. Evaluation of Scenario B

The result MUST keep the following dimensions separate.

### 5.1 Input validity

Validate required fields, types and time formats, unique trip IDs, terminal values, positive runtime, positive capacity, valid directions, chronological windows, and source metadata.

### 5.2 Parameter consistency

Validate exact-timetable total against declared total, directional timetable totals against declared directional totals, first/last departures, operating-window inclusion, and arrival/runtime consistency.

### 5.3 Technical and fleet feasibility

Validate turnaround, vehicle availability and location, continuous terminal stock, trip chronology, operating span, first/last locks, minimum service, fleet constraint mode, and initial-positioning mode. Report the independently calculated minimum required fleet and fleet margin separately from the required available limit and optional approved metadata.

### 5.4 Timetable quality

Measure consecutive directional headways, abnormal gaps, headway variation, avoidable short-long-short patterns, final-service coverage, continuity, and regime regularity. Quality findings do not override hard feasibility.

### 5.5 Demand suitability

Evaluate demand and supply by authoritative analysis block and direction; load factor; intervals above 85% and 90%; demand without service; service gaps; capacity shortfall; and directional confidence.

### 5.6 B disposition

Exactly one top-level disposition MUST be returned:

- `B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE`;
- `B_TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE`;
- `B_TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION`;
- `B_PARAMETERS_INFEASIBLE`;
- `B_INSUFFICIENT_DATA`.

C generation MAY proceed for a technically feasible but demand-unsuitable B, or for a technically infeasible B whose locked parameters may admit another distribution. If the fixed B parameters are infeasible, return a generation outcome with `NO_FEASIBLE_C_WITH_B_PARAMETERS`; do not fabricate C. `B_INSUFFICIENT_DATA` MUST return `C_NOT_GENERATED_INSUFFICIENT_DATA` and MUST NOT produce a demand-optimized C. If B is already suitable, return `C_NOT_REQUIRED_B_SUITABLE` rather than duplicating B as C.

## 6. Load-factor and capacity contract

The planning ceiling is `planning_load_factor_ceiling = 0.85`. The critical ceiling is `critical_load_factor_ceiling = 0.90`.

- `LF <= 0.85`: capacity is within the planning ceiling.
- `0.85 < LF <= 0.90`: warning.
- `LF > 0.90`: critical shortage.
- Low LF: review information only.

Load factor is a one-sided capacity constraint. `abs(load_factor - 0.85)` and any equivalent symmetric objective are prohibited. The engine MUST NOT reduce trips merely to raise a low load factor toward 85%.

Authoritative one-sided penalties MAY cover overload above 85%, overload above 90%, passenger backlog/shortage, demand without service, and excessive service gaps.

Block statuses are:

- `WITHIN_PLANNING_CEILING`;
- `WARNING_ABOVE_85`;
- `CRITICAL_ABOVE_90`;
- `NO_SERVICE_WITH_DEMAND`;
- `LOW_LOAD_REVIEW_ONLY`;
- `ELIGIBLE_DONOR_PERIOD`;
- `INSUFFICIENT_DATA`.

Low load alone never implies `ELIGIBLE_DONOR_PERIOD`. Donor eligibility additionally requires minimum-service protection, adequate demand confidence, acceptable resulting headways, no hidden directional shortage, and proven technical feasibility.

## 7. Demand resolution and analysis blocks

### 7.1 `DemandResolutionContract`

It MUST expose source resolution type/minutes; timestamp-, trip-, or irregular-level flags; block mode; manual boundaries; minimum/maximum block duration; minimum sustained intervals; material-change ratio; smoothing/interpolation methods; confidence; observation days; and sample count.

Supported `block_mode` values are `native`, `adaptive`, and `manual`.

### 7.2 Native mode

Native mode preserves the actual source resolution. Daily-total-only data MUST remain daily total; the engine MUST NOT fabricate intraday demand.

### 7.3 Adaptive mode

Adaptive mode begins with native observations and MAY merge adjacent intervals into variable-duration blocks. It MUST NOT split finer than the source unless actual timestamp-level or trip-level observations support the finer resolution. Boundaries SHOULD represent sustained material changes rather than every fluctuation. Merging MUST NOT hide critical overload, demand without service, or material directional differences.

### 7.4 Manual mode

Manual boundaries MUST be chronological, non-overlapping, cover the declared analysis/operating window, and state any aggregation or interpolation. Unsupported finer-than-source claims are invalid. A manual demand boundary is not automatically a headway-regime boundary.

### 7.5 `DemandAnalysisBlock`

Every block MUST expose block ID, start/end, duration, direction, observed passengers, passenger rate per hour, source interval IDs, source resolution, block mode, aggregation method, confidence, interpolation status, observation days, sample count, and boundary reason.

`demand_rate_per_hour = observed_passengers * 60 / duration_minutes`.

Raw totals from unequal-duration blocks MUST NOT be compared without exposing normalized rates.

## 8. Two-level supply planning

### 8.1 Level 1 — `BlockSupplyPlan`

For each scenario, direction, and authoritative analysis block, expose block identity and duration; passenger demand/rate; capacity; A/B trip counts; C planned and actual trip counts; trip rate per hour; required trips/rates at 85% and 90%; nominal and ceiling capacities; load factor; shortage; status; allocation reason; and confidence.

`required_trips_85 = ceil(passenger_demand / (vehicle_capacity * 0.85))`.

`required_trips_90 = ceil(passenger_demand / (vehicle_capacity * 0.90))`.

`trip_rate_per_hour = trip_count * 60 / duration_minutes`.

Level 1 decides the desired distribution across the day before individual times are optimized.

### 8.2 Level 2 — exact timetable

After allocation, the engine creates continuous headway regimes, generates exact departures, validates fleet/turnaround/location, and reconciles actual departures with planned block allocation. An implementation MUST NOT optimize individual departures first and infer the supply plan afterward.

A Level 1 plan is not an accepted Scenario C until Level 2 and independent domain validation succeed.

## 9. Headway regimes

A demand-analysis block and a headway regime are distinct. A regime is a continuous variable-length period with stable or nearly stable consecutive directional headways. It MAY cross analysis blocks and begin/end at any operationally meaningful minute. Analysis boundaries MUST NOT automatically reset headway, create a regime, create an anchor, or force a frequency change.

Within a normal regime, headways SHOULD be equal when mathematically possible. Balanced floor/ceiling rounding is allowed, and normal headways SHOULD differ by no more than one minute. Sequences such as `10,10,10,10`, `7,8,7,8`, and `37,38,37,38` conform; avoidable chaotic sequences such as `25,45,30,50,20` do not.

A redistributed trip MUST trigger coordinated local re-spacing; it MUST NOT be moved independently while neighboring gaps remain chaotic.

`HeadwayRegime` MUST expose regime ID, direction, start/end, covered analysis block IDs, trip count, target service rate/headway, actual sequence, transition and exceptional headways, boundary reason, and regularity status.

## 10. Scenario C generation

Each accepted C trip MUST retain C trip ID, source B trip ID, direction, departure terminal, B and C departure times, shift minutes, previous B and C headways, regime ID, change reason, and vehicle assignment. The B→C mapping MUST be one-to-one in `fixed_by_direction` mode.

Hard-priority order is: preserve B parameters; preserve total and default directional trip counts; preserve fleet contract; preserve first/last departures; satisfy runtime, turnaround, vehicle location, chronology, and minimum service.

Subject to all hard constraints, lexicographic optimization priorities are:

1. prevent demand intervals with no service;
2. reduce intervals and overload above 90%;
3. reduce intervals and overload above 85%;
4. reduce service gaps;
5. align service with sustained demand;
6. preserve stable headway regimes and avoid chaotic gaps;
7. minimize regime changes;
8. preserve stable B sections;
9. minimize shifted-trip count, total shift minutes, and maximum shift.

Low load is absent from the reduction objectives. Stable B portions SHOULD remain unchanged unless a higher-priority objective requires movement. Fleet minimization MAY be used only as a later tie-breaker after feasibility, critical demand coverage, service continuity, and headway regularity have been preserved.

## 11. Evaluation, generation outcomes, and accepted solutions

### 11.1 `ScheduleEvaluationResult`

The result MUST contain scenario ID; separate input-validity, parameter-consistency, technical-feasibility, demand-suitability, fleet-feasibility, and headway-quality results; block evaluations; warnings; limitations; and confidence. Each dimension MUST expose status, issue codes, evidence/references, and explanation.

### 11.2 `ScheduleGenerationOutcomeV1`

This is the top-level result of the C-generation decision. It MUST contain contract version, `result_status`, engine-level `execution_status`, nullable native `solver_status`, nullable solver adapter, solve duration, outcome/source-B fingerprints, nullable accepted solution, nullable rejected-candidate diagnostics, explanations, and limitations.

`execution_status` values are:

- `NOT_RUN` — no solver was invoked; `solver_status` and adapter are null and duration is zero.
- `COMPLETED` — a solver invocation returned a native status.

`NOT_RUN` is not a CP-SAT status.

`result_status` values are:

- `SOLUTION_ACCEPTED`;
- `NO_FEASIBLE_C_WITH_B_PARAMETERS`;
- `C_NOT_GENERATED_INSUFFICIENT_DATA`;
- `C_NOT_REQUIRED_B_SUITABLE`;
- `CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR`.

A non-accepted outcome MUST have no authoritative C solution. It MUST NOT populate C block plans, timetable, regimes, assignments, or fleet outputs with placeholders, a copy of B, or a rejected raw candidate.

A rejected candidate MAY retain only limited non-authoritative diagnostic metadata such as candidate fingerprint, rejection codes, and summary. It MUST NOT be rendered or exported as C.

### 11.3 `ScheduleSolutionV1`

`ScheduleSolutionV1` exists only when `result_status = SOLUTION_ACCEPTED`. It MUST contain contract version, native solver status/adapter, solve duration, solution and source-B fingerprints, operating locks, C block plan, headway regimes, exact timetable, fleet assignment, block evaluation, shift metrics, explanations, and limitations.

Fleet output MUST include `available_fleet_limit`, nullable/optional `approved_active_fleet`, independently calculated `minimum_required_fleet`, both recommended initial terminal counts, `initial_fleet_positioning_mode`, `fleet_margin`, `maximum_simultaneous_vehicle_use`, event-level stock profiles for both terminals, and `fleet_feasibility_status = FLEET_FEASIBLE`.

For the Contract V1 two-terminal no-deadhead model:

`minimum_required_fleet = recommended_initial_fleet_terminal_1 + recommended_initial_fleet_terminal_2`.

This value is calculated independently for A, B, and C; it is never copied from Scenario B. Each stock-profile record identifies event time/type, trip ID when applicable, stock before/after, ready arrivals, and departures.

Native solver statuses are `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `MODEL_INVALID`, and `UNKNOWN`. User-facing output MUST NOT label `FEASIBLE` as proven optimal. Only native `OPTIMAL` or `FEASIBLE` candidates that pass independent validation may produce `ScheduleSolutionV1`. `UNKNOWN` does not prove infeasibility.

## 12. Solver-independent architecture boundary

The target dependency flow is:

> Excel/UI input → import adapter → normalized contracts → business validator → `ScheduleProblemV1` → `ScheduleSolver` interface → solver adapter → raw candidate → independent domain validator → `ScheduleGenerationOutcomeV1` with optional accepted `ScheduleSolutionV1` → evaluation/diagrams/XLSX.

The interface is conceptually:

```text
ScheduleSolver.solve(ScheduleProblemV1) -> ScheduleSolutionCandidate
```

The domain layer MUST NOT import Plotly, Streamlit, or openpyxl. Solver adapters MUST NOT create UI-specific objects. Diagram and export layers MUST NOT contain authoritative allocation, load-factor, or optimization logic.

## 13. Visualization contract

Visualization modules consume authoritative block plans, evaluations, timetable rows, generation outcomes, and fingerprints. They MUST NOT recalculate demand blocks, trip counts, load factors, required trips, or scenario totals.

### 13.1 Diagram 1 — Nhu cầu và số chuyến theo thời gian

The X-axis MUST be continuous time with actual interval widths. Use the finest reliable source resolution, never fabricated intermediate observations. Demand is a straight/step filled area or polygon following authoritative blocks; unsupported spline smoothing is prohibited.

For combined demand, show one total-demand polygon and do not fabricate directions. For directional demand, show a light total envelope plus semi-transparent outbound and inbound components without stacking the total on top of its components. Outbound plus inbound MUST reconcile with total, and direction availability/confidence MUST be visible.

When both timetable directions exist, always support outbound, inbound, and combined trip/service-rate lines. These lines are departures, not vehicle count. Provide `Scenario B`, `Scenario C`, and `Compare B and C` display modes plus legend toggling.

Use dual Y-axes. Left is passengers per interval/hour; right is trips per interval/hour. For unequal durations, default to normalized hourly rates and provide an absolute/rate toggle. Reference lines for required trips at 85% and 90% are one-sided capacity references.

Hover MUST include interval bounds/duration, source resolution, demand mode/confidence, total and available directional demand, B/C directional and total trips, requirements at 85%/90%, B/C load factors, shortage, status, and interpolation/aggregation method.

A non-accepted C outcome appears as an explicit empty/status state. The visualization MUST NOT duplicate B or render a rejected candidate as C.

### 13.2 Diagram 2 — Phân bổ chuyến theo thời gian của từng biểu đồ giờ

Use aligned small multiples for A, B, and C on the same authoritative analysis intervals. Each panel supports outbound, inbound, and total trip/service-rate lines. Default to rates when block durations differ. The diagram MUST reveal B vs A changes, C vs B redistribution, total/directional locks, and donor/recipient movements.

The exact-departure diagnostic uses continuous time, scenario/direction lanes, and one marker per departure. It is supplementary and MUST NOT replace either primary analytical diagram.

## 14. Visualization, UI, and XLSX reconciliation

For an accepted solution, the following MUST hold for the same solution fingerprint:

- sum of A block trips equals A declared trips;
- sum of B block trips equals B declared trips;
- sum of C block trips equals B declared trips;
- C directional totals equal B directional totals in `fixed_by_direction` mode;
- C planned trips per block equal C exact departures counted using the declared boundary convention;
- directional demand components reconcile with total when directional demand exists.

The UI, both diagrams, and XLSX MUST identify the same outcome fingerprint and, when accepted, the same solution fingerprint. A departure exactly on a boundary belongs to the later block, except the final inclusive operating endpoint, which MUST use one explicit non-duplicating convention documented in the solution.

For a non-accepted outcome, authoritative C outputs are absent/null and all presentation/export layers MUST show the recorded status rather than synthetic C data.

## 15. XLSX result contract

The target workbook contains: `TONG_QUAN`, `DANH_GIA_B`, `PHAN_KHUNG_NHU_CAU`, `NHU_CAU_VA_CUNG_UNG`, `PHAN_BO_CHUYEN_A`, `PHAN_BO_CHUYEN_B`, `PHAN_BO_CHUYEN_C`, `BIEU_DO_GIO_A`, `BIEU_DO_GIO_B`, `BIEU_DO_GIO_C`, `CHE_DO_GIAN_CACH_C`, `PHAN_CONG_XE_C`, `SO_SANH_B_C`, `CANH_BAO`, `NHAT_KY_SOLVER`, `CAU_HINH_DA_DUNG`, and `GIOI_HAN_DU_LIEU`.

Headings are Vietnamese; table headers are frozen and filterable; time is `HH:mm`; load factors are percentages. Source, outcome, and applicable solution fingerprints MUST be visible in summary/configuration/solver-log contexts. Exports MUST create a new workbook and MUST NOT overwrite the source workbook. Workbook cells consume authoritative outputs rather than re-running optimization.

No-run, infeasible, and rejected outcomes record status/evidence but MUST NOT create fake C rows.

## 16. Fingerprints, provenance, confidence, and limitations

A source-B fingerprint identifies normalized B parameters plus ordered exact timetable. An outcome fingerprint identifies contract version, source-B fingerprint, decision/execution status, native solver status when applicable, accepted solution fingerprint when applicable, configuration, explanations, and limitations.

A solution fingerprint identifies contract version, source fingerprint, locks, authoritative block plan, exact C timetable, fleet assignment, native solver status/adapter, and relevant configuration. Canonical serialization and hash algorithm MUST be documented; SHA-256 is RECOMMENDED.

Demand confidence and direction availability propagate from source observations to blocks, evaluations, diagrams, explanations, and XLSX. Aggregation, interpolation, and assumptions MUST be explicit. A fingerprint proves identity, not correctness.

## 17. Versioning and unresolved decisions

Breaking semantic changes require a new contract major version. Additive optional fields may use a minor version after schema review. Results MUST state the exact contract version.

The following remain deliberate review decisions rather than hidden defaults:

1. controlled vocabulary for `operating_day_type` beyond a small portable core;
2. service-day encoding for cross-midnight schedules;
3. confidence scale calibration and the threshold for reliable directional demand;
4. minimum-service policy and donor-period protection by route class;
5. whether `total_only` is enabled in the first production cutover;
6. canonical fingerprint serialization and hash algorithm approval;
7. time limits and acceptable optimality gaps by benchmark tier;
8. policy details for pre-solve versus solver-proven infeasibility evidence.

Until approved, implementations MUST expose these as limitations/configuration and MUST NOT imply a stronger conclusion.

## 18. Supporting documents

- [Domain model](DOMAIN_MODEL_V1.md)
- [Input/output contracts](INPUT_OUTPUT_CONTRACTS_V1.md)
- [Schedule generation outcome contract](RESULT_ENVELOPE_CONTRACT_V1.md)
- [Demand resolution](DEMAND_RESOLUTION_CONTRACT_V1.md)
- [Scenario evaluation](SCENARIO_EVALUATION_CONTRACT_V1.md)
- [Visualization contract](VISUALIZATION_CONTRACT_V1.md)
- [XLSX export contract](XLSX_EXPORT_CONTRACT_V1.md)
- [OR-Tools CP-SAT target design](OR_TOOLS_CP_SAT_TARGET_DESIGN_V1.md)
- [Test and benchmark strategy](TEST_AND_BENCHMARK_STRATEGY_V1.md)
- [Current-state gap analysis](CURRENT_STATE_GAP_ANALYSIS.md)
- [Migration roadmap](MIGRATION_ROADMAP_TO_OR_TOOLS.md)

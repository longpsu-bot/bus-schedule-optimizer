# Extreme Service Change and Demand Scenario Amendment V1

**Status:** Normative amendment to Bus Schedule Engine Contract V1

**Amendment ID:** `V1-A1`

**Implementation version target:** `1.1.0`

This amendment is incorporated into [Bus Schedule Engine Contract V1](ENGINE_CONTRACT_V1.md). It governs cases where the proposed service pattern changes materially beyond the temporal and behavioral support of passenger-demand observations collected under Scenario A.

Until the corresponding schemas and runtime contracts are implemented, current `1.0.0` behavior that returns a stronger demand conclusion is a migration gap. Hard technical feasibility work may continue, but demand-allocation optimization MUST NOT claim conformance with this amendment until the required fields, statuses, provenance, and UI workflow exist.

## 1. Total-trip and directional semantics

`total_daily_trips` always means the total number of passenger trips operated across both directions during the operating day.

Examples under a symmetric directional allocation:

- 80 total trips means 40 outbound and 40 inbound;
- 40 total trips means 20 outbound and 20 inbound.

These examples are explanatory, not an inference rule. The engine MUST use the actual directional timetable counts. If the timetable contains 41 outbound and 39 inbound trips, it MUST report 41/39 and MUST NOT replace them with 40/40.

Headway is calculated separately by direction from exact directional departures. For a direction with at least two trips:

`mean_directional_headway = (last_directional_departure - first_directional_departure) / (directional_trip_count - 1)`.

The engine MUST NOT divide an operating span by the total two-direction trip count and present the result as directional headway.

## 2. Identifiability boundary

Observed demand is demand recorded under Scenario A's service conditions. It may combine:

- demand that was successfully served;
- demand accumulated during long waits;
- demand constrained by low frequency or insufficient capacity;
- no direct evidence about passengers who did not choose or could not board the service.

Demand recorded at a coarse source grain MUST NOT be presented as observed demand at the finer departure grain of Scenario B. When a source interval contains several proposed B departures, the engine may evaluate aggregate supply and capacity across the source interval, but it MUST NOT fabricate a passenger count for each new departure.

A major frequency increase may also create or recover demand through shorter waiting time, improved reliability, new connections, reduced schedule risk, or improved service visibility. Static A demand therefore cannot prove B ridership, even when it can support a lower-bound capacity comparison.

## 3. Derived service-change metrics

The engine derives all change metrics from exact Scenario A and B timetables; users do not re-enter trip totals, directional counts, headways, or change percentages.

Required derived metrics are:

- `service_change_factor_total = B.total_daily_trips / A.total_daily_trips`;
- `service_change_factor_by_direction` for outbound and inbound;
- `trip_change_ratio_total` and directional ratios;
- `mean_headway_A_by_direction` and `mean_headway_B_by_direction`;
- `headway_compression_factor_by_direction = mean_headway_A / mean_headway_B` when both values exist;
- `departures_per_source_demand_interval_A` and `departures_per_source_demand_interval_B`;
- local trip-count and headway changes for each authoritative source-demand interval;
- operating-span, first-departure, and last-departure changes.

A two-direction total MUST be reconciled to directional counts before any headway or local service-rate conclusion is produced.

## 4. Service-change classification

The engine returns one of:

- `routine_adjustment`;
- `material_change`;
- `structural_change`.

Classification MUST consider more than one global percentage. It evaluates total and directional trip factors, local interval changes, headway compression, operating-span changes, and the ratio between proposed departure grain and source-demand grain.

A configured percentage such as 20% MAY be one review signal, but it MUST NOT be the sole rule. A small daily change concentrated in one interval may be structural locally; a larger evenly distributed change may remain supportable by high-resolution data.

A change is `structural_change` when the proposal materially exceeds observed service support, including one or more of:

- extreme total, directional, or interval-level trip growth;
- multiple proposed departures inside one coarse source interval without finer demand evidence;
- major headway compression from a low-frequency baseline;
- material extension or contraction of the operating window;
- a change whose likely ridership response cannot be bounded from approved local evidence.

All thresholds are configuration with visible provenance. They are not hidden constants.

## 5. Demand-support classifications

The engine exposes:

### `demand_temporal_support`

- `full` — source evidence supports the analytical grain used for the proposed service comparison;
- `partial` — some periods or directions are supported, while others require aggregation or limitations;
- `coarse` — aggregate source intervals support only interval-level conclusions, not proposed departure-level demand;
- `unsupported` — the source does not support the requested intraday conclusion.

### `frequency_change_support`

- `within_observed_range`;
- `extrapolation`;
- `structural_change`.

### `demand_response_support`

- `static_comparison_only`;
- `scenario_analysis_required`;
- `calibrated_forecast_available`.

When `service_change_classification = structural_change` and no approved calibrated response model exists:

- `scenario_analysis_required` MUST be true;
- demand suitability MUST NOT be returned as an authoritative binary pass or fail;
- the engine MUST distinguish technical feasibility from unresolved demand response.

## 6. B disposition and generation gating

The additive target disposition is:

`B_TECHNICALLY_FEASIBLE_DEMAND_RESPONSE_UNRESOLVED`.

It means B is technically feasible, but the available A demand cannot authoritatively establish demand suitability under the proposed structural service change.

This disposition is distinct from:

- `B_INSUFFICIENT_DATA`, where there is insufficient evidence even for the applicable comparison;
- `B_TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE`, where supported evidence identifies a demand problem;
- `B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE`, where supported evidence is sufficient for the affirmative conclusion.

The additive target generation result is:

`C_NOT_GENERATED_DEMAND_RESPONSE_UNRESOLVED`.

Until an approved demand scenario is selected and recorded, or a calibrated model exists, a structural-change case MUST NOT produce an authoritative demand-optimized C. The technical feasibility solver MAY still evaluate hard constraints or produce explicitly labeled technical candidates, but those candidates MUST NOT be called demand-optimal or exported as authoritative Scenario C.

Adding these enum values and fields requires reviewed `1.1.0` schema and typed-domain updates before runtime use.

## 7. Scenario analysis

For a structural-change case without a calibrated model, the engine presents sensitivity scenarios rather than one forecast. The default scenario catalogue is:

- `static_lower_bound` — observed average-day demand under A is held constant;
- `cautious_growth` — a low approved response assumption;
- `moderate_growth` — a middle approved response assumption;
- `high_growth` — a high but bounded approved response assumption;
- `custom_approved` — an explicitly entered and provenance-backed assumption.

The scenario catalogue MUST be configuration, not an embedded empirical claim. Each scenario records:

- scenario ID and display name;
- method, such as direct growth factor or elasticity-based sensitivity;
- all parameter values and units;
- approval/provenance source;
- applicable route/day/service-change scope;
- lower, central, and upper demand values when available;
- confidence and limitations;
- whether the result is sensitivity analysis or a calibrated forecast.

Scenario demand is evaluated at the authoritative source-demand grain. It MUST NOT be split among individual B departures unless finer evidence or an approved allocation model supports that split.

For each scenario, the engine reports at least:

- total passenger demand and growth relative to observed A demand;
- passengers per total trip and, where direction is supported, per directional trip;
- load factor and capacity range by authoritative interval;
- intervals above 85% and 90%;
- demand-without-service findings;
- fleet margin and technical feasibility, which remain scenario-independent unless the timetable changes;
- assumptions, confidence, and required post-implementation monitoring.

## 8. UI workflow

### 8.1 Base user input

The base user workflow requires only:

- exact Scenario A timetable and operating parameters;
- exact Scenario B timetable and operating parameters.

The engine derives totals, directional counts, first/last departures, headways, change factors, fleet requirements, and service-change classification.

Observed passenger data is an engine evidence context loaded from an existing imported or linked dataset. The user MUST NOT be required to re-enter passenger rows during the structural-change workflow. If no demand dataset exists, the engine performs technical evaluation and reports passenger thresholds needed to reach selected load-factor references; it does not forecast ridership.

### 8.2 Structural-change interception

When `scenario_analysis_required = true`, the normal binary demand-suitability workflow is interrupted. The UI shows:

1. why the case was classified as structural;
2. total and directional A/B trips;
3. per-direction headway changes;
4. source-demand resolution and the unsupported finer proposed grain;
5. deterministic technical and fleet evaluation;
6. selectable demand-sensitivity scenarios;
7. assumptions, uncertainty, and monitoring requirements.

The user selects a scenario card or an approved custom scenario. Selecting a scenario is a recorded analysis decision, not an assertion that the scenario is observed fact.

### 8.3 Result language

The default conclusion is:

> Scenario B is technically evaluated under its declared operating parameters. Because the proposed service change is structural and observed demand under Scenario A is temporally or behaviorally insufficient to identify the response, demand results are presented as sensitivity scenarios and require post-implementation validation.

The UI MUST NOT display `demand suitable`, `optimized by demand`, or equivalent affirmative language for an unresolved structural-change case.

## 9. Visualization and export

Charts and XLSX preserve source interval widths and clearly separate:

- observed A demand;
- scenario demand assumptions;
- A and B directional and total service;
- technical results that do not depend on the selected demand scenario;
- scenario-dependent load-factor and capacity results.

Scenario series MUST be visually and textually labeled as assumptions. They MUST NOT be styled or described as observations.

The target UI/XLSX exposes:

- service-change classification and triggering metrics;
- demand temporal/frequency/response support;
- selected scenario and all assumptions;
- scenario comparison table;
- unresolved-demand disposition and generation status;
- post-implementation data-collection and review plan.

## 10. Monitoring requirement

A structural-change recommendation requires a monitoring plan. At minimum, the plan SHOULD identify:

- implementation and review dates;
- boarding counts by trip, direction, and time where available;
- denied boarding or capacity constraints;
- observed headways and reliability;
- operating-day segmentation;
- criteria for retaining, increasing, reducing, or redistributing service.

Post-implementation observations are new evidence under B. They MUST NOT be retroactively presented as evidence that was available when the pre-implementation scenario was selected.

## 11. Required diagnostics

At minimum, implementations expose the following issue codes where applicable:

- `DEMAND_RESOLUTION_TOO_COARSE_FOR_PROPOSED_SERVICE`;
- `FREQUENCY_CHANGE_OUTSIDE_OBSERVED_SUPPORT`;
- `STRUCTURAL_SERVICE_CHANGE_DETECTED`;
- `LATENT_DEMAND_NOT_IDENTIFIED`;
- `INDUCED_DEMAND_SCENARIO_REQUIRED`;
- `TRIP_LEVEL_DEMAND_NOT_OBSERVED`;
- `POST_IMPLEMENTATION_VALIDATION_REQUIRED`.

## 12. Implementation sequencing

This amendment MUST be implemented before OR-Tools demand-allocation objectives are considered production-conforming.

OR-Tools hard-constraint feasibility work MAY proceed in parallel because trip counts, direction, runtime, turnaround, fleet, terminal stock, and operating windows do not depend on a ridership-response forecast.

The required implementation sequence is:

1. schema and typed-domain amendment to `1.1.0`;
2. derived service-change metrics and classification;
3. demand-support and unresolved-demand disposition logic;
4. scenario catalogue, assumptions, and provenance;
5. UI scenario-selection workflow;
6. charts/XLSX scenario reconciliation;
7. post-implementation monitoring contract;
8. only then production-conforming demand-allocation optimization for structural-change cases.

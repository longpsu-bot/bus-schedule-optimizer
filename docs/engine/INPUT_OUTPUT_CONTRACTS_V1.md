# Input and Output Contracts V1

The normative rules are [Engine Contract V1 §§2–5 and §§11–16](ENGINE_CONTRACT_V1.md), together with the normative [Schedule Generation Outcome Contract V1](RESULT_ENVELOPE_CONTRACT_V1.md) and [Amendment V1-A1](EXTREME_SERVICE_CHANGE_AND_DEMAND_SCENARIO_AMENDMENT_V1.md). JSON files in `contracts/v1/` are draft validation artifacts; the Markdown contracts remain authoritative until schemas are formally approved.

## Contract envelope

Every top-level object contains `contract_version: "1.0.0"`. IDs are non-empty strings. Local dates use ISO `YYYY-MM-DD`; service times use `HH:mm` at adapter boundaries. Durations are integer minutes and counts are non-negative integers unless stated otherwise.

`source_metadata` includes `source_type`, `source_id`, `imported_at`, and optional `notes`. Fingerprints are lowercase SHA-256 hex drafts. The final canonical serialization decision remains open under Contract V1 §17.

## Input catalogue

| Schema | Domain object | Required semantic checks beyond JSON type validation |
|---|---|---|
| `scenario_a_input.schema.json` | `ScenarioAInput` | timetable/declared totals, terminal-direction match, first/last reconciliation, approved metadata ≤ available limit when present |
| `scenario_b_input.schema.json` | `ScenarioBInput` | same checks; capacity and all proposed values blocking |
| `observed_demand_input.schema.json` | `ObservedDemandInput` | date order, non-overlap policy, average-day normalization, no fabricated directions |
| `demand_resolution.schema.json` | `DemandResolutionContract` | mode-specific grain and manual-boundary checks |
| `demand_analysis_block.schema.json` | `DemandAnalysisBlock` | rate formula, source coverage, provenance preservation |
| `block_supply_plan.schema.json` | `BlockSupplyPlan` | required-trip formulas, status, planned/actual reconciliation |
| `schedule_problem.schema.json` | `ScheduleProblemV1` | source references, lock completeness, block uniqueness |

Schema validation is necessary but not sufficient. Cross-record and temporal constraints belong to the business validator.

## Direction mapping

Normalized contract directions are `outbound`, `inbound`, and demand-only `combined`. A legacy adapter must map terminal-specific labels deterministically and retain the original value in source metadata or diagnostics. `combined` is invalid on a timetable trip.

## Operating-day type

Scenario A and B accept `weekday`, `saturday`, `sunday`, `holiday`, `special`, and `all_days`.
`all_days` is the exact assertion that one authoritative timetable applies unchanged to every
listed calendar-day classification. It conveys no calendar-date inference and no demand coverage.
Trip-ridership evidence remains labeled with one concrete day type; a concrete evidence day may
bind to an `all_days` timetable without being relabeled, combined with other days, or extrapolated.

## Fleet fields

`available_fleet_limit` is the required hard upper bound. `approved_active_fleet` is optional governance metadata. `minimum_required_fleet` is calculated independently from the timetable and continuous terminal-stock model; `fleet_margin` is the available limit minus that minimum. These fields must never be collapsed into a single vehicle count.

`fleet_constraint_mode` defaults to `available_upper_bound`; `exact_scheduled_fleet` requires explicit authorization and an approved scheduled value, but does not force every vehicle to move. `initial_fleet_positioning_mode` defaults to `solver_determined`; `fixed` requires both terminal counts, and `bounded` requires valid terminal bounds. Cross-field sums, inequalities, stock continuity, and fleet-margin arithmetic are domain-validator responsibilities where JSON Schema cannot prove them.

## Output catalogue

### `ScheduleEvaluationResult`

The schema mirrors Contract V1 §11.1. Each evaluation dimension has a controlled status, issue list, evidence strings or entity references, and explanation. The top-level B disposition is not inferred by the UI.

### `ScheduleGenerationOutcomeV1`

This is the top-level result of the Scenario C generation decision. It distinguishes:

- engine-level `execution_status`: `NOT_RUN` or `COMPLETED`;
- nullable native solver proof status;
- accepted solution, no-run, proven infeasible, and rejected-candidate outcomes.

`NOT_RUN` is not a CP-SAT status. When B is already suitable or demand is insufficient, the solver fields are null, duration is zero, and `solution` is null. A no-feasible or rejected outcome also has no authoritative Scenario C.

Native `UNKNOWN` maps only to `C_NOT_FOUND_WITHIN_SOLVE_LIMIT`; it is not proof of infeasibility. Native `MODEL_INVALID` maps only to `C_NOT_GENERATED_MODEL_INVALID`; it is not a route or timetable conclusion.

### `ScheduleSolutionV1`

This schema represents only `SOLUTION_ACCEPTED`. It contains the complete independently validated C timetable, block plan, regimes, fleet assignment, terminal stock profiles, traceability, evaluation, and solution fingerprint. A `FEASIBLE` native solver result may become a conforming solution only after independent validation; it remains labeled feasible, not optimal.

Rejected raw candidates, when retained, belong only in the limited diagnostic field of `ScheduleGenerationOutcomeV1`. They must not populate authoritative C fields or be rendered/exported as C.

## Boundary convention

Block membership uses half-open intervals `[start, end)`. A departure at a shared boundary belongs to the later block. A final locked departure may be represented by a terminal sentinel block or a documented inclusive final endpoint, but it must be counted exactly once. The chosen convention is included in `ScheduleProblemV1` and outcome/solution explanations. This analytical boundary convention never resets terminal stock; fleet validation replays one continuous ordered event stream.

## Compatibility and unknown fields

Draft schemas set `additionalProperties: false` to expose accidental drift. Adapters may accept legacy extras but must emit warnings and produce a clean normalized object. Future optional fields require a reviewed schema version; consumers must not assign business meaning to unknown data.

## Example data

Anonymized examples under `examples/contracts/v1/` intentionally use a fictional two-terminal route. They demonstrate shape only and are not approved operational fixtures, benchmarks, or forecasts.

## V1-A1 target additions

The `1.1.0` target adds solver-neutral service-change and scenario-analysis contracts. Required derived fields include total/directional service-change factors, directional A/B headways, headway-compression factors, departures per source-demand interval, service-change classification, and demand temporal/frequency/response support.

The base user input remains exact A/B timetables plus operating parameters. Totals, directional counts, first/last departures, headways, change metrics, and fleet requirements are derived. Observed passenger data is imported or linked evidence context; the structural-change UI does not require users to re-enter passenger rows.

The target output catalogue adds:

- `B_TECHNICALLY_FEASIBLE_DEMAND_RESPONSE_UNRESOLVED`;
- `C_NOT_GENERATED_DEMAND_RESPONSE_UNRESOLVED`;
- scenario catalogue/selection, assumptions, provenance, confidence, and monitoring plan;
- per-scenario interval demand, capacity, load-factor, shortage, and comparison rows.

These additions are documentation-approved migration targets only until `1.1.0` schemas, examples, typed models, validators, serialization, and compatibility tests are merged. Strict `1.0.0` consumers MUST NOT receive undeclared fields or enum values.

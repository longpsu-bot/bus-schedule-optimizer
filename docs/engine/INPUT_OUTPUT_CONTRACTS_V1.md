# Input and Output Contracts V1

The normative rules are [Engine Contract V1 §§2–5 and §§11–16](ENGINE_CONTRACT_V1.md). JSON files in `contracts/v1/` are draft validation artifacts; the Markdown contract remains authoritative until schemas are formally approved.

## Contract envelope

Every top-level object contains `contract_version: "1.0.0"`. IDs are non-empty strings. Local dates use ISO `YYYY-MM-DD`; service times use `HH:mm` at adapter boundaries. Durations are integer minutes and counts are non-negative integers unless stated otherwise.

`source_metadata` includes `source_type`, `source_id`, `imported_at`, and optional `notes`. Fingerprints are lowercase SHA-256 hex drafts. The final canonical serialization decision remains open under Contract V1 §17.

## Input catalogue

| Schema | Domain object | Required semantic checks beyond JSON type validation |
|---|---|---|
| `scenario_a_input.schema.json` | `ScenarioAInput` | timetable/declared totals, terminal-direction match, first/last reconciliation, active ≤ available |
| `scenario_b_input.schema.json` | `ScenarioBInput` | same checks; capacity and all proposed values blocking |
| `observed_demand_input.schema.json` | `ObservedDemandInput` | date order, non-overlap policy, average-day normalization, no fabricated directions |
| `demand_resolution.schema.json` | `DemandResolutionContract` | mode-specific grain and manual-boundary checks |
| `demand_analysis_block.schema.json` | `DemandAnalysisBlock` | rate formula, source coverage, provenance preservation |
| `block_supply_plan.schema.json` | `BlockSupplyPlan` | required-trip formulas, status, planned/actual reconciliation |
| `schedule_problem.schema.json` | `ScheduleProblemV1` | source references, lock completeness, block uniqueness |

Schema validation is necessary but not sufficient. Cross-record and temporal constraints belong to the business validator.

## Direction mapping

Normalized contract directions are `outbound`, `inbound`, and demand-only `combined`. A legacy adapter must map terminal-specific labels deterministically and retain the original value in source metadata or diagnostics. `combined` is invalid on a timetable trip.

## Fleet fields

`available_fleet_limit` is the required hard upper bound. `approved_active_fleet` is optional governance metadata. `minimum_required_fleet` is calculated independently from the timetable and continuous terminal-stock model; `fleet_margin` is the available limit minus that minimum. These fields must never be collapsed into a single vehicle count.

`fleet_constraint_mode` defaults to `available_upper_bound`; `exact_scheduled_fleet` requires explicit authorization and an approved scheduled value, but does not force every vehicle to move. `initial_fleet_positioning_mode` defaults to `solver_determined`; `fixed` requires both terminal counts, and `bounded` requires valid terminal bounds. Cross-field sums, inequalities, stock continuity, and fleet-margin arithmetic are domain-validator responsibilities where JSON Schema cannot prove them.

## Output catalogue

### `ScheduleEvaluationResult`

The schema mirrors Contract V1 §11.1. Each evaluation dimension has a controlled status, issue list, evidence strings or entity references, and explanation. The top-level B disposition is not inferred by the UI.

### `ScheduleSolutionV1`

The schema mirrors Contract V1 §11.2. `solver_status` describes solver proof; `status` describes domain acceptance/disposition. A `FEASIBLE` solver result can become a conforming solution only after independent validation; it remains labeled feasible, not optimal.

## Boundary convention

Block membership uses half-open intervals `[start, end)`. A departure at a shared boundary belongs to the later block. A final locked departure may be represented by a terminal sentinel block or a documented inclusive final endpoint, but it must be counted exactly once. The chosen convention is included in `ScheduleProblemV1` and solution explanations. This analytical boundary convention never resets terminal stock; fleet validation replays one continuous ordered event stream.

## Compatibility and unknown fields

Draft schemas set `additionalProperties: false` to expose accidental drift. Adapters may accept legacy extras but must emit warnings and produce a clean normalized object. Future optional fields require a reviewed schema version; consumers must not assign business meaning to unknown data.

## Example data

Anonymized examples under `examples/contracts/v1/` intentionally use a fictional two-terminal route. They demonstrate shape only and are not approved operational fixtures, benchmarks, or forecasts.

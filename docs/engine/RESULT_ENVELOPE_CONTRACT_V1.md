# Schedule Generation Outcome Contract V1

**Status:** Normative Contract V1 clarification

This document is incorporated into Bus Schedule Engine Contract V1 and clarifies the distinction between an engine generation outcome and an accepted Scenario C solution. It governs any interpretation of `ScheduleSolutionV1` for no-run, infeasible, unresolved, model-invalid, or rejected states. It also incorporates [Amendment V1-A1](EXTREME_SERVICE_CHANGE_AND_DEMAND_SCENARIO_AMENDMENT_V1.md) for structural service changes whose demand response is unresolved.

## 1. Two distinct domain objects

### `ScheduleGenerationOutcomeV1`

This is the top-level result returned by the Scenario C generation workflow. It always exists after the engine decides whether C should be generated, attempts generation, or rejects a candidate.

It contains:

- `result_status`;
- engine-level `execution_status`;
- nullable native `solver_status`;
- nullable `solver_adapter`;
- solve duration;
- outcome and source-B fingerprints;
- nullable accepted `solution`;
- nullable rejected-candidate diagnostic metadata;
- explanations and limitations.

### `ScheduleSolutionV1`

This object exists only when `result_status = SOLUTION_ACCEPTED`. It is the authoritative, independently validated Scenario C and therefore contains the complete block plan, headway regimes, exact timetable, fleet assignment, terminal stock profiles, evaluation, and traceability fields.

A non-accepted outcome MUST NOT populate authoritative Scenario C fields with placeholders, a copy of B, or a rejected candidate.

## 2. Execution status versus solver proof status

`execution_status` is an engine-level state:

- `NOT_RUN` — no solver was invoked because C was not required, demand was insufficient, structural-change demand response was unresolved, or locked parameters were proven infeasible before solver invocation;
- `COMPLETED` — a solver invocation completed and returned a native status.

`NOT_RUN` is not a CP-SAT status.

When `execution_status = NOT_RUN`:

- `solver_status` is `null`;
- `solver_adapter` is `null`;
- `solve_duration_seconds` is `0`.

When a solver was invoked, `solver_status` retains its native meaning: `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `MODEL_INVALID`, or `UNKNOWN`. `FEASIBLE` MUST NOT be relabeled optimal.

## 3. Status rules

| `result_status` | Execution | Authoritative `solution` | Required interpretation |
|---|---|---|---|
| `SOLUTION_ACCEPTED` | `COMPLETED`; solver `OPTIMAL` or `FEASIBLE` | Required | Candidate passed independent domain validation and is authoritative C. |
| `NO_FEASIBLE_C_WITH_B_PARAMETERS` | `COMPLETED/INFEASIBLE` or `NOT_RUN` after pre-solve proof | `null` | No C is fabricated. Evidence must identify the locked parameters and proof boundary. |
| `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` | `COMPLETED`; solver `UNKNOWN` | `null` | No accepted C was found within the recorded solve limit. This is not proof of infeasibility. |
| `C_NOT_GENERATED_MODEL_INVALID` | `COMPLETED`; solver `MODEL_INVALID` | `null` | The encoded solver model was invalid. This is an implementation/configuration defect, not a business conclusion. |
| `C_NOT_GENERATED_INSUFFICIENT_DATA` | `NOT_RUN` | `null` | Demand-optimized C is not produced because the applicable evidence is insufficient. |
| `C_NOT_GENERATED_DEMAND_RESPONSE_UNRESOLVED` | `NOT_RUN` | `null` | V1-A1 target: B is a structural service change and no approved demand scenario or calibrated response model is recorded. Technical evaluation may exist, but no authoritative demand-optimized C is produced. |
| `C_NOT_REQUIRED_B_SUITABLE` | `NOT_RUN` | `null` | B remains the accepted proposal; no duplicate C is created. |
| `CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR` | `COMPLETED`; solver `OPTIMAL` or `FEASIBLE` | `null` | Raw candidate is non-authoritative and may appear only as diagnostic metadata. |

`UNKNOWN` does not prove infeasibility and MUST map to `C_NOT_FOUND_WITHIN_SOLVE_LIMIT`. It MUST NOT be mislabeled `NO_FEASIBLE_C_WITH_B_PARAMETERS` unless infeasibility was independently proven.

`MODEL_INVALID` MUST map to `C_NOT_GENERATED_MODEL_INVALID`. It MUST NOT be presented as route or timetable infeasibility.

`C_NOT_GENERATED_DEMAND_RESPONSE_UNRESOLVED` is distinct from insufficient data. It records that technical evidence may be complete while the ridership response to a structural change is not identifiable from demand observed under A. Its target schema semantics are `execution_status = NOT_RUN`, null solver fields, zero duration, null solution, and explicit scenario/monitoring limitations.

Adding this status to machine-readable contracts requires the reviewed `1.1.0` schema/domain amendment. Strict `1.0.0` outputs MUST NOT emit it before that implementation is merged.

## 4. Rejected candidate diagnostics

A rejected raw candidate MAY be retained in `diagnostic_candidate` only as:

- candidate fingerprint;
- rejection codes;
- concise diagnostic summary.

It MUST NOT be exposed as Scenario C in UI, diagrams, or XLSX. Future contracts may define a richer internal diagnostic payload, but authoritative C outputs remain null until validation succeeds.

## 5. Presentation and export

For non-accepted outcomes:

- the Scenario C diagram panel shows an explicit status/empty state;
- no C trip line or exact timetable is fabricated;
- XLSX records the outcome, evidence, and limitations but does not create fake C rows;
- UI text distinguishes solver not run, proven infeasible, solve-limit exhaustion, invalid model, candidate rejection, B already suitable, insufficient evidence, and unresolved structural-change demand response.

For `C_NOT_GENERATED_DEMAND_RESPONSE_UNRESOLVED`, UI/XLSX show deterministic technical results, triggering service-change/support metrics, available sensitivity scenarios, selected assumptions when any, and the post-implementation monitoring requirement. Scenario assumptions MUST NOT appear as observed demand or authoritative Scenario C.

For an accepted outcome, all UI, diagrams, and XLSX consume the embedded `ScheduleSolutionV1` and its solution fingerprint.

## 6. Machine-readable contracts

- `contracts/v1/schedule_generation_outcome.schema.json` defines the conditional top-level envelope.
- `contracts/v1/schedule_solution.schema.json` defines only an accepted, independently validated Scenario C.

JSON Schema validates structural conditions. Cross-field arithmetic, fleet continuity, B→C traceability, scenario provenance, service-change support, and domain conformance remain responsibilities of the independent domain validator.

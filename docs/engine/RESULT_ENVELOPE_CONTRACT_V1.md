# Schedule Generation Outcome Contract V1

**Status:** Normative Contract V1 clarification

This document is incorporated into Bus Schedule Engine Contract V1 and clarifies the distinction between an engine generation outcome and an accepted Scenario C solution. It governs any interpretation of `ScheduleSolutionV1` for no-run, infeasible, or rejected states.

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

- `NOT_RUN` — no solver was invoked because C was not required, demand was insufficient, or locked parameters were proven infeasible before solver invocation;
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
| `C_NOT_GENERATED_INSUFFICIENT_DATA` | `NOT_RUN` | `null` | Demand-optimized C is not produced. |
| `C_NOT_REQUIRED_B_SUITABLE` | `NOT_RUN` | `null` | B remains the accepted proposal; no duplicate C is created. |
| `CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR` | `COMPLETED`; solver `OPTIMAL` or `FEASIBLE` | `null` | Raw candidate is non-authoritative and may appear only as diagnostic metadata. |

`UNKNOWN` does not prove infeasibility. A time-limited search returning `UNKNOWN` must use an outcome/status that accurately states no accepted solution was found within the recorded limit; it MUST NOT be mislabeled `NO_FEASIBLE_C_WITH_B_PARAMETERS` unless infeasibility was independently proven.

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
- UI text distinguishes “solver not run”, “infeasible”, “candidate rejected”, and “B already suitable”.

For an accepted outcome, all UI, diagrams, and XLSX consume the embedded `ScheduleSolutionV1` and its solution fingerprint.

## 6. Machine-readable contracts

- `contracts/v1/schedule_generation_outcome.schema.json` defines the conditional top-level envelope.
- `contracts/v1/schedule_solution.schema.json` defines only an accepted, independently validated Scenario C.

JSON Schema validates structural conditions. Cross-field arithmetic, fleet continuity, B→C traceability, and domain conformance remain responsibilities of the independent domain validator.

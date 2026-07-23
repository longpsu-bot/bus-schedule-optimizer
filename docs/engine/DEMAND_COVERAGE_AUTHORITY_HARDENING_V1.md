# Contract V1 Demand Coverage Authority Hardening

**Status:** Approved implementation design for hardening existing Contract `1.0.0` demand-coverage and mixed-direction-grain semantics

**Design ID:** `V1-H3`

**Base:** `main@7ca35bb22b5df19f54689ffbca94284c242f174e`

**Applies to:** authoritative demand-source guards, demand-resolution diagnostics, Scenario B demand suitability, Scenario C generation gating, independent candidate validation, fingerprints, and regression tests

**Does not implement:** V1-A1 / Contract `1.1.0`, demand forecasting, elasticity, interpolation, combined-demand allocation, OR-Tools, `ScheduleProblemV1` schema migration, production runtime cutover, Streamlit, diagrams, XLSX, or workbook-format changes

This design closes a remaining Contract V1 integrity gap: the current evaluator can retain only observed intervals, silently ignore uncovered time, and then produce a stronger whole-day demand conclusion than the evidence supports.

V1-H3 preserves local observed findings while preventing missing temporal or directional evidence from being interpreted as zero demand or from authorizing an authoritative demand-optimized Scenario C.

## 1. Governing principles

Demand absence and demand equal to zero are different facts.

An interval with no observation is **uncovered**. It MUST NOT be represented as:

- zero passengers;
- low load;
- spare capacity;
- a donor period;
- evidence that service is sufficient;
- evidence that no service is needed.

Observed demand remains authoritative only at its source-supported temporal and directional grain.

The engine MUST distinguish:

1. local findings supported by actual observations;
2. whether the observations support a whole-comparison-window conclusion for Scenario B;
3. whether the observations support directional demand optimization for Scenario C.

A known local adverse finding is not erased by missing evidence elsewhere. Conversely, a local pass does not fill uncovered time.

## 2. Terminology

### 2.1 Demand stream

A demand stream is the set of non-daily-total observations for exactly one `ContractDirection`:

- `outbound`;
- `inbound`;
- `combined`.

Outbound and inbound are distinct directional streams. Combined is an aggregate two-direction stream and is not a substitute for either directional stream.

### 2.2 Source coverage segment

Within one stream, observations are sorted by:

`(interval_start, interval_end, observation_id)`.

A source coverage segment is the union of consecutive intervals whose boundaries touch exactly:

`previous.interval_end == current.interval_start`.

Intervals that overlap within the same stream are invalid. Intervals separated by time produce distinct coverage segments.

### 2.3 Coverage gap

A coverage gap is a positive-duration interval for which no authoritative observation exists at the required grain.

Coverage gaps may be:

- internal gaps between source intervals;
- leading gaps between the required comparison span and first supported observation;
- trailing gaps between the last supported observation and the required comparison span;
- uncovered exact A or B departures at a half-open interval boundary;
- missing directional streams.

### 2.4 Local finding

A local finding is a block result calculated only from an actual authoritative source interval or an allowed aggregation of actual source intervals.

A coverage gap is not a demand-analysis block and has no passenger count.

## 3. Required comparison spans

Coverage for a whole Scenario B comparison is evaluated against exact Scenario A and B timetables.

### 3.1 Directional comparison span

For each direction that exists in the exact timetables:

`directional_span_start = min(first_A_directional_departure, first_B_directional_departure)`

`directional_span_end = max(last_A_directional_departure, last_B_directional_departure)`

When Scenario A is absent, use Scenario B only.

The span represents continuous comparison time between its endpoints. In addition, every exact A and B departure in that direction MUST belong to a compatible half-open demand interval.

This separate departure-membership requirement prevents a final departure at an interval end from being treated as covered accidentally.

### 3.2 Combined comparison span

For combined-only evidence:

`combined_span_start = earliest exact A/B departure across both directions`

`combined_span_end = latest exact A/B departure across both directions`

Every exact A and B departure across both directions MUST belong to a combined source interval.

### 3.3 Evidence outside the comparison span

Observed intervals outside the required A/B comparison span remain valid evidence.

They MUST be retained and evaluated. For example, observed demand before B begins service may prove `NO_SERVICE_WITH_DEMAND`.

Extra evidence outside the required span does not compensate for a gap inside it.

## 4. Coverage modes

The implementation SHOULD use an internal typed assessment such as `DemandCoverageAssessmentV1`. This is an internal domain helper and does not add a serialized Contract `1.0.0` field.

The assessment distinguishes at least these modes:

- `directional_only`;
- `combined_only`;
- `mixed_direction_grain`;
- `daily_total_only`;
- `no_intraday_evidence`.

It records deterministically:

- required comparison spans;
- source coverage segments;
- uncovered segments;
- exact A/B departure IDs not covered;
- present and missing streams;
- whether whole-B demand suitability is supported;
- whether authoritative directional C generation is supported;
- issue codes, evidence strings, and limitations.

No new external enum is required.

## 5. Directional-only authority

Directional-only evidence contains outbound and/or inbound observations and no combined observations.

### 5.1 Full directional support

Whole-B directional demand suitability is supported only when:

- both outbound and inbound streams are present;
- each stream continuously covers its required directional comparison span;
- every exact A and B departure is covered by the matching directional stream;
- no same-stream overlaps exist;
- no unsupported interpolation is used;
- existing confidence requirements are satisfied.

When these conditions hold, current directional block evaluation and Scenario C demand optimization may proceed.

### 5.2 Missing direction

If only one directional stream is present, local findings for that direction remain valid, but whole-B demand suitability is not supported.

Stable issue code:

`DEMAND_DIRECTION_STREAM_MISSING`

The missing stream MUST NOT be inferred from the available direction and MUST NOT be assigned zero demand.

## 6. Combined-only authority

Combined-only evidence contains combined observations and no directional observations.

### 6.1 Aggregate Scenario B conclusion

Combined-only evidence may support an aggregate whole-B demand-suitability conclusion when:

- combined coverage continuously spans the combined comparison window;
- every exact A and B departure is inside a combined interval;
- no combined-stream overlap exists;
- confidence and interpolation requirements are satisfied.

The conclusion is aggregate only. It MUST carry the limitation:

`COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE`

Combined demand is evaluated against aggregate two-direction service and is never presented as observed outbound or inbound demand.

### 6.2 Scenario C generation prohibition

Combined-only evidence does **not** support authoritative directional Scenario C demand optimization under Contract `1.0.0`.

The current C model locks trips by direction. No approved model exists to allocate combined passengers between directions or proposed departures.

Therefore:

- a combined-only B may be reported aggregate-suitable;
- a combined-only B may have an aggregate observed adverse finding;
- but an authoritative demand-optimized C MUST NOT be generated from combined-only evidence;
- the solver MUST NOT reuse the same combined passenger volume independently for both directions;
- the solver MUST NOT divide combined passengers by trip shares or an even split.

Stable generation-support code:

`COMBINED_DEMAND_UNSUPPORTED_FOR_DIRECTIONAL_C`

## 7. Mixed combined and directional evidence

### 7.1 Overlapping mixed grain

A combined observation that overlaps in time with any outbound or inbound observation in the same dataset is ambiguous without explicit provenance describing whether the values are duplicates, components, independent samples, or reconciled totals.

The first Contract V1 implementation MUST reject such evidence before block construction.

Stable error code:

`MIXED_DIRECTION_GRAIN_OVERLAP`

The error is a demand-source contract defect. The records should be separated into distinct datasets or normalized under a future approved reconciliation policy.

### 7.2 Non-overlapping mixed grain

Combined and directional observations may coexist without temporal overlap. Their local blocks remain usable at their original grain.

However, a daily conclusion that changes between aggregate and directional denominators is not a single fully comparable whole-day demand conclusion under the first implementation.

Therefore non-overlapping mixed grain:

- preserves local block findings;
- is marked partial support;
- cannot produce `B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE`;
- cannot authorize authoritative Scenario C generation.

Stable issue code:

`MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT`

## 8. Gap detection rules

### 8.1 Same-stream internal gaps

For ordered observations in one stream, when:

`current.interval_start > previous.interval_end`

the interval:

`[previous.interval_end, current.interval_start)`

is an uncovered gap.

Stable issue code:

`DEMAND_TEMPORAL_COVERAGE_GAP`

### 8.2 Leading and trailing gaps

When source coverage starts after a required comparison-span start, the leading interval is uncovered.

When source coverage ends before a required comparison-span end, the trailing interval is uncovered.

Stable issue code:

`DEMAND_SERVICE_WINDOW_NOT_COVERED`

### 8.3 Uncovered departures

Every exact A and B departure must belong to a compatible source interval using the existing half-open convention:

`interval_start <= departure_time < interval_end`.

An uncovered departure produces:

`DEMAND_DEPARTURE_NOT_COVERED`

The evidence identifies scenario, direction, trip ID, and departure time.

### 8.4 No synthetic blocks

The implementation MUST NOT create a `DemandAnalysisBlockV1` for a gap by setting:

- `observed_passengers = 0`;
- `confidence = unknown`;
- `interpolation_status = unsupported`;
- or any equivalent placeholder passenger value.

Coverage diagnostics are metadata and evaluation evidence, not fabricated demand records.

The existing `DemandResolutionResultV1.blocks` remain composed only of observed or validly aggregated source intervals.

## 9. Block-construction behavior

### 9.1 Native mode

Native blocks remain one block per source interval. Gaps are reported separately and are not filled.

### 9.2 Adaptive mode

A gap is an absolute merge boundary. Adaptive mode MUST NOT merge observations across a positive-duration gap.

Critical/no-service protection continues to apply within covered evidence.

### 9.3 Manual mode

A manual block spanning an uncovered gap is invalid and continues to fail closed.

Manual boundaries cannot redefine an uncovered interval as observed.

### 9.4 Daily-total evidence

Daily-total-only demand remains intraday-insufficient and does not create intraday coverage.

Mixed daily-total and intraday evidence continues to require separate datasets under the current contract.

## 10. Demand-suitability status precedence

Coverage support and local block status are separate dimensions of evidence.

The evaluator MUST preserve known adverse findings using this precedence:

1. known blocking/error findings such as `NO_SERVICE_WITH_DEMAND` and `CRITICAL_ABOVE_90`;
2. known warning findings such as `WARNING_ABOVE_85`;
3. insufficient confidence, interpolation, temporal coverage, or direction support;
4. pass/review-only findings.

Missing coverage MUST NOT downgrade a known observed adverse finding into a local pass.

Missing coverage also MUST NOT convert locally passing observed blocks into a whole-day pass.

### 10.1 Technical infeasibility precedence

Technical and fleet feasibility remain independent of demand coverage.

When B is technically infeasible, the B disposition remains:

`B_TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION`

Demand-coverage limitations are still attached and may block C generation as described below.

### 10.2 Known demand adverse finding with incomplete coverage

When B is technically feasible and an authoritative observed block proves warning/failure, B remains:

`B_TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE`

The evaluator also records incomplete coverage. This preserves the known B defect without claiming full-day demand support.

### 10.3 No known adverse finding with incomplete coverage

When B is technically feasible, observed blocks do not prove an adverse condition, and required coverage is incomplete, return:

`B_INSUFFICIENT_DATA`

Do not return `B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE`.

### 10.4 Full supported coverage

Existing suitable/unsuitable behavior remains unchanged when the relevant coverage mode fully supports the conclusion.

## 11. Scenario C generation gate

A whole-B adverse finding and support for demand-optimized C are different questions.

The first implementation authorizes authoritative demand-guided Scenario C only when full directional support exists under §5.1.

The following conditions block authoritative C generation:

- any temporal coverage gap in a required directional span;
- any exact A/B directional departure not covered;
- a missing outbound or inbound stream;
- combined-only evidence;
- mixed direction grain;
- daily-total-only evidence;
- unsupported interpolation;
- insufficient confidence under existing policy.

Stable gate code:

`DEMAND_COVERAGE_INCOMPLETE_FOR_C_GENERATION`

### 11.1 Orchestration behavior

Before invoking a demand-guided solver, `run_schedule_solver_v1()` MUST evaluate the coverage/generation-support gate.

When the gate fails, return:

- `result_status = C_NOT_GENERATED_INSUFFICIENT_DATA`;
- `execution_status = NOT_RUN`;
- `solver_status = null`;
- `solver_adapter = null`;
- `solve_duration_seconds = 0`;
- `solution = null`;
- `diagnostic_candidate = null`.

This applies even when B has a known local demand defect or is technically infeasible, because the current heuristic adapter does not declare a demand-independent technical-feasibility-only objective mode.

A future approved technical-only solver capability may use different gating. V1-H3 does not create that capability.

### 11.2 Fixed-parameter infeasibility

A prior independent proof of `B_PARAMETERS_INFEASIBLE` remains stronger than demand coverage for the locked technical problem and continues to return:

`NO_FEASIBLE_C_WITH_B_PARAMETERS`.

No solver is invoked.

### 11.3 Already-suitable B

A B may be `B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE` only when its applicable aggregate or directional whole-window support is complete.

It continues to return `C_NOT_REQUIRED_B_SUITABLE`.

## 12. Independent validator backstop

Independent validation MUST prevent a caller from bypassing orchestration and turning a raw candidate into authoritative C when directional generation support is absent.

`validate_and_build_solution_v1()` MUST reject such a candidate with:

`DEMAND_COVERAGE_INCOMPLETE_FOR_AUTHORITATIVE_C`

The candidate remains diagnostic only. No `ScheduleSolutionV1` is constructed.

## 13. Evidence and limitations within Contract 1.0.0

V1-H3 does not add a serialized top-level field.

Coverage authority is exposed through existing shapes:

- `DemandResolutionResultV1.warnings` and `limitations`;
- demand-suitability dimension issues and evidence;
- evaluation warnings and limitations;
- generation outcome explanations and limitations;
- deterministic fingerprints.

Evidence strings SHOULD include:

- coverage mode;
- required span start/end;
- covered duration;
- uncovered start/end;
- affected stream;
- uncovered A/B trip IDs;
- whether B global suitability is supported;
- whether directional C generation is supported.

Ordering MUST be deterministic by direction, start, end, and trip ID.

Raw passenger values MUST NOT be inserted for uncovered intervals.

## 14. Fingerprint identity

V1-H1 and V1-H2 already bind normalized inputs, evaluation evidence, policy, operating facts, and configuration.

V1-H3 requires coverage diagnostics that affect disposition or solver gating to participate in identity through authoritative evaluation evidence and limitations.

Two otherwise identical problems MUST have different problem fingerprints when they differ in:

- an internal coverage gap;
- an uncovered exact departure;
- presence or absence of a directional stream;
- combined-only versus directional-only grain;
- mixed-grain support;
- C-generation support.

No timestamp or runtime duration participates.

## 15. Stable codes

The first implementation uses stable codes as applicable.

Demand-source errors:

- `OVERLAPPING_DEMAND_OBSERVATIONS`;
- `MIXED_DIRECTION_GRAIN_OVERLAP`.

Coverage/evaluation issues:

- `DEMAND_TEMPORAL_COVERAGE_GAP`;
- `DEMAND_SERVICE_WINDOW_NOT_COVERED`;
- `DEMAND_DEPARTURE_NOT_COVERED`;
- `DEMAND_DIRECTION_STREAM_MISSING`;
- `MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT`;
- `COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE`.

Generation/validation gates:

- `COMBINED_DEMAND_UNSUPPORTED_FOR_DIRECTIONAL_C`;
- `DEMAND_COVERAGE_INCOMPLETE_FOR_C_GENERATION`;
- `DEMAND_COVERAGE_INCOMPLETE_FOR_AUTHORITATIVE_C`.

These codes identify evidence support. They are not passenger-demand estimates and are not technical fleet-infeasibility conclusions.

## 16. Versioning and compatibility

V1-H3 remains a Contract `1.0.0` hardening clarification.

It does not add or remove serialized object properties or enum values.

Permitted changes include:

- a pure internal coverage-assessment helper;
- stronger public demand-source validation;
- deterministic warnings, limitations, evidence, and issue codes;
- status-precedence correction;
- no-run solver gating;
- candidate-validation backstop;
- fingerprint changes caused by complete evidence identity.

V1-H3 MUST NOT:

- create synthetic zero-demand blocks;
- add coverage fields to strict JSON schemas;
- allocate combined demand between directions;
- interpolate missing intervals;
- modify passenger values;
- introduce a technical-only solver mode;
- alter runtime, turnaround, fleet, headway-regime, or V1-A1 semantics;
- modify production UI or export paths.

## 17. Implementation boundary for Codex

### 17.1 Expected files

Implementation should remain concentrated in:

- `src/bus_schedule_engine/contracts_v1/demand_coverage.py` — new pure helper if useful;
- `src/bus_schedule_engine/contracts_v1/public_api.py`;
- `src/bus_schedule_engine/contracts_v1/demand_resolution.py`;
- `src/bus_schedule_engine/contracts_v1/evaluation.py`;
- `src/bus_schedule_engine/contracts_v1/solver_orchestration.py`;
- `src/bus_schedule_engine/contracts_v1/solver_validation.py`;
- `src/bus_schedule_engine/contracts_v1/evaluation_fingerprints.py` only if explicit coverage payload is necessary beyond existing evaluation evidence;
- Contract V1 demand-resolution, public-boundary, evaluation, and solver tests.

### 17.2 Prohibited files and areas

Codex MUST NOT modify:

- legacy `demand.py` or `c_generator.py`;
- runtime/turnaround/fleet logic hardened by V1-H2;
- Streamlit/application files;
- diagrams or XLSX exporters;
- workbook templates;
- external Contract `1.0.0` JSON schemas or enum sets;
- OR-Tools;
- V1-A1 / Contract `1.1.0`.

### 17.3 Required implementation sequence

1. Add a pure deterministic coverage assessment from normalized A/B timetables and observed demand.
2. Add same-stream and mixed-grain overlap guards with stable errors.
3. Detect internal, leading, trailing, and uncovered-departure gaps without creating blocks.
4. Preserve gap evidence in resolution limitations and evaluation evidence.
5. Correct demand-status precedence so known observed adverse findings survive insufficient support.
6. Prevent whole-B suitability when applicable coverage is incomplete.
7. Add directional C-generation support gating in orchestration.
8. Add the independent validator backstop.
9. Bind diagnostics through existing fingerprint evidence.
10. Add adversarial regressions and run full validation.

## 18. Mandatory adversarial regression suite

At minimum, tests MUST prove:

1. source intervals `06:00–07:00` and `08:00–09:00` create a coverage gap diagnostic;
2. the gap does not create a zero-passenger demand block;
3. a leading gap relative to the A/B comparison span blocks whole-B suitability;
4. a trailing gap relative to the A/B comparison span blocks whole-B suitability;
5. a final A or B departure at an uncovered half-open boundary is reported;
6. every uncovered departure diagnostic includes scenario, direction, trip ID, and time;
7. full outbound coverage with missing inbound stream returns insufficient support when no combined stream exists;
8. full outbound and inbound directional coverage preserves existing supported behavior;
9. outbound and inbound may use different valid source boundaries;
10. combined-only full global coverage may support aggregate B suitability;
11. combined-only evidence carries directional-support limitation;
12. combined-only demand-unsuitable B does not generate authoritative directional C;
13. the same combined demand is never reused independently as both outbound and inbound observed demand;
14. same-stream overlap fails with `OVERLAPPING_DEMAND_OBSERVATIONS`;
15. overlapping combined and directional evidence fails with `MIXED_DIRECTION_GRAIN_OVERLAP`;
16. non-overlapping mixed grain preserves local blocks but blocks whole-B suitability and C generation;
17. adaptive mode never merges across a gap;
18. manual mode rejects a block spanning a gap;
19. a known `NO_SERVICE_WITH_DEMAND` finding plus a gap remains a demand failure;
20. a known `CRITICAL_ABOVE_90` finding plus a gap remains a demand failure;
21. a known `WARNING_ABOVE_85` finding plus a gap remains a warning/unsuitable conclusion;
22. passing or low-load observed blocks plus a gap do not produce B suitable;
23. solver orchestration returns a sanitized `C_NOT_GENERATED_INSUFFICIENT_DATA` no-run envelope when C support is absent;
24. technically infeasible B with incomplete demand coverage does not invoke the current demand-guided heuristic;
25. independently proven fixed-parameter infeasibility retains its technical no-feasible outcome;
26. direct candidate validation rejects when authoritative C demand support is absent;
27. full directional support continues to allow existing heuristic adapter tests;
28. coverage changes alter authoritative evaluation/problem fingerprints;
29. daily-total-only behavior remains intraday-insufficient;
30. full Pytest, Ruff lint, Contract V1 format, and JSON Schema suites remain green.

## 19. Acceptance gate

V1-H3 is complete only when:

- uncovered time is never represented as zero demand;
- same-stream and mixed-grain overlap ambiguities fail closed;
- local observed adverse findings remain visible;
- incomplete coverage cannot produce a whole-B suitable conclusion;
- combined-only evidence is never allocated to directions;
- only full directional support authorizes current demand-guided C generation;
- orchestration and independent validation both enforce the gate;
- no external Contract `1.0.0` shape or enum changes;
- all mandatory adversarial tests pass;
- full Pytest passes;
- Ruff lint passes;
- Contract V1 Ruff-format gate passes;
- JSON Schema validation passes;
- no prohibited runtime, UI, export, OR-Tools, or V1-A1 scope drift occurs.

## 20. Explicitly deferred work

The following remain separate tasks:

- an explicit intraday coverage declaration in a future contract version;
- reconciliation policies for overlapping combined and directional sources;
- calibrated directional allocation of combined demand;
- technical-feasibility-only solver capability without demand support;
- typed `ScheduleProblemV1` alignment with its machine-readable schema;
- V1-A1 structural-change implementation;
- OR-Tools optimization and production runtime cutover.

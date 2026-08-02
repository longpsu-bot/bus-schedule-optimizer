# Milestone 6A2E: Real-route operational review pack

**Status:** Active next milestone

**Authoritative baseline:** `main@24384d6397bed40ffa46a93089b1193f556948e1`

**Review profile:** `m6a2e_real_route_operational_review_v1`

**Required disposition:** `EXPERT_REVIEW_REQUIRED`

## 1. Purpose and non-approval boundary

Milestone 6A2E runs one external workbook through the existing unified Contract V1 application
pipeline and creates a deterministic package for a transport-planning expert. The package makes
current Scenario B, demand authority, solver outcomes, fleet and terminal facts, protected
service floors, and an accepted B-to-C change visible before any optimization-semantic change is
authorized.

The package is decision support. It does not approve or publish a timetable, declare a ridership
forecast, claim global optimality, generalize a heuristic search failure into infeasibility, infer
missing terminal capacity, or choose a structural route policy. Every report states
`EXPERT_REVIEW_REQUIRED`.

## 2. Frozen authority

The review consumes the merged 6A1 through 6A2D behavior and the unified 5C2/5C3 runtime. It does
not change workbook import, readiness, normalization, Scenario B evaluation, adjustment-need
evaluation, `ScheduleProblemV1`, either solver adapter, solver controls, the 15 objective stages,
candidate validation, protected-floor classification or enforcement, recommendation, schemas,
the input template, Page 05, or the route corpus.

The review service calls `run_unified_application_pipeline_v1` and then supplies its verified
presentation, figures, and XLSX bytes to `build_unified_page5_artifacts_v1`. There is no second
workbook exporter or chart implementation.

## 3. Review model

`RealRouteOperationalReviewV1` is frozen and slotted. Its top-level status is one of
`REVIEW_COMPLETE`, `INPUT_NOT_READY`, `PIPELINE_FAILED`, or `ARTIFACT_FAILED`. Its derived
disposition is one of `CURRENT_B_RETAINED`, `ACCEPTED_CANDIDATE_AVAILABLE`,
`NO_ACCEPTED_CANDIDATE`, `SOLVER_DIVERGENCE_REVIEW_REQUIRED`,
`DEMAND_AUTHORITY_INCOMPLETE`, `PROTECTED_FLOOR_REJECTION`, or `EXPERT_REVIEW_REQUIRED`.

The model contains sorted reason and limitation codes, input readiness, supplied and derived
route facts, demand authority, Scenario B operations, separate solver outcomes, the existing
recommendation, an optional accepted B-to-C comparison, protected-floor evidence, artifact
metadata, an expert checklist, authoritative fingerprint references, and exactly one
next-decision category. It uses no weighted score.

Route facts identify each value as `SUPPLIED_FACT`, `DERIVED_FACT`, `ASSUMPTION`, or
`NOT_EVALUATED`. No available-fleet value or observed timetable behavior is treated as a terminal
occupancy limit.

## 4. CLI

The first implementation accepts exactly one workbook:

```text
python -m bus_schedule_engine.real_route_review \
  --workbook "private/route.xlsx" \
  --source-id "route-review-2026-08" \
  --solver BOTH \
  --output-dir "outputs/route-review"
```

`--solver` accepts only `HEURISTIC`, `OR_TOOLS`, or `BOTH`. `--overwrite` permits replacement of
only the five bounded output filenames. There is no readiness, validator, protected-floor, or
artifact-integrity bypass and no multi-route workflow.

## 5. Output files and exit codes

A completed package contains:

```text
operational-review.json
operational-review.md
Bus_Schedule_Contract_V1_Result.xlsx
Bus_Schedule_Contract_V1_Charts.html
Bus_Schedule_Contract_V1_Overview.png
```

If input is not ready, the unified pipeline fails, or artifact construction fails, only the JSON
and Markdown review files are written. A rerun with `--overwrite` removes stale files bearing the
three bounded Contract artifact names before writing a failed review, so unavailable artifacts
cannot appear current.

Exit codes are `0` for a completed review including valid no-C outcomes, `2` for input not ready,
`3` for a unified pipeline failure, `4` for artifact failure, and `5` for review serialization,
integrity, output collision, or bounded-write failure. A solver rejection or no accepted C is a
completed review and is not a CLI crash.

## 6. Deterministic fingerprint and privacy

The canonical serializer emits sorted, compact, ASCII-safe JSON. The SHA-256 review fingerprint
covers the complete review payload except its own field. Verification functions operate on both
the frozen model and canonical JSON bytes, and tamper tests change a payload fact without updating
the fingerprint.

The canonical payload excludes wall-clock timestamps, elapsed solver durations, workbook and
output paths, machine identity, workbook bytes, raw workbook rows, raw passenger observations,
and personal information. It includes existing authoritative Scenario A, Scenario B, demand,
evaluation, adjustment, presentation, solver-outcome, and accepted-solution fingerprints when
they are available. An unavailable fingerprint remains unavailable; it is not replaced with an
authoritative-looking token.

The CLI uses a fixed, timezone-aware review import instant because that runtime provenance does
not authorize any timetable fact and must not make repeated review JSON vary. Existing Contract
fingerprint functions already exclude that import instant from source-fact identity. Exceptions
are reduced to stable statuses and codes; reports do not echo a local path, cell value, workbook
content, or exception message.

## 7. Scenario B operational metrics

The review reports total and directional trips, first and last departures, minimum/median/mean/
maximum headway by direction, current sustained regimes and transition headways, the largest
service gap, no-service blocks, blocks above target and maximum load factors, authoritative daily
demand where available, nominal daily supply, minimum fleet, fleet slack, minimum observed
turnaround slack, supplied terminal limits, reconstructed maximum occupancy, and stable validation
codes.

Headway facts come from the normalized exact Scenario B timetable and existing regime authority.
Fleet and turnaround facts come from the current Scenario B evaluation and adjustment evidence.
Terminal reconstruction uses the existing solver-neutral Contract V1 occupancy assessor. The
review adds no alternate fleet model.

## 8. Demand authority

The demand section reports grain, coverage mode, direction streams, observation period and days,
confidence, uncovered segments and departures, demand gaps, canonical-request constructibility,
and explicit no-solve reasons. Complete temporal coverage is kept distinct from confidence and
solver eligibility.

Incomplete coverage remains fail-closed. The review never interpolates, stretches a neighboring
interval, duplicates an observation, or inserts zero demand. It cannot create a solver
recommendation when the application did not construct and execute a request.

## 9. Solver summaries

Each requested solver records request construction, adapter ID, execution and native statuses,
generation status, independent acceptance, diagnostic candidate fingerprint when retained,
accepted solution and outcome fingerprints, the existing objective vector when the BOTH-solver
comparison produced one, the unchanged objective-stage names, explanations, limitations,
validator codes, the protected-floor fingerprint, and native-search enforcement state.

The heuristic section always states that it proves neither optimality nor infeasibility. The
OR-Tools section limits `INFEASIBLE` to the exact encoded fixed-resource model; it does not extend
that status to variable trips, more fleet, relaxed policy, or structural demand response.

## 10. Accepted B-to-C comparison

When the existing recommendation contains an independently accepted C, the review compares total
and directional counts, service-window endpoints, maximum and mean headways, no-service blocks,
shortage blocks and volume, minimum fleet, fleet slack, turnaround slack, evaluated terminal
occupancy, protected compliance, shifted-trip count, maximum shift, and total shift.

The accepted C objective vector is included only when the existing BOTH-solver comparison made it
available. The review does not construct an alternative Scenario B vector. A numerical
improvement remains `EXPERT_REVIEW_REQUIRED`.

## 11. Protected-service-floor review

The protected section reports trip-ridership dataset status, scheduled-trip and direction
coverage, confidence, current Scenario B regimes, protected regime count and windows, protected
trip counts, internal headway maximums, candidate acceptance by solver, native heuristic and
OR-Tools results, the common validator result, and the exact enforcement fingerprint.

Source trip IDs are omitted from this general external-workbook review payload. Transition gaps
remain excluded from protected internal-headway checks. A regime that is not protected is not
relabeled as low demand. When no regime is enforceable, the report states that explicitly.

## 12. Expert checklist

The deterministic checklist covers route/day identity, current and proposed timetable meaning,
trip authority, capacity, fleet, runtimes, turnaround, terminal limits, observation period and
confidence, demand gaps, largest service gaps, peak blocks, protected regimes, large shifts,
solver divergence, traffic variability, driver/break/depot/deadhead/maintenance scope, and the
non-approval boundary.

Statuses are `CONFIRMED_BY_INPUT`, `DERIVED_FOR_REVIEW`, `REQUIRES_EXPERT_CONFIRMATION`,
`NOT_EVALUATED`, or `OUTSIDE_MODEL_SCOPE`.

## 13. Route-corpus evidence

Alpha proves deterministic review construction over complete LOW-confidence sensitivity-proxy
coverage. The review labels confidence honestly and never creates terminal-capacity approval when
no limit is supplied. Existing corpus characterization tests remain the authority for whether
both canonical solver requests are constructible under the approved LOW-confidence sensitivity
policy; solver timing, result quality, fingerprints, and recommendations remain non-frozen.

Beta preserves the outbound 17:00-18:00 interior gap. Its review remains complete as a package,
but demand authority is incomplete, no interpolation or fabricated zero appears, and no accepted
solver recommendation follows. No corpus fixture or reviewed fact changes in 6A2E.

## 14. Private workbook policy

Private workbooks stay external, untracked, and outside fixtures and repository history. The CLI
never includes a workbook path in the review. Private inputs and outputs, derived route facts, and
route fingerprints must not be committed. Private route commands may run only for explicit
user-designated paths and must use separate output directories.

No designated private workbook path was supplied in this checkout, so milestone validation uses
approved anonymized and synthetic evidence and records `PRIVATE_ROUTE_EXECUTION_NOT_PERFORMED` in
the implementation handoff rather than fabricating route 61-2, 61-4, or 61-8 results.

## 15. Fixed-resource limitation

The current solver locks total and directional trip counts. It can validate and analyze a
separately supplied timetable with a different count, but it cannot claim to have optimized that
structural increase or reduction. A route whose operating question is a material trip-count
change is classified `FIXED_RESOURCE_SCOPE_GAP`; the review does not implement variable trips,
fleet expansion, or fleet minimization.

## 16. Next-decision gate

Every completed review recommends exactly one of `NO_ENGINE_CHANGE_REQUIRED`,
`DATA_AUTHORITY_GAP`, `PRESENTATION_GAP`, `OBJECTIVE_QUALITY_GAP`, `HARD_CONSTRAINT_GAP`,
`FIXED_RESOURCE_SCOPE_GAP`, or `OUTSIDE_MODEL_SCOPE`.

Incomplete demand or missing terminal capacity selects `DATA_AUTHORITY_GAP`; a verified artifact
failure selects `PRESENTATION_GAP`; a structural trip-count decision selects
`FIXED_RESOURCE_SCOPE_GAP`; material accepted-solver divergence selects
`OBJECTIVE_QUALITY_GAP`. Otherwise the bounded review selects `NO_ENGINE_CHANGE_REQUIRED` unless
future external evidence explicitly demonstrates another category. This milestone recommends a
category only and implements none of them.

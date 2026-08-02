# Milestone 6A2F: Layered Data Authority Workflow

## Status

Milestone 6A2F adds a deterministic, offline pre-optimization review for exact Scenario B
timetables. It separates timetable facts that are already reviewable from conclusions that need
additional operator-owned authority.

The governing rule is:

> Missing authority blocks only the capability that requires it.

The workflow neither infers missing values nor changes the strict Contract V1 optimization
boundary introduced by Milestone 5A2A and used by Milestone 6A2E.

## Motivation

An exact timetable can contain enough information to check chronology, terminals, runtimes,
headways, service endpoints, and supplied vehicle chains even when vehicle capacity, available
fleet, turnaround authority, demand metadata, or terminal limits are absent. Previously, a blank
vehicle capacity failed workbook import, so all lower-level timetable facts appeared unevaluated.

Milestone 6A2F makes the import and review boundary match the authority actually required by each
conclusion. It does not treat missing optimization metadata as a technical rejection of a
timetable.

## Capability model

`LayeredDataAuthorityReadinessV1` is frozen and slotted. It contains one deterministic
`CapabilityReadinessV1` for each explicit capability:

| Capability | Required authority | Behavior when incomplete |
|---|---|---|
| `TIMETABLE_REVIEW` | Route, terminals, route type, trip count, exact Scenario B trips, directions, departure terminals/times, resolvable arrivals, and declared service endpoints | Only unavailable core timetable facts block this review. Vehicle capacity is irrelevant. |
| `TURNAROUND_COMPLIANCE` | Authoritative minimum turnaround and resolvable arrivals | Supplied cycle gaps and overlaps remain descriptive; compliance is `NOT_EVALUATED`. |
| `DEMAND_EVALUATION` | Vehicle capacity, demand data, demand metadata, and coverage for the requested grain | Combined demand permits combined descriptive review only. Directional demand is never fabricated. |
| `FLEET_FEASIBILITY` | Available-fleet limit plus sufficient runtime and turnaround authority | Source vehicle IDs can describe one supplied assignment but do not become the available-fleet limit. |
| `OPTIMIZATION` | Existing strict Contract V1 readiness | Normalization and both solvers remain unavailable until all existing authority is complete. |
| `TERMINAL_CAPACITY` | Explicit limit for each relevant terminal | Missing limits retain the existing terminal-capacity `NOT_EVALUATED` codes. |

Each capability reports `READY`, `PARTIAL`, or `BLOCKED`, together with stable missing-authority
and limitation codes. The existing all-or-nothing optimization readiness model remains in place
for the ordinary application and Milestone 6A2E.

## Importer behavior

`ScenarioParameters.vehicle_capacity_passengers` already supports `None`. The XLSX importer now
uses that model boundary:

- a blank Scenario A or Scenario B capacity imports as `None`;
- a nonblank value must remain a positive integer;
- zero, negative, boolean, fractional, and nonnumeric values raise `InputDataError`; and
- no default capacity is inserted.

Blank capacity produces the stable capability-specific codes
`VEHICLE_CAPACITY_REQUIRED_FOR_DEMAND_EVALUATION` and
`VEHICLE_CAPACITY_REQUIRED_FOR_OPTIMIZATION`. It does not block `TIMETABLE_REVIEW`.

## Timetable authority metadata

`THONG_TIN_DU_LIEU` accepts three optional workbook-owned fields:

- `timetable_authority_status`;
- `timetable_authority_reference`; and
- `timetable_effective_date`.

`TimetableAuthorityMetadataV1` is separate from demand authority. Its status enum accepts
`approved_operational`, `current_operational`, `proposed`, and `unknown`. Absence means `unknown`.
Only an explicit `approved_operational` value is reported as source-approved.

The engine does not promote proposed or unknown status. Approval metadata never bypasses
technical checks, and a technical review does not grant or revoke an external approval.

## Partial timetable review

`PartialTimetableReviewV1` is a frozen, slotted, deterministic model with profile
`m6a2f_partial_timetable_review_v1`. It reports:

- workbook-owned timetable authority and per-capability readiness;
- route and terminal facts;
- declared and exact trip and direction counts;
- declared-versus-exact service endpoints;
- chronology, terminal/direction, and runtime issues;
- exact runtime and same-direction headway statistics;
- canonical sustained regimes and transition headways;
- source vehicle-cycle counts, overlaps, and observed inter-trip gaps;
- turnaround-compliance status only when threshold authority exists;
- descriptive demand availability without raw passenger rows;
- fleet, terminal-capacity, and optimization authority; and
- limitations plus a canonical review fingerprint.

The payload excludes workbook/output paths, machine identity, wall-clock timing, raw passenger
rows, and inferred capacity, fleet, demand, turnaround, or terminal limits. Privacy validation
recursively inspects payload field names and string values. A complete string that is a Windows
drive path, UNC path, or POSIX absolute path is rejected; ordinary prose and slash-delimited
authority references such as `147/QĐ-SXD-QLVT` remain valid. Canonical JSON is serialized with
sorted keys and compact separators. The fingerprint covers the complete review except the
fingerprint field itself. Both the model and canonical bytes are verified before any filesystem
mutation.

## Canonical regime reuse

The existing Scenario B regime derivation was separated into the pure
`derive_exact_timetable_service_regimes_v1(...)` helper. The established
`derive_current_b_service_regimes_v1(...)` delegates to that helper, preserving its prior
semantics. The partial review calls the same helper and therefore does not introduce a competing
regime algorithm.

Regression tests compare both entry points. Existing protected-floor classification,
fingerprinting, and enforcement tests remain authoritative.

## Source vehicle-cycle review

When exact source vehicle IDs exist, trips are grouped by the unchanged ID and sorted by
departure time then trip ID. The review reports temporal overlaps, terminal discontinuities,
per-vehicle minimum arrival-to-next-departure gaps, and the overall minimum observed gap. For
each consecutive pair, the prior trip's direction determines its arrival terminal; a different
next departure terminal produces `SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY` without inferring
deadhead or repositioning.

Only a temporally overlap-free and terminal-continuous supplied assignment is labeled
`SOURCE_ASSIGNMENT_OVERLAP_FREE`; it is not called globally fleet-optimal. A terminal discontinuity
uses `SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY_DETECTED` and prevents a `COMPLIANT` turnaround
result. Temporal overlaps and terminal discontinuities remain separately visible. Source IDs do
not authorize an available-fleet limit. When IDs are absent, the result is
`SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED`; no assignments are fabricated and no fleet optimizer is
called.

The current-contract regulatory fallback may be displayed separately. It is not relabeled as an
operator-supplied, terminal-specific turnaround authority. Without an explicit minimum turnaround,
compliance is `NOT_EVALUATED` even though observed gaps and overlaps are still reported.

## Demand and terminal boundaries

The review reports demand record availability and declared direction grain, not passenger-row
contents. Combined records remain combined. They are not divided, duplicated, or used to
authorize directional load evaluation or directional optimization.

Terminal capacity is evaluated only from explicit terminal limits. Timetable occupancy, source
vehicle count, available fleet, terminal names, or authority status never create a terminal limit.

## Offline CLI

Run the no-solver review first:

```text
python -m bus_schedule_engine.data_authority_review \
  --workbook "private/route.xlsx" \
  --source-id "route-authority-review-2026-08" \
  --output-dir "outputs/authority-review"
```

Pass `--overwrite` to replace only the two approved output filenames:

- `data-authority-review.json`;
- `data-authority-review.md`.

Exit codes are:

- `0`: timetable review completed, including demand- or optimization-blocked cases;
- `2`: core workbook import/review was not possible; and
- `5`: serialization, integrity, collision, or write failure.

The Markdown document has fourteen fixed sections covering conclusion, authority, readiness,
timetable consistency, runtime, headways/regimes, source cycles, turnaround, demand,
fleet/terminals, optimization blockers, completion actions, limitations, and fingerprints.

## Workflow with Milestone 6A2E

The intended two-step workflow is:

1. run `data_authority_review` and inspect the exact timetable plus capability-specific gaps;
2. supply missing authority, then run `real_route_review` when optimization readiness is complete.

Milestone 6A2E remains strict. The new path does not change Contract V1 normalization, the
heuristic solver, OR-Tools adapters or objectives, the independent validator, Page 05 artifacts,
ordinary Streamlit, or the offline legacy oracle.

## Synthetic acceptance evidence

The test suite includes a private-data-free, 61-4-like fixture with 46 exact trips across seven
supplied vehicle cycles. The assignment is overlap-free and its minimum observed inter-trip gap
is exactly 10 minutes. Additional tests cover missing authority, invalid capacity, combined
demand, terminal limits, metadata preservation, count/endpoint/runtime discrepancies, no-solver
execution, deterministic fingerprints, tampering, CLI exit codes, and pre-mutation bounded-write
verification.

## Non-goals and unchanged boundaries

Milestone 6A2F does not add variable-trip-count optimization, change objectives, infer operational
facts, allocate combined demand, create approval logic, alter protected-floor policy, expose the
workflow in Streamlit, add persistence, or add multi-route execution. Contract V1 schemas and the
reviewed route corpus are unchanged. Private route workbooks and facts remain outside the
repository.

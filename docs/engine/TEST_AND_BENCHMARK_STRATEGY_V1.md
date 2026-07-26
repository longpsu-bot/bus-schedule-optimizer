# Test and Benchmark Strategy V1

**Status:** Active strategy

**Governing direction:** [Project Direction Reset](PROJECT_DIRECTION_RESET.md)

The immediate purpose of this strategy is to prove a fixed-resource one-route solver boundary
before adding demand objectives or cutting over the UI. Tests must establish correctness with
small explainable cases, then differential behavior, then real-route evidence.

## Priority order

1. Tiny hard-feasibility proofs.
2. Heuristic-versus-CP-SAT differential tests through the same problem and validator boundary.
3. Anonymized real-route fixtures, especially difficult headway, terminal-balance, turnaround,
   and fleet cases.
4. Fixed-resource demand/headway objective tests.
5. Application-service, chart, and XLSX reconciliation.
6. Performance benchmarks.

V1-A1 structural demand-response scenarios and monitoring tests are deferred. They do not block
hard-feasibility work.

## 1. Tiny feasibility proofs

Maintain hand-solvable instances with 4-12 trips. The first CP-SAT pull request must cover:

- one vehicle operating one feasible alternating chain;
- an unavoidable second vehicle;
- solver-determined initial positioning at both terminals;
- terminal imbalance requiring a specific initial split;
- exact runtime inherited from each source trip;
- unequal terminal-specific turnaround;
- a ready event and departure at the same timestamp, with ready processed first;
- locked first and last departures;
- fixed total and directional trip counts;
- a feasible schedule exactly at the available-fleet limit;
- infeasibility below the minimum required fleet;
- negative terminal-stock rejection;
- a deliberately corrupted raw candidate rejected by the independent validator; and
- honest mapping of `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `MODEL_INVALID`, and `UNKNOWN`.

Compare CP-SAT results with exhaustive enumeration where practical. A solver-native feasible
status is insufficient unless the independent validator accepts the candidate.

The first feasibility suite includes no demand objective. It must not depend on V1-A1 scenario
selection.

## 2. Canonical boundary and invariant tests

Property and regression tests must prove:

- normalization preserves exact source values and never mutates the source workbook;
- total trips are across both directions;
- actual directional counts remain authoritative, including asymmetric examples such as 41/39;
- `ScheduleProblemV1` carries the exact fixed-resource facts used by the solver;
- C total and directional trips equal B in `fixed_by_direction`;
- every accepted C trip maps one-to-one to a source B trip;
- first/last departures remain locked;
- per-trip runtime remains exact;
- turnaround is applied at the arrival terminal;
- minimum required fleet does not exceed the available upper bound;
- recommended initial terminal counts sum to minimum required fleet;
- terminal stock remains non-negative over the continuous event timeline;
- demand-block boundaries do not reset fleet or headway chronology;
- solver candidates are non-authoritative before validation;
- non-accepted outcomes contain no fabricated Scenario C; and
- problem, candidate, solution, and outcome fingerprints change when their persisted/cached
  authoritative payload changes.

Fingerprints are tested for reproducible identity and reconciliation, not internal authorization.

## 3. Heuristic versus CP-SAT differential tests

Run the existing heuristic adapter and CP-SAT adapter from the same canonical problem. Validate
both raw candidates independently and compare:

- candidate accepted/rejected state;
- hard-constraint issue codes;
- total and directional trip locks;
- endpoint locks;
- runtime and turnaround evidence;
- minimum required fleet and initial positioning;
- terminal-stock profile;
- no-service blocks;
- overload above 90%;
- overload above 85%;
- excessive gaps;
- headway regularity;
- shifted-trip count;
- total and maximum shift; and
- native solver status and limitations.

The comparison is a transparent ordered vector, not the legacy weighted scalar score. A solver may
win a lower-priority metric only when all higher-priority metrics are equal. The heuristic must
never pass when a hard rule fails and must never claim proof of infeasibility or optimality.

Include cases where:

- both solvers find the same canonical timetable;
- both find different but equally feasible timetables;
- CP-SAT finds a feasible timetable missed by the heuristic;
- the heuristic finds a candidate used as a CP-SAT hint;
- a candidate from either solver is corrupted before validation; and
- a time-limited CP-SAT run returns `UNKNOWN` without being called infeasible.

## 4. Real-route fixture corpus

Build versioned anonymized fixtures from actual route data. Each fixture must document:

- anonymized route ID and provenance;
- operating-day type;
- exact directional timetable;
- exact source-trip runtimes;
- terminal-specific turnaround;
- vehicle capacity and available-fleet limit;
- demand source grain, direction availability, confidence, and observation-day handling;
- expected expert-reviewed constraints or outcome; and
- any redaction or limitation.

The corpus must include:

- balanced and asymmetric directional counts;
- tight and loose fleet limits;
- difficult terminal imbalance;
- short turnaround and long runtime combinations;
- endpoint-lock pressure;
- irregular and near-balanced headway sequences;
- feasible and infeasible variants;
- demand with coarse, directional, and combined-only grain; and
- schedules near the intended interactive trip-count tier.

Add Route 61-8 and Route 61-4 when anonymized source data is available. Do not invent these
fixtures from route names or public summaries; require exact timetable and operating facts with
reviewable provenance.

For every approved route fixture, compare the legacy runtime where possible, the canonical
heuristic, CP-SAT, and any expert-reviewed timetable.

## 5. Fixed-resource demand and headway objectives

Add these tests only after the hard-feasibility gate is green.

### Demand authority and load factor

Test:

- 0, below 85%, exactly 85%, between 85% and 90%, exactly 90%, above 90%, and demand with no
  service;
- one-sided penalties only;
- no `abs(load_factor - 0.85)` or equivalent authoritative objective;
- no reduction of service merely to raise low load factor;
- native 15/30/60-minute and irregular source intervals;
- no unsupported split finer than source demand;
- combined demand remaining combined;
- directional conclusions only from authoritative directional evidence; and
- exact planned/actual block reconciliation.

### Lexicographic objectives

Fixtures must prove this order:

1. prevent demand intervals with no service;
2. reduce critical intervals and overload above 90%;
3. reduce overload above 85%;
4. reduce excessive gaps;
5. improve sustained-demand alignment;
6. improve regularity;
7. preserve stable B sections;
8. minimize shifted trips, total shift, and maximum shift; and
9. use fleet only as a late tie-breaker.

Fix each prior-stage optimum before solving the next stage, or prove a mathematically safe
lexicographic encoding. A lower-priority improvement must never degrade a higher-priority result.

### Headway

Include:

- exact regular sequences;
- balanced floor/ceiling sequences such as `22,23,22,23`;
- irregular sequences;
- zero-headway exceptions;
- regimes crossing demand-block boundaries;
- endpoint locks;
- stable-B preservation; and
- coordinated local re-spacing rather than isolated trip movement.

## 6. Unified application service

Before UI cutover, run legacy and unified services side by side and reconcile:

- imported/normalized inputs;
- B validation and evaluation;
- adjustment decision;
- solver invocation/no-run decision;
- generation outcome;
- accepted timetable;
- objective vector;
- fleet and stock evidence; and
- limitations.

Tests must prove that a no-run, infeasible, unknown, model-invalid, or validator-rejected result
does not produce Scenario C rows.

## 7. Charts and XLSX

For one accepted solution and outcome identity, verify:

- chart and workbook totals equal authoritative A/B/C totals;
- C directional totals equal B in `fixed_by_direction`;
- C planned block counts equal exact departures under the boundary convention;
- combined demand is not double-counted or fabricated into directions;
- UI, diagrams, and XLSX show the same solver status and limitations;
- exact-departure traces contain no missing or duplicate C trip;
- editable XLSX values come from domain rows rather than recalculation;
- expected Vietnamese headings, filters, frozen headers, time formats, and percentage formats are
  present;
- the source workbook is never overwritten; and
- a non-accepted outcome creates an explicit status without fake C rows.

Retain legacy exporter tests until the Contract V1 cutover is complete.

## 8. Performance matrix

Benchmark only after functional proof tests are stable.

| Daily trips | First feasible target | Total staged solve target | Peak memory target | Use |
|---:|---:|---:|---|---|
| 40-80 | <= 1 s | <= 5 s | <= 512 MB | interactive baseline |
| 150 | <= 5 s | <= 30 s | <= 1 GB | normal large route |
| 300 | <= 15 s | <= 120 s | <= 2 GB | large-case acceptance |
| 400-500 | <= 60 s | <= 300 s | <= 4 GB | stress |

Each tier should include balanced/asymmetric directions, tight/loose fleet, and
feasible/infeasible variants. Once demand objectives exist, add uniform and peaky demand variants.

Run at least five warm repetitions plus one cold start on a pinned machine. Record:

- model-build time;
- first-feasible and total time;
- variables and constraints by family;
- native status, objective vector, and best bound;
- branches and conflicts;
- peak memory;
- OR-Tools and Python versions;
- CPU, worker count, seed, and deterministic controls;
- commit SHA; and
- problem, candidate, solution, and outcome fingerprints.

## 9. Determinism and flake policy

Optimal cases require the same objective vector and canonical solution fingerprint for identical
inputs and deterministic controls. Time-limited cases require valid status and invariant behavior;
`UNKNOWN` is acceptable and is not infeasibility.

Run single-worker deterministic benchmarks separately from production parallel benchmarks. Do not
make a failing test pass by increasing its timeout without benchmark review.

## 10. Deferred V1-A1 scenario and monitoring tests

The following are deferred until fixed-resource feasibility, objectives, and the route corpus are
stable:

- structural service-change classification;
- 10-to-40 and 20-to-80 trip response scenarios;
- temporal/frequency/response-support classifications;
- sensitivity-scenario catalogue and selection;
- calibrated demand-response provenance;
- unresolved-demand dispositions and result statuses;
- observed-versus-assumed UI and XLSX presentation; and
- post-implementation monitoring plans.

When resumed, these tests must prove that coarse A demand is not fabricated into B
departure-level demand and that scenario assumptions are never presented as observations.

## Stage gates

- **Heuristic boundary:** legacy heuristic crosses the canonical problem/candidate/validator path
  with behavior parity.
- **CP-SAT feasibility:** all tiny hard-invariant proofs pass.
- **Differential:** heuristic and CP-SAT comparison suite passes.
- **Route corpus:** difficult anonymized real-route fixtures are approved.
- **Objectives:** one-sided demand and lexicographic headway/shift suites pass.
- **UI/XLSX:** unified-service reconciliation and no-fake-C tests pass.
- **Performance:** agreed benchmark tiers pass or carry documented exceptions.

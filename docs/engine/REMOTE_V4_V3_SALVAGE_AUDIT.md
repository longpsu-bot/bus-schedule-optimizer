# Remote V4/V3 Bus Schedule Engine salvage audit

Status: audit-only checkpoint. No historical implementation was merged or cherry-picked.

Audit base:

- branch: `recovery/bus-schedule-engine-current-state`
- commit: `c6ad712f2b1541564f6e3662b315d6b3fc491460`
- recovery PR: #60
- pre-audit tracked `artifacts/` tree: `975abc2ef7c2eb3899d587a4a631215c392cb15e`

The current architectural authority used by this audit is:

- `DemandRegime` is immutable evidence;
- `ServiceRegime` is a mutable operational decision;
- total and directional trips, first/last departures, runtime, B shift, fleet,
  turnaround, protected service, whole-minute uniform internal headway, and regime
  count are hard;
- a transition boundary is clean only when its gap equals the left or right regime
  headway;
- compilers do not silently change allocations and validators do not move departures;
- future service-plan search is closed-loop and arithmetic remains deterministic code.

## 1. Branch and PR history

Unique commits below are computed relative to the recovery base. A commit can be
graph-unique after a squash merge while its content is already present in recovery;
content comparisons are therefore authoritative.

| Remote branch | Merge base with recovery | Commits unique to remote graph | PR and state | Audit finding |
| --- | --- | --- | --- | --- |
| `origin/feat/v4-adaptive-regime-skeleton` | `ae5cab1598b22639224628f7c2bbb7915ad29b7b` | `90203ab` design document; `d5e5a64` `AGENTS.md` | #58, open draft | Design only. No V4 source or tests. |
| `origin/feat/v3-multi-period-demand-runner` | `40c4415f97f78f01b33717c80f20e1e86c23be82` | `3e3787e`, `df9699c` | #53, merged as `90706dd` | Core demand/workbook content is already recovered; runner/exporter/tests in recovery are newer. |
| `origin/pilot/mst6-mst10-fixed-resource` | `484a949f7e56d5122ccce1fc1c030bf469f1382e` | `91d77a0`, `e00aade`, `c7387b`, `ab5b6c`, `4f113f3` | #51, closed unmerged draft | Generic legacy pilot wrapper plus private-URL workflow; superseded. |
| `origin/agent/two-stage-uniform-regime-spec` | `484a949f7e56d5122ccce1fc1c030bf469f1382e` | `6e23c6e`, `5e3cff1`, `0a3c0eb`, `0201ee4` | #52, merged as `40c4415` | Content is already in recovery and later amended. Do not cherry-pick branch commits. |
| `origin/fix/v3-stage1-to-real-timetable` | `da5473e571189ba44e5b94605309bf8cdf4ef98d` | none; tip is an ancestor of recovery | #54, merged | Representability-first V3 coarsening and review-run experiments already recovered. |
| `origin/fix/v3-phase-review-necessary-feasibility` | `eddb85a8434f95f195169790aab69de0c58c0e69` | none; tip is an ancestor of recovery | #55, merged | Review-only bounded-phase necessary-feasibility adapter already recovered. |
| `origin/fix/v3-phase-review-validator-semantics` | `b9edf7cb5ce01f6404ed5a0b84a4caef2c2d42be` | none; tip is an ancestor of recovery | #56, merged | Review-only validator alignment already recovered. |
| `origin/fix/v3-global-regularity-product` | `b3b7341a0616b615d5f095d213459f9e65464ada` | none; tip is an ancestor of recovery | #57, open draft | Research policy is already in recovery; recovery adds `fb4931d` hardening. It is not a closed-loop foundation. |

No commit met the audit's cherry-pick gate. PRs #52-#56 are already represented in
recovery, PR #57 is an ancestor, PR #53 is content-subsumed, PR #51 is obsolete, and
PR #58 contains only reference documentation plus a conflicting repository-local
`AGENTS.md`.

## 2. Missing-milestone coverage

| Missing milestone | Remote coverage | Decision |
| --- | --- | --- |
| Raw T06/T10 daily adapter and V3 reconciliation | No raw T06/T10 adapter. PR #53 imports already-aggregated `PERIOD_CATALOG`, `SAN_LUONG_MULTI_PERIOD`, and `DEMAND_PROFILE_CONFIG` sheets. | Raw adapter and its reconciliation must be built; reuse the recovered normalized multi-period contracts downstream. |
| Deterministic `DemandRegime` exact-K/CV/one-SE/stability | No implementation or tests. PR #58 contains only conceptual deterministic segmentation and cross-period confidence prose. | Must rebuild. V4 prose is reference-only. |
| Deterministic C1/C2/C3 allocator frontier | No named candidate implementation or frontier tests on the inspected remotes. Recovery has only frozen bridge transcriptions. | Must rebuild. Do not relabel V3 Stage 1 alternatives as C1/C2/C3. |
| Fixed-first/fixed-last compiler authority | Existing OR-Tools/V3 code fixes endpoints and tests them, but the recovered uniform compiler has no endpoint fields. | Port the constraint pattern into the compiler contract; do not port its old block-allocation model. |
| Strict clean boundary `gap in {h_left, h_right}` | No implementation or test. V3 and the recovered compiler minimize/cap soft transition error instead. PR #58 states jump limits, not the clean-boundary rule. | Must rebuild as a hard compiler/validator invariant. |
| Tail-aware effective spans and settlement | Existing V3 has last lock, tail ceiling, tail-demand classification, and non-densification. No effective span, residual settlement, backward fixed-last compilation, eligibility, or debt capacity. | Port selected tail predicates; rebuild tail-aware compilation. |
| Adaptive service-plan search | PR #58 describes bounded skeleton candidates but implements none. V3 merges block-derived groups and tries bounded allocation plans. | New implementation required. |
| Closed-loop orchestration | No state graph, neighbor operators, compile frontier, validation-to-planning feedback, or search-exhaustion state. | New coordinator required. |

Therefore raw daily `DemandRegime`, C1/C2/C3 allocation, strict clean-boundary,
effective-span tail compilation, and the closed loop cannot be recovered from these
remotes.

## 3. Component-by-component classification

| Historical component | Classification | Reason |
| --- | --- | --- |
| `contracts_v1/multi_period_demand.py` and its tests | `REUSE_AS_IS` | Byte-identical between PR #53 and recovery. Deterministic aggregation, structural diagnostics, and fingerprints are compatible evidence-layer primitives. |
| `v3_workbook.py` | `REUSE_WITH_ADAPTER` | Byte-identical and fail-closed, but consumes aggregated period rows rather than raw date-keyed T06/T10 observations. Put a raw adapter before it or its neutral contracts. |
| `v3_runner.py`, `v3_result_exporter.py`, `run_v3_two_stage.py` | `REUSE_AS_IS` for V3 regression/export | Recovery versions are newer than PR #53. They are useful runners/exporters, not service-plan coordination. |
| `service_adjustment.py` | `PORT_SELECTED_LOGIC` | Provides deterministic adjustment-need, evidence, endpoint, turnaround, occupancy, and protected-floor diagnostics. It is an evaluator, not a candidate-search loop; old trip-removal semantics must not authorize fixed-pilot trip changes. |
| `regime_headway_policy.py` | `REJECT_SEMANTIC_CONFLICT` | Derives service phases from analysis blocks/`required_trips_85`, assigns departures by those boundaries, and accepts balanced floor/ceil headway sequences. This conflicts with immutable DemandRegime vs mutable ServiceRegime and exact uniform headway. |
| `service_quality_metrics.py` | `PORT_SELECTED_LOGIC` | Solver-neutral recomputation is useful, but its `required_trips_85` shortage vector and global ordering cannot become the new Pareto authority. Reuse component metrics only. |
| `solver_orchestration.py` | `REUSE_WITH_ADAPTER` | Useful one-shot solver/independent-validator finalization boundary. It contains no feedback to planning; place it inside a future per-state evaluation adapter. |
| `two_stage_models.py` | `REUSE_WITH_ADAPTER` | Immutable dataclasses, fingerprints, truthful statuses, diagnostics, and final sentinel are reusable patterns. Rename/restructure contracts so DemandRegime evidence is not a ProposedServiceRegime decision. |
| `two_stage_allocator.py` Stage 1 allocation/model | `REJECT_SEMANTIC_CONFLICT` | Precommits exact trips to demand blocks, optimizes against `required_trips_85`, and builds regimes by repairing that allocation. This is explicitly retired by the V4 design and violates the new compiler boundary. |
| `two_stage_allocator.py` budget/diagnostic helpers | `PORT_SELECTED_LOGIC` | Bounded alternatives, deterministic tie keys, truthful `UNKNOWN`, and necessary-only feasibility discipline are useful implementation patterns. |
| `two_stage_solver.py` endpoint/B-domain/runtime constraints | `PORT_SELECTED_LOGIC` | Fixed endpoints, B +/-30, ordered source trips, exact runtime, shared budget, and independent validation are compatible when driven by a neutral ServicePlan. |
| `v3_global_regularity.py` tail-demand and Scenario-B transition predicates | `PORT_SELECTED_LOGIC` | Tail non-densification and transition-not-worse-than-B are still hard policy, but should become explicit pure compiler/validator rules. |
| `v3_global_regularity.py` proportional targets/bounded block phase | `REJECT_SEMANTIC_CONFLICT` | Passenger-proportional largest-remainder block targets and +/-1 block phase remain observation-block allocation semantics, not adaptive ServiceRegime search. |
| `v3_global_regularity.py` runtime install/uninstall monkeypatch stack | `REJECT_SEMANTIC_CONFLICT` | Global function replacement is not explicit authority injection and is unsuitable for fingerprinted closed-loop state evaluation. |
| PR #58 `SCENARIO_C_V4_ADAPTIVE_REGIME_DESIGN.md` | `REFERENCE_ONLY` | Correctly separates demand evidence from timetable structure and proposes bounded skeletons, but supplies no implementation and predates the strict clean-boundary/Pareto closed loop. |
| PR #58 `AGENTS.md` | `OBSOLETE` | The current workspace `AGENTS.md` is user-owned authority and must not be overwritten by a historical branch-local file. |
| PR #51 pilot runner/workflow | `OBSOLETE` | Calls legacy `SolverChoice.BOTH`, has no semantic tests, and uses temporary private URLs. Current V3/final-product runners are more authoritative. |

## 4. What the inspected components actually do

- `service_adjustment.py` evaluates whether demand and technical evidence justify an
  adjustment. It can test removals and feasibility evidence, but it does not generate
  a fixed-total service-plan frontier.
- `regime_headway_policy.py` derives contiguous demand phases from equal
  `required_trips_85` rates, maps solved departures into those phases, repairs
  singletons, merges groups, and accepts either exact uniformity or floor/ceil balanced
  rounding. It is a post-solve reconciliation policy, not DemandRegime inference.
- `service_quality_metrics.py` independently recomputes demand and service objective
  vectors. It is a metric calculator, not a Pareto archive.
- `solver_orchestration.py` validates one context, invokes one solver, independently
  validates its candidate, and finalizes one outcome. It never feeds validation
  failures back into planning.
- `two_stage_allocator.py` runs a bounded CP-SAT Stage 1 over exact analysis-block trip
  counts, excludes each returned solution to enumerate alternatives, then tries to
  construct representable regimes from those counts.
- `two_stage_models.py` provides V3 policies, allocation plans, proposed regimes,
  sentinels, diagnostics, run results, and fingerprints. It has no `ServicePlanState`
  or neighbor graph.
- `v3_global_regularity*.py` overlays passenger-proportional targets, regime-count
  control, bounded block phase, tail/transition constraints, and domain-aware necessary
  feasibility by monkeypatching the V3 stack for a runner invocation.

None of those components implements the newer DemandRegime/ServiceRegime separation
as a closed-loop mutable state search.

## 5. Historical semantic conflicts

Do not revive these behaviors as new architecture:

1. **Demand boundary equals service boundary.** V3 derives phases from analysis blocks
   and preallocates trips to those blocks. DemandRegime evidence must not dictate exact
   ServiceRegime boundaries.
2. **Endpoint-anchored `N-1` semantics.** `regime_headway_policy.py`, V3 representability,
   and PR #58 resource-envelope examples use span divided by the number of inter-trip
   gaps. That can be a diagnostic for a fixed endpoint sequence, but it cannot replace
   canonical half-open demand interval `duration / trip_count` semantics.
3. **Balanced 10/11-style rounding.** Historical balanced headway shapes allow two
   adjacent integer values inside one regime. New internal headway must be exactly
   uniform.
4. **Soft transition gaps.** V3 and the recovered compiler cap/minimize transition
   errors; neither enforces `gap == h_left or gap == h_right`.
5. **CP-SAT invents timetable structure.** PR #58 proposes having the exact solver
   choose transition gaps/boundaries directly. The new architecture requires an
   explicit ServicePlan state compiled and independently validated.
6. **Proportional block targets.** V3 global regularity uses passenger-proportional
   largest remainder targets. Passenger demand may score fit but cannot silently become
   an exact allocation authority.
7. **`required_trips_85` as an optimum.** Historical absolute error and planning
   shortage terms can pull service toward a target. It remains a service floor, not a
   surplus target.
8. **Fixed block/regime candidate assumptions.** Bounded top-N block allocations and
   merges toward a 16-regime cap do not constitute adaptive merge/split/boundary/trip
   neighbor search.
9. **Global scalar/lexicographic authority.** Historical weighted objective packing may
   support deterministic subsolves but must not replace the new Pareto frontier.
10. **Global monkeypatch authority.** Runtime function replacement obscures which
    policy evaluated a state and must be replaced by explicit injected collaborators.

## 6. V4/OR-Tools architecture versus a closed loop

| Capability | Historical evidence | Equivalent to future closed loop? |
| --- | --- | --- |
| State fingerprints | Policy, problem, allocation, result, and diagnostic fingerprints exist. | No ServicePlan state fingerprint. Adapt the serialization pattern. |
| Bounded candidate search | Stage 1 enumerates a bounded top-N set under a shared budget. | No; candidates are fixed block allocations, not plan neighbors. |
| Merge/split/shift operators | Adjacent block-derived groups merge; bounded phase can move one trip across a block boundary. | No explicit `MERGE_ADJACENT`, `SPLIT_REGIME`, `SHIFT_BOUNDARY`, `MOVE_ONE_TRIP`, `TAIL_ABSORB`, or `TAIL_RELEASE` operators. |
| Adaptive candidates | PR #58 describes skeleton windows and 3-8 candidates. | Design only; no code/tests. |
| Pareto/nondominance | Historical V4/V3 solver search uses packed scalar/lexicographic objectives. Recovery's final selector has a downstream Pareto filter only. | No live Pareto search/archive. |
| Solve budgets | Shared 120-second budget, remaining-time propagation, truthful exhaustion status. | Reusable budget primitive. |
| Deterministic tie-breaking | Stable identities, lexicographic weights, fingerprints, and deterministic result serialization. | Reusable primitive, not coordinator logic. |
| Validation feedback | Candidate validation occurs after a solve. | No; rejection never generates neighboring ServicePlans or recompiles them. |

Historical V4 is therefore not an implemented solver architecture. Historical V3 is
CP-SAT orchestration with post-solve validation, not the proposed closed-loop process.

## 7. Exact code worth porting later

1. Raw-adapter output should target `DemandObservationPeriodV1`,
   `DemandPeriodObservationV1`, `MultiPeriodDemandInputV1`, and the existing canonical
   fingerprint functions in `multi_period_demand.py`.
2. Reuse `v3_workbook.py` fail-closed numeric/date/catalog validation where the raw
   T06/T10 schema overlaps; do not require raw sources to masquerade as its aggregated
   sheets.
3. Port fixed first/last constraints from `two_stage_solver.py` and endpoint tests from
   `test_contract_v1_ortools_solver.py` / `test_contract_v1_two_stage_allocator.py` into
   the neutral compiler input and independent validator.
4. Port final-tail demand-rate comparison and Scenario-B maximum-transition derivation
   from `v3_global_regularity.py` as pure functions with explicit inputs.
5. Reuse fixed timetable runtime/layover/fleet validation from the recovery checkpoint,
   without moving departures or authorizing deadhead.
6. Reuse canonical hashing/finalization patterns from `two_stage_models.py` for a new
   immutable `ServicePlanState` payload.
7. Reuse shared deadline/remaining-time and truthful `UNKNOWN` semantics from
   `two_stage_allocator.py` / `two_stage_solver.py`.
8. Reuse independent metric recomputation from `service_quality_metrics.py`, after
   splitting component metrics from the old packed objective.
9. Reuse the final selector's exact Pareto dominance utility concept only after the
   live coordinator's dimensions and equivalence rules are reviewed.

## 8. Exact code that must not be revived

- `_derive_sustained_service_regimes`, `_balanced_headway_shape`, singleton repair, and
  maximal balanced merging in `regime_headway_policy.py` as compiler authority;
- `_build_allocation_model` and `_representable_regimes` in `two_stage_allocator.py` as
  the new C1/C2/C3 allocator;
- `_largest_remainder_targets`, proportional demand objective replacement, bounded
  block-phase membership, and install/uninstall monkeypatches in
  `v3_global_regularity.py` as closed-loop behavior;
- review-run wrappers in `run_v3_two_stage_phase_review*.py` as production architecture;
- PR #51's `run_fixed_resource_pilot.py` and private-URL workflow;
- PR #58's historical `AGENTS.md`;
- any balanced floor/ceil internal headway representation;
- any transition objective that permits a gap other than the left or right headway;
- any validator adaptation that suppresses a rejection without an explicit versioned
  policy in the ServicePlan state.

## 9. Minimum rebuild set

### RECOVERABLE_FROM_REMOTE

- multi-period demand contracts, aggregation, structural diagnostics, and fingerprints
  (already in recovery);
- aggregated V3 workbook reader and deterministic runner/export infrastructure
  (already in recovery, with newer local versions where applicable);
- fixed endpoint, B-domain, exact runtime, budget, status, and independent-validation
  patterns;
- tail-demand non-rising classifier, tail ceiling/non-densification, and B transition
  cap predicates;
- deterministic serialization/fingerprint/tie-breaking patterns;
- V4's conceptual evidence -> skeleton -> exact compile -> validate decomposition.

### ADAPT_FROM_REMOTE

- a raw T06/T10 adapter into the recovered neutral multi-period demand contracts;
- selected adjustment evidence as coordinator diagnostics, never trip-count authority;
- fixed endpoint constraints in the neutral compiler;
- service-quality component metrics into reviewed Pareto dimensions;
- solver orchestration into a per-state compile/validate evaluator;
- V3 tail and transition predicates into pure hard-rule validators;
- allocation/result fingerprint patterns into `ServicePlanState` identity;
- deadline and truthful exhaustion handling into a closed-loop search budget.

### MUST_REBUILD

- raw daily source reconciliation specific to T06/T10;
- immutable deterministic DemandRegime subsystem: exact-K frontier, leave-one-day-out
  CV, one-SE selection, and boundary stability;
- deterministic named C1/C2/C3 allocation frontier with `required_trips_85` only as a
  floor;
- mutable ServiceRegime/ServicePlan model distinct from DemandRegime evidence;
- fixed-endpoint clean-boundary compiler with hard `gap in {h_left, h_right}`;
- effective operational spans, residual tail settlement, backward fixed-last compile,
  and tail eligibility/debt capacity;
- explicit neighbor operators and deterministic neighbor generation;
- live Pareto archive/nondominance, equivalence, state fingerprints, and bounded search;
- validation-feedback-to-planning loop and `SEARCH_BUDGET_EXHAUSTED` semantics;
- coordinator integration tests and real MST6 product acceptance.

The future Closed-Loop ServicePlan Coordinator cannot be built mostly from existing V4
pieces. Supporting contracts and constraints are recoverable, but the coordinator's
state model, operators, live Pareto frontier, feedback loop, and tail-aware compiler are
genuinely new.

## 10. Recommended integration order

1. Build and verify the raw T06/T10 daily adapter into existing demand contracts.
2. Build immutable DemandRegime exact-K/CV/stability evidence and freeze fingerprints.
3. Build the C1/C2/C3 allocation frontier without exact timetable invention.
4. Extend neutral compiler input with fixed first/last authority.
5. Implement strict clean-boundary compilation and independent validation.
6. Add effective-span/backward-tail settlement and debt-capacity rules.
7. Define immutable `ServicePlanState`, fingerprints, and explicit neighbor operators.
8. Add per-state compile -> fixed-timetable fleet validate -> service validate feedback.
9. Add bounded live Pareto search, deterministic tie-breaking, and budget exhaustion.
10. Integrate final selection/export, then run real MST6 acceptance before MST10.

No Closed-Loop ServicePlan Coordinator implementation belongs in this audit branch.

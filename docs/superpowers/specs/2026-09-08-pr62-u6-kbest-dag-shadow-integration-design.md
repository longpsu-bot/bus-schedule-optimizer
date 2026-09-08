# PR62-U6 k-best DAG shadow production integration design

## Decision and authority

PR62-U6 is the first production-oriented integration of the validated U5 exact
k-best layered-DAG architecture. It is a shadow integration only. The DAG backend
does not become authoritative, the legacy compiler remains available and unchanged,
existing application defaults remain unchanged, and U6 does not export or select a
new production timetable.

The branch starts directly from the authoritative PR #62 head
`59b892d3b367182b20734ad4e4405e264ba14024`. The U2-U5 experiment commits are not
ancestors of the production integration branch and will not be cherry-picked. The
only later authority imported by design is evidence and production-worthy behavior
that survives the port audit.

The U5 authorities are:

- design: `fc779e61186f38dc40066668ea20d2437687a6ac`;
- implementation: `0b51d07735a767eb1c7cba2fad899f007a6543cc`;
- evidence: `f689111357b2cf465e1d96e093a5ad9e0c3f61b3`;
- frozen family manifest:
  `465c0800be66ce991af017ecea6dc87cdd4db7342d8ac9adb30ba1b5678fa905`.

The historical classifications remain unchanged:

- production PR62-U:
  `ROUTE10_LOCAL_REFINEMENT_OPERATIONALLY_INTRACTABLE`, with Route 10 global
  executions `1` and Route 6 global executions `0`, and all four historical
  production-Q stages `UNADJUDICATED`;
- U2: `CP_SAT_LOCAL_REALIZATION_POC_NO_GO`;
- U3: `U3_EXACT_SHELL_EXHAUSTED_TOO_NARROW`;
- U4: `U4_IMPLEMENTATION_ERROR`;
- U5: `U5_EXACT_KBEST_DAG_FRONTIER_VALIDATED`.

U6 must never rewrite those historical records.

## Clean port and port audit

Before production implementation, the diff from `59b892d3` to U5 implementation
commit `0b51d077` is audited hunk by hunk in
`docs/engine/evidence/PR62_U6_KBEST_PORT_AUDIT.md`. Each U5 implementation hunk is
classified as exactly one of:

- `A. K_BEST_DAG_CORE`;
- `B. EXPERIMENT_ONLY`;
- `C. TEST_OR_EVIDENCE_ONLY`;
- `D. DEPENDS_ON_POST_59B_LOCAL_CHANGES`.

Only A behavior may be ported directly. An A hunk that depends on D is re-expressed
through the smallest production-safe equivalent and the dependency is recorded in
the audit. No U2 CP-SAT infrastructure, U3 exact-shell code, U4 tier-successor code,
experiment runner, experiment watchdog, recovery/checkpoint framework, historical-Q
certification rule, or unrelated U0 optimization is imported.

The audit treats the U5 experiment modules as read-only algorithmic evidence. It
separates the reusable layered-domain construction and k-best DP behavior from their
experiment-only dataclasses, artifact writers, subprocess controls, and imports from
U2/U3. The production implementation has no import from `experiments/` and makes no
OR-Tools or CP-SAT call.

The base `59b892d3` local state generator lacks the later validated endpoint
preflight. U6 ports only the narrow invariant that fixed first and last departures
must fall inside the first and final half-open planning regimes. It is introduced
with RED-to-GREEN tests and runs before DAG construction. Later checkpoint/recovery
hooks and other post-59b local-rhythm changes are excluded.

## Production module boundary and API

The exact graph compiler is isolated in
`src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py`. It exposes this
versioned entry point:

```python
def compile_service_plan_family_kbest_v1(
    *,
    states: Sequence[ServicePlanStateV1],
    endpoint_authority: OperationalEndpointAuthorityV1,
    raw_limit: int = 256,
) -> KBestDagFrontierV1:
    ...
```

`states` is one local-family state set for one route and direction. The API accepts
arbitrary caller order and internally freezes the state order as:

```python
ordered_states = tuple(sorted(states, key=service_plan_fingerprint_v1))
```

State indices, graph manifests, source edges, and tie identities use this internal
order. Input validation requires a non-empty sequence, rejects duplicate ServicePlan
fingerprints, and requires every state's route, direction, fixed endpoints, total
trips, and endpoint authority to agree. Caller order is technical input presentation,
not transport authority. The production function accepts `raw_limit` only in the
inclusive range `1..256`; canonical U6 runs always use `256`.

The frozen return contracts are immutable, slotted dataclasses:

```python
@dataclass(frozen=True, slots=True)
class KBestDagCandidateV1:
    state: ServicePlanStateV1
    state_fingerprint: str
    compilation: CleanBoundaryCompilationV1
    compilation_fingerprint: str
    compiler_objective: tuple[Fraction, int, int]
    exact_scaled_quantization: int
    path_score: tuple[int, int, int, tuple[int, ...], tuple[int, ...]]
    phase_indices: tuple[int, ...]
    headway_vector: tuple[int, ...]
    departure_vector: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class KBestDagGraphStatisticsV1:
    state_count: int
    layer_count: int
    node_count: int
    legal_transition_edge_count: int
    source_edge_count: int
    sink_edge_count: int
    reachability_trimmed_node_count: int
    retained_partial_path_count: int
    truncated_node_count: int
    duplicate_departure_path_count: int


@dataclass(frozen=True, slots=True)
class KBestDagTelemetryV1:
    graph_construction_seconds: float
    dynamic_programming_seconds: float
    final_merge_seconds: float
    decoding_seconds: float
    total_seconds: float


@dataclass(frozen=True, slots=True)
class KBestDagFrontierV1:
    candidates: tuple[KBestDagCandidateV1, ...]
    ordered_fingerprints: tuple[str, ...]
    requested_raw_limit: int
    natural_exhaustion: bool
    graph_statistics: KBestDagGraphStatisticsV1
    telemetry: KBestDagTelemetryV1
```

Timings are observable telemetry but are excluded from deterministic candidate and
evidence hashes. The return type contains no solver status, Q observation, experiment
path, subprocess, checkpoint, or artifact-runner field.

The new module reuses the unchanged clean compiler's phase-candidate, bounded-phase,
compilation-decoding, fingerprint, and structural-validation behavior read-only.
Because those operations are private in `59b892d3`, the port audit records the exact
symbols and production authority hashes. U6 does not modify
`clean_boundary_compiler.py` or `clean_compile_frontier.py` merely to publish new
wrappers.

## Layered-DAG semantics

One API invocation represents one local family. Every ServicePlan state contributes
one state branch between a conceptual super-source and super-sink. Within a state:

- each planning regime is one graph layer;
- every existing legal bounded phase candidate is a node;
- clean-boundary compatibility is a directed edge between adjacent layers;
- the super-source reaches every legal first-layer node;
- every reachable final-layer node reaches the super-sink;
- forward/backward reachability removes only nodes outside all complete legal paths.

The clean-boundary transition rule preserves U5's validated left-owned,
right-owned, and equal-headway merge semantics. No candidate is removed by a scalar
objective, diversity rule, Q identity, protection rule, or downstream V3 property
during graph construction.

Each partial path stores additive exact values and its exact canonical key:

```text
(
  exact_scaled_quantization,
  actual_service_regime_count,
  phase_imbalance,
  headway_vector,
  departure_vector,
)
```

Quantization uses exact `Fraction` arithmetic and an exact integer scale inferred
from candidate denominators or proven equal to the frozen `75600` scale in the U5
parity fixture. A scaled value with a non-unit denominator fails closed. No float or
arbitrary scalar score participates in path ordering. Heap merges include explicit
source and item indices after the canonical key so Python object comparison can never
become a tie breaker. Exact departure vectors are the path identity used for
deduplication.

### Top-K correctness argument

For the first layer, the one-node paths reaching each node are trivially the best
partial paths for that node. Inductively, suppose every predecessor retains its exact
best K partial paths in canonical order. Appending one fixed successor node adds the
same node contribution and transition contribution to every prefix from a given
predecessor, so it preserves that predecessor list's order. A deterministic k-way
merge of all predecessor lists therefore yields exactly the globally ordered partial
paths reaching the successor; retaining its first K is exact.

All extensions after a node share the same future feasibility structure. If a prefix
is ranked below K at that node, at least K better prefixes reach the same node and can
receive every suffix available to the lower prefix. The lower prefix therefore cannot
enter the global top K complete paths. Applying the same exact merge to all terminal
node lists and all state branches yields the exact global top K. If no node merge and
no terminal merge truncates, returning fewer than K proves natural exhaustion.

## Explicit shadow orchestration

Shadow integration lives in
`src/bus_schedule_engine/kbest_shadow_refinement.py`. Its only route-level entry point
is explicit:

```python
def run_kbest_dag_shadow_from_completed_result_v1(
    *,
    base_coordinator_result: RouteCoordinatorResultV1,
    context: RouteCoordinatorContextV1,
    coordinator_budget: CoordinatorSearchBudgetV1,
    directional_frontier_limit: int = 32,
) -> KBestDagShadowResultV1:
    ...
```

The function has no seed argument and no path to `search_route_service_plans_v1`.
It consumes an already completed global result, and its telemetry always records zero
global executions. The existing
`search_route_service_plans_with_local_rhythm_refinement_v1` entry point and all app,
Streamlit, export, and pilot defaults remain unchanged. No existing production entry
point imports or calls the new shadow driver.

The orchestrator reuses unchanged 59b authorities for local-family detection,
actual-family-to-planning-index mapping, radius-3 state generation, strict directional
canonicalization, exact pair evaluation, exact fleet validation, strict rhythm
progress, 10-dimensional Pareto update, and V3 selection. The local domain remains
boundary-step radius 3, trip-transfer radius 3, and one external side at a time.

The expensive realization stage alone changes conceptually:

```text
59b legacy local flow:
  every generated state -> one full legacy compiler invocation

U6 shadow flow:
  every state for one detected family -> one exact multi-state DAG invocation
```

## Directional hard eligibility before diversity

Every raw DAG candidate passes the following ordered pipeline:

1. `validate_clean_boundary_compilation_v1` structural validation;
2. fixed endpoint authority and fixed trip-total checks;
3. `validate_closed_loop_service_protection_v1` using translated authority;
4. `evaluate_actual_service_v1`, including all retained-candidate metrics;
5. the existing `metrics.tail_ordering.eligible` contract.

Failure at any step removes the candidate before diversity. Structural contract
mismatch fails closed instead of being recorded as an ordinary operational reject.
SSE/TE demand fit, Scenario-B max access, rhythm simplicity, and fleet efficiency
remain downstream ranking or reporting inputs and never become directional hard
constraints.

For one source pair and direction, eligible candidates from all detected-family DAG
frontiers are unioned with the already hard-valid source directional candidate and
deduplicated by compilation fingerprint. The unchanged 59b deterministic diversity
semantics are then applied once to the aggregate directional pool:

- preserve the compiler-quality anchor;
- preserve headway shapes;
- fill by exact-departure max-min distance;
- resolve ties by existing exact deterministic ordering.

Within one family DAG, `exact_scaled_quantization` participates in exact path ordering
under that DAG's proven denominator scale. It is never compared across separately
scaled family DAGs. Cross-family duplicate identity remains the compilation
fingerprint. After fingerprint deduplication, cross-family quality-anchor selection and
diversity ordering use the existing compiler objective
`(Fraction quantization, actual service regime count, phase imbalance)`, followed by
the existing headway-vector and departure-vector tie fields. Thus independently
inferred integer scales remain telemetry/proof fields local to their DAG and cannot
create cross-family quality authority.

The source candidate is eligible for a retained slot so one-direction changes remain
representable. If the eligible aggregate contains at most the configured cap, all are
retained. The canonical cap is 32 and is named the `TECHNICAL_SHADOW_FRONTIER_LIMIT`;
it is not production transport policy. The implementation first measures the 59b
selector on pools no larger than 256. If it is not operationally adequate, U6 stops
and reports measurements before any U0 optimization is considered.

## Pair, fleet, Pareto, and V3 integration

After each direction has at most 32 retained candidates, the driver evaluates their
complete ordered cross-product, with a maximum of `32 * 32 = 1024` combinations per
source pair. Every combination uses the existing `evaluate_operating_pair_v1`, which
includes exact fleet validation. A fleet rejection cannot enter the Pareto updater.

Duplicate pair fingerprints are suppressed by the existing pair identity. A
fleet-valid generated pair may continue only when this existing tuple strictly
lexicographically improves over its source pair:

```text
(
  total_directional_sustained_headway_level_count,
  actual_service_regime_count,
  total_directional_effective_palette_count,
  total_single_gap_regime_count,
)
```

Equal tuples do not progress. Strictly improving pairs pass to the unchanged
`update_operating_pair_pareto_v1` with the frozen 10-dimensional dominance semantics.
The driver never introduces a scalar pair score.

Selection uses unchanged
`legacy_calibrated_continuous_exposure_operational_selector_v3` behavior and hierarchy:

1. hard operational feasibility;
2. Scenario-B max-access non-regression;
3. common SSE/TE demand-fit anchor;
4. legacy one-trip TE semantic calibration;
5. route-local continuous-exposure materiality envelope;
6. rhythm simplicity;
7. fleet efficiency;
8. fingerprint tie.

No V3 weight, bound, order, or materiality rule changes in U6.

## Source/family worklist semantics

The initial worklist is the base V3 materiality source set sorted by pair fingerprint.
The driver keeps a processed-source fingerprint set; a semantic source pair is
processed at most once. Processing records every detected family, mapped planning
indices, generated state manifest, DAG graph/raw hashes, eligibility decisions,
retained directional hashes, pair decisions, Pareto evolution, V3 result, and timing.

When processing a source admits strict descendants, parent fingerprints and before/
after rhythm tuples are recorded. After the Pareto update, V3 is rerun unchanged. A
new materiality fingerprint may enter the sorted worklist only if it names an admitted
generated descendant whose recorded tuple strictly improves over its parent. Initial
base sources do not require a generated parent. Already processed or already queued
fingerprints are ignored. These rules provide finite source-once, no-equal-progress
termination without checkpoint or recovery infrastructure.

Telemetry includes source pairs processed, families processed, DAG graphs built, raw
paths produced, structural/protection/tail rejects, hard-eligible paths, retained
directional candidates, pair cross-products, fleet rejects, strict-progress rejects,
duplicate pairs, and Pareto admissions.

## U5 frozen-family parity gate

Before any route-level run, the production port loads a focused test fixture derived
from the committed U5 evidence without importing or running experiment code. The
fixture lives under `tests/fixtures/pr62_u6/`, contains only the frozen 49 input
states, endpoint authority, and expected semantic hashes needed for parity, and is
classified as test/evidence material rather than production runtime data. It is bound
to manifest
`465c0800be66ce991af017ecea6dc87cdd4db7342d8ac9adb30ba1b5678fa905`.
The production API must reproduce:

- top-1 fingerprint:
  `8e06dbcafc0194e5d338bc96b28569825bff30a79f96eaec8b5eda3c778ca7f6`;
- top objective `(8214, 7, 74)`;
- first distinct objective tiers `(8214, 7, 74)`, `(9264, 7, 51)`, and
  `(10734, 7, 58)`;
- raw top-256 SHA:
  `71092c883923e6d5460980a8c528f263a275255986e887bb03c3c1ef16c17601`.

Parity tests run without importing OR-Tools. Any mismatch classifies
`U6_PRODUCTION_PORT_DIVERGED_FROM_U5` and stops before Route 10.

## Deterministic replay and cap sensitivity

Canonical payloads use sorted keys, compact separators, UTF-8, and LF, and exclude
wall-clock timings. Candidate, eligible, retained, pair, Pareto, and selection hashes
are computed from explicit semantic fields rather than dataclass reprs or filesystem
paths.

Route 10 and Route 6 each require two fresh-process shadow local-stage runs with empty
process caches. Their processed source order, raw DAG hashes, eligible hashes,
retained hashes, pair fingerprints, final Pareto hash, and final V3 selection must be
identical. A Route 10 mismatch classifies
`U6_ROUTE10_SHADOW_NONDETERMINISTIC` and stops.

The 16, 32, and 64 sensitivity cases are complete independent shadow-local runs from
the same completed global result. Each case owns its source/materiality worklist,
Pareto evolution, and V3 history. A larger cap may admit a different pair, expose a
new materiality descendant, and therefore create a source/family DAG that no smaller
cap encounters; every such cap-specific descendant is processed normally.

DAG and hard-eligibility results may be content-addressed and reused across
sensitivity cases only when the semantic input key is identical. The key binds at
least the source-pair fingerprint, direction, family identity, sorted planning-state
manifest and fingerprints, endpoint authority, hard-eligibility context authorities,
raw limit `256`, and U6 implementation authority. Cache values contain only frozen
raw/eligible semantics and hashes, never cap-specific retention, pair, Pareto,
worklist, or V3 state. Reuse is an execution optimization, not a way to suppress a
cap-specific graph. Fresh-process determinism repeats start with empty caches so cache
hits cannot mask generation nondeterminism.

The cap-32 and cap-64 final Pareto frontiers are adjudicated by first deduplicating
their union by pair fingerprint in fingerprint order, then rebuilding the exact
combined nondominated frontier through unchanged
`update_operating_pair_pareto_v1` with `limit=None`. Running the unchanged V3 selector
directly on the unnormalized union is prohibited. V3 receives only this normalized
10-dimensional Pareto frontier. The cap is binding iff normalized-union V3 selects a
candidate available only through the complete cap-64 run instead of the cap-32 final
selection. That condition classifies `U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING` and
stops before Route 6. A cap-16 difference is diagnostic only.

## Route 10 saved-global continuation

Route 10 consumes only the preserved completed global coordinator result. Its input
loader verifies canonical saved-global SHA
`d2ba609ffd8fa4450e0a0662a0c9255dcdf1d8d2b759e63a8de6cf44fbfb114b`
before deserialization and reconstruction. Reconstruction must yield:

- base Pareto count 11;
- access-safe count 7;
- base V3 selection
  `6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16`;
- a materiality source set containing
  `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`.

The shadow API is instrumented so the Route 10 global coordinator call count is
provably zero. The run records initial Pareto, every work item and family, all raw and
filtered frontiers, every fleet-valid pair, Pareto and V3 histories, and strict-rhythm
continuations. Historical Q absence is never a stop condition.

Per-family generation is reported as family generation, graph construction, DAG DP,
and decoding; target is at most 30 seconds and hard ceiling is 60 seconds. The full
Route 10 local stage separately reports hard eligibility, diversity, pair/fleet,
Pareto/V3, and total; target is at most 120 seconds and hard ceiling is 300 seconds.
Crossing 300 seconds classifies `U6_ROUTE10_SHADOW_OPERATIONALLY_INTRACTABLE` and
stops before Route 6.

Passing every Route 10 structural, feasibility, authority, determinism, sensitivity,
termination, and performance gate classifies `ROUTE10_KBEST_DAG_SHADOW_VALIDATED`.

## Route 6 control

Route 6 starts at global execution count zero. Only after Route 10 is validated may
the U6 evidence runner bind all Route 6 canonical inputs and execute the production
global coordinator exactly once with the unchanged budget `24 / 512 / 4 / 24 / 512`.
The completed result is saved and hash-bound before the shadow local stage. Any base
mismatch classifies `U6_ROUTE6_GLOBAL_BASE_MISMATCH`; the global search is never
rerun during U6.

The base and final control selection must both be
`ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`.
The Route 6 shadow flow uses the same cap-32 canonical path and reused-pool cap-64
sensitivity. A changed final selection classifies
`ROUTE6_CONTROL_CHANGED_UNDER_KBEST_DAG_SHADOW` without rationalization.

The deterministic repeat reloads the saved completed Route 6 result and consumes no
second global execution. It must match source processing, DAG outputs, eligibility,
retention, pair frontier, final Pareto, and final V3.

## Historical Q policy

Historical Q
`12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5`
is `HISTORICAL_REFERENCE_ONLY` in U6. Its fingerprint is not accepted by any family,
graph, scoring, ordering, eligibility, diversity, pairing, Pareto, or V3 API. Tests
inject or remove the value and require identical pre-freeze semantic hashes. Only
after Route 10 and Route 6 canonical outputs are frozen may the evidence renderer
report whether Q occurred in raw, eligible, retained, pair, or final sets. Presence or
absence cannot affect classification.

## Tests and validation order

All production behavior follows RED-GREEN-REFACTOR. The required test groups are:

- one-layer and two-layer left/right-owned exact graph cases;
- illegal-boundary exclusion and exhaustive fixed-seed small-DAG parity;
- exact canonical score/tie ordering, departure deduplication, repeatability, and
  raw-limit validation;
- U5 top-1, first-three-tier, and raw-SHA parity without OR-Tools;
- endpoint-invalid state exclusion before DAG construction;
- structural, protection, and tail rejection before diversity;
- retain-all at most 32, deterministic diversity above 32, and no ineligible slot;
- eligible-only pair cross-product and fleet-reject exclusion from Pareto;
- unchanged Pareto and unchanged V3 authority locks;
- strict-only rhythm continuation, no equal re-enqueue, sorted source-once handling;
- completed-result zero-global-call enforcement;
- cap-binding and Route 6 control-change detectors;
- Q pre-freeze noninterference.

Bounded reference-backend parity covers synthetic one/two-regime ServicePlans, fixed
endpoints, clean-boundary ownership, saved legacy fingerprints, and the U5 family.
The 175-call pathological legacy local replay is prohibited.

Before Route 10, validation runs all new tests, U5 parity, relevant local-rhythm,
compiler structural, protection, tail, fleet, Pareto, and V3 tests, Ruff check, Ruff
format check, Python compilation, `git diff --check`, and a production-authority diff
audit. The historical broad-suite baseline includes platform-sensitive evidence and
private-artifact tests; U6 records those pre-existing exclusions separately and does
not mask new failures.

Before Route 6, every Route 10 canonical, repeat, cap-sensitivity, and runtime gate
must pass. Final closeout runs the broad approved regression suite. Evidence JSON and
Markdown are rendered twice and required to be byte-identical.

## Evidence and production authority audit

The canonical evidence files are:

- `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json`;
- `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md`.

They contain the requested PORT, ROUTE 10, ROUTE 6, Q, and READINESS sections,
including production file hashes, all input and output authorities, counts, ordered
hashes, decisions, histories, timings, classifications, and deterministic-repeat
comparisons.

The authority diff audit compares the final branch against `59b892d3` and requires:

- no diff in `clean_boundary_compiler.py`;
- no diff in `clean_compile_frontier.py`;
- no diff in demand detection, global coordinator, fleet solver, Pareto updater, V3
  selector, Streamlit defaults, or exported production timetables;
- no OR-Tools dependency added and no CP-SAT import or call in U6 modules;
- no experiment import from production code;
- new production calls reachable only through the explicit shadow API.

If integration appears to require changing any protected authority, U6 stops for
review before that file is modified and records
`U6_UNEXPECTED_PRODUCTION_AUTHORITY_CHANGE` or a more specific fail-closed label.

## Completion and readiness

`U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION_VALIDATED` requires every requested port,
U5 parity, Route 10, Route 6 control, deterministic replay, hard validity, exact-fleet,
unchanged Pareto/V3, performance, Q-independence, and authority-isolation gate.

Even on success, evidence records:

```text
DAG shadow backend authoritative = false
legacy backend removed = false
production default changed = false
READY_FOR_FINAL_PILOT_USE = false
READY_FOR_PR62_COMPLETION_REVIEW = false
```

U6 ends with local reviewable commits only. It does not push, merge, update PR #62,
amend U2-U5 commits, or switch authority.

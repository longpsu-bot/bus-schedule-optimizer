# Contract V1 Adjustment Decision Orchestration and Capability Routing Boundary

**Status:** Proposed implementation design

**Design ID:** `V1-D2`

**Baseline:** `main@cb4cad2fa7cf6b9e31359715d7fb471dd1802fa5`

**Applies to:** the boundary between authoritative Scenario B evaluation,
quantitative service-adjustment assessment, capability routing, optional
canonical problem construction, optional solver invocation, independent
candidate validation, and outcome construction

**Does not implement:** orchestration, new Python contracts, schema changes,
tests, application/runtime integration, UI, diagrams, XLSX, workbook changes,
legacy algorithm changes, OR-Tools, V1-A1 / Contract `1.1.0`, or production
solver selection

This design resolves the ordering inversion left after V1-H4 and V1-D1:
`evaluate_service_adjustment_need_v1()` currently accepts
`ScheduleGenerationContextV1`, but that aggregate already contains a
`ScheduleProblemV1`. The system can therefore construct a solver problem and
adapter compatibility context before deciding whether any solver problem is
authorized.

The target authoritative flow is:

```text
Normalized Contract V1 inputs
-> authoritative Scenario B evaluation
-> pre-problem evaluation context
-> quantitative service-adjustment assessment
-> capability routing
-> optional authorized-problem request
-> optional ScheduleProblemV1 construction
-> optional solver invocation
-> independent solution validation
-> adjustment orchestration outcome
```

Optimization MUST NOT begin, and a canonical problem MUST NOT be built, merely
because an adapter can generate an alternative timetable.

## 1. Governing authority

V1-D2 preserves and composes the approved authority of:

- V1-H1 solver-boundary integrity and sanitized exception handling;
- V1-H2 exact source-trip runtime and arrival-terminal turnaround;
- V1-H3 temporal and directional demand-coverage authority;
- V1-H4 canonical `ScheduleProblemV1`, adapter-context fingerprinting,
  independent problem validation, and solution validation;
- V1-D1 ordered quantitative adjustment gates and exactly one primary
  `ServiceAdjustmentDecisionV1`.

V1-D2 does not weaken or reinterpret any of those rules. It changes the target
ordering and ownership of responsibilities.

Normative principles:

1. Adjustment necessity is decided from authoritative pre-problem facts.
2. Capability routing interprets the decision but cannot change it.
3. Problem construction is an authorized consequence, never an input to the
   decision.
4. Adapter compatibility data can affect candidate generation and problem
   identity, but cannot affect whether adjustment is needed.
5. Unsupported or no-generation decisions remain explicit upstream decisions;
   they are not disguised as solver results.
6. Every transition is fingerprint-bound and fails closed on disagreement.
7. Scenario B, normalized inputs, evaluation evidence, policies, assessments,
   and routing results are immutable.

## 2. Current baseline and exact inversion

At the required baseline, the actual additive Contract V1 sequence is:

1. A caller constructs `NormalizedInputBundleV1`.
2. A caller invokes `evaluate_scenario_b_v1()`.
3. For the heuristic path,
   `build_heuristic_schedule_request_v1()` constructs
   `HeuristicCompatibilityContextV1`.
4. The same helper calls `build_schedule_problem_v1()`.
5. `build_schedule_problem_v1()` recomputes and reconciles the authoritative B
   evaluation, derives operating locks, constructs `ScheduleProblemV1`,
   calculates its fingerprint and ID, and validates it.
6. The helper calls `build_schedule_generation_context_v1()`, which recomputes
   and reconciles the evaluation again and validates the problem, inputs,
   evaluation, policy, blocks, requirements, locks, and fingerprints together.
7. Only after those steps can
   `evaluate_service_adjustment_need_v1(ScheduleGenerationContextV1)` be
   invoked.
8. Separately, `run_schedule_solver_v1()` validates the generation context,
   applies existing B-disposition and H3 no-run gates, invokes the selected
   solver, sanitizes exceptions, validates any candidate independently, and
   constructs `ScheduleGenerationOutcomeV1`.

The construction sites are:

- `ScheduleProblemV1`:
  `contracts_v1/solver_problem.py::build_schedule_problem_v1()`;
- `ScheduleGenerationContextV1`:
  `contracts_v1/solver_problem.py::build_schedule_generation_context_v1()`;
- heuristic composition of both:
  `contracts_v1/solver_adapter.py::build_heuristic_schedule_request_v1()`.

V1-D1 is publicly callable through
`contracts_v1/public_api.py::evaluate_service_adjustment_need_v1()`, which
delegates to `contracts_v1/service_adjustment.py`. Its required input is the
already-built `ScheduleGenerationContextV1`. At this baseline, its in-repository
callers are tests rather than an integrated production orchestration path.

The dependency inversion has four concrete forms:

1. `ServiceAdjustmentAssessmentV1.source_problem_fingerprint` makes a problem
   identity part of a decision that should precede the problem.
2. The evaluator reads solver adapter and operating-mode fields from
   `context.problem`.
3. The evaluator currently calculates `heuristic_authorized` and
   `authorized_generation_action`, mixing capability routing into the
   quantitative decision service.
4. The heuristic request helper builds adapter compatibility state and the
   canonical problem before the assessment exists.

The target design removes all four forms without modifying
`ScheduleGenerationContextV1` or `ScheduleProblemV1` in this documentation
task.

## 3. Required responsibility split

The target boundary has six distinct responsibilities.

### 3.1 Authoritative Scenario B evaluation

The existing authoritative evaluator remains responsible for deriving:

- normalized input validity and parameter consistency;
- H2 runtime, turnaround, and fleet evidence;
- H3 demand resolution, coverage, and directional support;
- authoritative A/B block-supply evidence;
- Scenario B evaluation dimensions and `BDisposition`;
- an evaluation fingerprint under the effective evaluation policy.

This step is pure and precedes adjustment assessment. A caller-supplied
evaluation remains only a cache candidate under H1. A builder MUST recompute it
or reconcile it exactly with a deterministically cached authoritative result.

### 3.2 Service-adjustment evaluation context

A new pre-problem immutable aggregate carries only the authority needed by
V1-D1. It contains no problem, adapter state, or solver authorization.

### 3.3 Service-adjustment need evaluator

The evaluator consumes the pre-problem aggregate and returns exactly one
primary decision with quantitative evidence. It does not route, build, mutate,
or generate.

### 3.4 Capability router

A separate pure router maps the exact assessment to a required capability and
records whether a currently configured solver capability may be used. It does
not generate a timetable or independently reassess demand.

### 3.5 Authorized problem factory

The problem factory accepts an explicit authorization request produced after
routing. It builds a canonical problem only for a supported, authorized
fixed-resource action. It validates identities and locks but does not
reinterpret the adjustment decision.

### 3.6 Solver orchestration and independent validation

Solver orchestration consumes an already-authorized problem, its exact route,
and a solver whose adapter-owned context matches the problem by fingerprint.
Independent validation remains the final authority for accepting Scenario C.

## 4. Canonical pre-problem input

### 4.1 Decision

V1-D2 requires a new immutable typed aggregate named:

`ServiceAdjustmentEvaluationContextV1`

This is the canonical evaluator input. It is preferred over either:

- a loose multi-argument evaluator signature; or
- a projection that continues to be owned by
  `ScheduleGenerationContextV1`.

A dedicated aggregate provides one validated cache identity, makes the
pre-problem boundary visible in type signatures, prevents callers from
omitting provenance fields, and can be constructed without selecting an
adapter.

### 4.2 Recommended fields

The recommended internal typed contract is:

```text
ServiceAdjustmentEvaluationContextV1
    normalized_inputs: NormalizedInputBundleV1
    b_evaluation: ScenarioBEvaluationBundleV1
    b_evaluation_policy: ScenarioBEvaluationPolicyV1
    adjustment_policy: ServiceAdjustmentPolicyV1
    repeatability_evidence: RepeatabilityEvidenceV1 | null
    normalized_bundle_fingerprint: str
    source_a_fingerprint: str | null
    source_b_fingerprint: str
    observed_demand_fingerprint: str | null
    b_evaluation_policy_fingerprint: str
    authoritative_b_evaluation_fingerprint: str
    adjustment_policy_fingerprint: str
    repeatability_evidence_fingerprint: str | null
    context_fingerprint: str
```

Field semantics:

- `normalized_inputs` is the immutable normalized A/B/demand authority.
- `b_evaluation` is the recomputed or exactly reconciled authoritative
  Scenario B evaluation.
- `b_evaluation_policy` is the policy under which `b_evaluation` was derived.
- `adjustment_policy` contains quantitative V1-D1 thresholds only. Solver
  adapter selection and decision-to-adapter mapping MUST move out of this
  policy during migration.
- `repeatability_evidence` is optional because only reduction needs it. When
  present it is immutable and fingerprinted as part of the context; callers
  cannot attach it after assessment.
- `normalized_bundle_fingerprint` binds the exact normalized A/B/demand
  bundle, including its source fingerprints.
- explicit source fingerprints are redundant validation anchors. They MUST
  equal the fingerprints carried by or recomputed from `normalized_inputs`.
- `b_evaluation_policy_fingerprint` identifies the complete effective B
  evaluation policy.
- `authoritative_b_evaluation_fingerprint` is the existing H1/H3 evaluation
  fingerprint and MUST bind the bundle and B evaluation policy.
- `adjustment_policy_fingerprint` identifies all V1-D1 decision thresholds.
- `repeatability_evidence_fingerprint` identifies every day and provenance
  value used for reduction, when present.
- `context_fingerprint` binds all preceding context identities using a new
  stable internal fingerprint profile.

The context does not duplicate H3 block or fleet evidence into new mutable
collections. That evidence remains reachable through the immutable
`b_evaluation`:

- H3 coverage through the authoritative demand-resolution coverage
  assessment;
- block-supply evidence through authoritative A/B block rows;
- runtime and turnaround through normalized exact timetable facts and
  evaluation evidence;
- fleet and continuous stock through the authoritative fleet assessment.

### 4.3 Required exclusions

`ServiceAdjustmentEvaluationContextV1` MUST NOT contain:

- `ScheduleProblemV1`;
- `ScheduleGenerationContextV1`;
- `HeuristicCompatibilityContextV1`;
- a solver adapter object or adapter-context fingerprint;
- an already-authorized solver action;
- `ScenarioCConfig`;
- raw legacy workbook objects;
- legacy `ScenarioParameters`, `Trip`, or `DemandRecord` objects;
- Scenario C, a candidate, solution, or generation outcome;
- UI/application services or mutable application state.

### 4.4 Context construction and validation

`build_service_adjustment_evaluation_context_v1()` MUST:

1. validate normalized inputs;
2. recompute Scenario B evaluation using the effective B evaluation policy, or
   validate a deterministic cached evaluation by exact fingerprint equality;
3. recompute A, B, and demand source fingerprints;
4. validate H3 coverage evidence and preserve all limitations;
5. validate adjustment-policy compatibility with B-evaluation ceilings and
   confidence authority;
6. validate and fingerprint optional repeatability evidence;
7. calculate the context fingerprint;
8. return a frozen aggregate.

Any mismatch fails closed with no context. Context construction does not build
adapter state or a solver problem.

## 5. ServiceAdjustmentNeedEvaluator boundary

### 5.1 Canonical signature

The target public signature is:

```text
evaluate_service_adjustment_need_v1(
    context: ServiceAdjustmentEvaluationContextV1,
) -> ServiceAdjustmentAssessmentV1
```

All effective policies and optional repeatability evidence are already bound
into the context. This gives the evaluator one authoritative input identity.

The evaluator remains:

- pure;
- deterministic;
- framework-neutral;
- non-mutating;
- non-generating;
- independent of `HeuristicCompatibilityContextV1`;
- independent of solver adapter selection;
- independent of `ScheduleProblemV1`.

The evaluator runs exactly once for one `context_fingerprint`, unless a cached
assessment is reused after its fingerprint is recomputed and validated.

### 5.2 Canonical assessment identity

The output remains `ServiceAdjustmentAssessmentV1` and continues to contain
exactly one `primary_decision`. Its canonical source anchor becomes:

`source_evaluation_context_fingerprint`

The target assessment fingerprint binds:

- evaluator fingerprint profile;
- source evaluation-context fingerprint;
- normalized bundle and source fingerprints;
- authoritative B evaluation fingerprint;
- adjustment-policy fingerprint;
- repeatability-evidence fingerprint when present;
- all quantitative block, donor, daily, allocation, headway, technical, and
  reduction evidence;
- primary decision;
- deterministic reason codes;
- limitations.

It MUST NOT bind a problem fingerprint, adapter ID, route, or authorized
generation action.

The current internal fields:

- `source_problem_fingerprint`;
- `heuristic_authorized`;
- `authorized_generation_action`

are transitional inversion artifacts. They are not authoritative fields in the
target evaluator result. During compatibility migration they MAY remain as
deprecated projections on the Python object, but:

- the canonical evaluator does not calculate them;
- they are excluded from the new assessment fingerprint;
- they cannot authorize problem construction or solver invocation;
- the old wrapper may populate them only for existing callers until Phase E.

No external `ServiceAdjustmentAssessmentV1` schema exists at this baseline, so
this is initially an internal typed-contract migration.

### 5.3 Decision authority

The evaluator retains the approved V1-D1 gate order:

1. data authority;
2. hard technical feasibility;
3. total supply shortage;
4. temporal/directional misallocation with jointly feasible donor proof;
5. repeatable and technically proven residual surplus;
6. complete diagnostic departure re-spacing;
7. keep the current timetable.

Capability availability MUST NOT change that order or its result. For example,
an unavailable fixed-resource adapter cannot turn `REDISTRIBUTE_TRIPS` into
`INSUFFICIENT_DATA` or `KEEP_CURRENT_TIMETABLE`.

## 6. Capability routing

### 6.1 Required contracts

V1-D2 requires a separate closed capability type:

```text
AdjustmentCapabilityV1
    NO_GENERATION_REQUIRED
    FIXED_RESOURCE_TRIP_REDISTRIBUTION
    FIXED_RESOURCE_DEPARTURE_RESPACE
    VARIABLE_TRIP_INCREASE_REQUIRED
    VARIABLE_TRIP_REDUCTION_REQUIRED
    TECHNICAL_PARAMETER_CHANGE_REQUIRED
    NOT_AUTHORIZED_INSUFFICIENT_DATA
```

This is a design proposal only. It is not added to code or an external schema
in V1-D2.

Solver availability belongs to a separate immutable internal policy:

```text
AdjustmentCapabilityRoutingPolicyV1
    fixed_resource_trip_redistribution_adapter: str | null
    fixed_resource_departure_respace_adapter: str | null
    supported_problem_modes: immutable mode tuple
    policy_fingerprint: str
```

Adapter configuration MUST NOT remain in `ServiceAdjustmentPolicyV1`, because
decision thresholds and implementation capability are separate authorities.

The recommended route contract is:

```text
AdjustmentCapabilityRoutingV1
    routing_id: str
    source_evaluation_context_fingerprint: str
    source_assessment_fingerprint: str
    source_adjustment_policy_fingerprint: str
    routing_policy_fingerprint: str
    primary_decision: ServiceAdjustmentDecisionV1
    routed_capability: AdjustmentCapabilityV1
    authorized_generation_action: str | null
    solver_adapter_id: str | null
    problem_construction_authorized: bool
    solver_invocation_authorized: bool
    required_operating_lock_mode: immutable lock-mode description | null
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    routing_fingerprint: str
```

Field semantics:

- source fields bind the route to the exact assessment and context;
- `primary_decision` must equal the assessment decision;
- `routed_capability` states the required capability, whether or not an
  implementation is currently available;
- `authorized_generation_action` is non-null only for the two supported
  fixed-resource actions;
- `solver_adapter_id` is non-null only when the routing policy identifies a
  compatible configured adapter;
- authorization booleans are true only when every required proof and current
  capability is present;
- `required_operating_lock_mode` records fixed total, fixed direction,
  endpoint, runtime, turnaround, fleet, and positioning requirements for a
  generated problem;
- reasons and limitations explain no-run and unsupported routes;
- `routing_fingerprint` binds the complete route.

### 6.2 Canonical signature

```text
route_adjustment_capability_v1(
    assessment: ServiceAdjustmentAssessmentV1,
    authoritative_context: ServiceAdjustmentEvaluationContextV1,
    routing_policy: AdjustmentCapabilityRoutingPolicyV1,
) -> AdjustmentCapabilityRoutingV1
```

The router is pure, deterministic, non-mutating, and non-generating.

Before routing it MUST verify:

- assessment context fingerprint equals the supplied context fingerprint;
- assessment B evaluation and adjustment-policy fingerprints equal the
  context;
- assessment fingerprint recomputes exactly;
- the primary decision is one of the seven closed V1-D1 values.

A stale or cross-context assessment produces no valid route. It is an
integration error, not `INSUFFICIENT_DATA`, and MUST NOT be repaired by
changing the primary decision.

The router may validate that evidence required by the selected decision is
present. It MUST NOT recalculate demand metrics or select a different
decision. If a supposedly fixed-resource decision lacks its mandatory V1-D1
proof, routing fails closed as an authority mismatch.

### 6.3 Mandatory routing matrix

| V1-D1 primary decision | Routed capability | Current problem/solver authorization | Normative behavior |
| --- | --- | --- | --- |
| `INSUFFICIENT_DATA` | `NOT_AUTHORIZED_INSUFFICIENT_DATA` | Problem: no. Solver: no. | Preserve known local evidence and the explicit insufficient decision. Build no demand-guided problem, create no Scenario C, and do not convert the state to solver `UNKNOWN`. |
| `TECHNICAL_ADJUSTMENT_REQUIRED` | `TECHNICAL_PARAMETER_CHANGE_REQUIRED` | Current heuristic problem: no. Solver: no. | Route to expert review or a future approved technical-parameter workflow. Do not run demand/headway optimization and do not hide the blocker as `MODEL_INVALID` or solver failure. |
| `INCREASE_TOTAL_TRIPS` | `VARIABLE_TRIP_INCREASE_REQUIRED` | Current fixed-resource problem: no. Solver: no. | Do not map to `REDISTRIBUTE_TRIPS`. Route to future variable-trip/resource planning. Produce no Scenario C under the current solver. |
| `REDISTRIBUTE_TRIPS` | `FIXED_RESOURCE_TRIP_REDISTRIBUTION` | Conditional yes. | Authorize only with full H3 directional authority, jointly feasible donor proof for the complete shortage quantity, fixed daily and directional trip counts, fixed endpoints, exact runtime and arrival-terminal turnaround, fixed available-fleet locks, supported positioning mode, and the exact action `fixed_resource_trip_redistribution`. |
| `REDUCE_TOTAL_TRIPS` | `VARIABLE_TRIP_REDUCTION_REQUIRED` | Current fixed-resource problem: no. Solver: no. | The recommendation and proven maximum remain advisory. Route to future variable-trip-count planning. Do not construct a fixed-trip-count problem or report B as suitable merely because reduction is unsupported. |
| `REDISTRIBUTE_DEPARTURE_TIMES` | `FIXED_RESOURCE_DEPARTURE_RESPACE` | Conditional yes. | Authorize only when demand supply is adequate, irregular regimes exist, complete diagnostic re-spacing passed, all fixed-resource locks remain preserved, and the exact action is `fixed_resource_departure_respace`. |
| `KEEP_CURRENT_TIMETABLE` | `NO_GENERATION_REQUIRED` | Problem: no. Solver: no. | Return no-generation-required evidence. Build no problem, invoke no solver, and create no Scenario C or duplicate of B. |

For the two fixed-resource decisions, a capability may be required while no
compatible adapter is currently configured. In that case the route keeps the
same decision and capability, uses null adapter/action authorization as
applicable, sets both authorization booleans false, and exposes
`CURRENT_SOLVER_CAPABILITY_INSUFFICIENT`. It does not substitute another
decision.

## 7. AuthorizedScheduleProblemRequestV1

### 7.1 Decision

An explicit immutable request object is required between capability routing
and `ScheduleProblemV1` construction:

`AuthorizedScheduleProblemRequestV1`

Without this object, the problem factory would need to infer authorization
from a collection of booleans and could silently reintroduce decision logic.
The request is a narrow, fingerprinted authorization token, not mutable
application state and not a solver problem.

### 7.2 Recommended fields

```text
AuthorizedScheduleProblemRequestV1
    request_id: str
    source_evaluation_context_fingerprint: str
    source_assessment_fingerprint: str
    source_routing_fingerprint: str
    normalized_bundle_fingerprint: str
    source_b_fingerprint: str
    authoritative_b_evaluation_fingerprint: str
    authorized_generation_action: str
    requested_solver_adapter: str
    direction_trip_lock_mode: DirectionTripLockMode
    fleet_constraint_mode: FleetConstraintMode
    initial_fleet_positioning_mode: InitialFleetPositioningMode
    boundary_convention: BoundaryConvention
    locked_total_daily_trips: int
    locked_directional_trip_counts: immutable directional counts
    locked_first_and_last_departures: immutable endpoint values
    runtime_lock_mode: str
    turnaround_application_mode: str
    operating_lock_profile_fingerprint: str
    request_fingerprint: str
```

The builder may derive the locked values from the authoritative context, but
the resulting request records them explicitly so the problem factory compares
rather than reinterprets.

The request builder exists only for a route where both authorization booleans
are true. It MUST reject:

- a no-generation or unsupported capability;
- a route whose source assessment/context does not match;
- a route without a concrete adapter;
- a route whose action does not exactly match its capability;
- any non-fixed trip/direction or unsupported fleet/positioning mode.

The request is initially an internal typed contract. It is not an external
bearer credential and grants no authority outside the exact fingerprint chain.

## 8. Authorized problem factory

### 8.1 Canonical signature

```text
build_authorized_schedule_problem_v1(
    request: AuthorizedScheduleProblemRequestV1,
    context: ServiceAdjustmentEvaluationContextV1,
    assessment: ServiceAdjustmentAssessmentV1,
    routing: AdjustmentCapabilityRoutingV1,
    adapter_context_fingerprint: str,
    solver_policy: SolverPolicyV1,
) -> ScheduleProblemV1
```

The factory is pure. It owns authorization reconciliation, existing H4
canonical problem construction, and independent problem validation.

### 8.2 Preconditions

A problem may be built only when:

1. the assessment permits one of the two supported fixed-resource actions;
2. the route authorizes the same concrete capability and adapter;
3. the request binds the exact assessment and route;
4. full required authoritative evidence remains available;
5. every context, assessment, route, request, and source fingerprint
   reconciles;
6. the adapter-context fingerprint is valid and belongs to the selected
   adapter;
7. all required operating locks and modes exactly match the request;
8. the existing H4 problem validator passes.

The problem factory MUST NOT:

- invoke the evaluator;
- recalculate the primary decision;
- map one decision to another;
- weaken requested locks;
- build a problem for future variable-resource or technical capabilities;
- build a problem only to determine whether it should have been built.

Adapter compatibility context construction moves after capability
authorization. For the heuristic path, the authorized adapter helper may
construct `HeuristicCompatibilityContextV1` after routing, calculate its
fingerprint, and pass only that fingerprint to the problem factory. The raw
compatibility object stays adapter-owned under H4.

## 9. Solver orchestration

### 9.1 Target inputs

The target solver entry point is:

```text
generate_authorized_schedule_v1(
    problem: ScheduleProblemV1,
    context: ServiceAdjustmentEvaluationContextV1,
    assessment: ServiceAdjustmentAssessmentV1,
    routing: AdjustmentCapabilityRoutingV1,
    request: AuthorizedScheduleProblemRequestV1,
    solver: ScheduleSolver,
) -> AdjustmentOrchestrationEnvelopeV1
```

This is the only public function in the target sequence that may invoke a
solver or observe elapsed time.

Before invocation it MUST:

- validate the problem independently;
- reconcile the full authorization fingerprint chain;
- require `problem_construction_authorized = true`;
- require `solver_invocation_authorized = true`;
- require problem adapter ID to equal route, request, and solver adapter IDs;
- require the problem's adapter-context fingerprint to match the
  adapter-owned context held by the solver;
- require the problem action and lock profile to equal the request;
- reconstruct or internally create the existing authoritative
  `ScheduleGenerationContextV1` only after authorization;
- retain H3 coverage as a defense-in-depth backstop.

The solver receives only `ScheduleProblemV1`. It never receives the assessment
as new optimization input and cannot change its decision.

### 9.2 Unsupported decisions

No solver function is called for:

- `INSUFFICIENT_DATA`;
- `TECHNICAL_ADJUSTMENT_REQUIRED`;
- `INCREASE_TOTAL_TRIPS`;
- `REDUCE_TOTAL_TRIPS`;
- `KEEP_CURRENT_TIMETABLE`.

The two fixed-resource decisions are the only current solver-eligible
decisions, and even those require a fully authorized route and request.

### 9.3 Independent validation and H1 sanitation

`validate_and_build_solution_v1()` remains independent and continues to:

- validate candidate/problem identity;
- derive shifts, previous headways, regimes, runtime, arrivals, ready times,
  fleet assignments, stock, blocks, and operating-lock conformance;
- reject missing H3 directional support;
- construct an accepted solution only after every check passes.

Solver exceptions remain inside the H1 sanitation boundary. A solver exception
may produce a nested generation result with `MODEL_INVALID`, but it cannot
rewrite the upstream primary adjustment decision or route.

## 10. Identity and fingerprint binding

### 10.1 Normative identity chain

The target identity chain is:

```text
source A/B/demand fingerprints
-> normalized bundle fingerprint
-> B evaluation policy fingerprint
-> authoritative B evaluation fingerprint
-> adjustment policy fingerprint
-> service-adjustment evaluation-context fingerprint
-> ServiceAdjustmentAssessmentV1 fingerprint
-> capability-routing fingerprint
-> authorized-problem-request fingerprint
-> ScheduleProblemV1 fingerprint
-> candidate fingerprint
-> solution fingerprint
-> adjustment orchestration outcome fingerprint
```

### 10.2 Binding rules

Each object binds its immediate authority:

- The normalized bundle fingerprint binds normalized A/B/demand facts and
  their source fingerprints.
- The B evaluation fingerprint binds the normalized bundle fingerprint, B
  evaluation policy fingerprint, complete evaluation evidence, H2 fleet and
  chronology evidence, and H3 coverage evidence.
- The evaluation-context fingerprint binds normalized bundle, B evaluation,
  B evaluation policy, adjustment policy, and repeatability evidence
  identities.
- The assessment fingerprint binds the exact evaluation-context fingerprint
  and all decision evidence. It contains no problem identity.
- The routing fingerprint binds the assessment fingerprint, context
  fingerprint, unchanged primary decision, routed capability, routing policy,
  adapter selection, authorized action, locks, reasons, and authorization
  booleans.
- The request fingerprint binds the assessment and routing fingerprints,
  normalized/evaluation identities, exact action, selected adapter, and exact
  lock profile.
- The problem fingerprint binds the request, assessment, and routing
  fingerprints, exact authorized action, and all existing H4 problem facts,
  including adapter-context fingerprint.
- The candidate fingerprint binds the exact problem fingerprint and raw
  candidate payload under H1.
- The solution fingerprint binds the problem and candidate fingerprints and
  all independently derived authoritative solution facts.
- The orchestration outcome fingerprint binds the assessment, routing and
  request identities, optional problem/candidate/solution identities, the
  nested generation outcome when present, explanations, and limitations.

For a no-problem route, the outcome fingerprint binds the assessment and route
directly. A problem fingerprint is absent rather than fabricated.

### 10.3 Stale and cross-assessment rejection

Every builder recomputes its input fingerprints. Exact equality is required.

Examples of required failures:

- assessment A plus context B: no route;
- route A plus assessment B: no request;
- request A plus route B: no problem;
- problem A plus route B: no solver invocation;
- adapter context A plus problem B: sanitized model-invalid integration
  result, never a business decision;
- a changed assessment under the same B: changed route fingerprint and stale
  prior route rejection;
- a changed route policy: changed route and problem identity.

No layer may repair a mismatch by substituting a decision, route, problem,
candidate, or status.

### 10.4 Authorized action in problem identity

The authorized action is a hard part of problem identity. Two otherwise
identical fixed-resource problems for:

- trip redistribution; and
- departure re-spacing

MUST have different problem fingerprints. A solver cannot treat the action as
an un-fingerprinted hint.

### 10.5 Adapter context remains non-authoritative

`adapter_context_fingerprint` remains required under H4 and participates in
problem identity. It proves which candidate-generation inputs were selected.
It does not participate in:

- B evaluation identity;
- adjustment-policy identity;
- assessment identity;
- the primary decision.

Changing adapter configuration after routing changes the adapter-context and
problem fingerprints. It does not change the existing assessment or route
unless the routing policy or available adapter capability also changed.

## 11. Recommended ScheduleProblemV1 additions

The current `ScheduleProblemV1` shape does not explicitly carry the
authorization chain. The later implementation should add these fields:

```text
service_adjustment_assessment_fingerprint: str
adjustment_capability_routing_fingerprint: str
authorized_problem_request_fingerprint: str
authorized_generation_action: str
```

All four are required for a V1-D2-authorized generated problem and participate
in `problem_fingerprint`.

Recommended visibility and versioning:

1. During Phases A and B, these identities live only in new internal
   assessment/routing/request contracts. `ScheduleProblemV1` and external
   schemas do not change.
2. Phase C first proves the complete binding in an internal authorization
   wrapper and tests.
3. Before adding any field to `ScheduleProblemV1`,
   `schedule_problem.schema.json`, canonical serialization, examples, or a
   public payload, implementation MUST STOP and obtain separate approval.
4. After that approval, the fields should be present in both the canonical
   typed problem and serialized problem. Keeping them only in hidden Python
   state would contradict H4.
5. The recommended approved schema action is a completion revision of the
   still-nonproduction Contract `1.0.0` Schedule Problem boundary, following
   the V1-H4 precedent. The engine contract remains `1.0.0`; this work MUST NOT
   consume or imply V1-A1 `1.1.0`.
6. The schema revision is nevertheless a real external-shape change under
   `additionalProperties: false` and is not authorized by V1-D2. Approval must
   explicitly confirm that the problem schema remains a draft/nonproduction
   boundary and approve migration of examples and schema tests.

If that approval is denied, implementation must keep
`AuthorizedScheduleProblemRequestV1` and an internal authorized-problem
envelope, must not emit the fields externally, and must not claim full H4
canonical authorization binding. Solver integration then stops before Phase D.

## 12. Result and outcome semantics

### 12.1 Existing types have narrower meanings

`BDisposition` summarizes authoritative Scenario B evaluation. It is upstream
evidence, not the service-adjustment decision and not capability routing.
There is no one-to-one mapping:

- one demand-unsuitable disposition may lead to increase, redistribution, or
  another supported decision;
- a suitable disposition supports, but does not replace, the full
  `KEEP_CURRENT_TIMETABLE` decision;
- technical and insufficient dispositions retain their own evidence
  precedence.

`GenerationResultStatus` describes the result of Scenario C generation or an
existing C no-run rule. It does not express all seven adjustment decisions.

The actual baseline type is `SolverExecutionStatus` rather than
`SolverExecutionState`. `NOT_RUN` means no solver invocation occurred; it is
not a reason why no solver ran.

The baseline contains no `SolverProofStatus` type. Solver proof semantics are
currently represented by `NativeSolverStatus` and the H1 mappings:

- `OPTIMAL` and `FEASIBLE` may carry a candidate;
- `INFEASIBLE` is proof only for the exact reviewed problem;
- `UNKNOWN` is not infeasibility;
- `MODEL_INVALID` is an implementation/integration defect.

V1-D2 does not invent `SolverProofStatus` or any other result enum.

`ScheduleGenerationOutcomeV1` is sufficient for:

- a completed authorized solver run;
- accepted or independently rejected candidates;
- exact solver status mapping;
- H1-sanitized adapter failure;
- existing semantically exact generation no-run states.

It is not sufficient as the sole top-level model for the entire adjustment
workflow.

### 12.2 Prohibited silent mappings

The following are forbidden:

- `INCREASE_TOTAL_TRIPS` to
  `C_NOT_GENERATED_INSUFFICIENT_DATA`;
- `REDUCE_TOTAL_TRIPS` to
  `C_NOT_REQUIRED_B_SUITABLE`;
- `TECHNICAL_ADJUSTMENT_REQUIRED` to
  `C_NOT_GENERATED_MODEL_INVALID` or native `MODEL_INVALID`;
- `INSUFFICIENT_DATA` to native `UNKNOWN`;
- any unsupported decision to an existing Scenario C;
- `KEEP_CURRENT_TIMETABLE` to an accepted copy of B as C.

`C_NOT_REQUIRED_B_SUITABLE` may be used only where its exact B-suitable
semantics are independently true. It must not become a generic no-generation
status.

### 12.3 Required orchestration envelope

The target needs a separate additive internal envelope:

```text
AdjustmentOrchestrationEnvelopeV1
    evaluation_context_fingerprint: str
    assessment: ServiceAdjustmentAssessmentV1
    routing: AdjustmentCapabilityRoutingV1
    authorized_problem_request_fingerprint: str | null
    problem_fingerprint: str | null
    generation_outcome: ScheduleGenerationOutcomeV1 | null
    outcome_fingerprint: str
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]
```

No new result enum is needed: the envelope's authoritative workflow state is
the assessment's existing primary decision plus the route's capability and
authorization booleans.

For unsupported and no-generation decisions, `generation_outcome` may be
null. This prevents a misleading `GenerationResultStatus`. For authorized
solver runs, it contains the existing `ScheduleGenerationOutcomeV1`.

This envelope should be internal in the first implementation. Any external
serialization, public schema, UI, or exporter use requires separate approval.

## 13. Target public API

The target public sequence is:

```text
build_service_adjustment_evaluation_context_v1(...)
-> evaluate_service_adjustment_need_v1(...)
-> route_adjustment_capability_v1(...)
-> optional build_authorized_schedule_problem_request_v1(...)
-> optional build_authorized_schedule_problem_v1(...)
-> optional generate_authorized_schedule_v1(...)
-> AdjustmentOrchestrationEnvelopeV1
```

### 13.1 Function contracts

#### `build_service_adjustment_evaluation_context_v1`

Inputs:

- `NormalizedInputBundleV1`;
- optional caller-supplied `ScenarioBEvaluationBundleV1` cache candidate;
- `ScenarioBEvaluationPolicyV1`;
- `ServiceAdjustmentPolicyV1`;
- optional `RepeatabilityEvidenceV1`.

Output:

- validated `ServiceAdjustmentEvaluationContextV1`.

Properties:

- pure;
- owns pre-problem context validation;
- recomputes or exactly reconciles authoritative B evaluation;
- fails closed;
- public additive domain API.

#### `evaluate_service_adjustment_need_v1`

Input:

- `ServiceAdjustmentEvaluationContextV1`.

Output:

- `ServiceAdjustmentAssessmentV1` with exactly one primary decision.

Properties:

- pure;
- owns only quantitative decision evaluation;
- fails closed on an invalid context;
- public additive domain API.

#### `route_adjustment_capability_v1`

Inputs:

- assessment;
- matching evaluation context;
- explicit immutable routing policy.

Output:

- `AdjustmentCapabilityRoutingV1`.

Properties:

- pure;
- owns decision-to-capability mapping and current capability availability;
- cannot alter the primary decision;
- fails closed on identity or evidence mismatch;
- public additive domain API.

#### `build_authorized_schedule_problem_request_v1`

Inputs:

- matching context, assessment, and route.

Output:

- `AuthorizedScheduleProblemRequestV1`.

Properties:

- pure;
- owns exact action and operating-lock authorization capture;
- fails closed for unsupported/no-generation routes;
- internal at first; public only after the authorization boundary is proven.

#### `build_authorized_schedule_problem_v1`

Inputs:

- authorized request;
- matching context, assessment, and route;
- selected adapter-context fingerprint;
- generic solver policy.

Output:

- canonical `ScheduleProblemV1`.

Properties:

- pure;
- owns existing H4 problem construction plus authorization reconciliation;
- invokes the independent problem validator;
- fails closed;
- internal until the schema stop gate is approved.

#### `generate_authorized_schedule_v1`

Inputs:

- already-authorized problem;
- matching context, assessment, route, and request;
- solver.

Output:

- `AdjustmentOrchestrationEnvelopeV1` containing a nested
  `ScheduleGenerationOutcomeV1` when appropriate.

Properties:

- the only function allowed to invoke a solver;
- owns final authorization checks and H1 exception sanitation;
- calls independent candidate validation;
- fails closed on mismatch;
- internal until migration and outcome-shape approval complete.

### 13.2 Existing API transition

The existing:

- `build_schedule_problem_v1()`;
- `build_schedule_generation_context_v1()`;
- `build_heuristic_schedule_request_v1()`;
- `run_schedule_solver_v1()`

remain compatibility/internal functions during migration. They MUST NOT remain
an alternative public path that bypasses assessment and routing after Phase D.

The existing `run_schedule_solver_v1()` B-disposition and H3 checks remain
defense-in-depth backstops. They cease to be the primary orchestration
decision.

## 14. Orchestration invariants

The implementation MUST enforce all of the following:

1. The evaluator runs exactly once for a specific authoritative input and
   policy identity unless a deterministically cached result is reused after
   fingerprint validation.
2. Problem construction cannot precede a supported adjustment assessment.
3. A solver cannot be invoked without a matching capability route.
4. Capability routing cannot change the evaluator's primary decision.
5. Unsupported decisions cannot be mapped to an existing Scenario C result.
6. `KEEP_CURRENT_TIMETABLE` cannot invoke the solver.
7. `INSUFFICIENT_DATA` cannot become solver `UNKNOWN`.
8. `TECHNICAL_ADJUSTMENT_REQUIRED` cannot become a demand-optimization run.
9. `INCREASE_TOTAL_TRIPS` and `REDUCE_TOTAL_TRIPS` cannot use the
   fixed-resource heuristic.
10. Combined-only demand cannot create a directional problem.
11. `HeuristicCompatibilityContextV1` cannot determine whether adjustment is
    required.
12. Scenario B, normalized inputs, and authoritative evaluation remain
    immutable.
13. Any context/assessment/routing/request/problem fingerprint mismatch fails
    closed.
14. Solver exceptions remain sanitized under H1 and cannot rewrite the
    upstream adjustment decision.
15. Problem construction is performed at most once for an exact authorized
    request unless a byte-identical deterministic cached problem is reused.
16. The authorized action is immutable from route through outcome.
17. No-run routes have no problem, candidate, solution, or fabricated Scenario
    C fingerprint.
18. A candidate cannot be validated against a different assessment or route
    merely because its problem source B matches.
19. Current fixed-resource generation preserves total daily trips,
    directional trip counts, endpoints, exact source runtimes,
    arrival-terminal turnaround, available-fleet locks, and supported
    positioning modes.
20. Independent domain validation remains mandatory even when the solver
    reports `OPTIMAL` or `FEASIBLE`.

## 15. Migration plan

Migration is staged so existing H1-H4 and V1-D1 behavior remains testable.

### 15.1 Phase A - Introduce pre-problem evaluation context

Changed responsibilities:

- add `ServiceAdjustmentEvaluationContextV1` and its pure builder;
- refactor the evaluator core to consume it;
- move problem/adapter access out of the canonical evaluator;
- establish the new assessment fingerprint profile.

Compatibility behavior:

- retain a temporary wrapper accepting `ScheduleGenerationContextV1`;
- the wrapper validates the old context, projects the new pre-problem
  context, and calls the same canonical evaluator exactly once;
- deprecated problem/heuristic fields may be projected for old callers but
  are excluded from canonical assessment identity and have no authorization
  force;
- old and new entry paths MUST produce identical canonical assessment
  fingerprints for identical authoritative facts and policies.

Test gate:

- all seven decision fixtures produce identical decisions, reason evidence,
  and assessment fingerprints through both paths;
- context construction rejects cross-bundle evaluations;
- no evaluator core import or field access depends on solver problem or
  heuristic context;
- full H1-H4 and V1-D1 suites pass.

Rollback condition:

- revert the additive context/wrapper if decision or evidence parity cannot be
  proven; do not proceed to routing.

### 15.2 Phase B - Introduce capability routing

Changed responsibilities:

- add capability and routing contracts;
- move adapter mapping and authorized action out of the evaluator;
- add pure deterministic routing and routing fingerprints.

Compatibility behavior:

- old assessment authorization fields may be populated by a compatibility
  projection from the new route;
- only the new route is authoritative for later phases;
- no solver or problem-construction behavior changes yet.

Test gate:

- all seven decisions route deterministically;
- only the two fixed-resource decisions can be currently authorized;
- stale assessment/context pairs fail;
- capability availability never changes primary decision;
- combined-only evidence never routes to a directional authorized action.

Rollback condition:

- remove the unused router if deterministic one-to-one capability mapping or
  identity reconciliation fails; preserve Phase A.

### 15.3 Phase C - Authorize problem construction

Changed responsibilities:

- add `AuthorizedScheduleProblemRequestV1`;
- add internal authorization binding around problem construction;
- construct heuristic compatibility context only after authorization;
- bind action, assessment, route, request, and adapter context into internal
  problem identity.

Compatibility behavior:

- direct problem builders remain available only for existing tests and
  explicitly marked internal compatibility paths;
- no external serialization changes occur before approval.

Test gate:

- no problem is created for five no-generation/unsupported decisions;
- fixed-resource problems require exact assessment/route/request agreement;
- changed route changes problem identity;
- stale pairs and adapter mismatches fail closed;
- canonical problem serialization and H4 validation remain unchanged until
  the stop gate.

Implementation stop and approval gate:

- STOP before modifying `ScheduleProblemV1`, its serializer, strict schema,
  examples, or contract version metadata;
- obtain explicit approval for the four additive problem fields and the
  Contract `1.0.0` draft schema completion.

Rollback condition:

- retain assessment and routing, remove the internal authorization wrapper,
  and do not integrate solver orchestration if canonical binding cannot be
  approved.

### 15.4 Phase D - Integrate orchestration

Changed responsibilities:

- compose evaluate -> route -> request -> problem -> solver -> validator;
- preserve explicit no-run envelopes without constructing a problem;
- require route and request at solver invocation;
- nest existing generation outcomes only where semantically accurate.

Compatibility behavior:

- old `run_schedule_solver_v1()` remains an internal backstop during
  transition;
- compatibility callers are routed through the new composition;
- no existing result enum is reinterpreted.

Test gate:

- ordering spies prove assessment and route precede problem construction;
- solver call count is zero for all five unsupported/no-generation decisions;
- supported actions preserve H1-H4 solution behavior;
- exception sanitation and independent validation remain exact;
- outcome fingerprints bind assessment and route.

Rollback condition:

- restore the prior additive solver entry point while keeping Phase A/B
  contracts if integrated outcome semantics or H1-H4 parity fails.

### 15.5 Phase E - Remove transitional inversion

Changed responsibilities:

- deprecate or remove evaluator dependence on
  `ScheduleGenerationContextV1`;
- remove authoritative use of assessment heuristic fields;
- reject direct unauthorized problem and solver entry points;
- retain compatibility only where separately approved and time-bounded.

Compatibility behavior:

- provide clear deprecation errors or wrappers for approved callers;
- external shapes remain unchanged unless their separate gates were approved.

Test gate:

- repository-wide call-site search finds no production bypass;
- no canonical evaluator reads a problem or adapter context;
- no public solver path accepts an unauthorized problem;
- all regression, lint, format, schema, and serialization tests pass.

Rollback condition:

- restore only the minimum compatibility wrapper required by a proven caller;
  do not restore decision authority to problem or adapter state.

## 16. Future implementation test strategy

### 16.1 Ordering

Mandatory tests:

- authoritative B evaluation precedes adjustment assessment;
- assessment precedes capability routing;
- routing precedes adapter-context and problem construction;
- problem construction precedes solver invocation;
- `KEEP_CURRENT_TIMETABLE` creates no problem;
- `INSUFFICIENT_DATA` creates no problem;
- unsupported increase and reduction create no current heuristic problem;
- technical adjustment creates no demand/headway problem.

Use recording fakes or dependency-injected builders. Tests MUST assert call
counts and object absence, not merely final statuses.

### 16.2 Routing

Mandatory tests:

- all seven decisions route deterministically;
- current heuristic authorization is possible only for fixed-resource trip
  redistribution and departure re-spacing;
- missing current adapter preserves the decision but denies invocation;
- combined-only evidence never routes to a directional capability;
- jointly incomplete donor proof fails routing rather than authorizing a
  partial move;
- failed re-spacing diagnostics cannot authorize departure re-spacing;
- routing cannot modify or replace an assessment.

### 16.3 Identity

Mandatory tests:

- changed normalized inputs change evaluation-context identity;
- changed assessment changes routing fingerprint;
- changed routing changes request and problem fingerprints;
- changed authorized action changes problem fingerprint;
- stale context/assessment, assessment/route, route/request, and
  request/problem pairs are rejected;
- a problem proves authorization by exact assessment, route, and request;
- candidate binds problem;
- solution binds candidate and problem;
- outcome binds assessment, route, and optional problem/solution;
- adapter context cannot replace assessment authority;
- changing only adapter algorithm configuration changes the problem but not
  the already-computed adjustment decision.

### 16.4 No mutation

Capture canonical serializations before and after every step and prove:

- normalized inputs are unchanged;
- Scenario B is unchanged;
- authoritative evaluation is unchanged;
- assessment is unchanged after routing;
- routing is unchanged after request/problem construction;
- no compatibility builder writes into legacy input objects.

### 16.5 H1-H4 preservation

Mandatory regressions retain:

- H1 solver exception sanitation and raw-candidate distrust;
- exact H2 per-trip runtime and arrival-terminal turnaround;
- H3 coverage, directional authority, and validator backstop;
- H4 canonical problem serialization and cross-field validation;
- operating-lock construction and reconciliation;
- candidate, solution, and outcome fingerprint integrity;
- independent fleet assignment and continuous terminal stock.

### 16.6 No-run semantics

Mandatory tests prove:

- no solver invocation for five unsupported/no-generation decisions;
- no fabricated Scenario C;
- no misleading native solver status;
- no `UNKNOWN` for insufficient data;
- no `MODEL_INVALID` for a technical-adjustment recommendation;
- no insufficient-data status for increase;
- no B-suitable status for reduction;
- no problem or solution fingerprint in a no-problem route;
- known local evidence remains present in insufficient outcomes.

## 17. Neutral headway-core technical debt

`contracts_v1/headway_regimes.py` currently imports the private pure helpers:

- `_balanced_values`;
- `_material_boundaries`;
- `_regime_drafts`

from legacy `c_generator.py`. This creates a Contract V1-to-legacy dependency
and makes the pre-problem evaluator indirectly depend on a generator module,
even though the imported operations are mathematical segmentation
primitives.

The future extraction plan is:

1. create a neutral shared pure module for balanced-value allocation and
   continuous-regime segmentation;
2. move the existing algorithms without semantic or ordering changes;
3. make both legacy `c_generator.py` and Contract V1 headway evaluation import
   the neutral core;
4. prohibit imports from the neutral core back into either caller;
5. preserve exact output and deterministic ordering;
6. add direct pure-unit tests for boundary, rounding, zero-headway, regime
   limit, and material-change cases;
7. add legacy-generator and Contract V1 parity tests against the current
   corpus.

Recommendation: this extraction is an immediately following hardening PR, not
a prerequisite to V1-D2 orchestration implementation. The current helpers are
pure and parity-tested, so orchestration can first correct the authority
ordering without combining it with algorithm movement. The extraction should
follow promptly, before broader headway or solver algorithm work, to eliminate
the dependency and reduce circular-import risk.

## 18. Explicit design decisions

V1-D2 makes these decisions:

1. The canonical pre-problem evaluator input is
   `ServiceAdjustmentEvaluationContextV1`.
2. A dedicated immutable evaluation context is required; loose direct inputs
   and `ScheduleGenerationContextV1` are not canonical.
3. A separate immutable `AdjustmentCapabilityRoutingV1` is required.
4. A separate immutable `AuthorizedScheduleProblemRequestV1` is required.
5. Assessment, routing, request, and authorized action fingerprints enter
   problem identity explicitly after the schema approval gate.
6. Backward compatibility is maintained with temporary wrappers and
   non-authoritative projections, while old and new evaluator paths produce
   the same canonical assessment fingerprint.
7. Contract semantics remain `1.0.0`; a later external Schedule Problem change
   requires a separately approved draft schema completion.
8. Implementation stops before any typed `ScheduleProblemV1`, serializer,
   schema, example, or external outcome-shape change.
9. Neutral headway-core extraction follows orchestration-boundary work as a
   separate hardening PR; it does not precede implementation.
10. No new result enum is introduced. A separate internal orchestration
    envelope carries the existing assessment decision and route.

## 19. Rejected alternatives

### 19.1 Keep ScheduleGenerationContextV1 as evaluator input

Rejected because it requires a problem before the decision and exposes adapter
and solver-mode facts to the evaluator.

### 19.2 Pass many existing objects directly to the evaluator

Rejected because callers could omit or cross-pair policies, fingerprints,
repeatability evidence, and evaluation provenance. There would be no single
validated cache identity.

### 19.3 Use a narrow view owned by ScheduleGenerationContextV1

Rejected as the canonical design because construction of the owner still
requires a problem. A temporary projection is acceptable only for backward
compatibility.

### 19.4 Let the problem builder run the evaluator

Rejected because the existence of the problem builder would still control the
decision lifecycle, and unsupported decisions would enter problem
construction.

### 19.5 Keep capability authorization inside the assessment

Rejected because solver availability is deployment capability, not
quantitative adjustment evidence. It would make decision fingerprints change
with adapter configuration.

### 19.6 Build every problem eagerly but block solver invocation

Rejected because it violates V1-D1's requirement that no problem be built
merely to discover whether adjustment is needed and retains the current
inversion.

### 19.7 Let HeuristicCompatibilityContextV1 authorize the solver

Rejected because legacy adapter state is non-authoritative under H4 and cannot
determine demand, technical, or adjustment necessity.

### 19.8 Omit AuthorizedScheduleProblemRequestV1

Rejected because the problem factory would need to reinterpret an assessment
and route instead of consuming an exact authorization token.

### 19.9 Hide authorization only inside a hash

Rejected because a hash without explicit canonical fields cannot explain or
validate what was authorized and conflicts with H4's canonical serializable
problem principle.

### 19.10 Reuse current generation statuses for every route

Rejected because increase, reduction, and technical adjustment have no
semantically accurate current `GenerationResultStatus`. Silent mapping would
misstate the decision and solver lifecycle.

### 19.11 Extract the headway core in the same implementation PR

Rejected because it combines authority-ordering work with algorithm movement,
widens rollback scope, and is not necessary to enforce the orchestration
boundary.

## 20. Implementation approval gates

Separate explicit approval is required before:

1. modifying `ScheduleProblemV1`;
2. modifying `schedule_problem.schema.json`;
3. modifying canonical problem serialization or examples;
4. exposing `AdjustmentOrchestrationEnvelopeV1` externally;
5. adding any public schema for assessment, routing, request, or orchestration
   outcome;
6. changing any current result enum;
7. changing Contract version metadata;
8. deprecating an externally proven caller of the current solver API;
9. selecting or implementing a variable-trip or technical-parameter solver;
10. starting V1-A1, OR-Tools, UI/export, or production runtime integration.

Until those approvals, V1-D2 implementation is limited to internal typed
contexts, pure evaluation/routing, internal authorization proof, wrappers, and
tests.

## 21. Acceptance gate for future implementation

V1-D2 implementation is complete only when:

- the evaluator has no canonical dependency on a problem or adapter context;
- all seven decisions route deterministically without changing the decision;
- a problem exists only for an authorized supported fixed-resource action;
- solver invocation requires exact context, assessment, route, request,
  problem, and adapter identity;
- all unsupported/no-generation decisions produce no problem, solver call, or
  Scenario C;
- current outcome enums are never used misleadingly;
- no-run and solver-run identities form one auditable fingerprint chain;
- H1 exception sanitation and independent candidate validation remain intact;
- H2 runtime/turnaround and fleet authority remain intact;
- H3 demand coverage and directional authority remain intact;
- H4 canonical problem validation and serialization remain intact;
- old/new compatibility paths have proven assessment parity;
- all required ordering, routing, identity, no-mutation, no-run, and
  regression tests pass;
- full Pytest, Ruff lint, Contract V1 Ruff-format, schema, serialization, and
  diff-scope gates pass;
- no UI, exporter, workbook, legacy algorithm, OR-Tools, V1-A1, or production
  cutover scope is introduced.

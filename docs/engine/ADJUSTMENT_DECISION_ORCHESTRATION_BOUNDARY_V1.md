# Contract V1 Adjustment Decision Orchestration and Capability Routing Boundary

## SUPERSEDED FOR IMPLEMENTATION

**Status:** Retained as architectural history; not an active implementation plan

[Project Direction Reset](PROJECT_DIRECTION_RESET.md) governs the active roadmap. The only part
retained for implementation is the Phase A separation of quantitative pre-problem evaluation:
decide whether adjustment is needed before building a solver problem.

V1-D2 Phases B through E are cancelled. Do not implement the capability router, authorization
request or profile, legacy assessment projection, orchestration envelope, or phase-by-phase
fingerprint-chain design described below. Unmerged commit
`bc391e1967957fd530b51755331ce92da0bfdea8` must not be merged, cherry-picked, or copied.

The remaining content is preserved unchanged as the historical design record that led to this
reset.

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
-> either a deterministic no-generation envelope
   or an authorized-problem request
      -> ScheduleProblemV1 construction
      -> solver invocation
      -> independent solution validation
      -> authorized-solver envelope
-> AdjustmentOrchestrationEnvelopeV1
```

Optimization MUST NOT begin, and a canonical problem MUST NOT be built, merely
because an adapter can generate an alternative timetable.

One canonical orchestration facade owns branch selection. It selects the
no-generation branch before adapter-context construction, problem construction,
solver lookup, or solver invocation.

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

The dependency inversion has five concrete forms:

1. `ServiceAdjustmentAssessmentV1.source_problem_fingerprint` makes a problem
   identity part of a decision that should precede the problem.
2. The evaluator reads solver adapter and operating-mode fields from
   `context.problem`.
3. The evaluator currently calculates `heuristic_authorized` and
   `authorized_generation_action`, mixing capability routing into the
   quantitative decision service.
4. The heuristic request helper builds adapter compatibility state and the
   canonical problem before the assessment exists.
5. `ServiceAdjustmentPolicyV1` and its current fingerprint payload mix
   quantitative decision thresholds with `fixed_resource_solver_adapter` and
   `fixed_resource_authorized_decisions`, so deployment routing can change
   decision identity.

The target design removes all five forms without modifying
`ScheduleGenerationContextV1` or `ScheduleProblemV1` in this documentation
task.

## 3. Required responsibility split

The target boundary has eight distinct responsibilities.

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

### 3.5 No-generation envelope builder

A separate pure builder constructs the required top-level orchestration
envelope whenever the route does not authorize problem construction and solver
invocation. It validates the exact context, canonical assessment, and route,
preserves their reasons, limitations, and known local evidence, and records the
explicit absence of request, problem, candidate, solution, and generation
outcome identities.

It cannot be used for a route that authorizes fixed-resource generation.

### 3.6 Authorized problem factory

The problem factory accepts an explicit authorization request produced after
routing. It builds a canonical problem only for a supported, authorized
fixed-resource action. It validates identities and locks but does not
reinterpret the adjustment decision.

### 3.7 Solver orchestration and independent validation

Solver orchestration consumes an already-authorized problem, its exact route,
and a solver whose adapter-owned context matches the problem by fingerprint.
Independent validation remains the final authority for accepting Scenario C.

### 3.8 Canonical orchestration facade

One facade owns the complete sequence and selects the branch immediately after
capability routing. It never constructs a problem speculatively and never
requires or resolves a solver registry for a route that does not authorize
generation.

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

### 4.2 Quantitative decision policy

Phase A MUST introduce a new frozen typed policy:

`ServiceAdjustmentDecisionPolicyV1`

It contains only configuration that can affect the quantitative V1-D1
decision:

```text
ServiceAdjustmentDecisionPolicyV1
    planning_load_factor_ceiling: float
    critical_load_factor_ceiling: float
    low_load_review_threshold: float
    minimum_authoritative_demand_confidence: DemandConfidence
    headway_rounding_tolerance_minutes: int
    required_regular_headway_rate: float
    minimum_sustained_change_intervals: int
    minimum_material_headway_change_minutes: int
    minimum_material_service_rate_change_ratio: float
    maximum_headway_regimes_per_direction: int
    minimum_valid_observed_days_for_reduction: int
    minimum_surplus_consistency_rate: float
    minimum_residual_surplus_trips_for_reduction: int
    minimum_service_trips_per_direction: int
    maximum_joint_donor_search_states: int
    maximum_joint_reduction_search_states: int
```

These fields cover the planning and critical ceilings, low-load review,
confidence, headway rounding and regularity, continuous-regime segmentation,
repeatability, residual-surplus, minimum-service, donor-search, and
reduction-search thresholds approved by V1-D1.

The decision policy MUST NOT contain:

- solver adapter IDs;
- authorized decision lists;
- solver availability;
- generation action strings;
- problem modes;
- routing capability configuration.

All fields participate in the service-adjustment decision-policy fingerprint.
The context and canonical assessment fingerprints bind the complete policy
payload, not a selected subset.

Phase A provides the pure compatibility function:

```text
project_service_adjustment_decision_policy_v1(
    legacy_policy: ServiceAdjustmentPolicyV1,
) -> ServiceAdjustmentDecisionPolicyV1
```

It copies only the quantitative fields above. It explicitly ignores
`fixed_resource_solver_adapter` and
`fixed_resource_authorized_decisions`. Changing only either ignored legacy
field MUST NOT change the decision-policy fingerprint, evaluation-context
fingerprint, canonical assessment fingerprint, or primary decision.

Any temporary capability-routing policy derived from those two legacy fields
is constructed only after the canonical assessment exists and participates
only in routing identity.

### 4.3 Recommended context fields

The recommended internal typed contract is:

```text
ServiceAdjustmentEvaluationContextV1
    normalized_inputs: NormalizedInputBundleV1
    b_evaluation: ScenarioBEvaluationBundleV1
    b_evaluation_policy: ScenarioBEvaluationPolicyV1
    decision_policy: ServiceAdjustmentDecisionPolicyV1
    repeatability_evidence: RepeatabilityEvidenceV1 | null
    normalized_bundle_fingerprint: str
    source_a_fingerprint: str | null
    source_b_fingerprint: str
    observed_demand_fingerprint: str | null
    b_evaluation_policy_fingerprint: str
    authoritative_b_evaluation_fingerprint: str
    adjustment_decision_policy_fingerprint: str
    repeatability_evidence_fingerprint: str | null
    context_fingerprint: str
```

Field semantics:

- `normalized_inputs` is the immutable normalized A/B/demand authority.
- `b_evaluation` is the recomputed or exactly reconciled authoritative
  Scenario B evaluation.
- `b_evaluation_policy` is the policy under which `b_evaluation` was derived.
- `decision_policy` is the complete immutable quantitative policy from
  Section 4.2 and contains no solver-routing configuration.
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
- `adjustment_decision_policy_fingerprint` identifies the complete
  `ServiceAdjustmentDecisionPolicyV1` payload.
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

### 4.4 Required exclusions

`ServiceAdjustmentEvaluationContextV1` MUST NOT contain:

- `ScheduleProblemV1`;
- `ScheduleGenerationContextV1`;
- `HeuristicCompatibilityContextV1`;
- a solver adapter object or adapter-context fingerprint;
- solver adapter IDs, solver availability, authorized decision lists, or
  capability-routing configuration;
- an already-authorized solver action;
- `ScenarioCConfig`;
- raw legacy workbook objects;
- legacy `ScenarioParameters`, `Trip`, or `DemandRecord` objects;
- Scenario C, a candidate, solution, or generation outcome;
- UI/application services or mutable application state.

### 4.5 Context construction and validation

`build_service_adjustment_evaluation_context_v1()` MUST:

1. validate normalized inputs;
2. recompute Scenario B evaluation using the effective B evaluation policy, or
   validate a deterministic cached evaluation by exact fingerprint equality;
3. recompute A, B, and demand source fingerprints;
4. validate H3 coverage evidence and preserve all limitations;
5. validate decision-policy compatibility with B-evaluation ceilings and
   confidence authority and bind the complete quantitative policy payload;
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

The canonical target `ServiceAdjustmentAssessmentV1` is a frozen internal typed
contract. It contains exactly one `primary_decision` and has this identity and
authority shape:

```text
ServiceAdjustmentAssessmentV1
    assessment_id: str
    evaluator_fingerprint: str
    evaluator_fingerprint_profile: str
    source_evaluation_context_fingerprint: str
    source_b_fingerprint: str
    observed_demand_fingerprint: str | null
    authoritative_b_evaluation_fingerprint: str
    adjustment_decision_policy_fingerprint: str
    primary_decision: ServiceAdjustmentDecisionV1
    quantitative block, donor, daily, allocation, headway,
        technical, repeatability, and reduction evidence
    reason_codes: tuple[str, ...]
    explanation: str
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]
```

The assessment fingerprint binds:

- evaluator fingerprint profile;
- source evaluation-context fingerprint;
- normalized bundle and source fingerprints reachable through the context;
- authoritative B evaluation fingerprint;
- complete service-adjustment decision-policy fingerprint;
- repeatability-evidence fingerprint when present;
- all quantitative block, donor, daily, allocation, headway, technical, and
  reduction evidence;
- primary decision;
- deterministic reasons, explanation, evidence, and limitations.

The canonical assessment MUST NOT contain or bind:

- `source_problem_fingerprint`;
- `heuristic_authorized`;
- `authorized_generation_action`;
- a solver adapter ID;
- a routing fingerprint;
- a problem fingerprint.

The pre-problem evaluator therefore never needs to invent a problem identity.
Because no external `ServiceAdjustmentAssessmentV1` JSON schema exists at the
current baseline, replacing the current internal target shape is an internal
typed-contract correction and does not require Contract `1.1.0`.

### 5.3 Legacy compatibility projection

Legacy compatibility uses a distinct frozen type created only after capability
routing:

```text
LegacyServiceAdjustmentAssessmentProjectionV1
    canonical_assessment: ServiceAdjustmentAssessmentV1
    canonical_assessment_fingerprint: str
    legacy_source_problem_fingerprint: str | null
    legacy_heuristic_authorized: bool
    legacy_authorized_generation_action: str | null
    source_routing_fingerprint: str | null
    projection_fingerprint: str
```

Normative rules:

- it is not the canonical assessment;
- it is created only after the canonical route is established;
- it has its own projection fingerprint over the canonical assessment
  fingerprint and every projected legacy field;
- changing a projected field changes the projection fingerprint;
- changing projected fields does not alter the already-established canonical
  assessment fingerprint;
- it cannot be passed to the canonical capability router, authorized-request
  builder, problem factory, or solver orchestration function;
- it cannot authorize request or problem construction;
- it cannot be serialized, cached, or presented as the canonical assessment;
- canonical code MUST NOT inspect it.

`dataclasses.replace` or any equivalent copy/mutation of the canonical
assessment to populate legacy fields while retaining its fingerprint is
forbidden. Two different canonical payloads can never claim the same canonical
assessment identity.

### 5.4 Decision authority

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
    configured_adapter_ids: immutable adapter-ID tuple
    supported_fixed_resource_capabilities: immutable capability tuple
    supported_problem_modes: immutable mode tuple
    supported_fixed_resource_profiles:
        immutable FixedResourceAuthorizationProfileV1 tuple
    current_capability_availability: immutable capability/adapter availability
    routing_policy_fingerprint: str
```

This policy owns adapter selection, supported capabilities, problem modes,
supported lock profiles, and current availability. Adapter configuration MUST
NOT participate in `ServiceAdjustmentDecisionPolicyV1`, the evaluation-context
identity, or canonical assessment identity.

During migration, a pure compatibility layer MAY derive a temporary routing
policy from `ServiceAdjustmentPolicyV1.fixed_resource_solver_adapter` and
`fixed_resource_authorized_decisions`. That derivation occurs only after
assessment and changes only routing-policy and downstream routing identities.

Fixed-resource authorization uses a closed frozen type:

```text
FixedResourceAuthorizationProfileV1
    direction_trip_lock_mode: DirectionTripLockMode
    fleet_constraint_mode: FleetConstraintMode
    initial_fleet_positioning_mode: InitialFleetPositioningMode
    boundary_convention: BoundaryConvention
    total_daily_trip_count_locked: bool
    directional_trip_counts_locked: bool
    first_departures_locked: bool
    last_departures_locked: bool
    source_trip_runtime_locked: bool
    arrival_terminal_turnaround_locked: bool
    vehicle_capacity_locked: bool
    available_fleet_limit_locked: bool
    operating_window_locked: bool
    minimum_service_locked: bool
    terminal_stock_must_remain_non_negative: bool
    profile_fingerprint: str
```

All modes and booleans participate in `profile_fingerprint`; the fingerprint
is derived under a stable internal profile identifier and excludes only its
own derived value. It is recomputed and validated whenever the profile is
consumed. No free-form dictionary or arbitrary text description is
authoritative. Unsupported mode or boolean combinations fail closed.

The recommended route contract is:

```text
AdjustmentCapabilityRoutingV1
    routing_id: str
    source_evaluation_context_fingerprint: str
    source_assessment_fingerprint: str
    source_adjustment_decision_policy_fingerprint: str
    routing_policy_fingerprint: str
    primary_decision: ServiceAdjustmentDecisionV1
    routed_capability: AdjustmentCapabilityV1
    authorized_generation_action: str | null
    solver_adapter_id: str | null
    problem_construction_authorized: bool
    solver_invocation_authorized: bool
    required_fixed_resource_profile:
        FixedResourceAuthorizationProfileV1 | null
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
- `required_fixed_resource_profile` is null for the five no-generation or
  unsupported capabilities and non-null for both fixed-resource capabilities,
  even when current adapter availability denies authorization;
- the route binds the exact fixed-resource profile fingerprint;
- reasons and limitations explain no-run and unsupported routes;
- `routing_fingerprint` binds the complete route, routing policy, and exact
  profile fingerprint or its explicit absence.

### 6.2 Canonical signature

```text
route_adjustment_capability_v1(
    assessment: ServiceAdjustmentAssessmentV1,
    context: ServiceAdjustmentEvaluationContextV1,
    routing_policy: AdjustmentCapabilityRoutingPolicyV1,
) -> AdjustmentCapabilityRoutingV1
```

The router is pure, deterministic, non-mutating, and non-generating.

Before routing it MUST verify:

- assessment context fingerprint equals the supplied context fingerprint;
- assessment B evaluation and decision-policy fingerprints equal the
  context;
- assessment fingerprint recomputes exactly;
- the primary decision is one of the seven closed V1-D1 values.

A stale or cross-context assessment produces no valid route. It is an
integration error, not `INSUFFICIENT_DATA`, and MUST NOT be repaired by
changing the primary decision.

The router accepts only the exact canonical `ServiceAdjustmentAssessmentV1`.
It MUST reject `LegacyServiceAdjustmentAssessmentProjectionV1` and any
structurally similar object.

The router may validate that evidence required by the selected decision is
present. It MUST NOT recalculate demand metrics or select a different
decision. If a supposedly fixed-resource decision lacks its mandatory V1-D1
proof, routing fails closed as an authority mismatch.

For a fixed-resource capability, the router also validates the required typed
profile against the routing policy's supported profiles. A supported route
with no currently available adapter retains the non-null required profile but
sets both authorization booleans false. An unsupported profile combination
cannot be weakened or converted to text; it fails closed.

### 6.3 Mandatory routing matrix

| V1-D1 primary decision | Routed capability | Required fixed-resource profile | Current problem/solver authorization | Normative behavior |
| --- | --- | --- | --- | --- |
| `INSUFFICIENT_DATA` | `NOT_AUTHORIZED_INSUFFICIENT_DATA` | Null | Problem: no. Solver: no. | Preserve known local evidence and the explicit insufficient decision. Build no demand-guided problem, create no Scenario C, and do not convert the state to solver `UNKNOWN`. |
| `TECHNICAL_ADJUSTMENT_REQUIRED` | `TECHNICAL_PARAMETER_CHANGE_REQUIRED` | Null | Current heuristic problem: no. Solver: no. | Route to expert review or a future approved technical-parameter workflow. Do not run demand/headway optimization and do not hide the blocker as `MODEL_INVALID` or solver failure. |
| `INCREASE_TOTAL_TRIPS` | `VARIABLE_TRIP_INCREASE_REQUIRED` | Null | Current fixed-resource problem: no. Solver: no. | Do not map to `REDISTRIBUTE_TRIPS`. Route to future variable-trip/resource planning. Produce no Scenario C under the current solver. |
| `REDISTRIBUTE_TRIPS` | `FIXED_RESOURCE_TRIP_REDISTRIBUTION` | Non-null exact typed profile | Conditional yes. | Authorize only with full H3 directional authority, jointly feasible donor proof for the complete shortage quantity, fixed daily and directional trip counts, fixed endpoints, exact runtime and arrival-terminal turnaround, fixed capacity and available-fleet locks, supported positioning and boundary modes, non-negative terminal stock, and the exact action `fixed_resource_trip_redistribution`. |
| `REDUCE_TOTAL_TRIPS` | `VARIABLE_TRIP_REDUCTION_REQUIRED` | Null | Current fixed-resource problem: no. Solver: no. | The recommendation and proven maximum remain advisory. Route to future variable-trip-count planning. Do not construct a fixed-trip-count problem or report B as suitable merely because reduction is unsupported. |
| `REDISTRIBUTE_DEPARTURE_TIMES` | `FIXED_RESOURCE_DEPARTURE_RESPACE` | Non-null exact typed profile | Conditional yes. | Authorize only when demand supply is adequate, irregular regimes exist, complete diagnostic re-spacing passed, the exact typed fixed-resource profile is supported, and the exact action is `fixed_resource_departure_respace`. |
| `KEEP_CURRENT_TIMETABLE` | `NO_GENERATION_REQUIRED` | Null | Problem: no. Solver: no. | Return no-generation-required evidence. Build no problem, invoke no solver, and create no Scenario C or duplicate of B. |

For the two fixed-resource decisions, a capability may be required while no
compatible adapter is currently configured. In that case the route keeps the
same decision, capability, and non-null required fixed-resource profile, uses
null adapter/action authorization as applicable, sets both authorization
booleans false, and exposes
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
    required_fixed_resource_profile: FixedResourceAuthorizationProfileV1
    fixed_resource_profile_fingerprint: str
    locked_total_daily_trips: int
    locked_directional_trip_counts: immutable directional counts
    locked_first_and_last_departures: immutable endpoint values
    request_fingerprint: str
```

The builder may derive the locked values from the authoritative context, but
the resulting request records them explicitly so the problem factory compares
rather than reinterprets. The request embeds the exact frozen profile from the
route and separately records its recomputed fingerprint. It does not translate
the profile into free-form runtime, turnaround, or lock-description strings.

The canonical builder is:

```text
build_authorized_schedule_problem_request_v1(
    context: ServiceAdjustmentEvaluationContextV1,
    assessment: ServiceAdjustmentAssessmentV1,
    routing: AdjustmentCapabilityRoutingV1,
) -> AuthorizedScheduleProblemRequestV1
```

The request builder exists only for a route where both authorization booleans
are true. It MUST reject:

- a no-generation or unsupported capability;
- a route whose source assessment/context does not match;
- a route without a concrete adapter;
- a route whose action does not exactly match its capability;
- a null, stale, weakened, or unsupported fixed-resource profile;
- any route/profile/request mode or boolean disagreement;
- any non-fixed trip/direction or unsupported fleet/positioning/boundary mode.

The request is initially an internal typed contract. It is not an external
bearer credential and grants no authority outside the exact fingerprint chain.
Changing any profile mode or lock boolean changes the profile, route, and
request fingerprints.

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
7. the route and request contain the same recomputed
   `FixedResourceAuthorizationProfileV1` and profile fingerprint;
8. every problem mode, generated operating lock, and locked authoritative
   value exactly satisfies that profile and the request;
9. weakening any one required lock would change route, request, and problem
   identity and is rejected;
10. the existing H4 problem validator passes.

The problem factory MUST NOT:

- invoke the evaluator;
- recalculate the primary decision;
- map one decision to another;
- weaken requested locks;
- reinterpret a dictionary or string as an authorization profile;
- build a problem for future variable-resource or technical capabilities;
- build a problem only to determine whether it should have been built.

Adapter compatibility context construction moves after capability
authorization. For the heuristic path, the authorized adapter helper may
construct `HeuristicCompatibilityContextV1` after routing, calculate its
fingerprint, and pass only that fingerprint to the problem factory. The raw
compatibility object stays adapter-owned under H4.

Until the separate `ScheduleProblemV1` schema stop gate is approved, an
internal authorization wrapper binds the exact profile fingerprint and proves
that the canonical problem's modes and operating locks satisfy it. After
approval, the profile fingerprint becomes explicit canonical problem identity
as specified in Section 11.

## 9. Solver orchestration

### 9.1 No-generation envelope path

The canonical pure no-generation builder is:

```text
build_no_generation_adjustment_envelope_v1(
    context: ServiceAdjustmentEvaluationContextV1,
    assessment: ServiceAdjustmentAssessmentV1,
    routing: AdjustmentCapabilityRoutingV1,
) -> AdjustmentOrchestrationEnvelopeV1
```

It MUST:

1. recompute and validate the context fingerprint;
2. recompute and validate the canonical assessment fingerprint;
3. recompute and validate the optional fixed-resource-profile fingerprint and
   the route fingerprint, which binds the established routing-policy
   fingerprint;
4. require assessment and route to reference the exact context;
5. require the route to preserve the assessment's exact primary decision;
6. require `problem_construction_authorized = false`;
7. require `solver_invocation_authorized = false`;
8. require no authorized problem request and set its fingerprint to null;
9. require no problem and set its fingerprint to null;
10. require no generation outcome;
11. require no candidate or solution identity;
12. preserve the assessment and route reasons, explanations, limitations, and
    known local quantitative evidence;
13. bind all those facts and the explicit absence of generation artifacts into
    a deterministic orchestration-outcome fingerprint.

The function is pure, deterministic, immutable, non-generating, and does not
accept or resolve a solver. It rejects any route that authorizes
fixed-resource generation. It also supports a fixed-resource capability route
whose current capability is unavailable, provided both authorization booleans
are false; the route retains its required non-null typed profile and capability
limitation.

This is the canonical envelope path for:

- `INSUFFICIENT_DATA`;
- `TECHNICAL_ADJUSTMENT_REQUIRED`;
- `INCREASE_TOTAL_TRIPS`;
- `REDUCE_TOTAL_TRIPS`;
- `KEEP_CURRENT_TIMETABLE`;

and for any otherwise fixed-resource route that is not currently authorized.

### 9.2 Authorized solver path

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

This is the only function in the target sequence that may invoke a solver or
observe elapsed time.

Before invocation it MUST:

- validate the problem independently;
- reconcile the full authorization fingerprint chain;
- require `problem_construction_authorized = true`;
- require `solver_invocation_authorized = true`;
- require problem adapter ID to equal route, request, and solver adapter IDs;
- require the problem's adapter-context fingerprint to match the
  adapter-owned context held by the solver;
- recompute the fixed-resource profile fingerprint and require exact
  route/request profile equality;
- require the problem action, modes, and operating locks to satisfy that exact
  request profile;
- reconstruct or internally create the existing authoritative
  `ScheduleGenerationContextV1` only after authorization;
- retain H3 coverage as a defense-in-depth backstop.

The solver receives only `ScheduleProblemV1`. It never receives the assessment
as new optimization input and cannot change its decision.

### 9.3 Decisions that cannot invoke a solver

No solver function is called for:

- `INSUFFICIENT_DATA`;
- `TECHNICAL_ADJUSTMENT_REQUIRED`;
- `INCREASE_TOTAL_TRIPS`;
- `REDUCE_TOTAL_TRIPS`;
- `KEEP_CURRENT_TIMETABLE`.

The two fixed-resource decisions are the only current solver-eligible
decisions, and even those require a fully authorized route and request.

Every non-authorized decision still returns a complete
`AdjustmentOrchestrationEnvelopeV1` through the no-generation builder.

### 9.4 Canonical orchestration facade

The target canonical facade is:

```text
orchestrate_service_adjustment_v1(
    normalized_inputs,
    evaluation_policy,
    decision_policy,
    routing_policy,
    repeatability_evidence=None,
    solver_registry=None,
) -> AdjustmentOrchestrationEnvelopeV1
```

Its exact concrete annotations may be refined during implementation, but its
ownership and ordering are normative. It MUST:

1. build the pre-problem `ServiceAdjustmentEvaluationContextV1`;
2. evaluate adjustment need exactly once for that context identity;
3. route the canonical assessment under the explicit routing policy;
4. when generation is not authorized, call
   `build_no_generation_adjustment_envelope_v1()` and return;
5. when generation is authorized, build the exact
   `AuthorizedScheduleProblemRequestV1`;
6. only then resolve the selected adapter and build its compatibility context;
7. build the authorized canonical problem;
8. call `generate_authorized_schedule_v1()`.

The facade MUST select the branch before any adapter-context or problem
construction. It MUST NOT build a problem speculatively. It MUST NOT require,
inspect, or resolve `solver_registry` for a no-generation route. A missing
solver registry is therefore valid for the complete no-generation path and
fails closed only when an authorized solver route actually needs resolution.

The facade does not call `ScheduleSolver.solve()` directly. It may cause a
solver invocation only by delegating the fully reconciled authorized branch to
`generate_authorized_schedule_v1()`.

### 9.5 Independent validation and H1 sanitation

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
-> service-adjustment decision-policy fingerprint
-> repeatability-evidence fingerprint, when present
-> service-adjustment evaluation-context fingerprint
-> canonical ServiceAdjustmentAssessmentV1 fingerprint
-> capability-routing-policy fingerprint
-> fixed-resource authorization-profile fingerprint, when applicable
-> capability-routing fingerprint
-> authorized-problem-request fingerprint, when applicable
-> ScheduleProblemV1 fingerprint, when applicable
-> candidate fingerprint, when applicable
-> solution fingerprint, when applicable
-> orchestration-envelope fingerprint
```

### 10.2 Binding rules

Each object binds its immediate authority:

- The normalized bundle fingerprint binds normalized A/B/demand facts and
  their source fingerprints.
- The B evaluation fingerprint binds the normalized bundle fingerprint, B
  evaluation policy fingerprint, complete evaluation evidence, H2 fleet and
  chronology evidence, and H3 coverage evidence.
- The evaluation-context fingerprint binds normalized bundle, B evaluation,
  B evaluation policy, the complete service-adjustment decision policy, and
  optional repeatability-evidence identities.
- The assessment fingerprint binds the exact evaluation-context fingerprint
  and all decision evidence. It contains no problem, adapter, or routing
  identity.
- The routing-policy fingerprint binds configured adapters, supported
  fixed-resource capabilities, problem modes, supported typed profiles, and
  current capability availability.
- The fixed-resource profile fingerprint binds every mode and lock boolean and
  is explicitly absent for non-fixed-resource capabilities.
- The routing fingerprint binds the assessment fingerprint, context
  fingerprint, unchanged primary decision, routed capability, routing policy,
  adapter selection, authorized action, exact profile fingerprint or its
  absence, reasons, and authorization booleans.
- The request fingerprint binds the assessment and routing fingerprints,
  normalized/evaluation identities, exact action, selected adapter, and the
  same recomputed typed profile and fingerprint.
- The problem fingerprint binds the request, assessment, and routing
  fingerprints, exact authorized action and fixed-resource profile, and all
  existing H4 problem facts, including adapter-context fingerprint.
- The candidate fingerprint binds the exact problem fingerprint and raw
  candidate payload under H1.
- The solution fingerprint binds the problem and candidate fingerprints and
  all independently derived authoritative solution facts.
- The orchestration-envelope fingerprint binds context, canonical assessment,
  route, optional request/problem/candidate/solution identities, the nested
  generation outcome when present, explanations, and limitations.

For a no-generation route, the request, problem, candidate, solution, and
generation-outcome identities are all absent. The envelope fingerprint binds
the context, canonical assessment, route, explanations, limitations, known
local evidence, and each explicit absence. No fingerprint is fabricated.

For compatibility projections, `projection_fingerprint` is a separate
identity outside this canonical chain. A legacy projection cannot authorize or
be used to construct any later canonical object.

### 10.3 Stale and cross-assessment rejection

Every builder recomputes its input fingerprints. Exact equality is required.

Examples of required failures:

- assessment A plus context B: no route;
- route A plus assessment B: no request;
- request A plus route B: no problem;
- route profile A plus request profile B: no problem;
- problem A plus route B: no solver invocation;
- adapter context A plus problem B: sanitized model-invalid integration
  result, never a business decision;
- a changed assessment under the same B: changed route fingerprint and stale
  prior route rejection;
- a changed route policy: changed route and downstream identity, but unchanged
  canonical assessment identity;
- any weakened profile lock: changed profile, route, request, and problem
  identity;
- a legacy projection passed as a canonical assessment: no route, request, or
  problem.

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
- service-adjustment decision-policy identity;
- assessment identity;
- the primary decision.

Changing adapter configuration after routing changes the adapter-context and
problem fingerprints. It does not change the existing assessment or route
unless the routing policy or available adapter capability also changed.

Changing only either legacy `ServiceAdjustmentPolicyV1` routing field changes
the derived routing policy and route identities. It does not change the
projected decision policy, evaluation context, canonical assessment, or primary
decision.

## 11. Recommended ScheduleProblemV1 additions

The current `ScheduleProblemV1` shape does not explicitly carry the
authorization chain. The later implementation should add these fields:

```text
service_adjustment_assessment_fingerprint: str
adjustment_capability_routing_fingerprint: str
authorized_problem_request_fingerprint: str
authorized_generation_action: str
fixed_resource_authorization_profile_fingerprint: str
```

All five are required for a V1-D2-authorized generated problem and participate
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
   boundary, approve all five additive authorization fields, and approve
   migration of examples and schema tests.

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

For unsupported and no-generation decisions, `generation_outcome` MUST be
null. In that case request and problem fingerprints are also null, no candidate
or solution identity exists, and `outcome_fingerprint` is the deterministic
orchestration-envelope fingerprint over the canonical context, assessment,
route, evidence, explanations, limitations, and explicit absence of all
generation artifacts. This prevents a misleading `GenerationResultStatus`.

`build_no_generation_adjustment_envelope_v1()` is the canonical owner for that
shape. `generate_authorized_schedule_v1()` is the canonical owner for an
authorized solver-run envelope and contains the existing
`ScheduleGenerationOutcomeV1` when generation is attempted. Both branches
return the same top-level type.

This envelope should be internal in the first implementation. Any external
serialization, public schema, UI, or exporter use requires separate approval.

## 13. Target public API

The coherent target sequence is:

```text
build_service_adjustment_evaluation_context_v1(...)
    -> ServiceAdjustmentEvaluationContextV1

evaluate_service_adjustment_need_v1(context)
    -> ServiceAdjustmentAssessmentV1

route_adjustment_capability_v1(assessment, context, routing_policy)
    -> AdjustmentCapabilityRoutingV1

if generation is not authorized:
    build_no_generation_adjustment_envelope_v1(
        context,
        assessment,
        routing,
    )
        -> AdjustmentOrchestrationEnvelopeV1

if fixed-resource generation is authorized:
    build_authorized_schedule_problem_request_v1(
        context,
        assessment,
        routing,
    )
        -> AuthorizedScheduleProblemRequestV1

    build adapter compatibility context after authorization

    build_authorized_schedule_problem_v1(
        request,
        context,
        assessment,
        routing,
        adapter_context_fingerprint,
        solver_policy,
    )
        -> ScheduleProblemV1

    generate_authorized_schedule_v1(
        problem,
        context,
        assessment,
        routing,
        request,
        solver,
    )
        -> AdjustmentOrchestrationEnvelopeV1

optional canonical composition:
    orchestrate_service_adjustment_v1(...)
        -> AdjustmentOrchestrationEnvelopeV1
```

### 13.1 Function contracts

#### `project_service_adjustment_decision_policy_v1`

Input:

- legacy `ServiceAdjustmentPolicyV1`.

Output:

- immutable `ServiceAdjustmentDecisionPolicyV1`.

Properties:

- pure and deterministic;
- copies only quantitative decision fields;
- ignores both legacy routing fields;
- internal compatibility API during Phase A.

#### `build_service_adjustment_evaluation_context_v1`

Inputs:

- `NormalizedInputBundleV1`;
- optional caller-supplied `ScenarioBEvaluationBundleV1` cache candidate;
- `ScenarioBEvaluationPolicyV1`;
- `ServiceAdjustmentDecisionPolicyV1`;
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

#### `build_no_generation_adjustment_envelope_v1`

Inputs:

- matching evaluation context;
- canonical assessment;
- matching non-authorized route.

Output:

- complete `AdjustmentOrchestrationEnvelopeV1` with no request, problem,
  generation outcome, candidate, or solution identity.

Properties:

- pure, deterministic, immutable, and non-generating;
- owns every no-run envelope;
- fails closed if either authorization boolean is true or any fingerprint
  disagrees;
- public additive domain API in Phase D;
- requires no solver registry.

#### `build_authorized_schedule_problem_request_v1`

Inputs:

- matching context, assessment, and route.

Output:

- `AuthorizedScheduleProblemRequestV1`.

Properties:

- pure;
- owns exact action and typed fixed-resource-profile authorization capture;
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
- verifies exact route/request profile equality and canonical lock conformance;
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

#### `orchestrate_service_adjustment_v1`

Inputs:

- normalized inputs;
- B evaluation policy;
- quantitative decision policy;
- capability-routing policy;
- optional repeatability evidence;
- optional solver registry.

Output:

- `AdjustmentOrchestrationEnvelopeV1` from exactly one branch.

Properties:

- canonical owner of sequencing and branch selection;
- public additive facade only after Phase D and the applicable outcome/API
  approval gate;
- does not resolve a solver for a no-generation route;
- may cause a solver run only through
  `generate_authorized_schedule_v1()`;
- fails closed before problem construction on any authority mismatch.

### 13.2 API visibility and transition

The initial public additive domain APIs are:

- `build_service_adjustment_evaluation_context_v1()`;
- `evaluate_service_adjustment_need_v1()`;
- `route_adjustment_capability_v1()`;
- in Phase D, `build_no_generation_adjustment_envelope_v1()`;
- after the Phase D API/outcome gate, `orchestrate_service_adjustment_v1()`.

The decision-policy compatibility projector and
`LegacyServiceAdjustmentAssessmentProjectionV1` builder are temporary internal
compatibility APIs. The authorized-request builder, authorized problem
factory, and authorized solver envelope path are initially internal while
their authorization and schema gates remain open.

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

No compatibility wrapper may return a modified canonical assessment carrying
the three legacy fields. After Phase B, callers that still need them receive a
separate `LegacyServiceAdjustmentAssessmentProjectionV1`, constructed only
after routing and never accepted by canonical APIs.

## 14. Orchestration invariants

The implementation MUST enforce all of the following:

1. The evaluator runs exactly once for a specific authoritative input and
   policy identity unless a deterministically cached result is reused after
   fingerprint validation.
2. Capability routing completes before any adapter compatibility context,
   authorized request, problem, or solver is resolved.
3. Problem construction cannot precede a supported and currently authorized
   capability route.
4. A solver cannot be invoked without matching context, canonical assessment,
   route, request, problem, adapter, and fixed-resource profile identities.
5. Capability routing cannot change the evaluator's primary decision.
6. Unsupported decisions cannot be mapped to an existing Scenario C result.
7. `KEEP_CURRENT_TIMETABLE` cannot invoke the solver.
8. `INSUFFICIENT_DATA` cannot become solver `UNKNOWN`.
9. `TECHNICAL_ADJUSTMENT_REQUIRED` cannot become a demand-optimization run.
10. `INCREASE_TOTAL_TRIPS` and `REDUCE_TOTAL_TRIPS` cannot use the
   fixed-resource heuristic.
11. Combined-only demand cannot create a directional problem.
12. `HeuristicCompatibilityContextV1` cannot determine whether adjustment is
    required.
13. Scenario B, normalized inputs, authoritative evaluation, decision policy,
    canonical assessment, route, and profile remain immutable.
14. Changing only adapter/routing configuration cannot change the decision
    policy, evaluation context, canonical assessment, or primary decision.
15. A legacy assessment projection cannot be used as a canonical assessment
    or authorize any canonical downstream object.
16. Any context/assessment/routing/profile/request/problem fingerprint
    mismatch fails closed.
17. Solver exceptions remain sanitized under H1 and cannot rewrite the
    upstream adjustment decision.
18. Problem construction is performed at most once for an exact authorized
    request unless a byte-identical deterministic cached problem is reused.
19. The authorized action and fixed-resource profile are immutable from route
    through outcome.
20. A no-generation route has no authorized request, problem, generation
    outcome, candidate, solution, or fabricated Scenario C fingerprint.
21. Every no-generation route still returns a complete deterministic
    `AdjustmentOrchestrationEnvelopeV1`.
22. The no-generation branch never resolves a solver registry or calls a
    solver.
23. Both no-generation and authorized-solver branches return the same
    top-level envelope type.
24. A candidate cannot be validated against a different assessment or route
    merely because its problem source B matches.
25. Current fixed-resource generation preserves total daily trips,
    directional trip counts, endpoints, exact source runtimes,
    arrival-terminal turnaround, vehicle capacity, available-fleet and
    operating-window locks, minimum service, non-negative terminal stock, and
    supported positioning and boundary modes.
26. Independent domain validation remains mandatory even when the solver
    reports `OPTIMAL` or `FEASIBLE`.

## 15. Migration plan

Migration is staged so existing H1-H4 and V1-D1 behavior remains testable.

### 15.1 Phase A - Pre-problem decision authority

Changed responsibilities:

- add immutable `ServiceAdjustmentDecisionPolicyV1`;
- add
  `project_service_adjustment_decision_policy_v1(ServiceAdjustmentPolicyV1)`
  and explicitly discard the two legacy routing fields;
- add `ServiceAdjustmentEvaluationContextV1` and its pure builder;
- refactor the evaluator core to consume it;
- replace the canonical internal `ServiceAdjustmentAssessmentV1` with the
  problem-free and routing-free shape in Section 5.2;
- move problem/adapter access out of the canonical evaluator;
- establish the new decision-policy, context, and canonical assessment
  fingerprint profiles;
- make no solver or routing behavior change in this phase.

Compatibility behavior:

- retain a temporary wrapper accepting `ScheduleGenerationContextV1`;
- the wrapper validates the old context, projects the quantitative decision
  policy and new pre-problem context, and calls the same canonical evaluator
  exactly once;
- the wrapper returns the canonical assessment and does not populate legacy
  problem/heuristic fields on it;
- a separate legacy assessment projection is deferred until Phase B, when a
  route exists;
- old and new entry paths MUST produce identical canonical assessment
  fingerprints for identical authoritative facts and policies.

Test gate:

- all seven decision fixtures produce identical decisions, reason evidence,
  and assessment fingerprints through both paths;
- changing only `fixed_resource_solver_adapter` or
  `fixed_resource_authorized_decisions` changes neither decision-policy,
  context, assessment identity, nor primary decision;
- changing a quantitative threshold changes the decision-policy, context, and
  canonical assessment fingerprints;
- context construction rejects cross-bundle evaluations;
- the canonical assessment has no problem, adapter, authorization, or route
  identity;
- no evaluator core import or field access depends on solver problem or
  heuristic context;
- full H1-H4 and V1-D1 suites pass.

Rollback condition:

- revert the additive context/wrapper if decision or evidence parity cannot be
  proven; do not proceed to routing.

### 15.2 Phase B - Capability routing and compatibility projection

Changed responsibilities:

- add `AdjustmentCapabilityRoutingPolicyV1`;
- add frozen `FixedResourceAuthorizationProfileV1`;
- add `AdjustmentCapabilityRoutingV1`;
- add `LegacyServiceAdjustmentAssessmentProjectionV1`;
- move adapter mapping and authorized action out of the evaluator;
- add pure deterministic routing, profile, routing-policy, route, and
  projection fingerprints.

Compatibility behavior:

- derive any temporary routing policy from the two legacy
  `ServiceAdjustmentPolicyV1` routing fields only after assessment;
- create the distinct legacy assessment projection only after routing;
- changing legacy projected fields changes only projection identity;
- canonical router, request, problem, and solver APIs reject the projection;
- only the new route is authoritative for later phases;
- no solver or problem-construction behavior changes yet.

Test gate:

- all seven decisions route deterministically;
- only the two fixed-resource decisions can be currently authorized;
- fixed-resource routes require a non-null typed profile and every other
  routed capability requires a null profile;
- stale assessment/context pairs fail;
- route/profile fingerprints change when any lock is weakened;
- capability availability never changes primary decision;
- changing routing policy changes route but not assessment;
- changing either legacy routing field changes the derived routing-policy and
  route identities but not decision identity;
- a legacy projection exists only after routing and cannot enter a canonical
  API;
- two different payloads cannot claim the same canonical assessment identity;
- combined-only evidence never routes to a directional authorized action.

Rollback condition:

- remove the unused router if deterministic one-to-one capability mapping or
  identity reconciliation fails; preserve Phase A.

### 15.3 Phase C - Authorize problem construction

Changed responsibilities:

- add `AuthorizedScheduleProblemRequestV1`;
- add internal authorization binding around problem construction;
- construct heuristic compatibility context only after authorization;
- bind canonical assessment, route, exact fixed-resource profile, authorized
  action, adapter, request, and adapter context into internal problem
  identity.

Compatibility behavior:

- direct problem builders remain available only for existing tests and
  explicitly marked internal compatibility paths;
- no external serialization changes occur before approval.

Test gate:

- no problem is created for five no-generation/unsupported decisions;
- fixed-resource problems require exact assessment/route/profile/request
  agreement;
- route/request profile mismatch, a weakened lock, a free-form lock
  description, or an unsupported profile combination fails closed;
- changed route changes problem identity;
- stale pairs and adapter mismatches fail closed;
- canonical problem serialization and H4 validation remain unchanged until
  the stop gate.

Implementation stop and approval gate:

- STOP before modifying `ScheduleProblemV1`, its serializer, strict schema,
  examples, or contract version metadata;
- obtain explicit approval for the five additive problem fields and the
  Contract `1.0.0` draft schema completion.

Rollback condition:

- retain assessment and routing, remove the internal authorization wrapper,
  and do not integrate solver orchestration if canonical binding cannot be
  approved.

### 15.4 Phase D - Integrate orchestration

Changed responsibilities:

- add `build_no_generation_adjustment_envelope_v1()`;
- add the authorized solver-envelope path;
- add `orchestrate_service_adjustment_v1()`;
- compose context -> evaluate -> route, then select exactly one branch before
  request, adapter-context, problem, or solver resolution;
- construct explicit no-generation envelopes without an authorized request or
  problem;
- require route and request at solver invocation;
- nest existing generation outcomes only where semantically accurate.

Compatibility behavior:

- old `run_schedule_solver_v1()` remains an internal backstop during
  transition;
- compatibility callers are routed through the new composition;
- no existing result enum is reinterpreted.

Test gate:

- each of the five mandatory no-generation decisions returns an envelope with
  no request, problem, generation outcome, candidate, or solution;
- ordering spies prove assessment and route precede every problem-construction
  call;
- the no-generation path never resolves a solver and requires no solver
  registry;
- only the two authorized fixed-resource decisions may create problem and
  solver artifacts;
- both branches return `AdjustmentOrchestrationEnvelopeV1`;
- no-generation and authorized envelope fingerprints bind their exact branch
  identities and absences;
- supported actions preserve H1-H4 solution behavior;
- exception sanitation and independent validation remain exact;
- unsupported fixed-resource availability still returns a complete
  no-generation envelope without changing the primary decision.

Rollback condition:

- restore the prior additive solver entry point while keeping Phase A/B
  contracts if integrated outcome semantics or H1-H4 parity fails.

### 15.5 Phase E - Remove transitional inversion

Changed responsibilities:

- deprecate or remove evaluator dependence on
  `ScheduleGenerationContextV1`;
- deprecate and remove legacy assessment projections except for a proven,
  separately approved, time-bounded compatibility need;
- remove authoritative use of old `ServiceAdjustmentPolicyV1` routing fields;
- reject direct unauthorized problem and solver entry points;
- retain compatibility only where separately approved and time-bounded.

Compatibility behavior:

- provide clear deprecation errors or wrappers for approved callers;
- external shapes remain unchanged unless their separate gates were approved.

Test gate:

- repository-wide call-site search finds no production bypass;
- no canonical evaluator reads a problem or adapter context;
- no canonical code inspects a legacy assessment projection;
- no decision identity depends on legacy adapter configuration;
- no public solver path accepts an unauthorized problem;
- all regression, lint, format, schema, and serialization tests pass.

Rollback condition:

- restore only the minimum compatibility wrapper required by a proven caller;
  do not restore decision authority to problem or adapter state.

## 16. Future implementation test strategy

### 16.1 No-generation envelope

Mandatory tests:

1. Each of the five mandatory no-generation decisions creates a complete
   `AdjustmentOrchestrationEnvelopeV1`.
2. No authorized request, problem, solver call, candidate, solution, or
   generation outcome exists on those paths.
3. The envelope fingerprint is deterministic for identical inputs.
4. A changed canonical assessment or route changes the envelope fingerprint.
5. The no-generation builder rejects a route that authorizes fixed-resource
   generation.

### 16.2 Canonical assessment and legacy projection

Mandatory tests:

6. The canonical assessment contains no problem identity, adapter ID,
   heuristic authorization, authorized generation action, or routing identity.
7. `LegacyServiceAdjustmentAssessmentProjectionV1` has its own recomputed
   projection fingerprint.
8. Changing only a projected legacy field changes only projection identity.
9. A legacy projection cannot be passed to the canonical router, request
   builder, problem factory, or solver path.
10. Two different canonical assessment payloads cannot claim the same
    canonical object identity; `dataclasses.replace` or equivalent projection
    cannot retain the original fingerprint.

### 16.3 Policy separation

Mandatory tests:

11. Changing only `fixed_resource_solver_adapter` in legacy
    `ServiceAdjustmentPolicyV1` does not change the projected decision-policy,
    evaluation-context, or canonical assessment fingerprints or primary
    decision.
12. The same change alters the derived routing-policy and route identities.
13. Changing a quantitative threshold changes the decision-policy,
    evaluation-context, and canonical assessment fingerprints.

The same isolation tests apply to
`fixed_resource_authorized_decisions`.

### 16.4 Typed fixed-resource profile

Mandatory tests:

14. Both fixed-resource capabilities require a non-null frozen
    `FixedResourceAuthorizationProfileV1`.
15. Each of the five decision-defined no-generation routes requires a null
    profile. A currently unavailable fixed-resource route remains a
    fixed-resource route and retains its non-null required profile.
16. Weakening any lock boolean or changing any mode changes the profile and
    routing fingerprints and downstream request/problem identity.
17. Any route/request profile mismatch fails closed.
18. Free-form dictionary or string lock descriptions are rejected and cannot
    be authoritative.

### 16.5 Full orchestration and ordering

Mandatory tests:

19. Problem construction is never called before routing authorization.
20. Solver lookup and solver invocation are never called for a no-generation
    route; no solver registry is required.
21. Unsupported decisions still return a complete top-level envelope, and
    both orchestration branches return the same envelope type.
22. The two authorized fixed-resource decisions may create request, problem,
    candidate, solution, and generation-outcome artifacts while H1-H4 and
    V1-D1 semantics remain unchanged.

Use recording fakes or dependency-injected builders. Tests MUST assert exact
ordering, call counts, registry access, and object absence, not merely final
statuses.

Additional routing tests prove:

- all seven decisions route deterministically;
- current heuristic authorization is possible only for fixed-resource trip
  redistribution and departure re-spacing;
- missing current adapter preserves the decision and required profile but
  denies invocation;
- combined-only evidence never routes to a directional capability;
- jointly incomplete donor proof fails routing rather than authorizing a
  partial move;
- failed re-spacing diagnostics cannot authorize departure re-spacing;
- routing cannot modify or replace an assessment.

### 16.6 Canonical identity and no mutation

Mandatory identity tests also prove:

- changed normalized inputs change evaluation-context identity;
- changed assessment changes routing fingerprint;
- changed routing changes request and problem fingerprints;
- changed authorized action changes problem fingerprint;
- stale context/assessment, assessment/route, route/profile,
  profile/request, route/request, and request/problem pairs are rejected;
- a problem proves authorization by exact assessment, route, profile, and
  request;
- candidate binds problem;
- solution binds candidate and problem;
- envelope binds context, assessment, route, and every applicable or
  explicitly absent downstream identity;
- adapter context and legacy projection cannot replace assessment authority.

Capture canonical serializations before and after every step and prove:

- normalized inputs are unchanged;
- Scenario B is unchanged;
- authoritative evaluation is unchanged;
- decision policy is unchanged;
- assessment is unchanged after routing;
- fixed-resource profile is unchanged after route construction;
- routing is unchanged after request/problem construction;
- no compatibility builder writes into legacy input objects.

### 16.7 H1-H4 and V1-D1 preservation

Mandatory regressions retain:

- H1 solver exception sanitation and raw-candidate distrust;
- exact H2 per-trip runtime and arrival-terminal turnaround;
- H3 coverage, directional authority, and validator backstop;
- H4 canonical problem serialization and cross-field validation;
- operating-lock construction and reconciliation;
- candidate, solution, and outcome fingerprint integrity;
- independent fleet assignment and continuous terminal stock;
- all seven V1-D1 decisions, precedence, joint donor proof, joint reduction
  proof, complete diagnostic re-spacing proof, and combined-only restrictions.

### 16.8 No-run result semantics

Mandatory tests prove:

- no fabricated Scenario C;
- no misleading native solver status;
- no `UNKNOWN` for insufficient data;
- no `MODEL_INVALID` for a technical-adjustment recommendation;
- no insufficient-data status for increase;
- no B-suitable status for reduction;
- no request, problem, candidate, solution, or generation-outcome fingerprint
  in a no-generation route;
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
3. `ServiceAdjustmentDecisionPolicyV1` is established in Phase A and contains
   only quantitative decision configuration.
4. The canonical `ServiceAdjustmentAssessmentV1` contains no problem, adapter,
   authorization, or route fields.
5. Legacy assessment compatibility is a separate post-routing
   `LegacyServiceAdjustmentAssessmentProjectionV1` with its own fingerprint.
6. Separate immutable `AdjustmentCapabilityRoutingPolicyV1`,
   `FixedResourceAuthorizationProfileV1`, and
   `AdjustmentCapabilityRoutingV1` contracts are required.
7. A separate immutable `AuthorizedScheduleProblemRequestV1` is required.
8. A pure `build_no_generation_adjustment_envelope_v1()` owns every
   non-authorized envelope, and
   `generate_authorized_schedule_v1()` owns the only solver path.
9. `orchestrate_service_adjustment_v1()` owns ordering and selects the branch
   before adapter, problem, or solver resolution.
10. Assessment, routing, profile, request, and authorized action fingerprints
    enter problem identity explicitly after the schema approval gate.
11. Backward compatibility is maintained with temporary input wrappers and
    separately fingerprinted non-authoritative projections, while old and new
    evaluator inputs produce the same canonical assessment fingerprint.
12. Contract semantics remain `1.0.0`; a later external Schedule Problem change
   requires a separately approved draft schema completion.
13. Implementation stops before any typed `ScheduleProblemV1`, serializer,
   schema, example, or external outcome-shape change.
14. Neutral headway-core extraction follows orchestration-boundary work as a
   separate hardening PR; it does not precede implementation.
15. No new result enum is introduced. A separate internal orchestration
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

### 19.6 Keep legacy fields on the canonical assessment but exclude them from its fingerprint

Rejected because two different payloads could claim one canonical assessment
identity, and a pre-problem evaluator has no legitimate problem fingerprint.
Compatibility must use a separate post-routing projection with its own
fingerprint.

### 19.7 Delay quantitative/routing policy separation until Phase B

Rejected because Phase A establishes canonical context and assessment
identity. Fingerprinting the current mixed `ServiceAdjustmentPolicyV1` in
Phase A would let adapter configuration alter a quantitative decision
identity.

### 19.8 Use a free-form lock dictionary or description

Rejected because arbitrary text or dictionary semantics cannot provide closed
canonical serialization, deterministic fingerprinting, exact route/request
reconciliation, or fail-closed profile support.

### 19.9 Route no-generation outcomes through the authorized solver function

Rejected because `generate_authorized_schedule_v1()` requires a problem,
request, and solver. Fabricating any of them violates the no-generation
decisions and would require solver resolution where none is authorized.

### 19.10 Build every problem eagerly but block solver invocation

Rejected because it violates V1-D1's requirement that no problem be built
merely to discover whether adjustment is needed and retains the current
inversion.

### 19.11 Let HeuristicCompatibilityContextV1 authorize the solver

Rejected because legacy adapter state is non-authoritative under H4 and cannot
determine demand, technical, or adjustment necessity.

### 19.12 Omit AuthorizedScheduleProblemRequestV1

Rejected because the problem factory would need to reinterpret an assessment
and route instead of consuming an exact authorization token.

### 19.13 Hide authorization only inside a hash

Rejected because a hash without explicit canonical fields cannot explain or
validate what was authorized and conflicts with H4's canonical serializable
problem principle.

### 19.14 Reuse current generation statuses for every route

Rejected because increase, reduction, and technical adjustment have no
semantically accurate current `GenerationResultStatus`. Silent mapping would
misstate the decision and solver lifecycle.

### 19.15 Extract the headway core in the same implementation PR

Rejected because it combines authority-ordering work with algorithm movement,
widens rollback scope, and is not necessary to enforce the orchestration
boundary.

## 20. Implementation approval gates

Separate explicit approval is required before:

1. modifying `ScheduleProblemV1`;
2. modifying `schedule_problem.schema.json`;
3. adding the five authorization/profile fields to canonical problem
   serialization or examples;
4. exposing `AdjustmentOrchestrationEnvelopeV1` externally;
5. adding any public schema for assessment, routing, request, or orchestration
   outcome;
6. changing any current result enum;
7. changing Contract version metadata;
8. deprecating an externally proven caller of the current solver API;
9. selecting or implementing a variable-trip or technical-parameter solver;
10. starting V1-A1, OR-Tools, UI/export, or production runtime integration.

Until those approvals, V1-D2 implementation is limited to internal typed
decision policies, contexts, canonical assessments, routing policies, typed
profiles, routes, legacy projections, pure no-generation envelopes, internal
authorization proof, wrappers, and tests.

Introducing the internal `ServiceAdjustmentDecisionPolicyV1`, corrected
internal canonical `ServiceAdjustmentAssessmentV1`,
`LegacyServiceAdjustmentAssessmentProjectionV1`, or
`FixedResourceAuthorizationProfileV1` does not itself require Contract
`1.1.0`, because none has an external schema at this baseline. Any later
external serialization still requires the applicable gate above.

## 21. Acceptance gate for future implementation

V1-D2 implementation is complete only when:

- the evaluator has no canonical dependency on a problem or adapter context;
- the context and canonical assessment bind a quantitative
  `ServiceAdjustmentDecisionPolicyV1` that contains no routing configuration;
- changing only legacy adapter configuration leaves decision-policy, context,
  assessment, and primary-decision identity unchanged;
- the canonical assessment has no problem, adapter-authorization, or routing
  fields;
- every legacy assessment projection is separate, post-routing, independently
  fingerprinted, and rejected by canonical APIs;
- all seven decisions route deterministically without changing the decision;
- fixed-resource routes carry an exact non-null typed authorization profile,
  non-fixed-resource routes carry null, and free-form lock descriptions are
  rejected;
- a problem exists only for an authorized supported fixed-resource action;
- solver invocation requires exact context, assessment, route, typed profile,
  request, problem, and adapter identity;
- all non-authorized routes return a deterministic no-generation envelope with
  no request, problem, generation outcome, candidate, solution, solver lookup,
  solver call, or Scenario C;
- the facade selects its branch before adapter-context and problem
  construction and does not require a solver registry for no-generation;
- both branches return `AdjustmentOrchestrationEnvelopeV1`;
- current outcome enums are never used misleadingly;
- no-run and solver-run identities form one auditable fingerprint chain with
  explicit absence semantics;
- H1 exception sanitation and independent candidate validation remain intact;
- H2 runtime/turnaround and fleet authority remain intact;
- H3 demand coverage and directional authority remain intact;
- H4 canonical problem validation and serialization remain intact;
- old/new evaluator inputs have proven canonical assessment parity;
- all required ordering, routing, identity, no-mutation, no-run, and
  regression tests pass;
- full Pytest, Ruff lint, Contract V1 Ruff-format, schema, serialization, and
  diff-scope gates pass;
- no UI, exporter, workbook, legacy algorithm, OR-Tools, V1-A1, or production
  cutover scope is introduced.

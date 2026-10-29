# Integrated vehicle and crew blocking V1

**Design verdict:** `DESIGN_READY_FOR_PO_REVIEW`, subject to the independent review record in section 12. This is a specification, not a solved rest-compliant Route 10 assignment or an operational approval.

**Evidence baseline:** `818b997d1726858e322e1bbb1420d3b03d979f78`, branch `feat/mvp5-route10-engine-pilot`. Review date: 29 October 2026. Scope: one fixed two-direction timetable, two terminals, one fixed driver/attendant team per vehicle for its entire daily block. No vehicle reuse by a second team, relief, deadheading, depot movement, timetable generation, production-score changes, GIS or new application platform.

The question is: **given these exact departures and declared working conditions, which resource minimum can be proved, and which feasible assignments can be independently verified?** A team means one driver and one attendant: K blocks require K vehicles, K teams, K drivers and K attendants, assuming both roles are required and distinct people fill them. It does not mean K individual employees.

## 1. Evidence, frozen timetable and existing behavior

P0 is the **p50 frozen C/I001 timetable**, not the original workbook B, recorded X, P1/P2, or the separately generated p75 C trial. For every runtime and duty sensitivity below, preserve the same P0 departure arrays. The workbook provides runtime observations; it does not directly supply this C timetable.

| Evidence | Identity and verification |
|---|---|
| Private `Bus10_MienTay_DHQG_A.xlsx` | SHA-256 `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b` |
| Private frozen MVP-6A `fleet_report.json` | SHA-256 `1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3`; schema `route10_fleet_pilot_v1`; pointer `scenarios[id=report_p50].comparison.C` |
| P0 departure identity | 51 outbound + 51 inbound. SHA-256 of UTF-8 `json.dumps(departures, sort_keys=True, separators=(',', ':'))`: `d20e26cc05c48a9d4c06c4937b1fc97e835be24d9f7c0f7dda46849c19f257a9` |
| Endpoints | A/outbound first 285 (04:45), B/inbound first 300 (05:00), both last 1260 (21:00), minutes from model-day midnight |
| Existing witness | 14 technical vehicle chains; starts A=8/B=6; nine inherited service-review exceptions. These start counts describe one assignment, not confirmed stock or a uniquely necessary terminal split. |

The source digests were checked locally. Reimporting the workbook and calling `runtime_scenarios`/`planning_bundle` reproduced both frozen runtime bundles exactly. Existing `validate_chains` and the separately built `SimpleMaxFlow` audit verified freshly assigned technical/task path covers. Private observations and full departure arrays remain in ignored evidence, not in this public specification.

All paths below are relative to `src/bus_schedule_engine/` unless otherwise stated.

| Existing module | Reuse | Boundary or missing constraint |
|---|---|---|
| `mvp/input.py` | `runtime_at`, integer/finite checks, validated runtime partitions and workbook adapter | `validate_bundle` rejects unknown fields. Keep crew policy in a separate envelope; do not insert new fields into existing bundles. |
| `mvp/circulation.py` | Arrival/ready convention, compatibility-DAG construction pattern, exact bipartite matching, `validate_chains`; stock-constrained CP-SAT reference | Finds minimum vehicle paths without duty/rest constraints. Its stock-limited search discards unproved feasible incumbents; the new result contract must retain them. No redesign of existing behavior. |
| `mvp/crew_review.py` | Independently useful dwell/exposure diagnostics and separation of technical time, terminal work, reserve and free time | Opportunities on one supplied assignment, not an integrated roster; meal windows evaluated separately; relief opportunities are outside V1. |
| `mvp/fleet_timespace.py` | A/B direction mapping, physical conservation/event ledger, disjoint activity reporting and no extra p75 margin | Read-only reconstruction; current meal policy accepts only `DUTY_INTERSECTS_WINDOW`; eight-hour flag is a screen; selected meals alone reset its exposure proxy. Do not treat this as a new-policy validator. |
| `mvp/peak_offpeak_pilot.py` | P0 source locks; independently auditable technical and 15-minute task connection scenarios | P1/P2 change departures and are excluded. One authored chain split is not a minimum rest-compliant cover. Hypothetical 8/6 stock is not operator authority. |
| `mvp/route10_pilot.py`, `route10_crew_review.py`, `route10_fleet_pilot.py` | Runtime provenance, frozen-evidence revalidation, `audit_fleet` maximum-flow cross-check | Do not rerun timetable optimization to redefine P0. The unrestricted flow audit cannot certify a stock-constrained or rest-constrained optimum. |
| `mvp/runner.py` and existing Excel exports | Table conventions, existing workbook/JSON consumers | New duties/report are additive, separately named outputs; existing recommendation, scoring and seven exports retain their behavior. |

Relevant existing tests are `tests/test_mvp_service_plan.py`, `test_mvp_acceptance.py`, `test_route10_pilot.py`, `test_crew_review.py`, `test_fleet_timespace.py` and `test_peak_offpeak_pilot.py`. They cover exact physical chains, stock, source locks, runtime boundaries, fixed-chain stress versus reassignment, continuous meals, disjoint reserve and conservation. None establishes the integrated optimum proposed here.

## 2. Complete input contract and policy authority

Use a separate, versioned `integrated_blocking_v1` request. The adapter reads the frozen timetable and validated bundle without mutation. A run is identified by the timetable digest, runtime digest, complete policy digest, stock mode and engine/dependency versions. Reject unknown constraint names and unsupported policy modes; missing never means zero or exemption.

| Required field | Meaning and validation |
|---|---|
| `schema_version`, `route_id`, `source` | Version, route 10, source digests/pointers and provenance per supplied parameter. Authority is `EXPERIMENTAL_DECLARED`, `OPERATOR_SUPPLIED_UNVERIFIED`, or source-backed operator authority; software cannot invent approval. |
| `timetable.trips` | Unique stable IDs, direction, integer departure minutes and source pointer. Identity is `(direction, ordinal)` with frozen departures; reject duplicates, missing trips or changed departure digest. |
| `terminals` | Exactly A and B; outbound A to B, inbound B to A. No travel arcs except scheduled passenger trips. |
| `runtime_scenario` | Exactly one named p50 or p75 profile per run, full directional half-open departure-time partitions, positive integer runtimes and provenance. Recompute arrival from departure/profile; ignore solver-supplied arrival claims. |
| `terminal_policy` | Technical q=5, post-arrival h=5, predeparture p=5 minutes at both terminals. All are separate, sequential, on-duty allowances, including technical and post work after the final trip and pre work before the first. They are not measured standards. |
| `recovery_policy` | Explicit runtime basis and complete nonnegative `reserve_by_arriving_trip` values, including explicit zeros. A trip's scalar rho_i applies identically to every chosen internal successor. No reserve is charged after a block's final trip. Reject successor-dependent reserve and final-arrival reserve as unsupported in V1. Use rho=0 when that traffic stress is already in the chosen runtime. Extra residual reserve requires a separate source/reason. |
| `crew_policy.assignment` | Exactly one fixed synchronized driver/attendant team per block, no relief, cross-vehicle sharing or reuse of a completed vehicle by a new crew. Both roles remain on duty through intermediate waiting. Task durations are elapsed team time, not two serial copies for two people. |
| `crew_policy.duty_limit_minutes` | Enabled positive integer, 480 or 600 in separate primary runs. Limit is elapsed first-preparation to final-post-task span, including waiting, recovery and meals; no split-duty subtraction. These are sensitivity assumptions, not legal certificates. |
| `crew_policy.driving` | Separate positive-integer total-driving limit or explicit `DISABLED_EXPERIMENTAL`; separate positive-integer continuous-driving limit C_max and qualifying reset length beta>0. Proposed sensitivity: C_max=240, beta=30 minutes. These values and the reset definition require PO/operator agreement; they are not inferred from a five-minute stop. |
| `crew_policy.meals` | Lunch [660,840), dinner [1020,1200), each positive integer B=30 continuous minutes; explicitly selected eligibility mode and nonnegative integer thresholds (section 3). Required for both synchronized crew roles under the experimental team policy. |
| `stock` | `RESOURCE_SIZING_UNCONFIRMED` (no numerical terminal caps), `EXPERIMENTAL_CAPS` with integers N_A/N_B, or `CONFIRMED_CAPS` with values and source/date. In all modes a block's vehicle starts at its origin terminal before its duty begins. |
| `resource_cap` | Explicit optional total K ceiling, with authority and purpose; absence means size resources. Do not inherit `bundle.fleet_ceiling=14` as an integrated limit. |
| `search` | Fixed solver version/seed, one worker, deterministic work limit, emergency wall limit, cancellation and memory/model-size limits; section 8. |
| `operating_date`, `operational_evidence` | Date may be null for a labelled hypothetical run. An actual operational-compliance request needs applicable work/reset policies, role duties, availability and terminal parking authority; missing evidence blocks that claim, not a fully declared experiment. |
| Optional `distance_km`, `commercial_km`, costs | Nonnegative finite trip/direction values, units, measurement basis, source and date. Preserve distinct meanings of cự ly and km vận doanh. Do not infer a round trip, empty running or money from an absent value. |

Times are half-open intervals on one model-day axis; arrivals may exceed 24:00 and must not wrap modulo 1440. P0 has whole-minute precision. V1 rejects fractional-minute inputs rather than rounding them into feasibility; a future exact shared integer scale would need an explicit contract change. Equal-time completion then departure is allowed only if every allowance has finished. Report horizon starts no later than the earliest predeparture task and ends after all final duties. Before/after duty, a vehicle still exists at its terminal but its crew is off duty. No pre-duty or post-duty interval is an internal meal.

Every rule has an explicit `ENFORCED` or `DISABLED_EXPERIMENTAL` mode. The latter is supported for synthetic isolation tests and labelled relaxations only: omit that rule's variables/constraints and report `CREW_RULES_DISABLED`, never integrated crew compliance. A test may disable an individual meal window; primary Route 10 runs enforce duty, both meals and the chosen continuous-driving policy. Missing fields do not disable anything. Durations, reserves and technical/post/pre tasks are finite integers with the positivity/nonnegativity bounds above; windows are ordered, nonoverlapping and long enough for B. Stock values are nonnegative integers; an enabled resource cap is a positive integer. Reject booleans, fractional/nonfinite values, beta=0, C_max=0, unsupported modes and incomplete reserve maps before model construction.

For the primary experiments, use V_max=H as an enforced, redundant arithmetic driving bound implied by elapsed duty. This adds no legal daily-driving interpretation. A stricter sourced total-driving cap, if supplied, must be declared separately and changes the model; disabled total-driving rules belong only to the labelled isolation/relaxation cases above.

No terminal capacity, parking authorization, driver availability, weekly schedule, night-work/overtime treatment or runtime reliability is established by P0. Those remain unresolved operational evidence. Unsupported hard constraints must be rejected explicitly, not silently omitted. Optional distance/cost input is not needed for feasibility.

## 3. Duty, meals, protected rest and recovery

For a path P=(i_1,...,i_k), with departure d_i, runtime r_i and arrival a_i=d_i+r_i:

```text
S(P) = d_first - p
E(P) = a_last + q + h
D(P) = E(P) - S(P)                  elapsed duty
V(P) = sum(r_i for i in P)          driving exposure
```

Require D(P)<=H and V(P)<=V_max if the latter is explicitly enabled. The driving limit C is a different resource: accumulate driving durations between qualifying protected rests. Waiting or terminal work does not reset it. A trip longer than C cannot be made compliant by a break before/after it; there is no mid-trip rest in V1. Attendants do not acquire a driver-only statutory rule by inference; the team can share the experimental rest schedule while driver exposure is checked separately.

Report active work as driving plus technical/post/pre task minutes, and report continuous work exposure as the maximum elapsed on-duty interval between protected rests qualifying under the declared reset policy, including intermediate waiting/recovery but excluding the qualifying rest itself. This latter metric is a labelled exposure proxy, not a legal definition of work or a hard continuous-work limit. Use the actual selected rest-union boundaries; do not infer it from driving totals.

### 3.1 Meal applicability: a policy choice, not an inferred legal rule

For meal m with window [L_m,U_m), define overlap O_m(P)=max(0,min(E(P),U_m)-max(S(P),L_m)).

| Mode | Required meal predicate | Consequence |
|---|---|---|
| `DUTY_INTERSECTS_WINDOW` | O_m(P)>0 | Reproduces the existing conservative screen, including a duty ending at 11:01 that owes lunch despite having only one minute in the window. A singleton can consequently be impossible even with unlimited buses. |
| Proposed `SUSTAINED_WINDOW_DUTY` | D(P)>=D_min **and** O_m(P)>=O_min,m | Based on sustained duty rather than trivial overlap. Proposed experimental D_min=360, O_min,lunch=O_min,dinner=60 minutes. Early-finish/late-start duties can be exempt; a 12:00–20:00 duty requires both meals. Thresholds are policy choices, with explicit inclusive boundaries. |

Recommend the second mode for the V1 experiment, and retain the first as a named sensitivity. **PO must select the predicate and thresholds before a run is described as authoritative.** The proposed rule does not claim to encode all working-time break entitlements. For example, a long duty outside both meal windows may need another statutory/operator break. The current specification can model general protected driving-reset rests, but a separate general work-break entitlement is unsupported until explicitly specified. Unknown entitlement policy blocks an operational certificate.

A required meal must occur between assigned trips, wholly inside its window, after all post-arrival/technical/recovery commitments and before predeparture work. Ending a duty early is a legitimate modelling choice; pretending an off-duty interval is a meal inside that duty is not. Report exemptions and exact duty/overlap values so the PO can see threshold effects. Optional meals may be selected, but cannot discharge another window's requirement.

### 3.2 One interval budget; no reuse of work/recovery minutes as rest

For a chosen connection i->j at the destination of i:

```text
gap       = d_j - a_i
free L_ij = a_i + q + h + rho_i
free U_ij = d_j - p
free F_ij = [L_ij,U_ij)
gap = q + h + rho_i + protected_rest_union + other_free_wait + p
```

All terms on the last line are nonnegative and disjoint physical durations. A meal is one labelled component of protected rest. A meal may also *qualify* as a driving reset: this is one physical rest with two policy consequences, counted once in the interval ledger. It cannot simultaneously be terminal work or committed recovery. Residual free waiting remains on duty and does not reset driving unless explicitly selected as protected rest under the agreed policy. No unavailable attendant/driver or substitute is assumed to cover terminal tasks during a meal.

Reserve is defined only for internal connections and depends on the arriving trip, not its successor. Final duty closes at a_last+q+h with no extra reserve. An operator requirement for successor-dependent recovery or recovery after the last arrival requires a later contract/formulation revision; it cannot be silently represented by the current rho_i or E(P).

Example: arrival 11:00, next departure 11:45, q/h/p=5 each and rho=0 gives free [11:10,11:40), exactly one 30-minute lunch. Adding rho=5 leaves 25 minutes and invalidates that lunch. Several 10/15-minute opportunities do not sum to one meal.

Runtime and traffic-stress definitions stay separate:

| Scenario | Arrival and reserve | Interpretation |
|---|---|---|
| `P0_P50_NOMINAL` | d+r50, rho=0 | p50 duties and exposure, tasks enforced |
| `P0_P75_STRESS` | d+r75, rho=0 | p75 duties and exposure, tasks enforced; no second charge for r75-r50 |
| Optional p50 reserve diagnostic | d+r50, rho=max(0,r75-r50) on internal connections | Same internal readiness as p75, but final arrival/duty length and driving totals are still p50. It is not a robust p75 crew certificate. |

Primary experiment: four separate optimization problems, p50/p75 crossed with H=480/600, under one fully declared meal/reset/stock policy. Do not mix p50 arrivals with p75 driving, pool scenario totals, average minimum fleets, or claim a common assignment from two independent solutions. Cross-testing a p50 assignment at p75 is an additional fixed-assignment check. A common assignment across runtimes is outside this first milestone.

## 4. Independently recomputed lower bounds

The runtime profiles use existing nearest-rank empirical quantiles, rounded upward to whole minutes, in the existing half-open departure-time partitions. They are summaries of recorded X report clocks applied hypothetically to P0, not calibrated traffic distributions or on-time probabilities. Observation counts differ from P0 departure counts.

| Direction and departure period | X observations | P0 trips | p50 minutes | p75 minutes |
|---|---:|---:|---:|---:|
| outbound [285,360) | 5 | 5 | 92 | 92 |
| outbound [360,540) | 10 | 11 | 111 | 115 |
| outbound [540,930) | 19 | 19 | 108 | 113 |
| outbound [930,1095) | 6 | 8 | 141 | 146 |
| outbound [1095,1261) | 11 | 8 | 97 | 106 |
| inbound [300,390) | 6 | 6 | 97 | 98 |
| inbound [390,540) | 9 | 9 | 111 | 112 |
| inbound [540,960) | 17 | 20 | 104 | 107 |
| inbound [960,1110) | 9 | 8 | 126 | 130 |
| inbound [1110,1261) | 10 | 8 | 88 | 89 |

P0 p50 workload = (5*92+11*111+19*108+8*141+8*97) + (6*97+9*111+20*104+8*126+8*88) = 5637+5373 = **11010 minutes = 183.5 vehicle-hours**. p75 analogously gives **11376 minutes = 189.6 hours**. Neither is a sum of crew duty spans.

For the ordinary DAG path-cover problem, split each trip into a left/right vertex; compatibility arcs have unit capacity. If the maximum matching is M, minimum paths = n-M: a K-path cover has n-K connections constituting a matching; conversely a matching yields vertex-disjoint paths because the graph is acyclic. Independently solved unit-capacity max flow and an equal-capacity minimum cut certify maximum matching, while reconstructed paths certify the upper bound.

| Same 102 P0 departures; unrestricted initial stock; no crew rules | Compatibility edges | Matching / cut capacity | Exact minimum paths |
|---|---:|---:|---:|
| p50, technical allowance 5 only | 2039 | 88 / 88 | **14** |
| p50, q+h+p=15 | 1987 | 86 / 86 | **16** |
| p75, technical allowance 5 only | 2016 | 87 / 87 | **15** |
| p75, q+h+p=15 | 1978 | 86 / 86 | **16** |

The tested p75-plus-tasks minimum 16 is therefore verified, **before meals and duty limits**. Its existing matching witness starts A=9/B=7; that is one feasible split with unconstrained supply. It is not an exact stock-constrained answer. Fourteen is the technical p50 minimum under weaker assumptions, not the integrated target. Failure of the existing fourteen fixed chains at p75 does not itself prove a global fleet minimum; the independent path-cover calculation does.

If each fixed driver can drive no more than its elapsed H-minute duty, K*H>=W gives the requested arithmetic workload bounds:

| Scenario | H=480 | H=600 |
|---|---:|---:|
| p50 driving only, W=11010 | ceil(11010/480)=**23** | ceil(11010/600)=**19** |
| p75 driving only, W=11376 | **24** | **19** |
| p50, also count all q/h/p in duty | ceil((11010+102*15)/480)=**27** | ceil(12540/600)=**21** |
| p75, also count all q/h/p in duty | ceil(12906/480)=**27** | ceil(12906/600)=**22** |

The stronger task-inclusive bounds follow because every trip contributes its driving plus 15 disjoint on-duty minutes, even at block boundaries. They depend on the explicitly serial task assumption; changing overlap/task treatment requires recomputation. Meals, recovery and other waiting can increase required resources further. No row proves a feasible assignment with its stated fleet. In particular, **19 or 23 buses/teams cannot be the p50 integrated optimum under this specification's task and elapsed-duty assumptions**, although they remain correct weaker driving-only bounds.

Bounds available from declared input alone include total workload, maximum simultaneous driving occupancy, and terminal stock-prefix necessary conditions. Matching/min-cut additionally certifies the complete compatibility graph's path minimum. Duty-based workload bounds require H and its meaning; task-inclusive bounds require task accounting; meal/reset bounds require eligibility and reset policy; a stock infeasibility conclusion requires actual or explicitly hypothetical caps. There is no unconditional numerical crew lower bound from departure clocks alone without runtimes and a working-condition model.

For terminal T at time t, a useful relaxed necessary stock bound is max_t(departures_T(<=t)-all_arrivals_T(<=t)), counting arrivals before same-time departures. It ignores readiness and parked-finished restrictions, so is not sufficient. With a selected path cover, count every block origin instead: vehicles for late starts are already stationed at that terminal. Finished vehicles stay in physical inventory but cannot be assigned a second block. In resource-sizing mode report the chosen A/B split and its authority as unconfirmed; never label its two components separate minima without additional proofs.

### 4.1 Reproduction without a new solver

The following uses only existing code; the private frozen path is supplied by the caller. First verify the workbook digest and regenerate/compare the runtime bundles as described in section 1. For each fresh cover, `audit_fleet` independently rebuilds the graph and solves max flow, then validates the chains.

```python
import json
from copy import deepcopy
from hashlib import sha256
from math import ceil
from pathlib import Path
from bus_schedule_engine.mvp.circulation import assign_fleet
from bus_schedule_engine.mvp.input import runtime_at
from bus_schedule_engine.mvp.route10_fleet_pilot import audit_fleet

raw = Path(FROZEN_EVIDENCE_PATH).read_bytes()
assert sha256(raw).hexdigest() == '1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3'
rows = {r['id']: r for r in json.loads(raw)['scenarios']}
departures = rows['report_p50']['comparison']['C']['departures']
assert all(len(ts) == 51 for ts in departures.values())
assert sha256(json.dumps(departures, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == 'd20e26cc05c48a9d4c06c4937b1fc97e835be24d9f7c0f7dda46849c19f257a9'
for name, workload, expected in [('report_p50', 11010, (14, 16)),
                                  ('report_p75', 11376, (15, 16))]:
    data = deepcopy(rows[name]['bundle'])
    assert 'initial_vehicles' not in data
    W = sum(runtime_at(data['directions'][d], t)
            for d, times in departures.items() for t in times)
    assert W == workload
    print(name, W, [ceil(W / H) for H in (480, 600)])
    for allowance, minimum in zip((5, 15), expected):
        data['layover_minutes'] = dict.fromkeys(departures, allowance)
        cover = assign_fleet(data, departures)
        assert audit_fleet(data, departures, cover) == minimum
```

`within_fleet_ceiling=False` for a fresh unrestricted cover above fourteen is a diagnostic, not a failed exact calculation. Reproduction must not add initial caps or change departures to force the benchmark. Archive matching/min-cut witnesses in future run evidence, not merely the scalar minimum.

## 5. Two viable formulations and choice

| Formulation | Soundness conditions | Single-route V1 trade-off |
|---|---|---|
| Resource-constrained paths plus set partitioning | Let P be all executable duty/rest-compliant paths and A_ip their trip incidences. Minimize sum(y_p), subject to sum(A_ip*y_p)=1 for each trip and origin-count caps; y_p binary. Each column includes its rest witness. | Clear block-level semantics, but up to 2^102-1 nonempty subsets before feasibility filtering. Bounded generation gives only a restricted master. A restricted LP objective is not a global lower bound; exact pricing at the root alone does not prove the integer optimum. Complete generation or exact branch-and-price/proof is required. Too much machinery for V1. |
| **Compact CP-SAT on the existing DAG (recommended)** | Complete compatible edge set; unlabelled start/end flow and per-trip propagated resources; meals/resets on chosen interior edges. No candidate-block truncation. | Reuses installed OR-Tools and deterministic settings, avoids bus-label symmetry and an exponential path pool. Thousands of edges/Boolean variables, with transparent proof statuses. Remains NP-hard; bounded runtime does not guarantee an optimum. |

Choose the compact formulation below. The path formulation states the underlying resource problem and provides a tiny-case independent enumeration oracle; it is not a second production solver to implement now. No column-generation service, generic scheduling framework or new optimizer dependency is needed.

## 6. Compact mathematical formulation

### 6.1 Complete physical/task DAG

Let I be the fixed trips, sorted by `(departure, trip_id)`. For a given scenario, create every edge

```text
(i,j) in E iff destination(i)=origin(j), d_i<d_j,
                 a_i+q+h+rho_i+p <= d_j.
```

This is a filtered version of the existing compatibility DAG; its terminal allowance is the **sum** of components, not a replacement for one component. Retain a physical/technical DAG separately for lower bounds. With positive runtimes/allowances, E is acyclic. Do not limit successors to the nearest departure, demand regime, current vehicle chain or a top-k list: those restrictions would remove legitimate rest-compliant solutions.

Binary variables x_ij choose edges; s_i and t_i mark a path start/end. All trips are compulsory:

```text
s_i + sum_j x_ji = 1       for every i
t_i + sum_j x_ij = 1       for every i
K = sum_i s_i = sum_i t_i
sum_{origin(i)=T} s_i <= N_T     when terminal caps are declared
K <= K_cap                     only when explicitly requested
```

These constraints cover every trip once and form disjoint paths; no cycle/subtour machinery is needed on a DAG. One path receives one unique vehicle/team ID after extraction. No end-to-start link across paths exists, even if a vehicle finishes at the same terminal as another path starts later.

### 6.2 Duty and total exposure propagation

Let S_i be duty start and V_i cumulative driving through trip i. Use bounded integer domains from the model horizon and W. Reified equalities mean **only when their indicator is true**, with no arbitrary loose big-M constants:

```text
s_i=1  => S_i=d_i-p, V_i=r_i
x_ij=1 => S_j=S_i, V_j=V_i+r_j
t_i=1  => (a_i+q+h)-S_i <= H
t_i=1  => V_i <= V_max              if enabled
```

At a path end i, E_i=a_i+q+h is known; evaluate the chosen meal eligibility predicate using S_i/E_i. Duty feasibility may also be imposed at every prefix because the path's final end can only be later. Do not reject a prefix merely because its required meal has not happened yet while a future eligible gap can still satisfy it.

### 6.3 Continuous meal coverage

For each edge e=(i,j) and meal m, precompute the free interval F_e from section 3 and the meal opportunity

```text
l_em = max(L_e,L_m)
u_em = min(U_e,U_m)
A_em = 1 iff u_em-l_em >= B
```

Binary b_em selects that meal, with b_em<=x_e and b_em<=A_em. Its witness is `[l_em,l_em+B)`. Earliest placement is sufficient for these V1 constraints: free time is contiguous, meal windows do not overlap, duties are fixed by their endpoint trips, and driving accumulation has no driving inside a gap. No other flexible task competes inside F_e. If such tasks or a hard maximum continuous-work rule are later introduced, this earliest-placement reduction must be reconsidered.

For each trip/meal let M_im be a binary prefix count:

```text
s_i=1  => M_im=0
x_ij=1 => M_jm=M_im+b_(ij)m
t_i=1  => M_im >= Required_m(S_i,E_i)
```

The binary domain allows at most one meal of each type per path. No summing short gaps, no meal before its first trip/after its last trip, and no lunch counted as dinner. A long gap may hold both lunch and dinner because the windows are distinct; it remains paid/on-duty span for H. Optional meals are permitted even when `Required=0`.

### 6.4 Continuous driving is a separate resource

Under the proposed experimental reset policy, a **selected uninterrupted protected rest** of at least beta minutes at a terminal resets driving accumulation. The break need not be in a meal window; a selected meal qualifies if its duration reaches beta. General free waiting is not automatically a reset.

For each edge let A_e^R=[U_e-L_e>=beta], with beta>0. Binary z_e chooses a reset; z_e<=x_e and z_e<=A_e^R. If selected, reserve witness `[L_e,L_e+beta)` as protected rest. It may overlap a selected meal because both are the same permissible rest activity; report the union once. When B>=beta enforce z_e>=b_em for each meal. The fixed nonoverlapping meal windows mean meals alone cannot create an unmodelled longer continuous union in this V1 policy.

Let C_i be accumulated driving since the latest qualifying rest, measured at arrival of trip i:

```text
s_i=1                    => C_i=r_i
x_ij=1 and z_ij=0        => C_j=C_i+r_j
x_ij=1 and z_ij=1        => C_j=r_j
0 <= C_i <= C_max        for every i
```

Driving during one trip is monotone, so checking arrivals suffices when rests occur only between trips. A reset affects exposure, not duty start, total driving, terminal inventory or mandatory meal coverage. Other definitions (elapsed work since a break, split resets, five-minute stops, role-dependent duties) are unsupported hard-policy modes until explicitly designed. Continuous **work** exposure is reported from actual activity intervals, separately from this driving accumulator; no work limit is silently substituted for C_max.

### 6.5 Objective and formulation guarantee

Minimize K subject to **all** constraints. The requested hierarchy is a hierarchy of obligations and reporting: (1) exact coverage/physical/team feasibility, (2) mandatory duty/meal/rest rules, (3) declared recovery/tasks, (4) minimum feasible resource count, (5) operating quality/cost supported by evidence. Items 1–3 all define the feasible set. No weighted penalty buys permission to violate them.

After proving K*, optionally fix K=K* and minimize total elapsed duty or an agreed quality metric. If that secondary search stops, keep the proved resource optimum and distinguish secondary optimality. Minimum recovery is hard if declared; extra residual recovery may be a secondary quality measure. Fixed departures leave trip totals and passenger waiting unchanged. Distance totals also remain fixed for identical trips; no monetary savings are claimed without verified cost parameters.

**Soundness:** each selected path has correct terminals, nonoverlapping task/rest budgets, fixed team, valid elapsed/total/continuous driving and required meals. **Completeness within the declared V1 model:** every feasible block assignment maps to flow variables and resource states. Any feasible meal can be moved to its earliest opportunity without conflict; any qualifying reset can be placed at the start of the free interval without changing driving between trips. Thus no feasible block is removed by not enumerating break start times. This argument relies on the explicit absence of other flexible work, terminal-capacity interactions and hard continuous-work limits.

## 7. Initial stock, availability and resource meaning

Resource sizing lets each selected block start at its origin and reports K and origin totals. This assumes enough hypothetical vehicles/teams already stationed there before preparation. It does not assume a later depot arrival. Experimental stock 8/6 can be tested as a hard sensitivity, but is not confirmed availability. Under those caps and a total cap of fourteen, the integrated task/duty workload bounds already prove infeasibility **of that declared scenario**, not of Route 10 with more resources.

Known initial stock caps require `sum starts at A<=N_A`, similarly B, including late-start paths. With this no-reuse model, physical arrivals from completed paths do not authorize additional crew starts. A selected path may park at its terminal across a gap; parking capacity and authority remain separate operational evidence. Stock conservation at every event checks no disappearance, teleportation or negative inventory; it does not certify readiness or permission to park.

Once individual vehicles/people have heterogeneous availability, maintenance or qualifications, the interchangeable-resource assumption fails. V1 must block that unsupported authoritative input rather than silently assign IDs. Unused stock does not require a team in the resource count. Selected crew pairs remain unique across blocks throughout the day.

## 8. Bounded strategy, proof status and retained evidence

1. Validate input identities, declared policies and authority mode. Build complete DAG, free/meal/reset opportunities and input-only bounds. If a mandatory value is absent, return `BLOCKED_INPUT_AUTHORITY` with the exact field. A fully declared hypothetical policy is permitted with conditional operational authority.
2. Compute unrestricted exact technical/task path covers with existing matching and independent max-flow checks. These are lower bounds, not integrated feasible incumbents. Combine valid bounds by **max**, not sum. A stock/resource cap below a proved lower bound provides an independent infeasibility certificate.
3. Build one complete compact model per scenario. Seed with a previous independently validated integrated solution only when timetable/runtime/policy/stock checks match. Validate singleton or split-path heuristics before treating them as an upper bound: strict meal eligibility or reset limits can make a singleton invalid. Never assume K<=102 is attainable; it is only a maximum number of nonempty blocks in any feasible solution.
4. Run deterministic single-worker CP-SAT with fixed seed 0 and pinned OR-Tools (currently 9.15.6755). Proposed per-scenario limits: 10 deterministic seconds, 60 wall seconds; global 300 wall seconds for the four primary scenarios including preprocessing/validation. Predeclare a 1 GiB process-memory ceiling and abort conservatively on breach; do not relax constraints. These are engineering budgets to calibrate, not measured solve-time promises. Deterministic work limits/order are the reproducibility basis; an emergency wall/memory cutoff can change search progress and must be recorded.
5. At every complete incumbent, retain its objective and extracted assignment; validate promptly and keep the best **verified** feasible incumbent in an atomic checkpoint. If validation is pending at cutoff, only an earlier verified incumbent may be advertised. Use monotone K improvement, then agreed secondary metric and canonical trip-chain order for ties. No best assignment is overwritten by a failed or weaker later trial.
6. At cutoff/finish, independently validate the best assignment, record solver bound, proof scope and stop reason. Native model-invalid or extraction/validation errors are internal failures, reported as `SEARCH_INCOMPLETE` with an error reason and any earlier verified witness, never as route infeasibility.

The [OR-Tools solver documentation](https://developers.google.com/optimization/cp/cp_solver) distinguishes optimal, feasible, infeasible and unknown native statuses and requires integer constraints. Application statuses add input authority, independent witness validation and completeness of the searched model.

| Application status | Required evidence |
|---|---|
| `OPTIMAL_PROVEN` | Valid complete-model assignment with U=K and a sound global lower bound L=U, or a complete exact proof with independently validated incumbent. A matching relaxation alone proves no integrated upper bound. |
| `FEASIBLE_NOT_PROVEN_OPTIMAL` | At least one independently verified complete assignment; no global proof L=U. Include current L/U and why the search stopped. |
| `INFEASIBLE_PROVEN` | Complete exact model proved infeasible, or an independent valid impossibility certificate (e.g. cap<L, or a compulsory trip longer than the enabled continuous-driving limit). State exact scenario/caps and evidence. |
| `SEARCH_INCOMPLETE` | No verified complete assignment and no global infeasibility proof, or an internal model/validation failure. Native `UNKNOWN` is not infeasibility. |
| `BLOCKED_INPUT_AUTHORITY` | Missing/contradictory essential input or undefined required policy/authority for the requested claim. List fields and the narrower hypothetical analyses, if any, still valid. |

Store `native_status`, `model_complete`, `validator_pass`, `proof_scope`, `termination_reason`, objective, bounds, versions, limits, actual deterministic/wall work, input/code digests and unresolved authority separately. An experiment may be mathematically optimal while operational approval is unverified. Exceeding an arbitrary pilot cap is not evidence of timetable infeasibility without that cap.

For minimization report L=max(independent valid bounds, certified full-model solver bound), integerized conservatively, U=best validated K, absolute gap U-L and relative gap (U-L)/U. Set relative/absolute proof tolerances to zero. With no U report no finite upper bound/gap. A feasible optimum of an incomplete candidate master gives an upper bound only. Its solver bound is not a global lower bound; its infeasibility is restricted. Only independent L=U can close that gap without complete candidates. Store bounds with provenance, scenario and objective; do not transfer a bound from different policy/runtime assumptions without a proved relaxation relation.

### 8.1 Search scope and explosion safeguards

For 102 trips, a generic DAG has at most 5151 ordered forward pairs; the two-direction 51/51 route has at most 2601 cross-direction pairs. P0 task graphs actually have 1987 p50 and 1978 p75 edges. The proposed model uses O(|E|+|I|*2) variables/constraints plus constant-size reifications per edge, not 102 interchangeable bus slots times every edge. There are at most two meal choices and one reset choice per edge, plus per-trip state. No departure decisions or minute-by-minute occupancy grid exist.

The global combinatorial search can still be exponential. Reject requests above 102 trips, two terminals/two nonoverlapping meal windows, or the declared edge/model-memory budget rather than silently truncating. Use complete arithmetic filtering, positive-duration/DAG checks, tight state domains, deterministic arc order, explicit time/memory limits, cancellation checkpoints and retained incumbents. Do not assert that all 102-trip instances will solve optimally in the budget. Resource/path pruning is allowed only with a written validity argument; sampled successors, beam search and prefix-meal rejection before a window closes invalidate completeness claims. Exhaustive path generation is not part of the recommended strategy.

## 9. Independent validator and proof obligations

The validator reads the immutable trip table, profiles, policy and an assignment witness; it does not trust model states, cached arrival/readiness, opportunity flags or native status. It must use a separate reconstruction, not call the new model's edge/free-interval/eligibility helpers to validate those same calculations.

For every selected block, independently:

1. Reconcile trip IDs/departure digest and assert exactly-once coverage of all 102 trips, one vehicle/team per nonempty block, no vehicle or person reused across blocks.
2. Recompute runtime by direction/departure, arrivals, terminal positions and every chronological connection. Rebuild technical, post, reserve and pre intervals. Reject even a one-minute shortfall; never shift departures to repair it.
3. Compute first-pre/final-post duty boundaries, elapsed span, total driving and role activities. Recompute eligibility from actual S/E and require every mandatory meal at its proper terminal/window, continuous length>=30, contained in one free interval.
4. Reconstruct the **union** of protected rests, verify reset qualification, and accumulate driving trip by trip between them. Recompute reported maximum continuous driving and continuous work separately. Work/recovery intervals must never overlap protected rest. Required meals remain separate labelled intervals even if one long protected rest covers both windows.
5. Count starts at A/B, test optional stock/total caps, and reconstruct the physical ledger through all initial/arrival/readiness/departure/final events. Late starts were already present initially. Check both nonnegative terminal inventory and constant total physical vehicles. Finished vehicles cannot become another block.
6. Compare every reported metric to the reconstruction and verify that all assumptions appear in the report. Keep offending trip/edge/window/role IDs and computed shortfall. An invalid witness is never a feasible upper bound.

Reuse `validate_chains` on a derived bundle/legacy-shaped physical view with connection allowance q+h+p when reserve is zero; retain the original bundle. It checks physical identity/coverage and scalar terminal allowance but cannot replace the independent duty/rest checks or handle arbitrary per-trip reserve alone. `audit_fleet` certifies the unrestricted **relaxation**, not the chosen larger rest-compliant K. Keep solver proof checks distinct from witness checks: the latter proves feasibility, not global optimality. Retain solver response/model/log digests and matching/flow-cut certificates for review. Tiny exhaustive oracles test global optimality on independently enumerable instances.

## 10. Acceptance specification with known answers

Synthetic clocks below are minutes from midnight; `O d->a` means outbound A->B, `I d->a` inbound B->A. Unless overridden, q/h/p=5, rho=0, H=600, unlimited hypothetical initial stock, and meals/reset limits disabled **explicitly for the stated isolation test**. Disabled rules are never called crew-compliant. Fixtures can supply exact trip runtimes without the Route 10 source locks. Every expected optimum below has a witness and a simple lower bound; the integrated solver is not the source of its own expected answer.

| Case | Input/policy | Independently known answer |
|---|---|---|
| T1 ordinary path cover | O 480->500, I 515->535, O 550->570; all crew rules off | K*=1, chain all three. Same graph passed to existing matching. |
| T2 meals need another resource | O 600->630, I 645->675, O 690->720, I 735->765, O 780->810, I 825->855. Only lunch enabled under intersection eligibility | With meals off K*=1. Every connecting free interval on the unique one-block chronological chain is empty, so lunch-on K>=2. K=2 witness [trip1,trip4,trip5] has lunch 660–690; [trip2,trip3,trip6] has lunch 730–760. Both duties require lunch. Dinner off in this isolated case. |
| T3 morning-only/afternoon-only | Separate O 360->420, I 435->495; and O 900->960, I 975->1035 | Under sustained mode both duties are <360, owe neither meal; K*=1 for each separate case. Under intersection mode afternoon path owes dinner and has none; even its final singleton intersects dinner without an internal gap, proving that policy variant infeasible. |
| T4 fragmented rest | O 600->660, I 690->720, O 750->780, I 810->850, prescribed as one block; intersection lunch | Free intervals are 15,15,15 minutes. Reject lunch; 45 summed free minutes do not create a 30-minute continuous break. |
| T5 one missing required window | Prescribed path O 600->660, I 720->780, O 900->960, I 975->1035 | Intersection rule requires lunch and dinner. Lunch 670–700 exists; dinner has no gap. Reject the full assignment even though lunch passes. |
| T6 right terminal, too late | O 600->660 followed by I 674->734 | Physical destination matches but readiness is 675: no edge. K*=2 with stock at both origins. At departure 675 the edge exists and K*=1. |
| T7 p50 versus p75 | O dep600, runtime50=60/runtime75=70; I dep675, runtime=60 in both | p50 K*=1; p75 K*=2. A p50 fixed-chain witness fails under p75; reassignment with another initial B vehicle succeeds. No doubled traffic margin. |
| T8 initial stock | O 480->500 and I 480->500 | K*=2 with N_A=N_B=1. N_A=2,N_B=0 is infeasible despite the same total; no repositioning. |
| T9 proved duty infeasibility | One O 600->1080; H=480; driving/rest rules off | Single duty spans 495 minutes including endpoint tasks. No assignment exists even with unlimited vehicles. |
| T10 bounded unproved search | T2, valid K=2 incumbent retained and exact crew-disabled matching bound L=1; force cutoff before integrated search proves a bound | `FEASIBLE_NOT_PROVEN_OPTIMAL`, L=1/U=2. The test harness knows the optimum from independent enumeration; the interrupted solver has not certified it. A second cutoff before any witness gives `SEARCH_INCOMPLETE`. Never label the forced cutoff infeasible. |
| T11 continuous driving separate | O 480->580, I 595->695, O 710->810; C=240, beta=30 | H permits one block but no reset gap exists: one-block exposure=300, so K>=2. [trip1,trip2] has exposure 200; [trip3] has 100, giving K*=2. A five-minute turnaround cannot reset the one-block exposure. |
| T12 reserve/rest boundary | O 600->660, I 705->765, prescribed one block; intersection lunch | rho=0 gives lunch 670–700; rho=5 leaves [675,700), so reject. Verify neither meals nor reserve consume the same minutes. |
| T13 eligibility thresholds | Directly evaluate sustained mode at D=359/360 and meal overlap=59/60 | Required iff both inclusive thresholds hold. A duty ending at L or starting at U has zero intersection. Strict mode with overlap=1 differs visibly. |
| T14 caps and incomplete columns | T2 with K_cap=1; compare complete small oracle to a deliberately incomplete pool | Complete problem infeasible at cap1; without cap K*=2. Removing valid columns may produce restricted infeasibility, which must not become global `INFEASIBLE_PROVEN`. |
| T15 reserve input scope/final boundary | Same arriving trip supplied with two different successor reserve requirements, or any requested final-arrival reserve | Reject unsupported policy input with `BLOCKED_INPUT_AUTHORITY`. For a supported singleton O 600->660 and rho_i=20, duty still ends at 670 because no internal connection exists; no final 20-minute reserve is invented. |
| T16 explicit modes/positive reset | Missing rule mode, beta=0, C_max=0, nonfinite/fractional reserve, or negative eligibility threshold | Reject before model construction. Explicitly disabling a rule omits only its variables/constraints and emits `CREW_RULES_DISABLED`; re-enabling it restores the known T2/T11 outcomes. |

Additional mandatory validator mutation tests: duplicate/omitted trip, wrong bus/team identity, fabricated arrival, same-direction continuation, overlapping meal/task, reset outside free time, dinner counted as lunch, late-start vehicle materialized at a terminal, reused finished vehicle, missing policy authority, fractional time and negative/nonfinite duration. Test half-open equality, last runtime-period inclusion and final-task inclusion. Exhaustive enumeration on tiny graphs must independently reconstruct intervals/eligibility and agree with the compact model when it claims an optimum. Tests must not simply mirror its reified constraints.

Route 10 integration acceptance locks both input digests, the P0 departure digest, all 102 identities, the four path-cover benchmarks and workloads above. Test four runtime/duty scenarios separately with one explicit policy. Require independently validated assignments and honest statuses; **do not assert an as-yet-unknown rest-compliant fleet number**. Preserve existing recommendation/scoring/export acceptance, all nine service-review exceptions and PR #63 Draft/unmerged state. Deterministic repeated runs should agree absent emergency cutoffs; cutoff runs must still preserve the strongest verified incumbent and state their proof limits.

## 11. Table interfaces and minimal future implementation

Excel remains the primary planning interface. A new, separately named `integrated_vehicle_crew_v1.xlsx`, with an inspectable JSON companion, has three principal tables:

| Table | Required columns |
|---|---|
| **Timetable** | trip ID, direction/A-B terminals, unchanged departure, scenario arrival/runtime, bus ID, team/driver/attendant IDs, scenario/policy IDs and source pointer |
| **VehicleCrewDuties** | block/bus/team IDs, ordered trip IDs, initial/final terminal, duty start/end/span, total/max continuous driving, continuous work exposure, per-connection dwell/tasks/reserve, lunch/dinner requirement and selected intervals/terminal, reset intervals, other waiting, remaining uncommitted recovery |
| **FeasibilityReport** | declared scenario/policies/authority, solve status/proof scope/stop reason, K vehicles/teams and individual role counts, stock required/available by terminal, L/U/gaps, witness validation, violations/shortfalls, assumptions and unresolved operator evidence |

Use linked detail rows for multiple gaps/breaks rather than comma-separated clocks as the only evidence. Remaining recovery is the residual interval budget after work and the **union** of selected rests, not the whole dwell. For p75, distinguish embedded traffic stress from any separately sourced reserve. Missing arrival/assignment or no incumbent stays blank with a reason; never fabricate a timetable. Optional distances include source/unit columns. Cost columns are absent or explicitly unknown until verified rates exist. A failure report may show violated proposed assignments for diagnosis, clearly excluded from feasible solutions.

Keep existing `departures`, stable `trip_id`, `vehicle_id`, `chains`, `required_fleet` and `initial_vehicles_required` shapes in a derived physical assignment view. Use a new schema for integrated statuses and crew witnesses; never change the meaning of existing `EXACT`, `quality.hard_constraints_pass` or production recommendation. Do not feed a rest-constrained K into an API whose contract is unrestricted minimum fleet. Demand/waiting scores are copied with provenance or rechecked unchanged, never reoptimized.

| Minimum new module (future) | Responsibility |
|---|---|
| `mvp/integrated_blocking.py` | Validate separate request, build complete arc/resource CP-SAT model, retain incumbents and bounds, extract canonical path/rest witnesses. Small local helpers; no new framework. |
| `mvp/integrated_blocking_validation.py` | Independent reconstruction and all duty/rest/stock checks; does not import the solver's mathematical helpers. |
| `mvp/integrated_blocking_report.py` | Three-table XLSX plus JSON, using installed openpyxl and existing privacy/provenance conventions. |

Future entry point can be one thin CLI alongside existing scripts, reading the pinned frozen evidence and separate policy file. No UI page is required. Implementation sequence, **not authorized by this design-only milestone**:

1. PO resolves section 13 choices and supplies/labels authority. Freeze request/result/witness examples and tiny cases; implement input validation and the independent validator first, testing hand-constructed valid/invalid assignments.
2. Implement only the compact model and deterministic checkpoint/status contract. Compare crew-disabled cases to existing matching and small integrated cases to exhaustive independent oracles. Do not replace existing fleet code.
3. Add the three Excel tables/JSON and provenance, write one thin CLI, and verify round-trip values/unchanged P0 clocks with source/output collision guards. Keep private inputs/generated evidence ignored.
4. Run the four declared Route 10 scenarios within fixed budgets, validate incumbents, publish actual bounds/gaps, run relevant regression tests, then obtain another independent technical review. Changing timetable optimization is a later separately approved project.

## 12. Verification and independent review record

Evidence recomputation on Python 3.12.14 / OR-Tools 9.15.6755: source/frozen SHA checks, workbook-derived p50/p75 bundle equality, P0 digest/counts, all four fresh exact covers and separate maximum-flow audits, explicit graph edge counts and equal matching/min-cut capacities, p50/p75 workloads and task-inclusive workload arithmetic. No integrated solver has been implemented or run.

Existing verification command, with the SHA-checked private workbook and frozen evidence configured via `BUS_MVP5_ROUTE10_WORKBOOK` and `BUS_CREW_FROZEN_EVIDENCE`, `PYTHONPATH=src`, `PYTHONUTF8=1` and `OPENPYXL_LXML=False`:

```text
python -m pytest tests/test_crew_review.py tests/test_fleet_timespace.py tests/test_peak_offpeak_pilot.py tests/test_mvp_service_plan.py tests/test_mvp_acceptance.py tests/test_route10_pilot.py --basetemp=outputs/integrated_v1_spec_checks -ra
```

Result: **120 passed, 4 skipped** in 542.94 seconds. The four skips are the older `BUS_MVP_ROUTE6_WORKBOOK`/`BUS_MVP_ROUTE10_WORKBOOK` parameterized acceptance cases; those differently named private inputs were not configured. The private frozen crew review, peak/off-peak acceptance and Route 10 pilot checks in the enabled groups ran. This is a focused existing-suite check, not a full-repository or new integrated-solver test run.

The reproduction snippet in section 4.1 was executed successfully. Separate hand-witness arithmetic checks verified T2's one-block meal failure and two-block meal feasibility, and T11's two-block driving feasibility; no integrated solver was written. T15/T16 specify future input-contract acceptance, not tests claimed to pass against unimplemented modules. Manual prose/consistency review was completed; the optional academic-prose scanner scripts could not run because their `defusedxml` dependency is absent from the local Python environments.

**Independent technical review:** a separate fresh-context reviewer using GPT-6.1 Terra, extra-high reasoning, inspected the user requirements, existing modules and proposed formulation, challenged the path/resource/rest and stock semantics, and checked synthetic fixtures and proof claims. One material finding identified a contract/formulation mismatch: the draft allowed successor-dependent reserve although its equations used rho_i. V1 was narrowed to per-arriving-trip internal reserve, final reserve excluded, unsupported variants rejected, with T15 added. Secondary comments prompted explicit disabled-rule modes and positive integer C_max/beta/input checks, with T16 added. Re-review confirmed that the revised contract matches the formulation and preserves completeness within its stated assumptions. **No material or important findings remain; reviewer verdict: `DESIGN_READY_FOR_PO_REVIEW`.** No second production solver or framework was requested by the review.

## 13. Product Owner decisions and stop condition

| Decision | Why it changes the mathematics |
|---|---|
| Meal eligibility | Strict intersection versus sustained duty, including exact thresholds, changes which paths exist and can even invalidate all partitions of a compulsory trip. |
| Duty metric and endpoint task accounting | Confirm elapsed H including meals/waiting and separate serial q/h/p, or provide a different sourced definition. The 27/21 stronger bounds depend on these assumptions. |
| Driving reset/limits and general break entitlements | Select C_max/beta and what protected rest qualifies; confirm whether additional daily/continuous-work breaks are mandatory. Meals and a duty limit do not define driving compliance. |
| Resource sizing versus hard availability | Unknown stock permits conditional sizing; confirmed A/B caps or a hard resource ceiling change feasibility. Eight/six is an experimental split, not confirmed authority. |
| Runtime and residual reserve | p50 versus p75 defines different arrivals/workloads. Any extra reserve beyond p75 needs an independent basis; p50 reserve diagnostics do not establish full-duty robustness. |
| Synchronized roles and terminal work | Confirm a driver plus attendant per vehicle, both available through duty, and no other competing terminal work. Different role duties/availability invalidate the earliest-rest reduction. |

These choices do not prevent delivery of a complete conditional mathematical specification. They must be explicit before future implementation acceptance or an operational verdict. Operational date, applicable rules, parking and actual people/vehicle availability remain additional evidence for deployment; this document makes no legal-compliance or monetary-savings claim.

Stop after independent review, necessary specification corrections and a documentation-only commit/push to the existing pilot branch, with a fresh clean-worktree/HEAD/remote check. PR #63 remains Draft and unmerged on its existing source branch; do not create another PR. Final design verdict is `DESIGN_READY_FOR_PO_REVIEW` only after the review finds no unresolved material mathematical/completeness issue; otherwise `DESIGN_BLOCKED` names the blocker. Neither verdict asserts that a feasible rest-compliant P0 assignment has already been found.

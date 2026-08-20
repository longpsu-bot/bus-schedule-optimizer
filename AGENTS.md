# Bus Schedule Optimizer agent instructions

## Scope

For Scenario C V4 work, treat `docs/engine/SCENARIO_C_V4_ADAPTIVE_REGIME_DESIGN.md` as the design authority.

Do not obtain feasibility by silently relaxing operating policy.

## V4 architectural rule

Demand observations are evidence, not timetable structure.

Do not recreate the V3 pattern of:

```text
30-minute demand block -> exact trip allocation -> regime repair
```

V4 must instead use:

```text
demand evidence -> adaptive demand shape -> bounded regime skeleton candidates -> exact timetable repair -> independent validation
```

The exact solver should operate on the ordered Scenario B trip sequence and choose exact departure minutes / integer headways inside candidate regime topology.

## Hard authorities

Unless an explicit reviewed policy change says otherwise, keep these hard:
- fixed total and direction-specific trip counts in fixed-resource mode;
- source direction/terminal and one-to-one B -> C traceability;
- exact Scenario B runtime per source trip;
- configured first/last locks;
- absolute Scenario B departure shift <= 30 minutes;
- fleet ceiling;
- turnaround / layover;
- protected service floors;
- whole-minute departures;
- exact integer-uniform headway inside each service regime;
- final-tail maximum headway;
- final-tail non-densification when demand is not rising;
- independent validation.

Current transition authority: Scenario C maximum adjacent regime-headway jump may not exceed Scenario B's relevant observed maximum.

## Exact regime rule

Within regime `r`:

```text
C[i+1] - C[i] = H[r]
H[r] is a positive integer minute value
```

Do not accept approximate patterns such as 10/11/10 as one regime.

## Tail policy

Tail policy is mandatory.

When final-tail demand is non-increasing / not rising:

```text
H_tail >= H_previous
```

The last departure remains locked when configured, and the configured tail headway ceiling remains hard.

## Headway quality intent

Service should be as frequent as resources and demand justify.

Preference bands:
- <=10 min: strongly preferred;
- 10-15 min: preferred;
- >15 min: increasingly unattractive but allowed when hard resource constraints make shorter service infeasible.

Do not make <=10 or <=15 a blanket hard constraint.

Use passenger-weighted waiting / demand fit plus explicit penalties above 10 and 15 minutes. Explain resource binding when preferred bands are impossible.

## Regime parsimony

Prefer a small number of meaningful regimes.
- normal skeleton search should favor 3-8 regimes;
- >8 requires evidence;
- 16 is an absolute safety ceiling, never a target;
- penalize short ordinary regimes and oscillating headway patterns.

## Demand granularity

Input may be 15/30/60-minute observations or raw data. Do not force service boundaries to equal observation boundaries.

Preserve evidence provenance. A service boundary may be selected inside an evidence region only as an operational decision, not as a claim that passenger demand was measured to change at that exact minute.

## V3 migration rule

Reuse V3 infrastructure where useful, but do not carry V3 block-level bounded phase, exact demand-block allocation, or phase-aware source slicing into V4 production authority.

V3 must continue to work unchanged as a regression/reference path.

PR #57 is research evidence and must not be merged as the V4 foundation.

## Solve budget

Keep ordinary pilot total solve budget at 120 seconds.

Do not increase it unless the exact solver is genuinely running, the total budget is exhausted, and evidence shows search time rather than semantics is the blocker.

## Development discipline

Before coding:
1. inspect current main and existing reusable contracts;
2. write/confirm the V4 contract being implemented;
3. add focused tests first or alongside implementation;
4. keep V4 opt-in and isolated from V3;
5. run focused tests, relevant full tests, Ruff lint and Ruff format;
6. record real-route evidence separately from unit-test success.

Do not merge merely because CI is green. MST6 and then MST10 product-level review are acceptance gates.

For every real-route trial, record concise engineering rationale:

```text
evidence -> diagnosis -> minimal correction -> verification -> decision
```

Do not record private chain-of-thought; record only observable, reviewable engineering rationale.

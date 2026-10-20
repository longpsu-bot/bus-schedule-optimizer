# MVP-6A: fleet-guided ServiceRegime optimization

**IMPLEMENTATION_VALIDATED. NO_MEASURED_REAL_ROUTE_GAIN. Retain the verified MVP-5A p50 incumbent.**

The new mechanism generates legal ServicePlans and passes the independently known synthetic case. Route 10 produces additional fleet-feasible candidates, including two directly from guided operations in p50, but none passes the unchanged incumbent service-quality policy. No p75 14-vehicle timetable was found. This is not an infeasibility proof. Stop after MVP-6A.

## Frozen controls

Starting SHA: `94be895b4c509c16c6d565b7bb9eea21596f1a15`. Target remote branch: `feat/mvp5-route10-engine-pilot`. PR #63 stays draft, unmerged and at `e9fe4eb92c785748d939d44c6386c005d5d9cd3c`. A separate managed worktree preserves the original workspace and pilot checkout owned by another chat.

Both arms use the identical workbook SHA `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`, demand normalization, p50/p75 runtime periods, 51/51 trips, endpoints, five-minute layover, ceiling 14, 25 evaluated plans, 160 distinct exact pairs including the independently recovered incumbent, four retained directional settlements, six pairs per plan, 256 directional previews, two seconds / 0.2 deterministic solver work, one worker, seed zero and 120 seconds per route. Baseline and incumbent policies are unchanged. Only the treatment enables fleet guidance.

The final control reproduces all 25 plan operations/structures, every distinct evaluated vector and its complete quality results from the frozen six-pair MVP-5B.1 evidence: 97 p50, 120 p75 and 80 B25 evaluations. The exact audit is `outputs/mvp6a_final/frozen_control_audit.json`.

## Mechanism and synthetic proof

`assign_fleet()` is unchanged. A separate diagnostic reconstructs the alternating residual graph from its exact matching, exposing chain starts/ends, readiness misses, residual bridges and terminal stock pressure. Closing a residual bridge would augment the frozen graph; moving times may remove other links. All feasibility claims still require the ordinary compiler, service evaluator and exact assignment. Initial-stock-constrained assignments receive no unconstrained residual-bridge certificate.

Bounded neighborhoods reallocate up to two gaps between meaningful regimes, derive integer headway adjustments from readiness lateness, move boundaries while preserving exact total duration, split blocks at observed pressure and canonically merge equal headways. Both directions can change together. Fixed whole-minute hints use the existing compiler; ordinary fallback revisions release the hints. Every compiled guided plan in acceptance has zero boundary residuals. Every third turn preserves generic exploration.

The mandatory synthetic case has two terminals, nine trips each from minute 0 to 120, 15-minute runtime, zero layover, hard maximum gap 30, and demand weights 81/1 in the two halves. Demand-first allocation gives six 10-minute gaps then two 30-minute gaps in both directions and requires four vehicles. Under the identical two-plan budget, the control changes only one direction and cannot recommend a two-vehicle timetable. The guided planner changes both allocations to eight 15-minute gaps and finds two vehicles. Two simultaneous first departures prove a lower bound of two; two alternating chains attain it. The improvement is in the generated ServicePlans, not selection of another original-family settlement.

A separate four-trip test has a one-minute residual bridge: delaying its target closes that connection but loses the next link, so exact fleet remains two. A closed local connection is not reported as an automatic fleet saving.

## Specific Route 10 revisions

- p50 I001 -> C002_01 splits the inbound 16-gap/17-minute morning block into eight gaps at 18 minutes and eight at 16 minutes, with pivot 07:24. It closes six diagnosed misses while losing four old matched links; exact fleet worsens 14 -> 15.
- p50 C007_02, an ordinary fallback descendant of the guided family, uses inbound blocks 13x17, 3x25, 8x18, 26x20, with pivots 08:41/09:56/12:20. It has fleet 14 and wait 9.439133, but 12 review intervals and 3,436.087 deterioration passenger-minutes, worse than I001's nine / 3,301.567.
- Guided p50 C020_01 changes middle inbound counts 3/8 -> 4/7 and headways 25/18 -> 25/17, moving pivot 09:56 -> 10:21 while preserving 12:20. Exact fleet stays 14; wait rises to 9.471078, with 12 review intervals / 3,535.380 passenger-minutes. Equivalent B25 C008_01 is legal but fails unchanged quality policy.
- Guided p50 C024_01 changes inbound counts 13/3 -> 14/2, first pivot 08:41 -> 08:58 and second headway 25 -> 29, preserving 09:56. Fleet stays 14 and wait falls to 9.438838, but 11 review intervals / 3,415.740 passenger-minutes worsen local service. The 29-minute gap is inadmissible in B25; its guardrail is enforced.
- p75 C002_01 changes both directions: outbound 8x15/15x21/27x20 (canonical merging), inbound 16x17/8x21/22x22/4x9 with a meaningful 36-minute tail. It closes 23 diagnosed misses but loses 12 old matched links. Exact fleet remains 15 and wait is 9.808467. None of the final guided real-route operations reduces its parent's exact fleet.

Lower-wait feasible candidates remain visible in the evidence, but the unchanged incumbent policy also requires a non-worsening hierarchical local-service key. No selected improvement qualifies as REAL_ROUTE_IMPROVEMENT.

## Accounting and remaining bottleneck

Guidance generated 184/135/166 distinct proposals for p50/p75/B25, of which 16 plans / 16 new exact vectors were evaluated in each scenario. Coupled changes account for 8/11/7 plans. Generated feasible candidates rose 1 -> 4 in p50 and 1 -> 2 in B25, with two/one directly guided feasible vectors. No p75 feasible timetable was found.

All 449 final exact evaluations were independently checked with a separately rebuilt unit-capacity SimpleMaxFlow graph, fresh quality/review evaluation and complete chain/runtime/layover validation. These are revalidations outside the search budget, not additional search. Baselines are also outside the distinct pair counter. Fixed integer plans often have only one settlement; four is a retention ceiling. Equal configured bounds do not mean equal computational effort. Times below include search and final review, excluding exports, incumbent recovery controls and the acceptance audit.

p50/B25 C has matching size 88, exact fleet 14 and terminal initial-stock pressure peaks outbound 8 / inbound 6. The rejected p75 C has matching size 87, fleet 15 and peaks 9/6. There are 291/290/291 readiness misses within 60 minutes, with 32 retained in each scenario and no single residual bridge found in that window. This does not exclude coordinated graph edits.

p75 treatment explores 25 plans / 49 exact pairs: 13 pairs require 15 vehicles; deficits range 1–9. It leaves 150 queued plans and 37 discovered retained pairs unexamined. Wider or three-regime integer changes, transfers beyond two gaps, splits away from retained misses, more than four regimes and misses beyond 60 minutes remain unexplored. The ungenerated space is uncounted. The bottleneck remains matching at least 88 trips under p75 while preserving local service. No expansion into another experiment is implemented.

The tables and exact C departures/regimes/chains below use I001 for p50/B25. **p75 C is hard-rejected near-feasible trial C001_04, not a recommendation.** Full B/X/C departures, regimes, arrivals, chains and all explored ServicePlan structures are in `outputs/mvp6a_final/fleet_report.json`.

# MVP-6A fleet-guided Route 10 acceptance

NO_MEASURED_REAL_ROUTE_GAIN

## report_p50 control / guided

Outcome: NO_MEASURED_REAL_ROUTE_GAIN. C role: VERIFIED_RECOMMENDATION.

| Metric | Six-pair control | Fleet-guided |
|---|---:|---:|
| Exact fleet | 14 | 14 |
| Modeled wait | 9.441295 | 9.441295 |
| Review exception intervals | 9 | 9 |
| Positive deterioration passenger-minutes | 3301.567 | 3301.567 |
| evaluations | 25 | 25 |
| exact_pair_evaluations | 97 | 49 |
| feasible_generated_candidates | 1 | 4 |
| fleet_guided_evaluations | 0 | 16 |
| fleet_guided_fleet_improvements | 0 | 0 |
| runtime_seconds | 13.764612099999795 | 7.138246700000309 |
| pending_plans | 100 | 150 |
| unexamined_retained_pairs | 175 | 10 |

Exact fleet distributions and independent validation: `{"control": {"exact_fleets_verified": 97, "fleet_distribution": {"14": 2, "15": 22, "16": 34, "17": 21, "18": 10, "19": 5, "20": 2, "21": 1}, "inside_search_budget": false, "method": "Independent SimpleMaxFlow graph, fresh quality/review, chain validation"}, "guided": {"exact_fleets_verified": 49, "fleet_distribution": {"14": 5, "15": 14, "16": 13, "17": 9, "18": 3, "19": 2, "20": 3}, "inside_search_budget": false, "method": "Independent SimpleMaxFlow graph, fresh quality/review, chain validation"}}`

## report_p75 control / guided

Outcome: NO_MEASURED_REAL_ROUTE_GAIN. C role: NEAR_FEASIBLE_TRIAL_ONLY.

| Metric | Six-pair control | Fleet-guided |
|---|---:|---:|
| Exact fleet | 15 | 15 |
| Modeled wait | 9.447497 | 9.447497 |
| Review exception intervals | 8 | 8 |
| Positive deterioration passenger-minutes | 2890.627 | 2890.627 |
| evaluations | 25 | 25 |
| exact_pair_evaluations | 120 | 49 |
| feasible_generated_candidates | 0 | 0 |
| fleet_guided_evaluations | 0 | 16 |
| fleet_guided_fleet_improvements | 0 | 0 |
| runtime_seconds | 12.020328599995992 | 9.557772300002398 |
| pending_plans | 100 | 150 |
| unexamined_retained_pairs | 168 | 37 |

Exact fleet distributions and independent validation: `{"control": {"exact_fleets_verified": 120, "fleet_distribution": {"15": 9, "16": 19, "17": 28, "18": 24, "19": 24, "20": 7, "21": 4, "22": 5}, "inside_search_budget": false, "method": "Independent SimpleMaxFlow graph, fresh quality/review, chain validation"}, "guided": {"exact_fleets_verified": 49, "fleet_distribution": {"15": 13, "16": 13, "17": 9, "18": 2, "19": 3, "20": 2, "21": 3, "22": 2, "23": 2}, "inside_search_budget": false, "method": "Independent SimpleMaxFlow graph, fresh quality/review, chain validation"}}`

## report_p50_B25_guardrail control / guided

Outcome: NO_MEASURED_REAL_ROUTE_GAIN. C role: VERIFIED_RECOMMENDATION.

| Metric | Six-pair control | Fleet-guided |
|---|---:|---:|
| Exact fleet | 14 | 14 |
| Modeled wait | 9.441295 | 9.441295 |
| Review exception intervals | 9 | 9 |
| Positive deterioration passenger-minutes | 3301.567 | 3301.567 |
| evaluations | 25 | 25 |
| exact_pair_evaluations | 80 | 54 |
| feasible_generated_candidates | 1 | 2 |
| fleet_guided_evaluations | 0 | 16 |
| fleet_guided_fleet_improvements | 0 | 0 |
| runtime_seconds | 12.256069899995055 | 12.508978700003354 |
| pending_plans | 100 | 150 |
| unexamined_retained_pairs | 124 | 28 |

Exact fleet distributions and independent validation: `{"control": {"exact_fleets_verified": 80, "fleet_distribution": {"14": 2, "15": 9, "16": 26, "17": 22, "18": 12, "19": 1, "20": 8}, "inside_search_budget": false, "method": "Independent SimpleMaxFlow graph, fresh quality/review, chain validation"}, "guided": {"exact_fleets_verified": 54, "fleet_distribution": {"14": 3, "15": 26, "16": 20, "17": 3, "18": 2}, "inside_search_budget": false, "method": "Independent SimpleMaxFlow graph, fresh quality/review, chain validation"}}`

# Route 10 engine optimization pilot

All operating results are conditional report-derived hypothetical scenarios. No operating approval is issued.
Source SHA-256: `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`.

Original recorded X trips/chains and the unchanged MVP-4 benchmark are stored separately. Common evaluations recompute every arrival and vehicle chain.

## report_p50

C role: VERIFIED_RECOMMENDATION. Outcome: NO_MEASURED_REAL_ROUTE_GAIN.

| Criterion | B | X | C |
|---|---|---|---|
| Trips outbound/inbound | 51/51 | 51/51 | 51/51 |
| Required fleet | 17 | 16 | 14 |
| Modeled wait (minutes) | 9.442026 | 10.366877 | 9.441295 |
| Max headway outbound/inbound (minutes) | 25/25 | 42/45 | 23/21 |
| Positive deterioration vs B (passenger-minutes) | 0.000 | 6593.907 | 3301.567 |
| Protected-rule violations | 0 | 0 | 0 |
| Uniform runs outbound/inbound | 8/7 | 31/28 | 4/3 |
| Singleton runs outbound/inbound | 0/0 | 22/18 | 0/0 |
| Operational feasibility | CONSTRAINT_FAILURE | CONSTRAINT_FAILURE | CONDITIONAL |

Zero explicit-rule violations does not certify protected service when no rules were supplied.

Full search statistics and all evaluated plan structures are in fleet_report.json and run_diagnostics.json.

C interval review warnings (review policy, not hard service authority):

- inbound 17:00-17:30: wait delta 4.167 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 15/20 min.
- outbound 15:30-16:00: wait delta 3.367 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 18/20 min.
- outbound 16:30-17:00: wait delta 3.333 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 20/20 min.
- outbound 14:30-15:00: wait delta 3.467 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 18/20 min.
- inbound 05:00-05:30: wait delta 1.867 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 15/17 min.
- inbound 16:30-17:00: wait delta 0.833 min; high-demand classification: True; HIGH_DEMAND_FREQUENCY_REDUCTION, HIGH_DEMAND_LONGER_GAP. B/C intersecting gaps 15/20 min.
- outbound 16:00-16:30: wait delta 0.833 min; high-demand classification: True; HIGH_DEMAND_FREQUENCY_REDUCTION, HIGH_DEMAND_LONGER_GAP. B/C intersecting gaps 15/20 min.
- outbound 18:00-18:30: wait delta 2.433 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 20/23 min.
- outbound 11:00-11:30: wait delta -1.967 min; high-demand classification: True; HIGH_DEMAND_FREQUENCY_REDUCTION. B/C intersecting gaps 20/19 min.

Exact C departures:

- outbound: 04:45, 05:00, 05:15, 05:30, 05:45, 06:00, 06:15, 06:30, 06:45, 07:04, 07:23, 07:42, 08:01, 08:20, 08:39, 08:58, 09:17, 09:36, 09:55, 10:14, 10:33, 10:52, 11:11, 11:30, 11:50, 12:10, 12:30, 12:50, 13:10, 13:30, 13:50, 14:10, 14:30, 14:50, 15:10, 15:30, 15:50, 16:10, 16:30, 16:50, 17:10, 17:33, 17:56, 18:19, 18:42, 19:05, 19:28, 19:51, 20:14, 20:37, 21:00
- inbound: 05:00, 05:17, 05:34, 05:51, 06:08, 06:25, 06:42, 06:59, 07:16, 07:33, 07:50, 08:07, 08:24, 08:41, 08:58, 09:15, 09:32, 09:53, 10:14, 10:35, 10:56, 11:17, 11:38, 11:59, 12:20, 12:40, 13:00, 13:20, 13:40, 14:00, 14:20, 14:40, 15:00, 15:20, 15:40, 16:00, 16:20, 16:40, 17:00, 17:20, 17:40, 18:00, 18:20, 18:40, 19:00, 19:20, 19:40, 20:00, 20:20, 20:40, 21:00

C ServiceRegimes (shared pivots, no transition gap):

- outbound 04:45-06:45: 15 min, 8 gaps.
- outbound 06:45-11:30: 19 min, 15 gaps.
- outbound 11:30-17:10: 20 min, 17 gaps.
- outbound 17:10-21:00: 23 min, 10 gaps.
- inbound 05:00-09:32: 17 min, 16 gaps.
- inbound 09:32-12:20: 21 min, 8 gaps.
- inbound 12:20-21:00: 20 min, 26 gaps.

## report_p75

C role: NEAR_FEASIBLE_TRIAL_ONLY. Outcome: NO_MEASURED_REAL_ROUTE_GAIN.

| Criterion | B | X | C |
|---|---|---|---|
| Trips outbound/inbound | 51/51 | 51/51 | 51/51 |
| Required fleet | 18 | 16 | 15 |
| Modeled wait (minutes) | 9.442026 | 10.366877 | 9.447497 |
| Max headway outbound/inbound (minutes) | 25/25 | 42/45 | 24/21 |
| Positive deterioration vs B (passenger-minutes) | 0.000 | 6593.907 | 2890.627 |
| Protected-rule violations | 0 | 0 | 0 |
| Uniform runs outbound/inbound | 8/7 | 31/28 | 4/3 |
| Singleton runs outbound/inbound | 0/0 | 22/18 | 0/0 |
| Operational feasibility | CONSTRAINT_FAILURE | CONSTRAINT_FAILURE | CONSTRAINT_FAILURE |

Zero explicit-rule violations does not certify protected service when no rules were supplied.

Full search statistics and all evaluated plan structures are in fleet_report.json and run_diagnostics.json.

C interval review warnings (review policy, not hard service authority):

- inbound 17:00-17:30: wait delta 4.167 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 15/20 min.
- outbound 16:00-16:30: wait delta 2.667 min; high-demand classification: True; MATERIAL_WAIT_DETERIORATION, HIGH_DEMAND_LONGER_GAP. B/C intersecting gaps 15/19 min.
- inbound 05:00-05:30: wait delta 1.867 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 15/17 min.
- outbound 17:00-17:30: wait delta 3.800 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 20/24 min.
- outbound 17:30-18:00: wait delta 2.600 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 20/24 min.
- inbound 16:30-17:00: wait delta 0.833 min; high-demand classification: True; HIGH_DEMAND_FREQUENCY_REDUCTION, HIGH_DEMAND_LONGER_GAP. B/C intersecting gaps 15/20 min.
- outbound 14:30-15:00: wait delta 2.033 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 18/19 min.
- outbound 11:00-11:30: wait delta 0.667 min; high-demand classification: True; HIGH_DEMAND_FREQUENCY_REDUCTION. B/C intersecting gaps 20/20 min.

Exact C departures:

- outbound: 04:45, 04:59, 05:13, 05:27, 05:41, 05:55, 06:09, 06:23, 06:37, 06:57, 07:17, 07:37, 07:57, 08:17, 08:37, 08:57, 09:17, 09:37, 09:57, 10:17, 10:37, 10:57, 11:17, 11:37, 11:56, 12:15, 12:34, 12:53, 13:12, 13:31, 13:50, 14:09, 14:28, 14:47, 15:06, 15:25, 15:44, 16:03, 16:22, 16:41, 17:00, 17:24, 17:48, 18:12, 18:36, 19:00, 19:24, 19:48, 20:12, 20:36, 21:00
- inbound: 05:00, 05:17, 05:34, 05:51, 06:08, 06:25, 06:42, 06:59, 07:16, 07:33, 07:50, 08:07, 08:24, 08:41, 08:58, 09:15, 09:32, 09:53, 10:14, 10:35, 10:56, 11:17, 11:38, 11:59, 12:20, 12:40, 13:00, 13:20, 13:40, 14:00, 14:20, 14:40, 15:00, 15:20, 15:40, 16:00, 16:20, 16:40, 17:00, 17:20, 17:40, 18:00, 18:20, 18:40, 19:00, 19:20, 19:40, 20:00, 20:20, 20:40, 21:00

C ServiceRegimes (shared pivots, no transition gap):

- outbound 04:45-06:37: 14 min, 8 gaps.
- outbound 06:37-11:37: 20 min, 15 gaps.
- outbound 11:37-17:00: 19 min, 17 gaps.
- outbound 17:00-21:00: 24 min, 10 gaps.
- inbound 05:00-09:32: 17 min, 16 gaps.
- inbound 09:32-12:20: 21 min, 8 gaps.
- inbound 12:20-21:00: 20 min, 26 gaps.

## report_p50_B25_guardrail

C role: VERIFIED_RECOMMENDATION. Outcome: NO_MEASURED_REAL_ROUTE_GAIN.

| Criterion | B | X | C |
|---|---|---|---|
| Trips outbound/inbound | 51/51 | 51/51 | 51/51 |
| Required fleet | 17 | 16 | 14 |
| Modeled wait (minutes) | 9.442026 | 10.366877 | 9.441295 |
| Max headway outbound/inbound (minutes) | 25/25 | 42/45 | 23/21 |
| Positive deterioration vs B (passenger-minutes) | 0.000 | 6593.907 | 3301.567 |
| Protected-rule violations | 0 | 2 | 0 |
| Uniform runs outbound/inbound | 8/7 | 31/28 | 4/3 |
| Singleton runs outbound/inbound | 0/0 | 22/18 | 0/0 |
| Operational feasibility | CONSTRAINT_FAILURE | CONSTRAINT_FAILURE | CONDITIONAL |

Zero explicit-rule violations does not certify protected service when no rules were supplied.

Full search statistics and all evaluated plan structures are in fleet_report.json and run_diagnostics.json.

C interval review warnings (review policy, not hard service authority):

- inbound 17:00-17:30: wait delta 4.167 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 15/20 min.
- outbound 15:30-16:00: wait delta 3.367 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 18/20 min.
- outbound 16:30-17:00: wait delta 3.333 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 20/20 min.
- outbound 14:30-15:00: wait delta 3.467 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 18/20 min.
- inbound 05:00-05:30: wait delta 1.867 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 15/17 min.
- inbound 16:30-17:00: wait delta 0.833 min; high-demand classification: True; HIGH_DEMAND_FREQUENCY_REDUCTION, HIGH_DEMAND_LONGER_GAP. B/C intersecting gaps 15/20 min.
- outbound 16:00-16:30: wait delta 0.833 min; high-demand classification: True; HIGH_DEMAND_FREQUENCY_REDUCTION, HIGH_DEMAND_LONGER_GAP. B/C intersecting gaps 15/20 min.
- outbound 18:00-18:30: wait delta 2.433 min; high-demand classification: False; MATERIAL_WAIT_DETERIORATION. B/C intersecting gaps 20/23 min.
- outbound 11:00-11:30: wait delta -1.967 min; high-demand classification: True; HIGH_DEMAND_FREQUENCY_REDUCTION. B/C intersecting gaps 20/19 min.

Exact C departures:

- outbound: 04:45, 05:00, 05:15, 05:30, 05:45, 06:00, 06:15, 06:30, 06:45, 07:04, 07:23, 07:42, 08:01, 08:20, 08:39, 08:58, 09:17, 09:36, 09:55, 10:14, 10:33, 10:52, 11:11, 11:30, 11:50, 12:10, 12:30, 12:50, 13:10, 13:30, 13:50, 14:10, 14:30, 14:50, 15:10, 15:30, 15:50, 16:10, 16:30, 16:50, 17:10, 17:33, 17:56, 18:19, 18:42, 19:05, 19:28, 19:51, 20:14, 20:37, 21:00
- inbound: 05:00, 05:17, 05:34, 05:51, 06:08, 06:25, 06:42, 06:59, 07:16, 07:33, 07:50, 08:07, 08:24, 08:41, 08:58, 09:15, 09:32, 09:53, 10:14, 10:35, 10:56, 11:17, 11:38, 11:59, 12:20, 12:40, 13:00, 13:20, 13:40, 14:00, 14:20, 14:40, 15:00, 15:20, 15:40, 16:00, 16:20, 16:40, 17:00, 17:20, 17:40, 18:00, 18:20, 18:40, 19:00, 19:20, 19:40, 20:00, 20:20, 20:40, 21:00

C ServiceRegimes (shared pivots, no transition gap):

- outbound 04:45-06:45: 15 min, 8 gaps.
- outbound 06:45-11:30: 19 min, 15 gaps.
- outbound 11:30-17:10: 20 min, 17 gaps.
- outbound 17:10-21:00: 23 min, 10 gaps.
- inbound 05:00-09:32: 17 min, 16 gaps.
- inbound 09:32-12:20: 21 min, 8 gaps.
- inbound 12:20-21:00: 20 min, 26 gaps.

## Limits and next step

- Report-derived hypothetical operating scenario, not observed B runtime authority.
- Source trip clocks have whole-minute precision; no sub-minute accuracy is claimed.
- Five to seven observations are sparse; p75 is descriptive sensitivity, not a reliability guarantee. No statistical independence or day-to-day representativeness is established.
- Windows were declared after inspecting broad X duration patterns; no change-point or population-quantile inference is claimed.
- X's selected departures and recorded durations may bias both summaries and their application to different B/C departure times.
- Five-minute layover is an explicit experimental assumption, not an operating requirement. Terminal stock, drivers and onboard capacity are unverified.
- Boarding/chart demand is a proxy with uniform within-bucket arrivals. Outside-service passengers are disclosed and excluded equally for B/X/C; no V3 demand is used.
- Headway 25 minutes is a separate B-derived experiment, not a regulatory limit. No inferred peak becomes mandatory protection.
- High-demand frequency/gap warnings remain for human review even where average waiting improves; no claim of unqualified operator acceptance is made.
- A failed bounded search is SEARCH_INCOMPLETE, never proof of route infeasibility. Native exact-model certification does not establish real-world operational authority.
- Joint search retains at most four directional vectors per plan, 6 pairs per plan, 25 plans and 160 distinct exact pair evaluations, plus the separately disclosed baseline and independent acceptance validations. Unexamined directional and plan families remain; no global infeasibility or optimality proof exists.
- Residual and terminal-pressure evidence only ranks revisions. At most 32 readiness misses, 12 directional shortlists, four alternatives per direction and 12 proposals per witness are retained. Every third search turn preserves generic exploration. Fixed integer feedback plans may retain fewer than four settlements. Independent acceptance validations are outside search budgets.

## report_p50 exact vehicle chains

- V001: outbound-001 -> inbound-006 -> outbound-014 -> inbound-021 -> outbound-028 -> inbound-035 -> outbound-042 -> inbound-048
- V002: inbound-001 -> outbound-009 -> inbound-014 -> outbound-022 -> inbound-029 -> outbound-036 -> inbound-042 -> outbound-051
- V003: outbound-002 -> inbound-007 -> outbound-015 -> inbound-020 -> outbound-029 -> inbound-034 -> outbound-043 -> inbound-051
- V004: outbound-003 -> inbound-008 -> outbound-016 -> inbound-023 -> outbound-030 -> inbound-037 -> outbound-045 -> inbound-050
- V005: inbound-002 -> outbound-010 -> inbound-016 -> outbound-025 -> inbound-030 -> outbound-039 -> inbound-045
- V006: outbound-004 -> inbound-009 -> outbound-017 -> inbound-022 -> outbound-031 -> inbound-036 -> outbound-044 -> inbound-049
- V007: inbound-003 -> outbound-011 -> inbound-017 -> outbound-024 -> inbound-031 -> outbound-038 -> inbound-044
- V008: outbound-005 -> inbound-010 -> outbound-018 -> inbound-025 -> outbound-032 -> inbound-039 -> outbound-047
- V009: inbound-004 -> outbound-012 -> inbound-018 -> outbound-027 -> inbound-032 -> outbound-041 -> inbound-047
- V010: outbound-006 -> inbound-012 -> outbound-020 -> inbound-027 -> outbound-034 -> inbound-041 -> outbound-048
- V011: inbound-005 -> outbound-013 -> inbound-019 -> outbound-026 -> inbound-033 -> outbound-040 -> inbound-046
- V012: outbound-007 -> inbound-013 -> outbound-021 -> inbound-026 -> outbound-035 -> inbound-040 -> outbound-049
- V013: outbound-008 -> inbound-015 -> outbound-023 -> inbound-028 -> outbound-037 -> inbound-043 -> outbound-050
- V014: inbound-011 -> outbound-019 -> inbound-024 -> outbound-033 -> inbound-038 -> outbound-046

Matching size 88; fleet shortfall 0. Detailed chain starts/ends, terminal stock pressure, residual reachability and 291 readiness misses (32 retained) are in report_p50/fleet_pressure.json. All parent witnesses and proposed regime changes are in run_diagnostics.json. Missing connections are diagnostic hints, not fleet-reduction certificates.

## report_p75 exact vehicle chains

- V001: outbound-001 -> inbound-006 -> outbound-014 -> inbound-020 -> outbound-027 -> inbound-034 -> outbound-044 -> inbound-051
- V002: outbound-002 -> inbound-007 -> outbound-016 -> inbound-022 -> outbound-031 -> inbound-038 -> outbound-046
- V003: inbound-001 -> outbound-010 -> inbound-015 -> outbound-022 -> inbound-027 -> outbound-035 -> inbound-042 -> outbound-050
- V004: outbound-003 -> inbound-008 -> outbound-018 -> inbound-023 -> outbound-030 -> inbound-035 -> outbound-043 -> inbound-049
- V005: inbound-002 -> outbound-011 -> inbound-017 -> outbound-024 -> inbound-029 -> outbound-037 -> inbound-043
- V006: outbound-004 -> inbound-009 -> outbound-017 -> inbound-024 -> outbound-034 -> inbound-039 -> outbound-049
- V007: inbound-003 -> outbound-013 -> inbound-019 -> outbound-028 -> inbound-033 -> outbound-041 -> inbound-047
- V008: outbound-005 -> inbound-011 -> outbound-019 -> inbound-026 -> outbound-036 -> inbound-041 -> outbound-051
- V009: inbound-004 -> outbound-012 -> inbound-018 -> outbound-032 -> inbound-037 -> outbound-047
- V010: outbound-006 -> inbound-010 -> outbound-020 -> inbound-025 -> outbound-033 -> inbound-040 -> outbound-048
- V011: inbound-005 -> outbound-015 -> inbound-021 -> outbound-029 -> inbound-036 -> outbound-045 -> inbound-050
- V012: outbound-007 -> inbound-014 -> outbound-023 -> inbound-030 -> outbound-040 -> inbound-046
- V013: outbound-008 -> inbound-013 -> outbound-021 -> inbound-028 -> outbound-038 -> inbound-044
- V014: outbound-009 -> inbound-016 -> outbound-025 -> inbound-032 -> outbound-042 -> inbound-048
- V015: inbound-012 -> outbound-026 -> inbound-031 -> outbound-039 -> inbound-045

Matching size 87; fleet shortfall 1. Detailed chain starts/ends, terminal stock pressure, residual reachability and 290 readiness misses (32 retained) are in report_p75/fleet_pressure.json. All parent witnesses and proposed regime changes are in run_diagnostics.json. Missing connections are diagnostic hints, not fleet-reduction certificates.

## report_p50_B25_guardrail exact vehicle chains

- V001: outbound-001 -> inbound-006 -> outbound-014 -> inbound-021 -> outbound-028 -> inbound-035 -> outbound-042 -> inbound-048
- V002: inbound-001 -> outbound-009 -> inbound-014 -> outbound-022 -> inbound-029 -> outbound-036 -> inbound-042 -> outbound-051
- V003: outbound-002 -> inbound-007 -> outbound-015 -> inbound-020 -> outbound-029 -> inbound-034 -> outbound-043 -> inbound-051
- V004: outbound-003 -> inbound-008 -> outbound-016 -> inbound-023 -> outbound-030 -> inbound-037 -> outbound-045 -> inbound-050
- V005: inbound-002 -> outbound-010 -> inbound-016 -> outbound-025 -> inbound-030 -> outbound-039 -> inbound-045
- V006: outbound-004 -> inbound-009 -> outbound-017 -> inbound-022 -> outbound-031 -> inbound-036 -> outbound-044 -> inbound-049
- V007: inbound-003 -> outbound-011 -> inbound-017 -> outbound-024 -> inbound-031 -> outbound-038 -> inbound-044
- V008: outbound-005 -> inbound-010 -> outbound-018 -> inbound-025 -> outbound-032 -> inbound-039 -> outbound-047
- V009: inbound-004 -> outbound-012 -> inbound-018 -> outbound-027 -> inbound-032 -> outbound-041 -> inbound-047
- V010: outbound-006 -> inbound-012 -> outbound-020 -> inbound-027 -> outbound-034 -> inbound-041 -> outbound-048
- V011: inbound-005 -> outbound-013 -> inbound-019 -> outbound-026 -> inbound-033 -> outbound-040 -> inbound-046
- V012: outbound-007 -> inbound-013 -> outbound-021 -> inbound-026 -> outbound-035 -> inbound-040 -> outbound-049
- V013: outbound-008 -> inbound-015 -> outbound-023 -> inbound-028 -> outbound-037 -> inbound-043 -> outbound-050
- V014: inbound-011 -> outbound-019 -> inbound-024 -> outbound-033 -> inbound-038 -> outbound-046

Matching size 88; fleet shortfall 0. Detailed chain starts/ends, terminal stock pressure, residual reachability and 291 readiness misses (32 retained) are in report_p50_B25_guardrail/fleet_pressure.json. All parent witnesses and proposed regime changes are in run_diagnostics.json. Missing connections are diagnostic hints, not fleet-reduction certificates.

## Reproduction and local evidence

With the unchanged private workbooks and installed development dependencies, from the repository root:

```powershell
$env:PYTHONPATH='src'
$env:OPENPYXL_LXML='False'
python scripts/run_route10_pilot.py --joint --pairs-per-plan 6 --fleet-guided --input <Route10-workbook.xlsx> --output-dir outputs/mvp6a_reproduction
$env:BUS_MVP5_ROUTE10_WORKBOOK='<Route10-workbook.xlsx>'
$env:BUS_MVP_ROUTE6_WORKBOOK='<V3-route6-workbook.xlsx>'
$env:BUS_MVP_ROUTE10_WORKBOOK='<V3-route10-workbook.xlsx>'
python -m pytest -ra
python -m ruff check . --exclude .artifact --exclude outputs --exclude .venv
python -m ruff format --check src/bus_schedule_engine/contracts_v1 tests/test_contract*.py
python -m ruff format --check src/bus_schedule_engine/mvp/fleet_feedback.py src/bus_schedule_engine/mvp/route10_fleet_pilot.py src/bus_schedule_engine/mvp/runner.py src/bus_schedule_engine/mvp/planning.py scripts/run_route10_pilot.py tests/test_mvp_fleet_feedback.py tests/test_route10_pilot.py
```

Use canonical Git LF source on Windows for inherited byte-based fixtures. The final full-suite snapshot is a canonical archive plus normalized changed files, verified byte-for-byte against every changed Python file. `OPENPYXL_LXML=False` selects the standard XML writer expected by the inherited frozen template fingerprint. No fixture or benchmark was edited.

Detailed local artifacts are under `outputs/mvp6a_final`: comparison report, full fleet report, per-scenario exact timetable/regime/chain JSON, operator XLSX/HTML, `fleet_pressure.json`, and parent witnesses in `run_diagnostics.json`. Private source data and detailed exports remain ignored.

Independent fresh-context review found one material issue: raw edge scores from worse parents could starve near-feasible plans. The fix ranks the parent's exact fleet first, counts distinct unmatched target starts and replaces queued duplicate evidence when priority improves. The new cross-parent regression failed before the fix and passes after it. The reviewer additionally checked disabled single/joint control equivalence, 300 randomized matching cases (524 true bridges), and all 364 preliminary certificates. Final acceptance independently revalidates 449 certificates after the fix. No material finding remains.

These are local Windows / Python 3.12.14 / OR-Tools 9.15.6755 checks, not GitHub Actions. The repository's Python workflow does not trigger for a feature-branch-only push. Existing PR #63 checks refer to its separate unchanged SHA.

No K-best or pair-budget tuning, new optimizer architecture, source workbook or demand-normalization change, new PR, merge or MVP-6B work was performed. Operating conclusions remain conditional on report-derived runtimes, boarding-proxy demand and the experimental layover. Initial terminal-stock authority, drivers, onboard loads and operational approval remain unverified.

## Final validation

| Check | Observed result |
|---|---|
| Focused final public checks | 111 passed; eight private-input cases skipped in this focused invocation |
| Full final canonical source, all three Route 6/10 workbooks enabled | 1,662 passed, four skipped, two inherited Kaleido deprecation warnings; 663.81 seconds |
| Private Route 10 control and guided acceptance | All scenarios pass; all 449 exact fleet certificates independently verified |
| Independent repeat inside the final full suite | Same control/treatment plan structures, exact evaluation counts and selected departures as the final standalone acceptance |
| Whole-repository Ruff | Pass |
| Contract V1 formatting / changed Python formatting | 59 files pass / seven files pass |
| Source bytes | All changed Python files match the tested canonical final snapshot after LF normalization |
| Frozen control / workbook | All 297 control vectors and quality results match MVP-5B.1; workbook SHA unchanged |
| Independent code review | One material ranking finding resolved with failing-then-passing regression; no material finding remains |

The four full-suite skips require a separate private route-corpus source directory, which was not configured; they are not Route 10 acceptance skips. Both Kaleido warnings are inherited. Full logs are retained at `outputs/mvp6a_full_final.log` and `outputs/mvp6a_focused_final.log`; the canonical source and private full-suite artifacts are under `outputs/mvp6a_ci_final/`. No GitHub Actions run is claimed for this feature-branch push.

# PR62-U Local Rhythm Refinement Design

## Scope

Add a production post-frontier refinement stage that calls the unchanged global coordinator once, refines every V3 phase-robust materiality source with an actual sustained local rhythm family, admits valid descendants through the unchanged 10-dimensional Pareto updater, and reruns the frozen V3 selector until no unprocessed materiality source can make strict rhythm progress.

The coordinator, compiler, V1/V2/V3 selectors, fleet validator, global budgets, canonical workbooks, and terminal occupancy behavior remain unchanged.

## Components and data flow

`src/bus_schedule_engine/local_rhythm_refinement.py` owns immutable family, policy, statistics, and result records plus the integrated `search_route_service_plans_with_local_rhythm_refinement_v1` entry point. It detects maximal contiguous actual-service families, selects the gap-weighted canonical integer representative, maps actual regimes to contiguous planning regimes through `demand_regime_slices`, merges that planning span, and enumerates radius-3 boundary/transfer adjustments on one external side at a time.

Each state is validated with the original trip total and planning grid and compiled with a local frontier limit of 256. Every compile passes existing translated protection, actual-service/tail evaluation, and directional micro-boundary improvement. Complete outbound/inbound option cross-products pass `evaluate_operating_pair_v1`; only strict lexicographic V3-rhythm improvements can enter the existing Pareto updater or become later sources.

The loop terminates because each source fingerprint is processed once, descendants are deduplicated, and every accepted edge strictly decreases the finite non-negative V3 rhythm tuple.

## Failure behavior

Invalid family-to-plan mapping rejects only that family with `LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID`. Any local compiler pruning produces `LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING` and readiness false. V3 anchor/reference conflicts fail closed. Completed global replay results are never repeated automatically.

## Verification

Use RED → GREEN unit tests for the 22 specified behaviors, integration tests for exact live Route 10 Q generation and Route 6 stability, focused frozen-authority regressions, Ruff, compilation, deterministic double-rendered evidence, immutable byte hashes, and exact local/remote/PR head verification. Route 6 and Route 10 each permit exactly one global coordinator execution.

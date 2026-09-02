# PR62-R — Demand-fit metric validity review

Root classification: **BUCKET_EDGE_ALIASING_CONFIRMED**.

Production point-count SSE/TE remain unchanged. Bucket exposure and exact continuous exposure are review-only diagnostics; neither is production TE.

## Metric definitions

- Production: whole departures are assigned to half-open immutable demand buckets; directional TE is trips × TV.
- Bucket exposure: each complete interdeparture exposure unit is fractionally split by exact overlap with immutable demand buckets.
- Continuous exposure: normalized service and demand densities are integrated exactly over the union of demand boundaries and departures.

## Route 10 ranking

Production access-safe candidates: `7`.
- production_SSE: best `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; anchor rank `1`; P rank `3`; Q external-review rank `8` among frontier plus Q.
- production_TE: best `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; anchor rank `1`; P rank `2`; Q external-review rank `8` among frontier plus Q.
- bucket_exposure_SSE: best `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; anchor rank `1`; P rank `6`; Q external-review rank `4` among frontier plus Q.
- bucket_exposure_equivalent: best `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; anchor rank `1`; P rank `5`; Q external-review rank `4` among frontier plus Q.
- continuous_exposure_equivalent: best `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; anchor rank `1`; P rank `6`; Q external-review rank `3` among frontier plus Q.
- Pairwise disagreements: `{"production_SSE_vs_bucket_exposure_SSE":4,"production_TE_vs_bucket_exposure_equivalent":4,"production_TE_vs_continuous_exposure_equivalent":6}`.

## P versus Q

P `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24` versus Q `12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5`.
- Q − P production_SSE: `0.003236466886`.
- Q − P production_TE: `2.658161318976`.
- Q − P bucket_exposure_SSE: `-0.000472516619`.
- Q − P bucket_exposure_equivalent: `-0.429636402762`.
- Q − P continuous_exposure_TV: `-0.008424243191`.
- Q − P continuous_exposure_equivalent: `-0.429636402762`.
- Q − P continuous_L2: `-0.016192423046`.
- Deficit effect: `{"bucket_exposure_equivalent":"reverses","continuous_exposure_equivalent":"reverses"}`.
- Exact decision states: `{"BUCKET_EXPOSURE_EQUIVALENT_TIE":false,"BUCKET_EXPOSURE_PREFERS_P":false,"BUCKET_EXPOSURE_PREFERS_Q":true,"CONTINUOUS_EXPOSURE_EQUIVALENT_TIE":false,"CONTINUOUS_EXPOSURE_PREFERS_P":false,"CONTINUOUS_EXPOSURE_PREFERS_Q":true,"POINT_COUNT_PREFERS_P":true,"root_classification":"BUCKET_EDGE_ALIASING_CONFIRMED"}`.

## Bucket-edge audit

Changed departures `46`; bucket-changing departures `13`; crossed immutable boundaries `13`.

Top production-TE contribution changes:

- inbound bucket 24 `16:30–17:00`: Q − P contribution `0.500000000000`.
- inbound bucket 25 `17:00–17:30`: Q − P contribution `-0.500000000000`.
- outbound bucket 2 `05:30–06:00`: Q − P contribution `0.500000000000`.
- outbound bucket 6 `07:30–08:00`: Q − P contribution `0.500000000000`.
- outbound bucket 8 `08:30–09:00`: Q − P contribution `0.500000000000`.
- inbound bucket 23 `16:00–16:30`: Q − P contribution `0.079601719084`.

## Anchor validity

`ANCHOR_STABLE_ACROSS_DEMAND_FIT_SEMANTICS` with states `{"bucket_exposure_best":true,"classification":"ANCHOR_STABLE_ACROSS_DEMAND_FIT_SEMANTICS","continuous_exposure_best":true,"fingerprint":"bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c","production_SSE_best":true,"production_TE_best":true}`.

## Route 6 control

Candidates `41`; `ROUTE6_CONTROL_TOP_STABLE`; disagreements `{"production_SSE_vs_bucket_exposure_SSE":57,"production_TE_vs_bucket_exposure_equivalent":49,"production_TE_vs_continuous_exposure_equivalent":53}`.

## Next milestone

Recommend **PR62-S_PHASE_ROBUST_DEMAND_FIT_POLICY_EXPERIMENT** with scope **materiality metric only**. No policy or threshold change is implemented in R.

## Readiness and guards

`READY_FOR_PR62_COMPLETION_REVIEW = false` and `READY_FOR_FINAL_PILOT_USE = false`.

All production guards are `false` (NO change), canonical XLSX files remain hash-locked, and PR62-Q/P authorities remain immutable.

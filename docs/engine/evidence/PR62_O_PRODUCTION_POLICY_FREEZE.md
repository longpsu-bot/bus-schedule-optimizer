# PR62-O — One-trip TE production policy freeze

V1 remains the historical strict-SSE-first selector. V2 is the current production post-search selector for future closed-loop final selection.

## Frozen production hierarchy

1. HARD_OPERATIONAL_FEASIBILITY
2. SCENARIO_B_MAX_ACCESS_NON_REGRESSION
3. COMMON_SSE_TE_DEMAND_FIT_ANCHOR
4. ONE_TRIP_TE_MATERIALITY_ENVELOPE
5. RHYTHM_SIMPLICITY
6. FLEET_EFFICIENCY

The fixed materiality envelope is +1.0 pair trip-equivalent around a unique common SSE/TE anchor. Anchor conflict or ambiguity fails closed; there is no V1 fallback.

## Route 6

- Pareto / hard feasible / access safe: 47 / 47 / 41
- SSE-best / TE-best: `['ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b']` / `['ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b']`
- Common anchor: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`
- Anchor SSE / TE: 0.006691497 / 20.923773759
- One-trip materiality set: 5
- Selected: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`
- Selected SSE / TE: 0.006691497 / 20.923773759
- Average wait: 6.087639156 minutes
- Directional max access: `{'outbound': 10.5, 'inbound': 12.5}`
- Rhythm / fleet: `[8, 14, 6, 0]` / `[20, 5219, 75]`
- Tails: `{'outbound': 15, 'inbound': 15}`
- Classification: `ONE_TRIP_MATERIALITY_SELECTS_ANCHOR`

Stage trace: HARD_OPERATIONAL_FEASIBILITY → SCENARIO_B_MAX_ACCESS_NON_REGRESSION → COMMON_SSE_TE_DEMAND_FIT_ANCHOR → ONE_TRIP_TE_MATERIALITY_ENVELOPE → RHYTHM_SIMPLICITY → FLEET_EFFICIENCY

## Route 10

- Pareto / hard feasible / access safe: 11 / 11 / 7
- SSE-best / TE-best: `['bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c']` / `['bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c']`
- Common anchor: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`
- Anchor SSE / TE: 0.009369737 / 16.957200066
- One-trip materiality set: 2
- Selected: `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`
- Selected SSE / TE: 0.010728881 / 17.669451511
- Average wait: 9.636890464 minutes
- Directional max access: `{'outbound': 12.900000000000002, 'inbound': 14.066666666666666}`
- Rhythm / fleet: `[9, 11, 6, 0]` / `[12, 1683, 71]`
- Tails: `{'outbound': 23, 'inbound': 29}`
- Classification: `ONE_TRIP_MATERIALITY_SELECTS_SIMPLER_ALTERNATIVE`

Stage trace: HARD_OPERATIONAL_FEASIBILITY → SCENARIO_B_MAX_ACCESS_NON_REGRESSION → COMMON_SSE_TE_DEMAND_FIT_ANCHOR → ONE_TRIP_TE_MATERIALITY_ENVELOPE → RHYTHM_SIMPLICITY → FLEET_EFFICIENCY

### Selected versus anchor tradeoff

ΔTE 0.712251446; ΔSSE 0.001359144; Δwait 2.658654865 seconds/passenger; fleet -1; terminal excess wait -749. Directional max access, P90, rhythm, and tail changes are serialized in JSON without suppression.

Inbound-tail 30/45/48/54-minute candidates remain `ACCESS_EXCLUDED_BEFORE_MATERIALITY`; headway is evidence, not a policy rule.

## Readiness

Cross-route classification: `ONE_TRIP_PRODUCTION_POLICY_FROZEN`.

- `READY_FOR_FINAL_XLSX_RECERTIFICATION = true`
- The full immutable 10-D Pareto frontier and coordinator search are unchanged.
- No final XLSX was regenerated and no private workbook was opened.

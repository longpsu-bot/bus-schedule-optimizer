# PR62-S — Phase-robust materiality policy experiment

Classification: **PHASE_ROBUST_MATERIALITY_PATH_SUPPORTS_CANONICAL_Q**.

R confirmed bucket-edge aliasing while both anchors remained stable. S therefore reviews materiality only; the old numeric +1.0 point-TE threshold is not transferred.

## Route 10 phase-robust paths

Anchor `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; P `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`; Q `12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5` is `Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE`.

### continuous_exposure_equivalent

- `0.000000000000`: 1 admitted; selected `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; rhythm `[11, 12, 7, 0]`; fleet `[13, 2432, 71]`.
- `0.391823005611`: 2 admitted; selected `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0`; rhythm `[10, 12, 6, 0]`; fleet `[13, 2447, 71]`.
- `1.556244264116`: 3 admitted; selected `12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5`; rhythm `[6, 6, 6, 0]`; fleet `[12, 1716, 71]`.
- Q admission / selection: `1.556244264116` / `1.556244264116`.
- Legacy preservation bound: `1.985880666878`.

### bucket_exposure_equivalent

- `0.000000000000`: 1 admitted; selected `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; rhythm `[11, 12, 7, 0]`; fleet `[13, 2432, 71]`.
- `0.309491097046`: 2 admitted; selected `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0`; rhythm `[10, 12, 6, 0]`; fleet `[13, 2447, 71]`.
- `1.610363996917`: 3 admitted; selected `c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7`; rhythm `[8, 12, 6, 0]`; fleet `[13, 2207, 81]`.
- `1.833182789030`: 4 admitted; selected `12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5`; rhythm `[6, 6, 6, 0]`; fleet `[12, 1716, 71]`.
- Q admission / selection: `1.833182789030` / `1.833182789030`.
- Legacy preservation bound: `2.262819191793`.

## Q versus P

- Continuous deltas from anchor: Q `1.556244264116`; P `1.985880666878`.
- Bucket deltas from anchor: Q `1.833182789030`; P `2.262819191793`.
- Under phase-robust demand fit, Q is closer to the demand-fit anchor than the currently accepted P timetable.
- Under both diagnostics, Q requires less phase-robust concession than preserving the old P eligibility set; this is descriptive and does not freeze a band.
- Average wait P/Q: `9.636890463523` / `9.550674843256` minutes.
- Inbound maximum access P/Q: `14.066666666667` / `13.800000000000` minutes.
- Fleet P/Q: `12` / `12`; micro-rhythm boundaries `5` / `0`; ServiceRegimes `11` / `6`.
- These passenger and operating facts are context only, not new hard gates.

## Cross-route breakpoint comparison

| Route | Metric | First simpler | First winner change | First zero-micro | Q admitted | Q selected | P admitted |
|---|---|---:|---:|---:|---:|---:|---:|
| 6 | continuous_exposure_equivalent | 2.558959187290 | 2.558959187290 | None | None | None | None |
| 6 | bucket_exposure_equivalent | 2.570552051572 | 2.570552051572 | None | None | None | None |
| 10 | continuous_exposure_equivalent | 0.391823005611 | 0.391823005611 | 1.556244264116 | 1.556244264116 | 1.556244264116 | 1.985880666878 |
| 10 | bucket_exposure_equivalent | 0.309491097046 | 0.309491097046 | 1.833182789030 | 1.833182789030 | 1.833182789030 | 2.262819191793 |

## Route 6 control

Anchor `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b` over 41 access-safe candidates.

- continuous_exposure_equivalent: first winner change `2.558959187290206` → `1efac6b6aaa18c159d794434bdfbce0c2dbe0a9db961442a0987a5a03700c402`; Route-10-Q envelope selects `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`.
- bucket_exposure_equivalent: first winner change `2.5705520515718128` → `1efac6b6aaa18c159d794434bdfbce0c2dbe0a9db961442a0987a5a03700c402`; Route-10-Q envelope selects `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`.

## Conclusion

- Exact classification: `PHASE_ROBUST_MATERIALITY_PATH_SUPPORTS_CANONICAL_Q`.
- Recommended next milestone: `PR62-T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE`.
- Continuous and bucket breakpoint paths do not materially disagree, and Route 6 stays anchored at both Route-10-Q diagnostic envelopes.
- No universal band or production threshold is defined in S.
- `READY_FOR_FINAL_PILOT_USE = false`.
- `READY_FOR_PR62_COMPLETION_REVIEW = false`.
- All production guards are false; no XLSX was regenerated.

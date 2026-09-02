# PR62-N — One-trip TE materiality policy rehearsal

This is a post-search rehearsal only. SSE remains the authoritative demand-fit anchor; TE defines a fixed one-trip operational materiality envelope; frozen rhythm simplicity selects inside that envelope; fleet efficiency acts only after an exact rhythm tie.

A one-trip-equivalent concession is an interpretable service-mass allocation quantum. It is not a literal fractional trip and does not describe timetable edits. No SSE tolerance, SSE/TE blend, or full-rank concordance requirement is introduced.

## Policy stages

1. Hard Operational Feasibility
2. Directional Scenario B Max Access Safeguard
3. Demand Fit Anchor Consistency
4. One Trip Te Materiality Envelope
5. Rhythm Simplicity
6. Fleet Efficiency

## Route 6

- Classification: `ONE_TRIP_BAND_SELECTS_ANCHOR`
- Policy health: `REHEARSAL_POLICY_COHERENT_BUT_COMPLEX_ANCHOR_RETAINED`
- Common SSE/TE anchor: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`
- Anchor TE: 20.923773759
- Materiality-set size: 5
- Rhythm-simpler member in band: false
- Selected: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`
- Selected SSE / TE: 0.006691497 / 20.923773759
- Selected average wait: 6.087639156 minutes
- Selected directional max access: `{'inbound': 12.5, 'outbound': 10.5}`
- Selected rhythm / fleet: `[8, 14, 6, 0]` / `[20, 5219, 75]`
- Selected tails: `{'inbound': 15, 'outbound': 15}`
- Top anchor concordant: true
- In-band deterministic: true
- In-band SSE/TE pairwise disagreements: 2

### Materiality set

| Fingerprint | SSE | TE | delta TE | SSE rank | TE rank | Avg wait | Max OB/IB | Rhythm | Fleet | Tails |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b` | 0.006691497 | 20.923773759 | 0.000000000 | 1 | 1 | 6.087639156 | 10.500000000 / 12.500000000 | `[8, 14, 6, 0]` | `[20, 5219, 75]` | `{'inbound': 15, 'outbound': 15}` |
| `7626c51434bdfea5615100eaa15c8a8ff5cf3d1ee43282e77edc2243d24a2a1e` | 0.007624455 | 21.018437783 | 0.094664024 | 3 | 2 | 6.082724564 | 10.500000000 / 10.500000000 | `[10, 15, 5, 0]` | `[19, 4159, 71]` | `{'inbound': 15, 'outbound': 15}` |
| `017daab382aff6b20febeec27745ab7764c8fedc64ab928e0e4d3377c0ae4699` | 0.007844749 | 21.409068472 | 0.485294713 | 4 | 3 | 6.074348103 | 10.500000000 / 11.500000000 | `[9, 14, 5, 0]` | `[19, 4778, 75]` | `{'inbound': 15, 'outbound': 15}` |
| `1ee89f8429eb087e4f9663975ae893fb8e636d0eadd617783cbc8428847192e8` | 0.006996508 | 21.653274999 | 0.729501240 | 2 | 4 | 6.086718273 | 10.500000000 / 12.500000000 | `[8, 15, 5, 0]` | `[19, 5042, 84]` | `{'inbound': 15, 'outbound': 15}` |
| `14c734fd84cb8c5fcf9c43c7bbcf147ac62c1db128e003844955c1bac840c6e6` | 0.007929467 | 21.747939023 | 0.824165264 | 5 | 5 | 6.081803681 | 10.500000000 / 10.500000000 | `[10, 16, 4, 0]` | `[18, 4312, 60]` | `{'inbound': 15, 'outbound': 15}` |

### Human Final context

Human Final remains `POST_SEARCH_EXPERT_BENCHMARK` and is not selection eligible. Its TE is 19.892406776, versus anchor TE 20.923773759. The anchor has better SSE and average wait, is lexicographically more complex on the first rhythm component, and needs one more vehicle.

## Route 10

- Classification: `ONE_TRIP_BAND_SELECTS_SIMPLER_ALTERNATIVE`
- Policy health: `REHEARSAL_POLICY_COHERENT_SIMPLICITY_GAIN`
- Common SSE/TE anchor: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`
- Anchor TE: 16.957200066
- Materiality-set size: 2
- Rhythm-simpler member in band: true
- Selected: `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`
- Selected SSE / TE: 0.010728881 / 17.669451511
- Selected average wait: 9.636890464 minutes
- Selected directional max access: `{'inbound': 14.066666666666666, 'outbound': 12.900000000000002}`
- Selected rhythm / fleet: `[9, 11, 6, 0]` / `[12, 1683, 71]`
- Selected tails: `{'inbound': 29, 'outbound': 23}`
- Top anchor concordant: true
- In-band deterministic: true
- In-band SSE/TE pairwise disagreements: 0

### Materiality set

| Fingerprint | SSE | TE | delta TE | SSE rank | TE rank | Avg wait | Max OB/IB | Rhythm | Fleet | Tails |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 0.009369737 | 16.957200066 | 0.000000000 | 1 | 1 | 9.592579549 | 12.900000000 / 13.366666667 | `[11, 12, 7, 0]` | `[13, 2432, 71]` | `{'inbound': 24, 'outbound': 23}` |
| `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24` | 0.010728881 | 17.669451511 | 0.712251446 | 3 | 2 | 9.636890464 | 12.900000000 / 14.066666667 | `[9, 11, 6, 0]` | `[12, 1683, 71]` | `{'inbound': 29, 'outbound': 23}` |

### Selected versus anchor tradeoff

The simplicity gain concedes 0.712251446 TE and 0.001359144 SSE. Average wait changes by 0.044310914 minutes (2.658654865 seconds/passenger); fleet changes by -1 vehicle and total terminal excess wait by -749 minutes. Max-access, P90, rhythm, and tail effects are serialized without suppression in JSON.

The 30/45/48/54-minute extreme-tail candidates are `ACCESS_EXCLUDED_BEFORE_MATERIALITY`; TE tolerance cannot rescue them.

## Decision

Cross-route classification: `ONE_TRIP_POLICY_REHEARSAL_SUPPORTED`.

- `READY_FOR_ONE_TRIP_POLICY_FREEZE = true`
- `READY_FOR_FINAL_XLSX_RECERTIFICATION = false`

Lower-rank SSE/TE disagreement is acceptable here because the top anchor is common, the TE envelope is fixed, selection inside it is deterministic, and all candidates are feasibility/access safe. This gives SSE and TE distinct roles rather than treating them as interchangeable rankings.

## Production guards

Production selector, coordinator search, 10-D Pareto, compiler, access, rhythm, fleet validation, queue, budgets, and tail eligibility are unchanged. No final XLSX was regenerated and no private workbook was opened or committed. The one-trip threshold exists only in this rehearsal.

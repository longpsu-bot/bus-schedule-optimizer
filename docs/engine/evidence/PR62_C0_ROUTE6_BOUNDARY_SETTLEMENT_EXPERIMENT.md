# PR62-C0 — Route 6 boundary-settlement experiment

> Review-only evidence. No compiler, search, fleet-validator, or transport policy changed.

## Input and authority

- Workbook: `Route_6_Current_ExternalAI_HumanFinal.xlsx`
- SHA-256: `c2038b31c5a3f6a3ee2377ce2067542cc718a7d1907722efa3ab45a536bdd14a`
- Sheets: CURRENT = `06 hiện hữu`, EXTERNAL_AI = `06 AI`, HUMAN_FINAL = `06 final`
- Primary fleet authority: 70 minutes each direction, 5 minutes minimum layover, 20-vehicle ceiling.
- Demand objective: `sum((service_share - demand_share)^2)` against the existing immutable Route 6 demand buckets.

All three references parse as 78 outbound + 78 inbound departures, with fixed 04:55 and 21:00 endpoints.

## Corrected C0 scope framing

The 14-minute gap is the conditional arithmetic residue of the supplied principal 8/15-minute composition, not an independently selected standard headway. The Human editor moved that residue from the final trip to the start of the slower 15-minute regime.

The exact Human Final inbound arithmetic is `27 × 8 + 1 × 14 + 49 × 15 = 965` over 77 gaps. C0 compares only local strict families; it does not establish global optimality of this supplied composition. Removing the residue may require a wider timetable redesign.

## CURRENT → EXTERNAL_AI → HUMAN_FINAL benchmark

The `EXTERNAL_AI` timetable is an external supplied reference and is not engine lineage.

| Reference | Fleet | Pair mismatch | Out/In unique headways | Out/In runs | Out/In singleton runs | Max raw jump | Total raw variation | Out/In final tail | Out/In tail start | Out/In exact alignment | Out/In tail phase error |
|---|---:|---:|---|---:|---:|---:|---:|---|---|---:|---:|
| CURRENT | 20/20 | 0.0067811133 | [8, 10, 15] / [8, 10, 15] | 10 / 10 | 3 / 3 | 0.628609 | 7.543304 | 15 / 15 min | 17:45 / 17:45 | 100% / 100% | 0 / 0 min |
| EXTERNAL_AI | 20/20 | 0.0069443750 | [7, 8, 9, 10, 11, 12, 15] / [8, 14, 15] | 14 / 8 | 6 / 1 | 0.628609 | 9.192919 | 15 / 15 min | 17:45 / 17:16 | 100% / 100% | 0 / 0 min |
| HUMAN_FINAL | 19/20 | 0.0068020725 | [8, 10, 15] / [8, 14, 15] | 9 / 8 | 0 / 1 | 0.628609 | 7.543304 | 15 / 15 min | 17:45 / 17:30 | 100% / 100% | 0 / 0 min |

## Detected Human Final settlement

The selected inbound witness is `8 → 14 → 15` minutes, with the residual from 17:16 to 17:30.

Local anchors are 16:52 and 18:15: `[8, 8, 8, 14, 15, 15, 15]` = 83 minutes over 7 gaps.

## Strict local alternatives

- Two-rhythm candidates: 0
- Repeated bridge-regime candidates: 4
- Deduplicated total: 4

| Candidate | Family | Local gaps | Pair mismatch | Fleet | Total/max excess wait | Peak minutes | Peak ends earlier | Tail start/error | Pareto |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| STRICT_B_001 | BRIDGE_REGIME | `[8, 10, 10, 10, 15, 15, 15]` | 0.0068020725 | 19/20 | 5352/93 | 8 | 16 min | 17:30 / 0 min | no |
| STRICT_B_002 | BRIDGE_REGIME | `[8, 8, 11, 11, 15, 15, 15]` | 0.0068020725 | 19/20 | 5352/93 | 16 | 8 min | 17:30 / 0 min | yes |
| STRICT_B_003 | BRIDGE_REGIME | `[8, 12, 12, 12, 12, 12, 15]` | 0.0068020725 | 19/20 | 5352/93 | 8 | 16 min | 18:00 / 0 min | no |
| STRICT_B_004 | BRIDGE_REGIME | `[8, 8, 13, 13, 13, 13, 15]` | 0.0068020725 | 19/20 | 5352/93 | 16 | 8 min | 18:00 / 0 min | yes |

Pareto frontier: `STRICT_B_002`, `STRICT_B_004`

Evidence classification: **HUMAN_FINAL_DOMINATES_ALL_STRICT**.

This classification is evidence only. It does not decide whether the clean-boundary rule should change.

## Pareto candidate detail

### STRICT_B_002

- Local departures: `['16:52', '17:00', '17:08', '17:19', '17:30', '17:45', '18:00', '18:15']`
- Absolute local movement: 3 minutes total; 3 minutes max.
- Last departure on the 8-minute rhythm: 17:08.

### STRICT_B_004

- Local departures: `['16:52', '17:00', '17:08', '17:21', '17:34', '17:47', '18:00', '18:15']`
- Absolute local movement: 11 minutes total; 5 minutes max.
- Last departure on the 8-minute rhythm: 17:08.

## Limitations

- C0 is conditional on the supplied surrounding principal-rhythm composition.
- Single Route 6 private reference workbook; no cross-route generalization.
- External AI is a supplied reference only and has no project-engine lineage.
- Clockface descriptors are non-objective engine diagnostics in this milestone.
- Strict alternatives are exhaustive only within the two specified local families.
- Workbook-displayed runtimes are descriptive and do not alter the 70-minute authority.
- No production compiler, search, fleet-validation, or transport policy changed.

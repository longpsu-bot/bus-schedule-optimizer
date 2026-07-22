# XLSX Export Contract V1

The normative export rules are [Engine Contract V1 §§14–16](ENGINE_CONTRACT_V1.md) together with the [Schedule Generation Outcome Contract V1](RESULT_ENVELOPE_CONTRACT_V1.md). This is a target design only; Contract V1 does not change the current exporter.

## Workbook principles

The exporter serializes one authoritative evaluation plus `ScheduleGenerationOutcomeV1`. It must not regenerate C, rebuild demand blocks, or recompute authoritative load factors/requirements. It writes a new output path and never overwrites the source workbook.

An accepted outcome serializes the embedded `ScheduleSolutionV1`. A non-accepted outcome is represented by disposition, execution/solver status, evidence, and limitations. It must not create synthetic C rows, copy B into C, or export a rejected raw candidate as Scenario C.

## Required sheets

| Sheet | Purpose | Authoritative source |
|---|---|---|
| `TONG_QUAN` | disposition, execution/solver status, locks, KPIs, fingerprints | evaluation + generation outcome |
| `DANH_GIA_B` | separate B evaluation dimensions/issues | `ScheduleEvaluationResult` |
| `PHAN_KHUNG_NHU_CAU` | resolution contract, blocks, provenance | demand resolution + blocks |
| `NHU_CAU_VA_CUNG_UNG` | demand/supply/LF/requirements by block | block supply plans |
| `PHAN_BO_CHUYEN_A` | A outbound/inbound/total by block | A block plan |
| `PHAN_BO_CHUYEN_B` | B outbound/inbound/total by block | B block plan |
| `PHAN_BO_CHUYEN_C` | C planned/actual by block; explicit empty state when no accepted C | accepted solution or outcome status |
| `BIEU_DO_GIO_A` | exact A timetable | normalized A |
| `BIEU_DO_GIO_B` | exact B timetable | normalized B |
| `BIEU_DO_GIO_C` | exact C timetable and B trace; absent/empty when no accepted C | accepted solution only |
| `CHE_DO_GIAN_CACH_C` | regimes and sequences | accepted C regimes only |
| `PHAN_CONG_XE_C` | available/minimum/margin, initial terminal allocation, stock events, and fleet chains/readiness | accepted C fleet result only |
| `SO_SANH_B_C` | per-trip shifts and block movements; absent/empty when no accepted C | accepted trace + plans |
| `CANH_BAO` | warnings, rejection codes, residual overload, limitations | evaluation + generation outcome |
| `NHAT_KY_SOLVER` | execution status, adapter/native status when run, timings, stages/objectives | generation outcome + solver diagnostics |
| `CAU_HINH_DA_DUNG` | thresholds, modes, lock values | problem/configuration |
| `GIOI_HAN_DU_LIEU` | demand/static-mode/solver limitations | provenance + generation outcome |

## Formatting

- Vietnamese display headings; stable machine field name may appear in a secondary row/comment.
- Freeze the title/header area and enable filters on every data table.
- Display service times as `HH:mm`; include day offset where needed.
- Display load factors and ceilings as percentages, durations/rates with units, and IDs as text.
- Use consistent status colors with an icon/text equivalent; color alone is insufficient.
- Protect formula-free authoritative value regions from accidental editing when practical.

## Fingerprints and metadata

`TONG_QUAN` always shows contract version, source-B fingerprint, outcome fingerprint, generated-at timestamp, demand-response mode, result status, and execution status. Native solver status and solution fingerprint are shown only when applicable. `NHAT_KY_SOLVER` and `CAU_HINH_DA_DUNG` repeat applicable fingerprints for audit.

For accepted outcomes, all C sheet values match the embedded solution fingerprint. For non-accepted outcomes, C sheets must not claim a solution fingerprint or contain authoritative C data.

## Reconciliation before save

For an accepted outcome, the exporter fails closed if Contract V1 §14 checks fail. It also verifies required sheets, exact B→C trace coverage, C fleet constraint/positioning modes, minimum-versus-limit and fleet-margin arithmetic, initial-terminal reconciliation, non-negative continuous stock, no duplicate trip IDs, and that workbook metadata fingerprints match the generation outcome and accepted solution.

For non-accepted outcomes, the exporter verifies that authoritative C fields are absent/null and that no C timetable, regime, assignment, or block-plan rows were fabricated. Save to a temporary output path and atomically finalize where supported.

## Charts in workbook

If embedded, the two primary charts follow the visualization contract and use the same data tables. Excel category charts must not replace continuous-time/proportional-width semantics; when Excel limitations prevent fidelity, embed a verified image and retain the underlying authoritative table. A non-accepted C appears as a labeled empty state, never as a duplicated B line.

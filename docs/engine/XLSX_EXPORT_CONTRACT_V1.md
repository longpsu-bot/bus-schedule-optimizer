# XLSX Export Contract V1

The normative export rules are [Engine Contract V1 §§14–16](ENGINE_CONTRACT_V1.md). This is a target design only; Contract V1 does not change the current exporter.

## Workbook principles

The exporter serializes one accepted evaluation/solution object. It must not regenerate C, rebuild demand blocks, or recompute authoritative load factors/requirements. It writes a new output path and never overwrites the source workbook. Missing C is represented by status and explanation, not synthetic rows.

## Required sheets

| Sheet | Purpose | Authoritative source |
|---|---|---|
| `TONG_QUAN` | disposition, solver status, locks, KPIs, fingerprints | evaluation + solution |
| `DANH_GIA_B` | separate B evaluation dimensions/issues | `ScheduleEvaluationResult` |
| `PHAN_KHUNG_NHU_CAU` | resolution contract, blocks, provenance | demand resolution + blocks |
| `NHU_CAU_VA_CUNG_UNG` | demand/supply/LF/requirements by block | block supply plans |
| `PHAN_BO_CHUYEN_A` | A outbound/inbound/total by block | A block plan |
| `PHAN_BO_CHUYEN_B` | B outbound/inbound/total by block | B block plan |
| `PHAN_BO_CHUYEN_C` | C planned/actual by block | C block plan |
| `BIEU_DO_GIO_A` | exact A timetable | normalized A |
| `BIEU_DO_GIO_B` | exact B timetable | normalized B |
| `BIEU_DO_GIO_C` | exact C timetable and B trace | accepted solution |
| `CHE_DO_GIAN_CACH_C` | regimes and sequences | C regimes |
| `PHAN_CONG_XE_C` | fleet chains/readiness | C fleet assignment |
| `SO_SANH_B_C` | per-trip shifts and block movements | trace + plans |
| `CANH_BAO` | warnings, residual overload, limitations | evaluation + solution |
| `NHAT_KY_SOLVER` | adapter, status, timings, stages/objectives | solver diagnostics |
| `CAU_HINH_DA_DUNG` | thresholds, modes, lock values | problem/configuration |
| `GIOI_HAN_DU_LIEU` | demand/static-mode/solver limitations | provenance + result |

## Formatting

- Vietnamese display headings; stable machine field name may appear in a secondary row/comment.
- Freeze the title/header area and enable filters on every data table.
- Display service times as `HH:mm`; include day offset where needed.
- Display load factors and ceilings as percentages, durations/rates with units, and IDs as text.
- Use consistent status colors with an icon/text equivalent; color alone is insufficient.
- Protect formula-free authoritative value regions from accidental editing when practical.

## Fingerprints and metadata

`TONG_QUAN` shows contract version, source-B fingerprint, solution fingerprint, generated-at timestamp, demand-response mode, and solver proof status. `NHAT_KY_SOLVER` and `CAU_HINH_DA_DUNG` repeat the fingerprints for audit. Sheet-level data can carry a hidden/visible fingerprint column, but all values must match.

## Reconciliation before save

The exporter fails closed if Contract V1 §14 checks fail. It also verifies required sheets, exact B→C trace coverage, C fleet mode, no duplicate trip IDs, and that workbook metadata fingerprint equals the accepted solution. Save to a temporary output path and atomically finalize where supported.

## Charts in workbook

If embedded, the two primary charts follow the visualization contract and use the same data tables. Excel category charts must not replace continuous-time/proportional-width semantics; when Excel limitations prevent fidelity, embed a verified image and retain the underlying authoritative table.

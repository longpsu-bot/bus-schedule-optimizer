# Current-State Gap Analysis

Audit date: 2026-07-22. The target rules are in [Engine Contract V1](ENGINE_CONTRACT_V1.md). This report describes the inspected workspace without changing runtime code.

## Inspected structure

- Entry/UI: `streamlit_app.py`, five pages under `app_pages/`.
- Core package: `src/bus_schedule_engine/` with models, importer, validator, demand evaluation, block supply, heuristic C generators, fleet assignment, scoring, service orchestration, diagrams, fingerprints, and two exporters.
- Configuration: `config/scoring.json`.
- Tests: 74 tests collected across 9 files.
- Existing docs: `README.md` and `docs/KIEN_TRUC_MVP.md`.
- Workbook input: `Schedule template.xlsx`; generated samples live under `outputs/`.

## Current flow

The workbook importer requires `THONG_SO_B` and `BIEU_DO_B`; A, demand, and configuration are optional. `service.py` validates/evaluates B, infers a fleet count, calls the deterministic heuristic generator, validates C, builds fingerprints, then UI/diagram/export adapters serialize the bundle.

## Component classification

| Component | Current behavior | Classification | Contract V1 gap/action |
|---|---|---|---|
| `models.py` | useful dataclasses for scenarios, trips, blocks, regimes, traces | reusable after refactor | add normalized A/B/demand envelopes, required available upper bound, optional approved metadata, positioning/stock records, resolution/lock/problem/solution records, normative statuses |
| `importer.py` | Excel adapter; capacity may parse as missing then validator blocks; average-day fields retained | reusable after refactor | A is optional; no declared directional trip totals/fleet fields/operating-day/source metadata; demand lacks source type/resolution/confidence |
| `validator.py` | totals, terminals, first/last, runtime, assigned vehicle chains, regulatory turnaround | reusable after refactor | explicitly hard-codes block size to 30/60; no separate parameter-consistency result or declared directional totals/fleet mode |
| `demand.py` | correctly normalizes multi-day totals and classifies LF one-sided at 85/90 | reusable after refactor | evaluates source rows directly; no adaptive/manual resolution, rate/confidence/provenance-rich blocks or V1 status vocabulary |
| `comparator.py` | scores valid scenarios | conflicts with Contract V1 | uses `abs(load_factor - target_load_factor)`, symmetrically penalizing low LF; replace demand-fit scoring |
| `block_supply.py` | reconciles B/C counts and calculates comparison rows | reusable after refactor | may re-grid to fixed `time_block_minutes` and recomputes requirements/LF/status; move authoritative calculations upstream, add A/planned/rates/confidence |
| `c_config.py` | fixed-direction locks and regularity controls | reusable after refactor | only `fixed_by_direction`; no fleet lock mode or explicit authorization evidence |
| `c_generator.py` | deterministic B copy, one-to-one trace, parameter/count/endpoint locks, balanced regimes, validator/fleet gates, mostly one-sided objective | replace as production optimizer; retain as temporary adapter | no explicit Level 1 block plan; candidate heuristic is not globally proving feasibility/optimality; no solver status; generation begins with exact times |
| `generator.py` | orchestrates C and optional expanded `C2` | reusable only as migration shell | `C2` changes trip totals as a separate scenario; policy is outside C V1 and needs explicit product decision; legacy per-block generation exists here |
| `fleet.py` | deterministic greedy two-terminal assignment with runtime/turnaround/location | reusable after refactor/validator oracle | not a proof-oriented global solver; does not expose solver-determined initial terminal stock profiles under an input available upper bound |
| `service.py` | protects B immutability and asserts strong C locks/fingerprint | reusable after refactor | current MVP conflates inferred minimum/declared IDs into an exact active-fleet equality; lacks required available limit, optional approved metadata, B disposition, and solver interface |
| `fingerprint.py` | stable timetable hash | reusable after refactor | solution fingerprint must include parameters, locks, plans, assignments, solver/config/version and canonicalization spec |
| `diagram.py` | Plotly primary combo plus exact-departure diagnostic | replace primary analytical views | primary uses equal-width category X, stacked demand bars, absolute/block units, and one selected direction; not area polygons, six B/C directional lines, rate toggle, or A/B/C small multiples |
| `excel_exporter.py` | input template and general result workbook | reusable after substantial refactor | sheet contract differs and output is not the V1 authoritative workbook shape |
| `comparison_exporter.py` | B/C trace, regimes, fleet, warnings, fingerprints | reusable after refactor | second workbook and legacy sheets; consumes/recalculates some comparison aggregates rather than a full `ScheduleSolutionV1` |
| `ui_utils.py`, `app_pages/` | thin Streamlit presentation over bundle | reusable after refactor | current frames calculate some display summaries; require V1 statuses, controls, two diagrams, and explicit solver/limitation presentation |
| tests | strong MVP regression coverage for locks, demand normalization, diagrams, fleet, runtime | reusable and extend | no schema, adaptive/manual blocks, solver proofs/statuses, performance tiers, V1 workbook, or full fingerprint tests |

## Major conflicts and defects

1. **Hard-coded resolution:** `ScenarioParameters.time_block_minutes` defaults to 60 and the validator accepts only 30 or 60. Legacy generators/re-gridding also use it. This directly conflicts with source-derived resolution.
2. **Symmetric LF scoring:** `comparator.py` calculates `abs(block.load_factor - parameters.target_load_factor)`. Low LF therefore lowers the demand-fit score, prohibited by Contract V1 §6.
3. **No explicit supply-planning layer:** heuristic C candidate times are produced before a durable `BlockSupplyPlan`; exact times and inferred block allocation are coupled.
4. **Fleet constraint conflict:** available fleet limit is not an input field. `service.py` derives an “active” count from calculated minimum and declared vehicle IDs, then requires C to retain it. This is the superseded MVP behavior; Contract V1 instead uses a required upper bound, optional approved metadata, and solver-determined initial terminal positioning.
5. **Incomplete normalized inputs:** no required trips-by-direction fields, operating-day type, source metadata, demand source resolution/type/confidence, or demand-response mode.
6. **B status model:** technical/demand statuses exist, but the five V1 B dispositions and parameter-level feasibility decision do not.
7. **Visualization mismatch:** primary chart uses a categorical axis and stacked bars; it does not preserve proportional block widths, use demand polygons, show all three service lines per scenario simultaneously, or provide the required A/B/C panel diagram.
8. **Presentation calculations:** `block_supply.py` and diagram helpers count/re-grid/aggregate trips; exporter/UI helpers calculate summaries. These should consume an authoritative planning/evaluation dataset.
9. **Export mismatch:** current workbooks do not match the 17-sheet target contract, even though formatting, no-source-overwrite behavior, traces, warnings, and fingerprints are valuable.
10. **No solver abstraction/CP-SAT:** no `ScheduleProblemV1`, `ScheduleSolver`, candidate/independent-solution boundary, solver proof status, or benchmark harness.

No evidence was found that C itself silently changes B operating parameters: current assertions preserve parameter object equality, total/directional counts, endpoints, per-trip runtime, active fleet IDs/count, and B→C identity. The active-fleet equality is current MVP behavior and conflicts with the amended target contract; it must remain untouched until the staged migration. The separate `C2` expansion is visibly labeled, but it is not part of the Contract V1 C definition and needs a future product decision.

## Reusable strengths

Multi-day demand normalization, blocking capacity validation, regulatory turnaround defaults, terminal-aware vehicle readiness, immutable B checks, one-to-one trip tracing, coordinated balanced headway regimes, deterministic behavior, shared C timetable fingerprint checks, exact-departure diagnostics, Vietnamese Excel formatting, and the existing regression suite provide useful migration assets.

## Known scope limitations

The current README explicitly excludes mixed fleet optimization, multi-route operations, deadhead, driver duties, maintenance, mature cross-midnight optimization, and global optimality. These remain outside Contract V1 unless separately approved.

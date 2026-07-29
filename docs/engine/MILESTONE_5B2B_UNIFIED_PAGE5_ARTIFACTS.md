# Milestone 5B2B: Unified Page 05 artifacts

## 1. Purpose

Milestone 5B2B cuts over Streamlit Page 05 charts and downloads when the existing visible-result
authority gate selects `UNIFIED_CONTRACT_V1`. It consumes the aligned Milestone 5B1 session
evidence and never reruns analysis, Contract normalization, validation, a solver, demand
allocation, fleet assignment, or Scenario C generation.

## 2. Existing visible-result authority reuse

Page 05 calls `resolve_visible_result_context_v1(...)`, the same resolver used by Pages 02–04.
There is no second authority resolver or user-selectable legacy/unified toggle. Unified rendering
starts only after the resolver selects Contract V1 and
`build_unified_page5_artifacts_v1(...)` returns a complete artifact bundle.

`UnifiedPage5ArtifactsV1` is frozen and slotted. Construction is fail-closed: semantic,
figure-metadata, XLSX-metadata, HTML, and PNG checks must all succeed before any unified chart or
download is exposed. A construction failure displays `UNIFIED_PAGE5_ARTIFACT_FAILED` and renders
the complete legacy Page 05 instead.

The stored departure figure is shadow evidence, not trusted visible content. After verifying the
presentation DTO, the artifact builder rebuilds the canonical departure figure through
`build_unified_departure_figure_v1(...)` and requires exact deterministic Plotly JSON equality
with the stored figure. This comparison includes trace times, lanes, names, `x`, `y`,
`customdata`, hover templates, lane order, and metadata. Any changed, added, or removed trace
fails closed. The rebuilt canonical figure—not the mutable stored object—is returned for
Streamlit and embedded in HTML.

## 3. Exact-direction chart selection

`available_unified_directions_v1(...)` returns only directions present in
`presentation.blocks`, ordered `combined`, `outbound`, then `inbound`. It never invents
`combined`, splits combined demand, or combines outbound and inbound.

`build_unified_demand_supply_figure_for_direction_v1(...)` filters blocks by exact string
equality. It does not aggregate blocks or recompute demand or supply. The selected figure retains
the presentation fingerprints and records:

- `displayed_direction`;
- `displayed_grain = EXACT_DIRECTION_SUBSET`.

When only one direction exists, Page 05 labels that direction without presenting a selector for
nonexistent alternatives. Terminal-aware Vietnamese direction labels remain visible.

## 4. Actual XLSX-byte metadata verification

`read_unified_export_metadata_bytes_v1(...)` loads the actual session XLSX bytes through
`BytesIO` and openpyxl read-only mode. The path reader and byte reader share one canonical
workbook parser.

The parser requires a complete `FINGERPRINTS` sheet and validates the workbook's accepted-C sheet
shape. The Page 05 artifact builder aligns presentation, normalized-B, and accepted-C
fingerprints—including `None`—plus source identity, `VALIDATION_ONLY`, and cutover state against
the presentation. Malformed, stale, or mismatched bytes are rejected before download exposure.
Page 05 returns the exact validated XLSX bytes; it does not regenerate the workbook.

## 5. Unified HTML contract

The HTML download is a deterministic, offline UTF-8 document containing the selected exact
demand/supply figure and the canonical verified departure figure. Plotly JavaScript is embedded
inline once. The fixed div IDs are:

- `contract-v1-demand-supply`;
- `contract-v1-departures`.

Displayed route and authority metadata are HTML-escaped. The report includes route identity,
presentation mode, all three semantic fingerprints, cutover state, expert-review state, and the
explicit statement that the report supports expert review and is not operational approval. It
contains no external script source, runtime path, temporary path, legacy chart, or legacy fact.

## 6. Unified PNG contract

The PNG is rendered from the exact selected demand/supply figure at a fixed size and scale.
Kaleido's JavaScript path is copied to a stable ASCII temporary path when necessary because
Kaleido 0.2.1 cannot open a Unicode package path on Windows. That compatibility step does not
change figure data or the presentation fingerprint.

PNG failure rejects the entire unified bundle. Page 05 never exposes XLSX or HTML while silently
omitting the PNG.

## 7. Accepted-C authority

Only an independently validated accepted Scenario C projected into the unified presentation may
appear. Its solution fingerprint must align across the presentation, both stored figures, and the
actual XLSX metadata. The demand/supply figure displays its exact returned block counts; the
departure figure retains source-B mapping, shift, regime, reason, vehicle, and exact departure
times.

For mixed solver outcomes, an accepted recommended solution remains authoritative even when the
other solver candidate was rejected. Rejection codes remain diagnostic workbook evidence, while
the rejected raw timetable is absent and no artifact claims the accepted solution was rejected.

## 8. No-C behavior

When no accepted C exists:

- the accepted-C fingerprint remains `None`;
- no C trace or departure lane is rendered;
- all C block facts, fleet assignments, and headway regimes remain absent;
- the workbook requires `C_TRANG_THAI` and rejects accepted-C sheets;
- HTML contains no C timetable facts;
- Scenario B is never substituted for C;
- a legacy-only C remains fallback/review evidence, not unified authority.

Alpha characterizes this legacy-C-without-unified-authority boundary. Beta preserves its exact
outbound 17:00–18:00 demand gap and also has no accepted C.

## 9. Legacy fallback parity

The fallback retains the existing supply summary, direction selector, comparison overview,
departure detail, captions, C fingerprint behavior, and four download filenames. It is selected
for input-not-ready, unified-runtime-failed, cutover-blocked, incomplete/stale shadow evidence,
and Page 05 artifact failure states. Unified and legacy downloads are never mixed.

## 10. Expert-review behavior

Expert-review-only codes do not block unified Page 05. The page lists every code and states that
the charts and downloads are validation evidence, not operating approval. Blocking discrepancy
codes continue to select the labeled legacy fallback through the existing authority resolver.

## 11. Explicit non-approval status

All unified Page 05 artifacts remain `VALIDATION_ONLY`. They support deterministic review and
traceability; they do not approve an operating timetable, ridership forecast, solver quality,
fleet plan, terminal capacity, or deployment decision.

## 12. Remaining legacy-retirement decision

Milestone 5B2B does not remove legacy modules, session fields, exports, or fallbacks and does not
declare Milestone 5 complete. A separate reviewed decision is required before any legacy
retirement begins.

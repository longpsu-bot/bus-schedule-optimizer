# Milestone 5A2A: Authoritative Input Template

## Status and scope

Milestone 5A2A stabilizes the XLSX input boundary before unified chart and workbook
presentation adapters. It adds explicit field classifications and a deterministic readiness
assessment. It does not cut over Streamlit, change a solver, revise Contract V1, or redesign
result workbooks.

## Three requirement levels

Every parameter or authority field shown in the generated template has a text label as well as
distinct formatting:

- `BẮT BUỘC`: absence prevents meaningful import and continues to raise `InputDataError`.
- `BẮT BUỘC ĐỂ TỐI ƯU`: absence permits import and preview, but blocks authoritative fixed-resource
  normalization and optimization.
- `TÙY CHỌN`: absence does not block import or fixed-resource optimization.

Demand source type, confidence, and response mode use the conditional label
`BẮT BUỘC ĐỂ TỐI ƯU KHI CÓ SẢN LƯỢNG`. They are optimization authority only when `SAN_LUONG`
contains observations.

`vehicle_capacity_passengers` and `total_daily_trips` are import-required positive integers.
Blank, boolean, zero, negative, non-integral, and non-numeric values fail at import; integer
numeric text such as `"60"` is accepted. Runtime authority remains a one-of rule:
`allowed_trip_runtime_minutes` is preferred, while `trip_runtime_minutes` remains the legacy
fallback.

## Import readiness versus optimization readiness

`assess_workbook_input_readiness_v1(imported)` consumes only imported facts. It does not mutate
input, infer authority, normalize Contract V1 data, execute a solver, or create Scenario C. It
returns deterministic sorted codes in `WorkbookInputReadinessV1`.

A blank Scenario B `available_fleet_limit` therefore has this result:

- workbook import succeeds and the field remains `None`;
- `import_ready` is true;
- `optimization_ready` is false;
- `AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION` is reported; and
- the strict options builder refuses to construct Contract V1 options.

The builder never substitutes minimum calculated fleet, approved active fleet, timetable vehicle
IDs, timetable size, terminal positioning, zero, or a synthetic large value. A supplied fleet
limit is preserved exactly as the hard upper bound.

Scenario B `operating_day_type` is governed by the same fail-closed rule. When Scenario A is
present, its fleet limit and operating-day type are also required for authoritative optimization.
When Scenario A is absent, they are irrelevant to Scenario B readiness.

## Readiness API

The application-layer API is:

```python
assess_workbook_input_readiness_v1(
    imported: ImportedWorkbook,
) -> WorkbookInputReadinessV1

normalization_options_from_workbook_v1(
    imported: ImportedWorkbook,
    *,
    source_id: str,
    imported_at: datetime,
    source_type: InputSourceType = InputSourceType.XLSX,
) -> NormalizationOptions
```

`normalization_options_from_workbook_v1` applies the same readiness rules. If authority is
missing, it raises `WorkbookOptimizationAuthorityError` containing every sorted missing code.
Contract normalization is not called with placeholders.

The builder requires a non-empty string `source_id`, trims surrounding whitespace, and uses the
cleaned value consistently. It preserves declared workbook `demand_dataset_id`; only a blank
workbook dataset ID falls back to the cleaned runtime source identity.

## Optional facts and explicit limitations

`approved_active_fleet`, `demand_dataset_id`, `source_notes`, trip vehicle IDs, per-trip capacity
overrides, and an absent Scenario A remain optional. They are not converted into technical
authority.

Scenario B terminal occupancy limits remain independent and optional:

- neither supplied: `TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED`;
- only terminal 1 supplied: `TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED`;
- only terminal 2 supplied: `TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED`; and
- both supplied: complete terminal-capacity evaluation is available.

These limitations do not block other fixed-resource checks or optimization.

When workbook demand metadata omits the optional dataset ID, the imported metadata retains
`None`. The strict application builder maps the application-supplied runtime `source_id` to the
Contract-required demand identity; it does not create a route-derived ID or append a synthetic
`:demand` suffix.

## Conditional demand authority

`THONG_TIN_DU_LIEU` stores workbook-owned demand authority:

- `demand_dataset_id`;
- `demand_source_type`;
- `demand_confidence`;
- `demand_response_mode`; and
- `source_notes`.

With no passenger observations, blank demand authority does not block technical schedule
optimization. With observations, source type, confidence, and response mode must all be declared.
Confidence is preserved exactly and is never inferred or upgraded from observation count,
coverage, totals, or sheet names. Combined observations remain combined.

## Workbook-owned and runtime-owned facts

The workbook owns route, timetable, fleet, operating-day, terminal-capacity, and demand-authority
facts. Runtime provenance remains outside the workbook:

- `source_id`;
- `imported_at`; and
- `source_type`.

The domain layer does not derive runtime source identity from route ID or file name.

## Backward compatibility

Old workbooks without `THONG_TIN_DU_LIEU` still import and receive empty authority metadata. Blank
fleet or operating-day authority no longer reclassifies such workbooks as import-invalid; it
simply makes unified optimization readiness false. Existing direct `ImportedWorkbook`
constructors continue to work through a default metadata value, and the legacy analysis path
remains unchanged.

## Gate to Milestone 5A2B

The generated sample template declares complete optimization authority and round-trips through
Contract V1 normalization and side-by-side validation. Blank variants prove the fail-closed
readiness behavior.

This milestone supplies the input gate for a later Milestone 5A2B presentation-adapter task. It
does not authorize a Streamlit cutover, unified chart cutover, unified result-XLSX cutover, solver
change, Contract/schema change, variable-trip optimization, V1-A1, or the cancelled Phase B
architecture.

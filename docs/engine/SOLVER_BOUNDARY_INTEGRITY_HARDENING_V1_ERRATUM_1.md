# V1-H1 Erratum 1 — Zero-Minute Headway Semantics

**Status:** Normative clarification and implementation amendment

**Applies to:** `SOLVER_BOUNDARY_INTEGRITY_HARDENING_V1.md`, Contract V1 exact-timetable/headway semantics, and `contracts/v1/schedule_solution.schema.json`

**Contract version:** remains `1.0.0`

This erratum resolves the conflict between the approved V1-H1 requirement to preserve exact consecutive directional headways and the draft machine-readable schema that previously required every serialized regime headway to be at least one minute.

Where this erratum conflicts with V1-H1, this erratum controls. All other V1-H1 requirements remain unchanged.

## 1. Authoritative semantic decision

Contract V1 prohibits simultaneous departures **by one vehicle**. It does not prohibit two or more distinct vehicles from departing in the same direction at the same timestamp.

Therefore:

- exact directional ordering continues to use `(departure_time, trip_id)`;
- two consecutive same-direction departures may have an exact headway of `0` minutes;
- zero-minute headway is a representable observed timetable fact;
- the validator MUST NOT coerce `0` to `1`;
- the validator MUST NOT reject a candidate solely because an exact directional gap is `0`;
- the validator MUST still prove that simultaneous trips use sufficient distinct vehicle stock and do not assign one vehicle to simultaneous movements;
- normal fleet, terminal-stock, runtime, turnaround, count, lock, and traceability rules continue to apply.

A zero-minute headway may be undesirable from a service-quality perspective, but quality classification is distinct from technical representability and technical feasibility.

## 2. Schema erratum

The following fields in `contracts/v1/schedule_solution.schema.json` MUST accept non-negative integer minute values:

- `actual_headway_sequence`;
- `transition_headways`;
- `exceptional_headways`.

Their item constraint changes from:

```json
{"type": "integer", "minimum": 1}
```

to:

```json
{"type": "integer", "minimum": 0}
```

The following rules do **not** change:

- `target_headway` remains strictly positive;
- `target_service_rate` remains non-negative;
- `previous_b_headway` and `previous_c_headway` remain nullable and non-negative;
- timetable and regime times retain their existing Contract V1 representation;
- no new JSON field or enum is introduced.

## 3. Versioning and compatibility

This is a correction to a draft validation artifact, not a new business feature or a new contract shape.

Contract version remains `1.0.0` because:

- no property is added, removed, or renamed;
- no enum value is added or removed;
- every payload valid under the previous schema remains valid;
- the accepted numeric domain is widened only to include a timetable state already permitted by the authoritative semantic contract;
- coercing or discarding the exact zero gap would be a stronger and incorrect semantic change.

Consumers pinned to an older copy of the draft schema may reject a valid zero-headway payload. The repository schema after this erratum is the authoritative Contract V1 validation artifact for V1-H1 implementation and testing.

The V1-H1 statement that external schemas should remain unchanged is superseded only for this narrow `minimum: 1` to `minimum: 0` correction. It remains prohibited to add undeclared fields, change external object shape, add V1-A1 statuses, or otherwise broaden the implementation scope.

## 4. Independent derivation and reconciliation

For ordered same-direction member departures `d[0], d[1], ..., d[n-1]`, the authoritative regime sequence is:

```text
actual_headway_sequence[i] = (d[i + 1] - d[i]) / 60
```

Every value MUST be a non-negative whole number of minutes under the current minute-granularity Contract V1 representation.

The raw candidate claim must exactly reconcile with the derived sequence, subject only to the V1-H1 floating-representation tolerance where raw values are represented as numbers. A raw claim of `1` for a derived `0` is a `HEADWAY_REGIME_SEQUENCE_MISMATCH`; it is not accepted as rounding.

The same rule applies to validator-derived previous B and previous C headways: exact simultaneous directional departures produce a previous headway of `0`, not `null` and not `1`, except that the first directional trip remains `null`.

## 5. Regularity classification with zero gaps

V1-H1 §6.3 is clarified as follows:

- `REGULAR` when the regime has no gaps, or all actual gaps are equal and strictly positive;
- `BALANCED_ROUNDING` when all actual gaps are strictly positive and differ by no more than one minute;
- `EXCEPTIONAL` when any actual gap is `0`, or when positive gaps otherwise fail the two rules above;
- `TRANSITION` remains unavailable in the first cut without an explicit transition-evidence contract.

Thus, simultaneous departures are preserved as exact facts but are not presented as a normal regular service pattern.

For an `EXCEPTIONAL` regime, `exceptional_headways` remains the complete actual sequence under the current V1-H1 first-cut output rule. This ensures the zero gap remains visible and auditable.

## 6. Required implementation behavior

The implementation MUST:

1. derive zero gaps from the exact timetable without coercion;
2. compare raw previous-headway and regime-sequence claims against those exact values;
3. construct `ScheduleSolutionV1` using validator-derived zero values;
4. classify any regime containing a zero gap as `EXCEPTIONAL`;
5. serialize the zero values unchanged;
6. validate the resulting accepted solution against the corrected Contract V1 schema;
7. continue independent fleet and terminal-stock validation so simultaneous trips require distinct available vehicles.

The implementation MUST NOT:

- add a one-minute epsilon;
- move one of the departures solely to satisfy serialization;
- reject zero-gap candidates as structurally invalid when all hard technical constraints pass;
- treat simultaneous trips as movements of the same vehicle;
- change `target_headway` to zero;
- use this erratum to modify unrelated runtime, UI, diagram, XLSX, OR-Tools, or V1-A1 behavior.

## 7. Mandatory regression additions

In addition to the existing V1-H1 adversarial suite, tests MUST prove:

1. the corrected `schedule_solution.schema.json` accepts `actual_headway_sequence: [0]`;
2. two same-direction trips at the same timestamp derive a zero previous headway for the later trip under `(departure_time, trip_id)` ordering;
3. a raw claim of `1` when the exact gap is `0` is rejected;
4. a raw claim and exact derived sequence containing `0` can pass regime reconciliation;
5. an accepted solution preserves `0` in `actual_headway_sequence` and does not serialize it as `1`;
6. a regime containing a zero gap is classified `EXCEPTIONAL`;
7. a simultaneous-trip case with sufficient fleet can remain technically feasible;
8. the same case with insufficient fleet is rejected through existing fleet/stock rules rather than through a fabricated minimum-headway rule;
9. all payloads previously valid under the schema remain valid;
10. the full Pytest, Ruff lint, Ruff format, and JSON Schema suites remain green.

## 8. Scope boundary

This erratum does not establish a business minimum headway. A future approved policy may classify or prohibit headways below a configured threshold, but such a policy must have explicit configuration, provenance, disposition semantics, and versioned contract treatment. It must not be inferred from the former schema value `minimum: 1`.

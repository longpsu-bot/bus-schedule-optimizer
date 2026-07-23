# Visualization Contract V1

The authoritative visual rules are [Engine Contract V1 §§13–14](ENGINE_CONTRACT_V1.md) and [Amendment V1-A1](EXTREME_SERVICE_CHANGE_AND_DEMAND_SCENARIO_AMENDMENT_V1.md). Visuals consume authoritative domain outputs and fingerprints; they do not recalculate them.

## Shared controls and units

- Scenario mode: `Scenario B`, `Scenario C`, or `Compare B and C`.
- Value mode: `absolute interval values` or `normalized rate per hour`.
- Direction legend toggles: outbound, inbound, total.
- Unequal block durations default to normalized rates.
- Time uses a continuous axis; block geometry reflects actual duration.
- Passenger and trip measures use separate Y-axes and explicit units.

## Diagram 1 — Nhu cầu và số chuyến theo thời gian

### Demand layers

| Available evidence | Required traces | Composition |
|---|---|---|
| combined only | total demand polygon | one step/straight filled area; no directional traces |
| directional | total envelope + outbound + inbound | total is a light envelope; components overlap or sit within it, never stack with total |

No spline may imply unsupported observations. Boundaries and rates come from authoritative blocks. The layer label includes demand-response mode and direction confidence.

### Service lines

When both directions exist, B and/or C each provide outbound, inbound, and total lines. In compare mode this is six service lines, controlled by legend groups and sensible defaults. Labels use “chuyến”, “lượt xuất bến”, or “tần suất phục vụ”; never “số xe”. Fleet is a separate card or diagnostic.

Required-service references at 85% and 90% are visually subordinate dashed lines. Their legend/hover says “capacity ceiling”, not “target to match from both sides”.

### Hover contract

Hover reads the domain row for the interval and includes all items required by Contract V1 §13.1. Missing directional demand is shown as “not observed”, not zero. Status and shortage use stable codes plus localized labels.

## Diagram 2 — Phân bổ chuyến theo thời gian của từng biểu đồ giờ

Use three vertically aligned panels with shared X-axis and intervals:

1. A — current timetable;
2. B — proposed timetable;
3. C — demand redistribution.

Each panel shows outbound, inbound, and total. C absent/infeasible is an explicit empty-state panel with status, not a fabricated line. Optional B−A and C−B change shading may show donor/recipient periods but must reconcile to zero across the day in fixed-total mode.

Annotations identify total trip lock, directional lock mode, and moved-from/moved-to blocks. Panel scales remain aligned unless the user explicitly chooses independent scaling.

## Exact-departure diagnostic

Continuous-time X-axis, scenario/direction lanes, one marker per exact departure. C marker hover includes source B trip, B/C time, shift, regime, reason, and vehicle. This diagnostic does not substitute for either analytical diagram.

## Accessibility and export

Do not rely on color alone: use line dash/markers and textual status. Legends are toggleable. Vietnamese titles and units survive PNG/HTML export. Fingerprint and contract version are available in metadata and the exported caption/footer.

## Rendering acceptance tests

- variable-duration blocks have proportional widths;
- combined demand produces one demand polygon;
- directional components reconcile without double counting;
- all three timetable direction lines are available;
- B/C compare produces six service series when both directions exist;
- rates are default for unequal durations;
- trace totals reconcile with timetable totals;
- no trace is labeled vehicle count;
- view metadata fingerprint equals solution fingerprint.

## Structural-change scenario workflow

When `scenario_analysis_required = true`, the UI first presents a technical-change summary rather than a binary demand verdict. It shows A/B total trips, actual directional counts, directional headways, service-change factors, source-demand resolution, departures per source interval, triggering diagnostics, technical/fleet results, and the unresolved-demand status.

The base workflow does not ask users to re-enter demand. It offers configured scenario cards (`static_lower_bound`, `cautious_growth`, `moderate_growth`, `high_growth`, and `custom_approved`) with visible assumptions, provenance, confidence, total demand, passengers per trip, interval LF/shortage ranges, and monitoring requirements.

Observed A demand and scenario demand MUST use different labels and visual treatments. Scenario curves/areas are assumptions, never observations. Demand remains at source-supported interval grain; charts MUST NOT create one passenger point per proposed B departure.

Rendering acceptance additionally requires actual directional counts to reconcile to the two-direction total, per-direction headway display, structural-change trigger explanations, scenario-selection provenance, and an explicit post-implementation validation notice.

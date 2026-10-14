# MVP-3 operational timetable review and service guardrails

The existing CLI now delivers `operational_review.html`, a self-contained Vietnamese
report that opens from disk without a server or internet. It preserves the six
original JSON/XLSX outputs and adds an `operational_review` object to
`quality_report.json`. No search, compiler, selection, fleet optimizer, input workbook
or 25-plan budget was changed. No extra frontend dependency was added.

## Evidence and decisions

`mvp/review.py` independently checks engine quality and exact chains before building
the report. For each direction and demand interval it reports B/C departures, their
counts, full consecutive departure gaps, the positive overlap of each gap with that
interval, waiting integrals, waiting differences and passenger-minute impact. The
complete pair is retained even when one or both departures lie outside the bucket.
Integration uses the existing uniform-arrival `waiting` model against the actual
following departure; it never clips the full headway into an artificial shorter gap.

Demand buckets follow the existing `[start,end)` convention, including the final
service departure when it coincides with the bucket end. Protected minimum departure
counts use the existing authoritative `[start,end)` contract. The report discloses
passengers outside the service endpoints and excludes their unknown wait from the
modeled average. Provenance identifies the workbook hash, profile, dataset, demand
time basis and source assumptions; the workbook itself is not embedded.

`operator_decision` remains the engine's `REPLACE_BASELINE`, `KEEP_BASELINE` or
`UNRESOLVED`. Selection is never relabeled as operational approval. When B is retained,
the report compares its actual timestamps with the first engine-ranked generated
alternative, explicitly labeled as a trial, and uses B's exact chains as the selected
circulation. When no timetable is selected, an available alternative is only a review
reference; if none exists, actual B is reviewed as `BASELINE_REFERENCE`. A blocked
input still produces an insufficient-evidence HTML without invented metrics or regimes.

Readiness is separate, in precedence order:

1. `CONFIRMED_HARD_RULE_FAILURE`: a proven engine-contract failure blocks candidate approval.
2. `HUMAN_REVIEW_REQUIRED`: a material service warning requires operator review.
3. `INSUFFICIENT_OPERATIONAL_EVIDENCE`: required operational evidence remains absent.
4. `READY_FOR_HUMAN_APPROVAL_CONSIDERATION`: no hard failure or material warning and
   required operational assumptions/stock/protection declarations are supplied.

All missing evidence remains listed even when a hard failure or warning takes precedence.
Unknown protection or stock is never converted to PASS or FAIL. Existing applicable
fleet ceiling, stock, trip count, endpoints, protected headways/departure counts,
transition and configured hard boarding-proxy constraints retain their engine meaning.
The ready classification is consideration under declared assumptions, not approval or
certification of actual onboard load. That latter certification is always withheld.

### Review policy, not regulatory authority

`--review-settings review-settings.json` accepts these documented defaults:

```json
{
  "waiting_increase_minutes": 1.0,
  "waiting_increase_relative": 0.20,
  "high_demand_fraction": 0.75,
  "departure_reduction_fraction": 0.25,
  "headway_increase_minutes": 3.0
}
```

Warn when bucket waiting increases by more than
`max(waiting_increase_minutes, B_bucket_wait * waiting_increase_relative)`.
High demand means the bucket's passenger rate reaches at least 75% of the maximum
rate in the same direction. Warn on at least 25% fewer departures, or a longer maximum
intersecting gap by at least three minutes, in such a bucket. These thresholds are
provisional review calibration, not service authority; they do not affect the engine
decision. Percentages alone do not rank exceptions: proven protected failures come
first, then positive passenger-minute impact. Every intersecting pair is disclosed,
not just the day's longest gap. No school/worker peak or legal route class is inferred.

## Circulation and operating scenarios

The selected exact chains expose vehicle ID, starting terminal, trip sequence,
departure, arrival, ready time after layover, turnaround elapsed time and slack
`next_departure - ready`. No slack is invented after a vehicle's final trip.
Terminal flow starts with the chain-required stock and nets simultaneous events:
departure removes physical and ready stock, arrival adds physical stock, layover
completion adds ready stock. Every event conserves fleet and satisfies
`0 <= ready <= physically_present`. Concurrency is shown both for running vehicles
and running plus mandatory layover; it is not a substitute minimum-fleet calculation.

Flow models only the required vehicles. It excludes extra declared idle stock,
depot transfers, disruptions, driver shifts and stop-level passenger movement.
`initial_vehicles` is compared through the existing constrained path-cover contract.
`VERIFIED_AGAINST_DECLARED_STOCK` means the declaration supports the modeled chains,
not that physical availability was verified at a terminal. Absent stock is `UNVERIFIED`.
The optional provenance booleans `runtime_verified` and `layover_verified` must be
explicitly supplied to record operating confirmation; neither is inferred from
workbook presence, an explicit CLI value or route identity.

`--operating-scenarios scenarios.json` accepts only a list of uniquely named,
explicit runtime/layover changes. Each override must contain both directions:

```json
[
  {
    "name": "Explicit sensitivity supplied by operations",
    "runtime_minutes": {"outbound": 80, "inbound": 80},
    "layover_minutes": {"outbound": 7, "inbound": 7}
  }
]
```

These numbers are an example, not a route recommendation. Runtime overrides explicitly
replace any time-dependent runtime periods with the supplied constant model. Every
scenario keeps selected departures, independently rebuilds and validates chains,
reevaluates B under the same changed assumptions and applies the unchanged engine
constraints. Scenario evidence appears in JSON and HTML; it cannot change the selected
main timetable or decision. An exact scenario chain may still violate fleet/service
rules; independent validation does not mean operational admissibility. Solver limits
remain incomplete evidence, not a demonstrated hard failure. No scenario is generated
unless explicitly supplied.

## Independently rerun private-route evidence

Unmodified authoritative workbooks, `STABLE_MAR_JUL_2026`, explicit five-minute layover;
each route was run separately and reproduced deterministically:

| Measure | Route 6 | Route 10 |
| --- | ---: | ---: |
| Decision / selection | REPLACE_BASELINE / C010 | KEEP_BASELINE / B |
| B fleet → selected fleet | 20 → 16 | 12 → 12 |
| B wait → selected wait, minutes | 6.1656251053 → 6.1652384347 | 9.5702955186 → 9.5702955186 |
| Selected wait difference, minutes | -0.0003866706 | 0 |
| B maximum headway → selected | 15 → 18 | 25 → 25 |
| Selected starting stock, outbound / inbound | 7 / 9 | 5 / 7 |
| Declared hard rules | PASS_DECLARED_RULES | PASS_DECLARED_RULES |
| Selected readiness | HUMAN_REVIEW_REQUIRED | INSUFFICIENT_OPERATIONAL_EVIDENCE |
| Actual stock / onboard certification | Unverified / withheld | Unverified / withheld |

Route 6's justification remains four fewer vehicles with daily and directional wait
inside the existing equivalence bands, not material average waiting improvement.
There are **12** warning intervals: **12** material wait warnings, **7** high-demand
departure reductions and **4** high-demand longer-gap warnings (types can overlap).
Its most exposed deterioration is inbound 06:30–07:00, **+380.0331 passenger-minutes**.

| Route 6 direction / interval | B wait | C wait | B / C departures | C responsible departure pairs |
| --- | ---: | ---: | ---: | --- |
| Outbound 06:30–07:00 | 3.866667 | 6.566667 | 4 / 2 | 06:26→06:39, 06:39→06:52, 06:52→07:05 |
| Inbound 06:30–07:00 | 3.866667 | 6.400000 | 4 / 3 | 06:19→06:31, 06:31→06:43, 06:43→06:55, 06:55→07:07 |
| Inbound 16:30–17:00 | 4.000000 | 6.400000 | 4 / 3 | 16:19→16:31, 16:31→16:43, 16:43→16:55, 16:55→17:07 |

All eleven full 18-minute gaps are inbound, from **17:42→18:00** through
**20:42→21:00**. The three mandatory deterioration intervals above instead intersect
13- or 12-minute gaps. The report derives and distinguishes both concerns.

Route 10 retains B because generated alternatives do not justify replacement.
The comparison trial C013 uses 11 vehicles but modeled wait 9.7857123912 exceeds
service equivalence; simpler regimes/lower fleet cannot override that decision.
That trial has **16** exception intervals, including **15** material waiting warnings,
**3** high-demand departure reductions and **2** high-demand longer-gap warnings.
These are C013 comparison warnings, not warnings attributed to selected B.

Both routes lack actual terminal stock, protected-window authority, operational
runtime/layover confirmation and stop-level occupancy evidence. Out-of-service demand
is disclosed as another missing waiting-evidence boundary. Reports explicitly state
`CHƯA ĐỦ DỮ LIỆU ĐÁNH GIÁ` without inventing protection or certifying field operation.

Source SHA256 identities:

- Route 6: `4a5030da74d809b8a8bb40364bdc54f625c12469850d1d6ba1385622ab8d8f11`.
- Route 10: `876c5c709dfb6fee21ade63150302704f6c09589bf8a927bad279fbc88ff2b94`.

Hard 0.8 boarding-proxy checks independently preserve MVP-2 behavior: Route 6 keeps
compliant B (20 vehicles; maximum proxy 51.5882352941 <=54.4); Route 10 is UNRESOLVED
because B exceeds 40.8 and no admissible generated timetable is found within the
unchanged budget. This is not proof of route infeasibility or of actual onboard load.

## Validation and handoff

Focused command, with both private workbook environment variables supplied:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_mvp_service_plan.py tests/test_mvp_acceptance.py tests/test_mvp_review.py --basetemp outputs/mvp3_validation/focused-last --tb=short
python -m pytest -s --basetemp outputs/mvp3_validation/full-last --tb=short
python -m ruff check . --exclude .artifact --exclude outputs --exclude .venv
python -m ruff format --check src/bus_schedule_engine/contracts_v1 tests/test_contract*.py
python -m ruff format --check src/bus_schedule_engine/mvp scripts/run_mvp_service_plan.py tests/test_mvp*.py
```

Focused: **87 passed**, including six separately parameterized private acceptance
cases and actual CLI scenario/settings handling. Exact HTML metric attributes equal
JSON values; deterministic repeated results and HTML, escaped malicious route/source
text, protected headway and minimum-departure failures, actual/missing stock, terminal
conservation, sensitivity fleet failures and baseline-only/UNRESOLVED reports are tested.
Full local suite had **1539 passed, 4 skipped, 4 inherited failures**; subsequent
precision/missing-label fixes and one added 0.85-factor regression passed the final
87-test focused run. The pushed CI outcome is reported with the final SHA in the
completion message. The unchanged inherited tests alone reproduced **59 passed, 4 skipped,
4 failures**: frozen template fingerprint under the local Python/runtime and three
CRLF/LF corpus-byte comparisons. No frozen source expectations were altered.

Offline Chromium checks covered 1440-pixel desktop, 390-pixel narrow view, SVG content,
zero script errors, no document overflow and print. Open detail tables are printable;
the default print keeps a compact main report and respects which details are expanded.
All assets are inline. The Impeccable mechanical detector returned no findings.
Vietnamese language QA confirmed NFC and formal impersonal wording. The copy linter's
NUM001 flags legitimate three-place Vietnamese comma decimals as English grouping;
these were reviewed as false positives rather than changing numeric meaning.

Independent implementation review found and reproduced one P2: UNRESOLVED could claim
B was retained. A failing regression preceded the fix; the reviewer then verified the
decision wording and fallback, with no further logic findings. The minor fallback
heading that named C while reviewing B was also corrected.

Local output folders under the MVP worktree:

- `outputs/mvp3_validation/route_6/operational_review.html`.
- `outputs/mvp3_validation/route_10/operational_review.html`.
- `outputs/mvp3_validation/route_6_hard08/operational_review.html`.
- `outputs/mvp3_validation/route_10_hard08/operational_review.html`.

Private inputs/reports stay ignored, outside the commit. Continue existing Draft PR
#63; never merge. The next product decision is to review Route 6's affected intervals
with operations, agree on service protection and warning materiality, confirm stock
7/9 and runtime/layover, then choose whether C010 should be revised or submitted for
human approval consideration. Retain Route 10 B. Capacity lookahead, new compilation,
network optimization and Streamlit redesign remain excluded.

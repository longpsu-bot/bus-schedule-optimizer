# Crew rest and recovery review

This is a read-only review of the frozen MVP-6A Route 10 evidence from engine base `6f8f7644b8ac642f6eabc0ad5e6ba0ca0ef9f56e`. It does not search for timetables, change circulation/selection, impose constraints, or create crew assignments. PR #63 stays unchanged and unmerged.

## Reproduce with private inputs

The workbook must match SHA-256 `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`. Reuse the existing `outputs/mvp6a_final/fleet_report.json`; the reviewed frozen file has SHA-256 `1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3`. Keep those files outside Git. Run from the repository root:

```powershell
$env:PYTHONPATH='src'
$env:OPENPYXL_LXML='False'
python scripts/review_route10_crew.py --input '<private-workbook.xlsx>' --evidence '<private-fleet_report.json>' --evidence-sha256 1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3 --output-dir outputs/crew_rest_review
```

Outputs, all private and Git-ignored:

- `crew_review.json`: input digests, normalized analysis-code fingerprints, explicit policies, every chain/trip/connection and conditional break/relief opportunity.
- `crew_report_vi.md`: Vietnamese findings A–F, common-runtime B/X/C comparisons, sensitivity and legal limits.
- `chain_evidence_vi.md`: every-chain vehicle metrics, trip clocks, terminal dwells and role-specific opportunities.

The command verifies the frozen bundles against the workbook, re-evaluates passenger metrics, validates stored chains and independently audits exact fleet counts with the existing maximum-flow implementation. It locks the p50 incumbent and nine review exceptions. Its only new fleet assignments use the **unchanged p50 departures** at p75 runtime. Native p75 C remains the existing near-feasible trial, never a recommendation. Original recorded X clocks/vehicle groups remain separate from common-runtime X; reported layover discrepancies are retained for reconciliation.

Output bytes are deterministic for identical source bytes, analysis code, profile values and operating-date input. No machine paths or wall-clock durations are exported. The source JSON digest changes if the original pilot is rerun with different diagnostic timing; the pinned digest identifies the reused frozen evidence, not a claim that the original optimizer's wall-clock diagnostics are byte-identical across runs.

## Operational meaning and policy inputs

Vehicle feasibility, recovery resilience, crew-rest feasibility and operational approval are separate claims. The overall result is `PARTIAL_EVIDENCE` because actual assignments, duties, relief availability and work/break records are absent. `VERIFIED_CONSTRAINT_FAILURE` refers only to a demonstrated vehicle-connection failure under the declared scenario, not a finding of labour-law violation.

Scheduled dwell is next departure minus modeled arrival. Technical turnaround is the declared experimental five minutes at the destination terminal. Slack is dwell minus technical turnaround; negative stress values describe missing scheduled recovery, without propagating delay. The default short-turnaround threshold is strictly less than ten minutes and is illustrative.

Exact minimum fleet counts are certificates; dwell and break statistics describe the particular stored/recomputed minimum-fleet witness. They are not bounds on all assignments with the same fleet. Common runtimes are descriptive nearest-rank summaries of recorded X trips, with some sparse groups, not calibrated B/C reliability distributions or probabilistic on-time guarantees.

For the fixed-vehicle proxy, **technical turnaround + post-arrival tasks + separately reserved recovery + continuous free interval + pre-departure tasks** occupy disjoint modeled time. Charging technical time separately from crew tasks is a conservative sensitivity assumption, not a calibrated work standard. A free interval must fit wholly within one declared window; short waits never aggregate into one break. Only interior gaps between assigned trips count; pre-duty/post-duty time is not a midshift break. Overlap with the vehicle span is only a sensitivity denominator, not proof that a worker is owed a break at that time.

The relief scenario assumes that an eligible substitute is already at the terminal, the declared handover can finish before the next departure, and remaining vehicle/boarding duties can be delegated. It lists the trips that would need a substitute, while recording staff availability and the relieved worker's return assignment as unknown. It neither repairs a broken vehicle connection nor certifies staffing. Break candidates are evaluated separately and do not form a simultaneous roster.

Without operator policies, three explicitly illustrative profiles vary windows, break lengths, terminal work and reserved recovery. Drivers and attendants have separate inputs; no driver-only rule is inferred for an attendant. All profile values are in the exported JSON. To supply alternatives, use `--policies <private-profiles.json>`; time values are minutes from midnight. For example:

```json
{
  "operator_draft": {
    "authority": "OPERATOR_SUPPLIED_UNVERIFIED",
    "short_turnaround_minutes": 10,
    "roles": {
      "driver": [
        {"name": "meal", "start": 660, "end": 840, "minutes": 30, "tasks_after": 5, "tasks_before": 5, "reserve": 5, "handover": 5},
        {"name": "afternoon", "start": 840, "end": 1020, "minutes": 20, "tasks_after": 5, "tasks_before": 5, "reserve": 5, "handover": 5}
      ],
      "attendant": [
        {"name": "meal", "start": 660, "end": 840, "minutes": 30, "tasks_after": 5, "tasks_before": 5, "reserve": 5, "handover": 5},
        {"name": "afternoon", "start": 840, "end": 1020, "minutes": 30, "tasks_after": 5, "tasks_before": 5, "reserve": 5, "handover": 5}
      ]
    }
  }
}
```

These clock windows are **not legal requirements**. A named empty policy (`{"unknown": {}}`) exports missing policy/crew evidence instead of inferring compliance. Malformed, negative, nonfinite, contradictory-duration, duplicate-name and overlapping-window inputs are rejected. Overlapping windows would require joint coverage reasoning outside this review's scope. A role may be omitted only as unknown, not as an implicit exemption. `--operating-date YYYY-MM-DD` records an operator-supplied date; it does not certify legal applicability or update the legal review.

## Legal verification as of 27 October 2026

The workbook does not establish an operating date. Distinguish the applicable period before evaluating a real roster:

- [Article 64, consolidated Law 55/VBHN-VPQH](https://vanban.chinhphu.vn/?classid=0&docid=217295&pageid=27160): Article 7(15) of Law 118/2025/QH15 changes paragraph 1 from **1 July 2026**. It retains a four-hour continuous-driving limit, subject to force majeure/objective obstacles, while daily/weekly working time follows the Labour Code. The previous ten-hour daily/48-hour weekly driving limits must not be restated as the amended current text. [Official gazette containing Law 118](https://congbao.cdnchinhphu.vn/180507251028987904/2026/1/23/cong-bao-so-35-ngay-21-01-46933signed-17691635381941800021702.pdf).
- [Labour Code 2019, Article 109](https://vanban.chinhphu.vn/?classid=1&docid=198540&pageid=27160&typegroupid=3), effective 1 January 2021, and [2026 consolidated Labour Code](https://chinhphu.vn/?docid=217002&pageid=27160): work of at least six hours/day triggers a continuous break of at least 30 minutes; qualifying night work requires 45 minutes. Article 116 includes special transport work while retaining Article 109 protection. Actual employee work/duties, rather than a vehicle span, determine applicability.
- [Decree 145/2020, Articles 63–64](https://vanban.chinhphu.vn/default.aspx?docid=201967&pageid=27160), initially effective 1 February 2021: the 45-minute night break requires at least six hours' daily work including at least three hours in 22:00–06:00. Breaks cannot be placed at the beginning/end of the shift. Continuous-shift paid-break treatment has separate conditions, including a shift of at least six hours and transition of at most 45 minutes. The decree is partially expired; no amendment to these two articles was identified in the sources checked. [Official explanation of Articles 63–64](https://baochinhphu.vn/thoi-gian-nghi-trong-gio-lam-viec-co-duoc-tinh-tra-luong-102291050.htm).
- [Decree 158/2024](https://chinhphu.vn/?classid=1&docid=212082&pageid=27160) replaced Decree 10/2020 from 1 January 2025; [Decree 218/2026](https://chinhphu.vn/?classid=1&docid=218537&pageid=27160&typegroupid=4) amended it from **10 August 2026**. Do not carry over an old five-/15-minute stop rule, or automatically reset continuous-driving exposure using five minutes, without confirming the current basis. Such a stop is distinct from a Labour Code continuous break.

No universal statutory lunch/afternoon clock window was found in those provisions. Route-specific special rules and local requirements remain unverified. The review cannot certify compliance/noncompliance, actual continuous-driving exposure, overtime or employee headcount without authoritative crew records.

## Validation

```powershell
$env:PYTHONPATH='src'
$env:OPENPYXL_LXML='False'
$env:BUS_MVP5_ROUTE10_WORKBOOK='<private-workbook.xlsx>'
$env:BUS_CREW_FROZEN_EVIDENCE='<private-fleet_report.json>'
python -m pytest tests/test_crew_review.py --basetemp=outputs/crew_tests -ra
python -m ruff check . --exclude .artifact --exclude outputs --exclude .venv
python -m ruff format --check src/bus_schedule_engine/mvp/crew_review.py src/bus_schedule_engine/mvp/route10_crew_review.py scripts/review_route10_crew.py tests/test_crew_review.py
```

The private review test consumes frozen evidence; it does not rerun the optimizer. Legacy private pilot tests do run the old search and were left disabled for this review because the frozen evidence was available. Synthetic MVP, circulation, review and external-import/benchmark regressions were exercised separately.

Independent reviewers checked legal sources and independently reconciled raw workbook clocks, runtime quantiles, 3,102 native/fixed-stress interval comparisons and minimum fleets. Review found and resolved a per-file Git-ignore guard gap and malformed-policy validation. A further self-check fixed stale ready-time metadata when arrivals change under stress; source arrival is retained separately. Final validation counts and local-versus-Actions status are recorded in the execution plan. No new PR, merge or operational-constraint implementation is part of this review.

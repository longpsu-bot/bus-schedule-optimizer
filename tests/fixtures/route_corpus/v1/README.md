# Anonymized Route Corpus V1

**Status: DRAFT — NOT AN APPROVED OPERATIONAL TIMETABLE**

This directory contains two versioned, anonymized, real-route-derived fixtures:

- `CORPUS-ALPHA-80`;
- `CORPUS-BETA-46`.

The private source workbooks remain outside the repository. `manifest.json` records their
SHA-256 identities, audited corrections, observed facts, derived datasets, and corpus scenario
assumptions without recording a local path or private route, terminal, operator, organization, or
vehicle identity.

## Demand evidence and proxy

`SAN_LUONG` rows are preserved one-to-one as `raw_trip_observations`. Their intervals exactly
match Scenario A trip departure-to-arrival spans, so their overlaps are retained and documented.
They are evidence rows, not Contract V1 demand intervals, and test support never supplies them to
normalization.

`departure_hour_proxy_v1` is a separate LOW-confidence sensitivity dataset. It:

- groups passenger volumes by direction and Scenario A departure hour;
- lists every contributing Scenario A trip ID;
- conserves directional and overall 15-day passenger totals exactly;
- retains `volume_type=total_observation_period` and `observation_days=15`;
- uses one exact clock-hour block for each ordinary observed departure hour;
- clips the first block to the exact Scenario B first departure;
- ends the final block one minute after the exact Scenario B last departure; and
- leaves an unobserved interior hour as an explicit gap rather than filling or absorbing it.

Contract V1 derives average daily demand by dividing each exact source-period total by its
15-day observation count. The committed passenger values are never relabeled as average-day
counts, rounded, interpolated, or rescaled.

With the default MEDIUM authority threshold, the LOW-confidence proxy legitimately produces an
insufficient-data/no-solver result. A separately labeled `PROXY_SENSITIVITY_ONLY` diagnostic may
lower the threshold to LOW, but both solvers run only when a complete common canonical quality
problem can be constructed. Incomplete coverage or unsupported normalized decimal precision
produces an explicit not-run result.

## Authority and exclusions

Exact timetable rows are authoritative over inconsistent Scenario A summary fields documented in
the manifest. The historical diagnostic, hourly-allocation, and optimized timetable sheets are
excluded from corpus truth. They are never engine input or exact expected output.

Observation dates use a fixed −365-day shift. Exact timetable times, trip-specific runtimes,
direction, relative terminal identity, passenger volumes, observation-day count, vehicle
capacity, route type, load-factor policy, and turnaround are otherwise retained under the
documented reconciliation and proxy rules.

## Rebuild and verify

Set `BUS_SCHEDULE_PRIVATE_CORPUS_DIR` to the approved external directory, then run:

```powershell
.\.venv\Scripts\python.exe tools\build_route_corpus_v1.py --write
.\.venv\Scripts\python.exe tools\build_route_corpus_v1.py --verify
```

Generation is deterministic: UTF-8, sorted keys, two-space indentation, one terminal newline, and
no generated timestamp.

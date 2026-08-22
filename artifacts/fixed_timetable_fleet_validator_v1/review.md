# Fixed-Timetable Fleet Feasibility Validator V1 — MST 6 & 10

> Fixed departures, trip allocations, runtimes, and layover authority are immutable.
> `available_fleet_limit` is a pilot hard upper bound; approved active fleet and
> terminal physical capacity remain unknown.

## Input verification

- Operational inputs SHA-256: `69eb92b7c13f3c6e4861a3898709bfdc8f857b151723113ab31525a3129de6c3` (verified)
- Scenario B departures SHA-256: `ac6291dbdef6d8afc30788b584541d56bac96f8a3563a3ae415e01685ca1a340` (verified)
- Compiler artifacts byte-identical after validation: `true`

## Feasibility matrix

| Route | Out | In | Fleet | Limit | Margin | Initial T1/T2 | End T1/T2 | Min/Median/Max layover | Total excess wait | Max excess wait | Δ fleet vs B | Δ wait vs B | Status |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 10 | B | B | 12 | 13 | 1 | 5/7 | 5/7 | 5/35/60 | 2645 | 55 | 0 | 0 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C1 | C1 | 13 | 13 | 0 | 6/7 | 6/7 | 5/22/62 | 1640 | 57 | 1 | -1005 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C1 | C2 | 12 | 13 | 1 | 6/6 | 6/6 | 5/19/65 | 1722 | 60 | 0 | -923 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C1 | C3 | 12 | 13 | 1 | 6/6 | 6/6 | 5/19/65 | 1722 | 60 | 0 | -923 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C2 | C1 | 12 | 13 | 1 | 6/6 | 6/6 | 6/22/40 | 1443 | 35 | 0 | -1202 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C2 | C2 | 11 | 13 | 2 | 6/5 | 6/5 | 5/17/39 | 1276 | 34 | -1 | -1369 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C2 | C3 | 11 | 13 | 2 | 6/5 | 6/5 | 5/17/39 | 1276 | 34 | -1 | -1369 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C3 | C1 | 12 | 13 | 1 | 6/6 | 6/6 | 6/20/44 | 1447 | 39 | 0 | -1198 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C3 | C2 | 11 | 13 | 2 | 6/5 | 6/5 | 5/15/45 | 1280 | 40 | -1 | -1365 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 10 | C3 | C3 | 11 | 13 | 2 | 6/5 | 6/5 | 5/15/45 | 1280 | 40 | -1 | -1365 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 6 | B | B | 20 | 20 | 0 | 10/10 | 10/10 | 5/39/80 | 4830 | 75 | 0 | 0 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 6 | C1 | C1 | 21 | 20 | -1 | 9/12 | 9/12 | 5/26/93 | 4055 | 88 | 1 | -775 | FEASIBLE_BUT_EXCEEDS_PILOT_FLEET_LIMIT |
| 6 | C1 | C2 | 21 | 20 | -1 | 8/13 | 8/13 | 5/27/109 | 4011 | 104 | 1 | -819 | FEASIBLE_BUT_EXCEEDS_PILOT_FLEET_LIMIT |
| 6 | C1 | C3 | 21 | 20 | -1 | 8/13 | 8/13 | 5/27/109 | 4011 | 104 | 1 | -819 | FEASIBLE_BUT_EXCEEDS_PILOT_FLEET_LIMIT |
| 6 | C2 | C1 | 19 | 20 | 1 | 9/10 | 9/10 | 5/31/76 | 3938 | 71 | -1 | -892 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 6 | C2 | C2 | 19 | 20 | 1 | 8/11 | 8/11 | 5/27/80 | 3566 | 75 | -1 | -1264 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 6 | C2 | C3 | 19 | 20 | 1 | 8/11 | 8/11 | 5/27/80 | 3566 | 75 | -1 | -1264 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 6 | C3 | C1 | 19 | 20 | 1 | 9/10 | 9/10 | 5/31/76 | 3938 | 71 | -1 | -892 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 6 | C3 | C2 | 19 | 20 | 1 | 8/11 | 8/11 | 5/27/80 | 3566 | 75 | -1 | -1264 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |
| 6 | C3 | C3 | 19 | 20 | 1 | 8/11 | 8/11 | 5/27/80 | 3566 | 75 | -1 | -1264 | FEASIBLE_WITHIN_PILOT_FLEET_LIMIT |

Every combination has a detailed canonical vehicle-block JSON artifact referenced in `review.json`. No final Scenario C timetable is selected by this milestone.

# PR62-G — Final Route 6 / Route 10 pilot selection

Certification status: **PILOT_FINAL_CERTIFIED**.

## Route 6

- Pair: `b6712e5e1a552fa75fbfe042454b7d0568e4cd06b265b7d38d8760358dfb4063`
- Trips: 156
- Fleet: 19/20
- Expected wait: 6.043783 minutes
- Mismatch: 0.007197
- ServiceRegime headways: 16 / 10 / 14 / 10 / 15 / 8 / 14 / 15 / 16 / 9 / 14 / 10 / 15 / 9 / 15
- Workbook: `outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx` (34569 bytes; SHA-256 `35a4ef65b0bc64cc8e18397c27bc7a135d5039857321f06e5ec5aadf15bf8879`; logical `7c66dc26d59a4ae157d9ed0900ce823c63b280512bedf8e77320aa8da50d0028`)

## Route 10

- Pair: `e8daa851f95a2eee08d6e6ccf6524adfbd5a0187932dcf35cb90f257f9d0043b`
- Trips: 102
- Fleet: 12/13
- Expected wait: 9.537105 minutes
- Mismatch: 0.011871
- ServiceRegime headways: 17 / 18 / 20 / 19 / 17 / 22 / 23 / 19 / 20 / 17 / 21 / 20
- Workbook: `outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx` (29256 bytes; SHA-256 `e49031892388714850001c0a97f91db9e3380b2dc0808d45095ce9825abf9da0`; logical `4604cec74defddb37df12e2b6b3aedffa5371e50777f1050a4cd9bf08074571a`)

Route 6 robustness classification: **BASELINE_TIMETABLE_ROBUST_AT_10**; the same timetable requires 20/20 vehicles at the 10-minute sensitivity and the official authority remains 5 minutes.

Search architecture, budgets, queue, Pareto, compiler, fleet validator, demand-response semantics, official Route 6 layover, and settlement are unchanged. No selected time was manually edited.

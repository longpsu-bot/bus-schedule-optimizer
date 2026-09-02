# PR62-P — Final V2 timetable recertification

Cross-route classification: **FINAL_PILOT_PRODUCTS_RECERTIFIED_V2**.

## Route 6

- Selected pair: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`
- Common anchor: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`
- Selection: `ONE_TRIP_MATERIALITY_SELECTS_ANCHOR`
- Trips: 78 outbound / 78 inbound
- Fleet: 20/20
- SSE / TE: 0.006691496954 / 20.923773759044
- Workbook SHA-256: `13454026722f996d8b06e5305b3b6ab2d57ea6126734f4deeb23c3e7dbafd02c`; logical `99f68763c30d99b3690da77d96079cdeef18705a9ad82dfbe40b4b5375726864`

## Route 10

- Selected pair: `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`
- Common anchor: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`
- Selection: `ONE_TRIP_MATERIALITY_SELECTS_SIMPLER_ALTERNATIVE`
- Trips: 51 outbound / 51 inbound
- Fleet: 12/13
- SSE / TE: 0.010728881378 / 17.669451511449
- Workbook SHA-256: `d84dd2e873d3ba30275463a5eff67277a22467839af0f0125e69160a891fc3db`; logical `bfc1687b66a6e38f51459a516e50b1caa01ae438296bbbf1a95bf94c5b99f338`

Both timetables passed exact production selection, protection, tail, directional access, fleet, artifact, formula, visual, and deterministic-generation checks.

`READY_FOR_FINAL_PILOT_USE = true`

`READY_FOR_PR62_COMPLETION_REVIEW = true`

## Validation

Overall validation: **PASSED**.

- focused_p_and_g_tests: `PASSED`
- requested_regression_suites: `PASSED`
- artifact_tool_staged_and_canonical_verification: `PASSED`
- deterministic_workbook_generation: `PASSED`
- deterministic_evidence_render: `PASSED`
- ruff: `PASSED`
- format_check: `PASSED`
- python_compilation: `PASSED`
- mjs_syntax_and_runtime: `PASSED`
- git_diff_check: `PASSED`

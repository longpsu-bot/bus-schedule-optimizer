# PR62-U6 V3 anchor conflict review

This is an evidence/root-cause review only. No selector, coordinator, compiler, validator, Pareto logic, timetable, XLSX, or production policy was changed. No replacement timetable is selected.

## Authority and invariant

- Base SHA: `185dbee3b86a7ec838723c4e9d50bc2e88bf373b`.
- Canonical U6 semantic SHA-256: `46cd605e4ffb0a9aa00bb9376002b2001ada60760d460e1cbf38ba69aa549d99`.
- Canonical U6 evidence SHA-256: `0dcb75205c329a3fc512f475cb619eee61be9b3d25342ae6e12fa923a9bf6877`.
- Frozen Route 10 demand SHA-256: `f60e06f5de337a0acb1aa4716b951a6c6d5477c0ccbe9dc41e57c4814871600d`.
- Route 6 global execution count: `0`.

Source verification confirms half-open bucket membership `[start,end)`, directional SSE as the sum of squared service-share residuals, and directional TE as directional trips times half the L1 residual. Pair values are directional sums. Thus SSE and TE are L2-squared and L1/TV norms over the same residual vectors; a common minimizer was never mathematically guaranteed.

## Exact conflict

The complete canonical 123-candidate Pareto frontier was reconstructed. All 83 access-safe snapshots independently reproduced serialized SSE, expected-wait, and access values within `1e-12`; TE was recomputed from exact counts and the verified V2 formula rather than trusted from serialization.

| Role | Pair fingerprint | SSE | TE | Cross metric | Continuous | Continuous rank |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| SSE-best | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 0.009369737096 | 16.957200065675 | TE=16.957200065675 | 12.905528866964 | 2 |
| TE-best | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | 0.009503607918 | 16.582604218230 | SSE=0.009503607918 | 14.157160266920 | 26 |

Both candidates independently satisfy fixed trips/endpoints, strict whole-minute departures, tail eligibility, protected-service authority, Scenario-B directional access, and exact fleet validation; both also appear in the canonical hard-feasible and access-safe stage traces.

### Candidate identity and operations

#### SSE-best

- Lineage: `{"child_rhythm":null,"generated_by_u6":false,"parent_pair_fingerprint":null,"parent_rhythm":null,"present_in_original_11_candidate_base_frontier":true,"source_pair_fingerprint":null}`.
- Outbound/inbound compilation: `d94f17e5bb584aff6fc78dd20030746d9cd51a60cc79348c98b3b59554f62f9b` / `d408d4a638de816da92c060d0d73cbe0bc07f66dfdba0ae68b6117aa8addee06`.
- Rhythm tuple: `[11, 12, 7, 0]`; fleet `13`; terminal excess total/max `2432` / `71`.
- Average expected passenger wait: `9.592579549111` minutes; maximum access outbound/inbound `12.900000000000` / `13.366666666667` minutes.
- Outbound exact departures: `05:00, 05:19, 05:38, 05:57, 06:16, 06:35, 06:56, 07:17, 07:38, 07:59, 08:19, 08:39, 08:59, 09:19, 09:39, 09:59, 10:19, 10:39, 10:59, 11:19, 11:39, 11:59, 12:19, 12:38, 12:57, 13:16, 13:35, 13:54, 14:13, 14:32, 14:51, 15:10, 15:29, 15:48, 16:02, 16:16, 16:30, 16:44, 16:58, 17:12, 17:30, 17:48, 18:06, 18:24, 18:42, 19:05, 19:28, 19:51, 20:14, 20:37, 21:00`.
- Outbound exact ServiceRegime headway runs: `19m×5, 21m×4, 20m×13, 19m×11, 14m×6, 18m×5, 23m×6`.
- Inbound exact departures: `04:45, 05:00, 05:15, 05:30, 05:45, 06:00, 06:15, 06:30, 06:45, 07:07, 07:29, 07:51, 08:13, 08:35, 08:57, 09:19, 09:41, 10:03, 10:25, 10:47, 11:09, 11:31, 11:53, 12:15, 12:37, 12:59, 13:21, 13:43, 14:05, 14:27, 14:49, 15:11, 15:33, 15:46, 15:59, 16:12, 16:25, 16:38, 16:51, 17:04, 17:17, 17:30, 17:53, 18:16, 18:39, 19:02, 19:25, 19:48, 20:12, 20:36, 21:00`.
- Inbound exact ServiceRegime headway runs: `15m×8, 22m×24, 13m×9, 23m×6, 24m×3`.

#### TE-best

- Lineage: `{"child_rhythm":[8,11,6,0],"generated_by_u6":true,"parent_pair_fingerprint":"c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7","parent_rhythm":[8,12,6,0],"present_in_original_11_candidate_base_frontier":false,"source_pair_fingerprint":"c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7"}`.
- Outbound/inbound compilation: `954d4c8f729b597220ac43b9cd5de69307220d271ac542769c9fd1638b1c01c9` / `b8095af0143a2e433957851a3fdd87d2c72dcad7bcd5417ba604432949c560ad`.
- Rhythm tuple: `[8, 11, 6, 0]`; fleet `12`; terminal excess total/max `2035` / `59`.
- Average expected passenger wait: `9.649154876527` minutes; maximum access outbound/inbound `13.800000000000` / `14.066666666667` minutes.
- Outbound exact departures: `05:00, 05:17, 05:34, 05:51, 06:08, 06:25, 06:42, 06:59, 07:16, 07:33, 07:50, 08:14, 08:38, 09:02, 09:26, 09:50, 10:07, 10:24, 10:41, 10:58, 11:15, 11:32, 11:49, 12:06, 12:27, 12:48, 13:09, 13:30, 13:51, 14:12, 14:33, 14:54, 15:15, 15:30, 15:45, 16:00, 16:15, 16:30, 16:45, 17:00, 17:15, 17:30, 17:52, 18:14, 18:36, 19:00, 19:24, 19:48, 20:12, 20:36, 21:00`.
- Outbound exact ServiceRegime headway runs: `17m×10, 24m×5, 17m×8, 21m×9, 15m×9, 22m×3, 24m×6`.
- Inbound exact departures: `04:45, 05:04, 05:23, 05:42, 06:01, 06:20, 06:39, 06:58, 07:17, 07:36, 07:55, 08:14, 08:33, 08:52, 09:11, 09:30, 09:49, 10:08, 10:27, 10:46, 11:05, 11:24, 11:43, 12:02, 12:21, 12:40, 12:59, 13:18, 13:37, 13:56, 14:15, 14:34, 14:53, 15:12, 15:31, 15:51, 16:11, 16:31, 16:51, 17:11, 17:30, 17:49, 18:08, 18:27, 18:46, 19:05, 19:24, 19:43, 20:02, 20:31, 21:00`.
- Inbound exact ServiceRegime headway runs: `19m×34, 20m×5, 19m×9, 29m×2`.

## Root cause

Diagnostic sub-classification: **SSE_TE_NORM_DISAGREEMENT_CONFIRMED**.

The independently reconstructed candidates use the same frozen bucket assignments for both metrics. Their valid residual vectors reverse order because squared L2 favors more dispersed smaller residuals while L1/TV favors less total displaced mass despite a larger peak residual. Boundary crossings affect the residual vectors, but no separate bucket or pair aggregation path exists between SSE and TE, so aliasing is not the primary cause of their mutual reversal.

Both candidates have `68` nonzero residual buckets, so the reversal is not a literal nonzero-bucket-count difference. The SSE-best maximum absolute residual is `0.029241578520` and its concentration index is `0.021188464147`; TE-best has the larger peak `0.031415091189` and higher concentration index `0.022473121548`. Squared error rejects that concentration, while L1/TV accepts it because total displaced service mass falls from `0.664988237870` to `0.650298204636`.

### Materially differing buckets

Only buckets whose point-count residuals differ are shown.

| Dir | Bucket | Demand share | SSE-best count/residual/SSE/TE | TE-best count/residual/SSE/TE | TE-best − SSE-best SSE/TE |
| --- | --- | ---: | --- | --- | --- |
| outbound | 06:00–06:30 | 0.030653012090 | 1 / -0.011045168953 / 0.000121995757 / 0.281651808301 | 2 / 0.008562674184 / 0.000073319389 / 0.218348191699 | -0.000048676368 / -0.063303616602 |
| outbound | 08:30–09:00 | 0.040566827753 | 2 / -0.001351141479 / 0.000001825583 / 0.034454107713 | 1 / -0.020958984616 / 0.000439279036 / 0.534454107713 | +0.000437453453 / +0.500000000000 |
| outbound | 09:00–09:30 | 0.024721296603 | 1 / -0.005113453466 / 0.000026147406 / 0.130393063382 | 2 / 0.014494389671 / 0.000210087332 / 0.369606936618 | +0.000183939926 / +0.239213873236 |
| outbound | 09:30–10:00 | 0.019884331548 | 2 / 0.019331354727 / 0.000373701276 / 0.492949545526 | 1 / -0.000276488411 / 0.000000076446 / 0.007050454474 | -0.000373624830 / -0.485899091052 |
| outbound | 10:00–10:30 | 0.040462150421 | 1 / -0.020854307284 / 0.000434902132 / 0.531784835744 | 2 / -0.001246464147 / 0.000001553673 / 0.031784835744 | -0.000433348459 / -0.500000000000 |
| outbound | 12:00–12:30 | 0.024254610164 | 1 / -0.004646767027 / 0.000021592444 / 0.118492559186 | 2 / 0.014961076110 / 0.000223833798 / 0.381507440814 | +0.000202241355 / +0.263014881627 |
| outbound | 12:30–13:00 | 0.031603831190 | 2 / 0.007611855084 / 0.000057940338 / 0.194102304646 | 1 / -0.011995988053 / 0.000143903729 / 0.305897695354 | +0.000085963392 / +0.111795390708 |
| outbound | 15:00–15:30 | 0.028262879673 | 2 / 0.010952806601 / 0.000119963972 / 0.279296568328 | 1 / -0.008655036536 / 0.000074909657 / 0.220703431672 | -0.000045054315 / -0.058593136656 |
| outbound | 15:30–16:00 | 0.048849421658 | 1 / -0.029241578520 / 0.000855069914 / 0.745660252272 | 2 / -0.009633735383 / 0.000092808857 / 0.245660252272 | -0.000762261057 / -0.500000000000 |
| outbound | 16:30–17:00 | 0.053027791832 | 3 / 0.005795737580 / 0.000033590574 / 0.147791308292 | 2 / -0.013812105557 / 0.000190774260 / 0.352208691708 | +0.000157183686 / +0.204417383416 |
| outbound | 17:00–17:30 | 0.039620370209 | 1 / -0.020012527072 / 0.000400501240 / 0.510319440325 | 2 / -0.000404683934 / 0.000000163769 / 0.010319440325 | -0.000400337471 / -0.500000000000 |
| outbound | 18:00–18:30 | 0.023578569061 | 2 / 0.015637117214 / 0.000244519435 / 0.398746488948 | 1 / -0.003970725924 / 0.000015766664 / 0.101253511052 | -0.000228752770 / -0.297492977896 |
| inbound | 05:30–06:00 | 0.051022934326 | 2 / -0.011807248052 / 0.000139411107 / 0.301084825319 | 1 / -0.031415091189 / 0.000986907954 / 0.801084825319 | +0.000847496848 / +0.500000000000 |
| inbound | 07:00–07:30 | 0.031009862949 | 2 / 0.008205823326 / 0.000067335536 / 0.209248494811 | 1 / -0.011402019811 / 0.000130006056 / 0.290751505189 | +0.000062670519 / +0.081503010378 |
| inbound | 07:30–08:00 | 0.027390477699 | 1 / -0.007782634562 / 0.000060569401 / 0.198457181336 | 2 / 0.011825208575 / 0.000139835558 / 0.301542818664 | +0.000079266157 / +0.103085637329 |
| inbound | 09:30–10:00 | 0.031405965301 | 1 / -0.011798122164 / 0.000139195687 / 0.300852115187 | 2 / 0.007809720973 / 0.000060991742 / 0.199147884813 | -0.000078203945 / -0.101704230373 |
| inbound | 11:00–11:30 | 0.029370989464 | 1 / -0.009763146326 / 0.000095319026 / 0.248960231324 | 2 / 0.009844696811 / 0.000096918055 / 0.251039768676 | +0.000001599029 / +0.002079537352 |
| inbound | 11:30–12:00 | 0.029172938287 | 2 / 0.010042747987 / 0.000100856787 / 0.256090073675 | 1 / -0.009565095150 / 0.000091491045 / 0.243909926325 | -0.000009365742 / -0.012180147350 |
| inbound | 12:00–12:30 | 0.023597797671 | 1 / -0.003989954534 / 0.000015919737 / 0.101743840608 | 2 / 0.015617888604 / 0.000243918444 / 0.398256159392 | +0.000227998707 / +0.296512318783 |
| inbound | 13:30–14:00 | 0.032104095698 | 1 / -0.012496252561 / 0.000156156328 / 0.318654440307 | 2 / 0.007111590576 / 0.000050574721 / 0.181345559693 | -0.000105581608 / -0.137308880615 |
| inbound | 14:00–14:30 | 0.019587261348 | 2 / 0.019628424926 / 0.000385275065 / 0.500524835618 | 1 / 0.000020581789 / 0.000000000424 / 0.000524835618 | -0.000385274641 / -0.500000000000 |
| inbound | 14:30–15:00 | 0.038619979403 | 1 / -0.019012136265 / 0.000361461325 / 0.484809474768 | 2 / 0.000595706872 / 0.000000354867 / 0.015190525232 | -0.000361106459 / -0.469618949537 |
| inbound | 15:30–16:00 | 0.053478768914 | 3 / 0.005344760498 / 0.000028566465 / 0.136291392696 | 2 / -0.014263082639 / 0.000203435526 / 0.363708607304 | +0.000174869062 / +0.227417214608 |
| inbound | 16:00–16:30 | 0.027850946685 | 2 / 0.011364739590 / 0.000129157306 / 0.289800859542 | 1 / -0.008243103547 / 0.000067948756 / 0.210199140458 | -0.000061208550 / -0.079601719084 |
| inbound | 17:00–17:30 | 0.048121484592 | 2 / -0.008905798317 / 0.000079313244 / 0.227097857086 | 1 / -0.028513641454 / 0.000813027749 / 0.727097857086 | +0.000733714505 / +0.500000000000 |
| inbound | 18:00–18:30 | 0.023488869524 | 1 / -0.003881026387 / 0.000015062366 / 0.098966172859 | 2 / 0.015726816751 / 0.000247332765 / 0.401033827141 | +0.000232270399 / +0.302067654282 |

### Direction aggregation

| Direction | SSE-best SSE rank | TE-best SSE rank | SSE-best TE rank | TE-best TE rank | Pairwise SSE preference | Pairwise TE preference |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| outbound | 12 | 1 | 14 | 1 | TE_BEST | TE_BEST |
| inbound | 13 | 26 | 13 | 19 | SSE_BEST | SSE_BEST |
| pair | 1 | 2 | 5 | 1 | SSE_BEST | TE_BEST |

Aggregation diagnosis: `OUTBOUND_INBOUND_TRADE`. Pair aggregation introduces a defect: `false`. Directional trip totals are fixed and TE scaling is independently recomputed per direction before summation.

### Continuous-exposure cross-check

Classification: `CONTINUOUS_EXPOSURE_PREFERS_THIRD_CANDIDATE`. Continuous exposure best is `1d3e0a6bf5508c30a45f919c37e30f81ea4857de806947288014c8d549f7d241` at `12.762989322347`. SSE-best is `12.905528866964` (outbound/inbound `7.235966368275` / `5.669562498689`, rank `2`); TE-best is `14.157160266920` (outbound/inbound `6.501717101353` / `7.655443165567`, rank `26`). The anchors differ by `1.251631399956` and are numerically equivalent: `false`. This diagnostic is not used to choose an anchor.

### Bucket-edge audit

Changed departures `97`; total absolute shift `1570.000000000000` minutes; boundary-crossing assignments `43`; exposure-only bucket changes `39`.

Classification: `BUCKET_EDGE_ALIASING_NOT_PRIMARY_DRIVER`. Bucket edges affect the candidate residual vectors, but they do not create separate SSE and TE data paths; the verified ranking reversal is caused by applying different norms to the same vectors.

## History

PR62-M observed a common top candidate on the 41-access-safe Route 6 and 7-access-safe Route 10 universes while treating SSE as authoritative and TE as review-only calibration. M1 explicitly corrected the stronger reading: lower ranks already disagreed (61 Route 6 pairs and 2 Route 10 pairs). N/O froze a fail-closed common anchor because top-rank concordance held empirically, not because it was proved invariant. R/S/T preserved that requirement while adding phase-robust materiality diagnostics; they tested the same production universes (plus one external Q review candidate), not a materially expanded search universe. U6 is the first saved production-search counterexample at the exact top rank.

## U6 transition and cap stability

| Batch | Pareto | Access-safe | SSE-best | TE-best | Common | V3 |
| --- | ---: | ---: | --- | --- | --- | --- |
| `BASE_FRONTIER` | 11 | 7 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | true | `PHASE_ROBUST_MATERIALITY_SELECTS_TRANSLATED_ALTERNATIVE` |
| `2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3` | 48 | 23 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | false | `DEMAND_FIT_ANCHOR_CONFLICT` |
| `6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16` | 68 | 35 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | false | `DEMAND_FIT_ANCHOR_CONFLICT` |
| `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0` | 89 | 55 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | false | `DEMAND_FIT_ANCHOR_CONFLICT` |
| `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 94 | 60 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f` | false | `DEMAND_FIT_ANCHOR_CONFLICT` |
| `c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7` | 106 | 66 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | false | `DEMAND_FIT_ANCHOR_CONFLICT` |
| `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24` | 123 | 83 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` | false | `DEMAND_FIT_ANCHOR_CONFLICT` |

First transition: batch `2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3`; responsible newly admitted top candidate(s): `['f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f']` with lineage `{"f1d3b96a84029bee10131bbf29991db4beea919092c0346b58f0c98d79abf47f":{"child_rhythm":[9,10,6,0],"generated_by_u6":true,"parent_pair_fingerprint":"2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3","parent_rhythm":[9,11,5,0],"present_in_original_11_candidate_base_frontier":false,"source_pair_fingerprint":"2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3"}}`.

The first break is triggered by one local-rhythm source family. The conflict then persists after every later batch, the TE-best is replaced by the `c8eeb7…` family, and each cap has a different TE-best identity. The initial trigger is local, but persistence across sources and caps shows that disagreement is a broader property of the enriched universe.

| Cap | Pareto | Access-safe | SSE-best/value | TE-best/value | SSE/TE continuous ranks |
| ---: | ---: | ---: | --- | --- | --- |
| 16 | 88 | 55 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` / 0.009369737096 | `9da4067ec1f7f7e7372cc9ea1062317c2f37ef6d72d4f556324833c8b59c5eec` / 16.273635987801 | 1 / 18 |
| 32 | 123 | 83 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` / 0.009369737096 | `da2f6518758a74f3f5e63145f58ad3b32e088a26bb5bd4d4be6d0a247364ad90` / 16.582604218230 | 2 / 26 |
| 64 | 228 | 154 | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` / 0.009369737096 | `47230f4b711a8d9d36213e62e93ff507ac28258ba494fea0b569edc44495317f` / 16.470407564416 | 3 / 59 |

Anchor conflict: `ANCHOR_CONFLICT_CANDIDATE_UNIVERSE_SENSITIVE`. Selection-cap binding remains separately reported as `U6_DIRECTIONAL_FRONTIER_32_CAP_NON_BINDING` and is not evidence that a null selector is adequate.

## Rank concordance

Across 83 access-safe candidates there are `371` SSE/TE ordering disagreements among `3403` possible pairs; Kendall tau-b is `0.779122863219`. Top-5 overlap is `4/5`; top-10 overlap is `7/10`. Exact common candidates by ranks 1–10 are `{"1":[],"10":[],"2":[],"3":["1663f2d8cf376ab39d5387b6704f31460b15b0ac7ff73adbcdb9d1a1cf9eb298"],"4":[],"5":[],"6":[],"7":[],"8":[],"9":[]}`.

## Materiality

From SSE-best to TE-best: ΔSSE `+0.000133870823`, ΔTE `-0.374595847445`, Δcontinuous `+1.251631399956`, Δaverage wait `+0.056575327417` minutes, Δmax access OB/IB `+0.900000000000` / `+0.700000000000` minutes, Δrhythm `[-3, -1, -1, 0]`, Δfleet `-1`, changed bucket allocations `26`, changed departures `97`.

Their absolute TE difference is within 1.0 TE: `true`. The numeric continuous delta can be compared with the old Route 10 bound, but that bound is **not semantically valid for anchor adjudication** because V3 derived it only after a common anchor existed.

## Policy options — evidence only

| Option | Historical intent | Passenger meaning | Edge sensitivity | Growth behavior | New weight/threshold | Fail closed | Route 10 | Route 6 control | Migration |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_SSE_AUTHORITATIVE_ANCHOR | Strongest continuity: M/N explicitly kept production SSE authoritative. | Indirect; TE remains the service-mass calibration diagnostic. | Retains point-count boundary sensitivity. | Always defines a scalar anchor when the SSE minimum is unique, but identity may change as the universe grows. | false | Preservable through uniqueness and metric-validity gates. | Would make the observed SSE-best candidate the anchor; downstream selection was not rehearsed. | Historical Route 6 SSE/TE top candidate was common, so no historical anchor change is expected. | Low. |
| B_TE_AUTHORITATIVE_ANCHOR | Changes anchor authority; aligns with TE's later materiality interpretation but not M/N's SSE-authoritative statement. | Direct trip-equivalent displaced service mass. | Retains point-count boundary sensitivity. | Always defines a scalar anchor when the TE minimum is unique, but identity may change as the universe grows. | false | Preservable through uniqueness and metric-validity gates. | Would make the observed TE-best candidate the anchor; downstream selection was not rehearsed. | Historical Route 6 SSE/TE top candidate was common, so no historical anchor change is expected. | Low to medium because authority documentation changes. |
| C_CONTINUOUS_EXPOSURE_AUTHORITATIVE_ANCHOR | Promotes a metric frozen in T for materiality, not anchor authority. | Phase-robust service-exposure mismatch in trip-equivalent units. | Lower point-boundary sensitivity; demand support remains bucket-defined. | Scalar and phase-aware, but expanded-universe behavior still needs a policy rehearsal. | false | Preservable through uniqueness, finite-value, and authority gates. | Continuous exposure prefers a third candidate; downstream selection was not rehearsed. | Historical Route 6 continuous best agreed with the common anchor; U6 Route 6 remains unexecuted. | Medium to high because the metric's role changes. |
| D_MULTI_METRIC_DEMAND_FIT_FRONTIER | Acknowledges M1's non-interchangeable rankings but departs from the single-anchor contract. | Preserves both concentration-sensitive SSE and displaced-mass TE evidence. | Retains both point metrics unless phase-robust evidence is added separately. | Does not fail solely because minima differ; frontier membership can still grow or change. | false | Possible, but later-stage admissibility and boundedness must be predeclared to avoid an implicit tradeoff. | Would retain both observed anchors in a demand-fit nondominated set; no final timetable was selected. | Historical common top remains nondominated; later-stage equivalence has not been rehearsed. | High because the selector contract changes from one anchor to a set. |

Route 6 impact statements above are reference-only expectations from committed historical evidence. Route 6 was not executed in this review.

## Primary classification

**COMMON_SSE_TE_ANCHOR_ASSUMPTION_INVALIDATED**

The common-anchor contract was supported by the old finite universes, but U6 supplies a top-rank counterexample whose existence is stable across caps even though the TE-best identity is universe-sensitive. The review finds no metric implementation, data, gate-survival, or pair-aggregation defect.

## Next decision

Run one evidence-only PR62-U7 demand-fit authority rehearsal over the saved U6 Route 10 cap/batch universes and the already-committed historical Route 6 snapshots, predeclaring stability, boundary-sensitivity, passenger-interpretability, and fail-closed criteria for options A-D; do not run either global coordinator or select a replacement timetable.

Route 6 global execution count = `0`.

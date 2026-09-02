# PR62-M1 — Demand-fit rank-concordance clarification

Same SSE/TE best candidate does not imply zero rank disagreement.

TOP-RANK CONCORDANCE means the two metrics select the same best candidate. FULL-RANK CONCORDANCE means every epsilon-qualified candidate pair has the same relative ordering.

## Route 6

Candidates `41`; possible pairs `820`; disagreements `61` (7.439024%); decision-relevant `29`; materiality-path effect `23`.

SSE best: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`. TE best: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`. Same: `True`.

First SSE simpler: `1efac6b6aaa18c159d794434bdfbce0c2dbe0a9db961442a0987a5a03700c402`. First TE simpler: `ae3c74d827222635551a604db5dfcc138d439813d4fcff2d3a85d4102b2a17fa`. Same: `False`.

TE path: ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b -> ae3c74d827222635551a604db5dfcc138d439813d4fcff2d3a85d4102b2a17fa -> 469d9aca5c96181be86ec08d2fa606bb8114dd45e8389d693ae1ce2967704ab9 -> 91bd392692a31e0c33b59cc5e0ec893d1147fcb7fb7b04661a40a378a2abc6dc -> ccd0e2b10d9ec9c2f1cd1cf41e6a3ea72c3f84283830af9277b3dfb5fd620fdb

SSE path: ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b -> 1efac6b6aaa18c159d794434bdfbce0c2dbe0a9db961442a0987a5a03700c402 -> ae3c74d827222635551a604db5dfcc138d439813d4fcff2d3a85d4102b2a17fa -> 91bd392692a31e0c33b59cc5e0ec893d1147fcb7fb7b04661a40a378a2abc6dc -> ccd0e2b10d9ec9c2f1cd1cf41e6a3ea72c3f84283830af9277b3dfb5fd620fdb

Exact path sequence identical: `False`; final candidate same: `True`; overlap/union `4/6`.

Classification: `TOP_CONCORDANT_FIRST_SIMPLICITY_CONFLICT`.

### Required review

- Any disagreement involves L_SELECTED: `False`.
- Any disagreement alters SSE_BEST versus TE_BEST: `False`.
- FIRST_TE_SIMPLER equals FIRST_SSE_SIMPLER: `False`.
- TE and SSE preferred paths differ: `True`.
- Differing path positions: `[{"SSE": "1efac6b6aaa18c159d794434bdfbce0c2dbe0a9db961442a0987a5a03700c402", "TE": "ae3c74d827222635551a604db5dfcc138d439813d4fcff2d3a85d4102b2a17fa", "position": 2}, {"SSE": "ae3c74d827222635551a604db5dfcc138d439813d4fcff2d3a85d4102b2a17fa", "TE": "469d9aca5c96181be86ec08d2fa606bb8114dd45e8389d693ae1ce2967704ab9", "position": 3}]`.
Disagreements with both candidates beyond the exact first-TE-simpler breakpoint: `50`.

The at-least-one-TE conclusion remains structurally meaningful: `True`. The exact TE path minimizes TE across every rhythm-simpler candidate and its first simpler breakpoint remains above one TE; the SSE path is reported independently without an invented SSE threshold.

## Route 10

Candidates `7`; possible pairs `21`; disagreements `2` (9.523810%); decision-relevant `2`; materiality-path effect `2`.

SSE best: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`. TE best: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`. Same: `True`.

First SSE simpler: `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0`. First TE simpler: `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`. Same: `False`.

TE path: bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c -> e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24 -> c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7 -> 91e7e59f64f782f45705d945fa8a8338cf5cd4c812a3e97a93e40d95b0d79ede

SSE path: bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c -> 9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0 -> e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24 -> c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7 -> 91e7e59f64f782f45705d945fa8a8338cf5cd4c812a3e97a93e40d95b0d79ede

Exact path sequence identical: `False`; final candidate same: `True`; overlap/union `4/5`.

Classification: `TOP_CONCORDANT_FIRST_SIMPLICITY_CONFLICT`.

### Exact disagreement pairs

- `2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3` vs `91e7e59f64f782f45705d945fa8a8338cf5cd4c812a3e97a93e40d95b0d79ede`; SSE prefers `91e7e59f64f782f45705d945fa8a8338cf5cd4c812a3e97a93e40d95b0d79ede`; TE prefers `2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3`; tags: INVOLVES_FOCUSED_ROLE_CANDIDATE, INVOLVES_TE_BREAKPOINT_PREFERRED, INVOLVES_SSE_BREAKPOINT_PREFERRED, DECISION_RELEVANT.
- `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0` vs `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`; SSE prefers `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0`; TE prefers `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`; tags: INVOLVES_NEXT_BEST_SSE, INVOLVES_FOCUSED_ROLE_CANDIDATE, INVOLVES_TE_BREAKPOINT_PREFERRED, INVOLVES_SSE_BREAKPOINT_PREFERRED, INVOLVES_FIRST_SIMPLER_WITNESS, DECISION_RELEVANT.

Involves L_SELECTED: `False`; NEXT_BEST_SSE: `True`; +0.712251 first-TE-simpler witness: `True`; any pair entirely inside <=1 TE: `False`.

### Route 10 <=1 TE envelope

| fingerprint | ΔTE | SSE rank | TE rank | rhythm | fleet |
|---|---:|---:|---:|---|---|
| `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 0.000000 | 1 | 1 | (11, 12, 7, 0) | (13, 2432, 71) |
| `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24` | 0.712251 | 3 | 2 | (9, 11, 6, 0) | (12, 1683, 71) |

Review preferred: `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24`. In-envelope disagreements: `0`. Changes review preference: `False`.

Sub-one-trip simplicity result robust: `True`.

## Route 6 Human Final context

Human Final is `POST_SEARCH_EXPERT_BENCHMARK` and is not selectable. Human Final TE `19.892407`; selected TE `20.923774`; selected-minus-Human-Final SSE `-0.000110576`.

Selected-minus-Human-Final rhythm: sustained headway levels `3`; effective palette `1`.

Human Final is outside the selectable universe and cannot create candidate-ranking discordance.

## Policy readiness

Cross-route classification: `MATERIALITY_PATH_VARIATION_REQUIRES_POLICY_REVIEW`.

One-trip materiality discussion can proceed: `False`. No threshold is implemented.

PR62-M remains unchanged historical evidence. Its classification was too coarse for lower-rank concordance analysis.

## Production guards

- Coordinator search changed: **NO**
- 10-D Pareto changed: **NO**
- L selector changed: **NO**
- SSE mismatch semantics changed: **NO**
- TE semantics changed: **NO**
- One-trip threshold added: **NO**
- Access guardrail changed: **NO**
- Compiler changed: **NO**
- Tail eligibility changed: **NO**
- Rhythm semantics changed: **NO**
- Fleet validator changed: **NO**
- Queue changed: **NO**
- Budgets changed: **NO**
- Settlement added: **NO**
- Final XLSX regenerated: **NO**
- Private workbook opened: **NO**
- Private workbook committed: **NO**
- M artifacts modified: **NO**

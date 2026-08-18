# Ordinary OR-Tools Runtime Policy V1

## Decision

Ordinary application execution applies a finite **120-second total staged OR-Tools budget** when
no explicit `SolverPolicyV1.time_limit_seconds` is supplied.

The budget covers the complete lexicographic service-quality solve, not 120 seconds per objective
stage. Each stage receives only the remaining wall-clock budget.

## Semantics

- an explicitly supplied finite time limit is preserved unchanged;
- an application policy with `time_limit_seconds=None` receives the 120-second ordinary default;
- worker count, random seed, and independent-validation settings are not changed;
- HEURISTIC-only execution is unchanged;
- BOTH keeps the heuristic on its existing bounded search when no policy is supplied and applies
  the finite ordinary budget to OR-Tools;
- low-level Contract V1 request builders retain their historical `None` default for controlled
  tests and research calls.

When the budget expires, existing solver semantics remain authoritative: a known candidate may be
returned as `FEASIBLE`; otherwise the result is `UNKNOWN`. Timeout is never treated as proof of
`INFEASIBLE`.

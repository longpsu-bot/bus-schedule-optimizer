# Uniform-Headway Schedule Compiler V1

Status: compiler contract and temporary-authoritative bridge implementation.

## Boundary and authority

The compiler accepts only `CompilerInputV1`:

```text
TemporaryAuthoritativeAllocationFixtureAdapterV1 --┐
                                                   ├--> CompilerInputV1
RealTripAllocatorAdapter (future) -----------------┘
                                                            |
                                                            v
                                      UniformHeadwayScheduleCompiler
                                                            |
                                                            v
                                          CompiledScheduleCandidateV1
```

It never imports the fixture adapter and has no allocator or demand-model
logic.  Each source demand regime remains a half-open `[start,end)` evidence
interval, and its exact allocation is immutable.

The temporary bridge uses provenance profile
`TEMPORARY_AUTHORITATIVE_BRIDGE_V1`.  Its supplied upstream hashes are
assertions transcribed from the unavailable source machine.  They were not
reproduced on this machine.

## Local schedules

For duration `D` and allocation `x >= 2`, enumeration covers every integer:

```text
1 <= h <= floor((D - 1) / (x - 1))
0 <= phase <= D - 1 - (x - 1)h
departure[k] = start + phase + k*h
```

For `x == 1`, every minute phase is enumerated and headway remains `None`.
No regime endpoint is an anchor.

## Whole-direction dynamic program

The DP retains one best prefix for every local candidate in the current
regime.  A future transition depends only on that candidate's last departure
and integer headway, so discarding a worse prefix for the same current local
candidate is exact.

The complete lexicographic objective is:

1. maximum positive transition/service-edge gap excess;
2. total positive gap excess;
3. total rational headway quantization error;
4. resulting ServiceRegime count;
5. transition-shape error;
6. phase/edge imbalance;
7. integer-headway vector;
8. phase vector;
9. departure vector.

The DP has no scalar weights.  For performance without loss of exactness,
quantization fractions are multiplied by the LCM of regime durations, and
transition-shape error is stored in half-minute units.  All inner-loop
comparisons are therefore exact integer tuple comparisons.  After headway and
phase vectors are equal, the frozen starts/counts uniquely determine the
departure vector, so the ninth tie-break is mathematically redundant but is
still present in final complete-schedule ranking.

## ServiceRegime merge

Adjacent demand regimes merge only when both have the same actual measurable
headway and their cross-boundary gap equals that headway.  The merged exact
sequence is revalidated against every original half-open interval, preserving
each member's authoritative count.  Singleton regimes are not merged in V1.

## Validation and non-goals

An independent compiler-only validator recomputes totals, per-regime counts,
minute alignment, ordering, internal uniformity, merged-sequence uniformity,
member mapping and immutable input binding.  Every result remains
`NOT_FLEET_VALIDATED`.

This milestone does not assign vehicles, propagate travel time, validate
layover/turnaround, interline directions, create duties, or run OR/CP-SAT.

## Real-route review record

Evidence: all 12 bridge allocations compile with exact totals and zero positive
transition/edge gap excess; only Route 10 outbound C3 merges, at 10:00.

Conclusion: joint phase/headway selection resolves boundary holes without
renegotiating allocation; equal allocator proxy headway is not used as merge
authority.

Minimal correction: none to upstream allocation.  The implementation adds only
the neutral compiler contract, bridge adapter and compiler artifacts.

Verification: focused compiler tests, independent invariant validation,
deterministic serialization and full repository checks are recorded in the
implementation report/artifacts.

Decision: hand all 12 exact schedules to the later travel-time, layover and
vehicle-chaining milestone; do not claim fleet feasibility here.

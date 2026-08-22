# Fixed-Timetable Fleet Feasibility Validator V1

## Boundary

This validator consumes immutable outbound and inbound departure timestamps,
directional runtime, minimum terminal layover, and a pilot fleet ceiling. It does
not generate, move, repair, or select timetable departures. It has no deadhead,
driver, crew, or terminal-capacity model.

`available_fleet_limit` is a pilot hard upper bound. It is not approved active
fleet metadata. Accordingly, the positive assessment wording is
`WITHIN_PILOT_FLEET_LIMIT`; `approved_active_fleet` remains null.

## Trip and compatibility contract

Each departure becomes one trip node. Arrival is calculated only as:

```text
arrival = fixed departure + authoritative directional runtime
```

An edge `i -> j` exists only when the destination terminal of `i` is the origin
terminal of `j`, and `departure(j) >= arrival(i) + minimum_layover`. With no
deadhead authority, two same-direction trips cannot be consecutive.

## Exact fleet and canonical blocks

The compatibility graph is a DAG because every legal edge advances time. The
exact minimum fleet is its minimum path cover:

```text
minimum fleet = fixed trip count - maximum bipartite matching cardinality
```

Among maximum-cardinality matchings, the implementation applies these exact
objectives in order:

1. minimum total excess terminal waiting;
2. minimum maximum individual excess terminal waiting;
3. lexicographically earlier complete successor assignments, with unmatched
   sorting after every trip ID.

The first waiting objective is solved by exact min-cost flow. The second retains
that optimum while finding the smallest feasible edge-wait threshold. The final
min-cost flow uses a positional integer encoding whose entire lexicographic range
is smaller than the cost of one minute of total waiting, so tie-breaking cannot
override an earlier objective.

## Outputs and non-claims

Every result includes minimum fleet, pilot margin, canonical vehicle blocks,
initial and ending terminal distributions, actual-layover metrics, excess-wait
metrics, input and upstream fingerprints, and fleet/terminal-capacity statuses.

Long waiting is reported but is not a feasibility violation without additional
authority. Initial/end distribution is reported but terminal physical capacity
is `TERMINAL_CAPACITY_NOT_VALIDATED`. Scenario B is the operational baseline;
all 18 Scenario C outbound/inbound candidate combinations are evaluated without
selecting a final timetable.

# Contract V1 terminal physical occupancy

Contract V1 optionally accepts an authoritative physical vehicle-occupancy capacity for either
terminal in Scenario B. This is independent of available route fleet, minimum required fleet,
approved active fleet, ready stock, and turnaround feasibility.

For terminal `T` at event time `t`:

```text
occupancy_T(t)
  = independently_derived_initial_fleet_T
  + arrivals_to_T_at_or_before_t
  - departures_from_T_before_t
```

Events are grouped by integer minute and always use
`ARRIVAL_BEFORE_DEPARTURE`: add all arrivals, test capacity, then remove all departures. Thus a
same-minute arrival and departure can create a transient overflow. A vehicle occupies terminal
space from arrival through unloading, turnaround, ready/waiting time, and departure.

The shared CP-SAT hard model uses exact reified comparisons at each arrival event. With `a`
arrivals and `d` departures at one evaluated terminal, it adds
`a * (a - 1) + a * d` comparison binaries and two reification constraints per binary, plus one
capacity constraint per arrival and one initial-occupancy bound. The model is `O(n^2)` per
terminal and creates no minute grid or second-level variables.

Independent candidate validation reconstructs the timetable, exact runtimes, circulation, and
minimum initial terminal stocks before rebuilding the grouped physical-occupancy profile. It
does not trust CP-SAT occupancy indicators. A native `OPTIMAL` or `FEASIBLE` candidate that
overflows a supplied capacity is rejected with the terminal-specific issue code and no solution.

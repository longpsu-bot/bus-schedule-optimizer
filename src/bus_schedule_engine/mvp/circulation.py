"""Exact minimum DAG path cover and independent vehicle-chain verification."""

from __future__ import annotations

from collections import defaultdict
from time import perf_counter as monotonic

from ortools.sat.python import cp_model

from .input import DIRECTIONS, runtime_at
from .planning import solver


def _matching(adjacency, deadline=None):
    # Adapted augmenting-path cover from clean_boundary_pilot (69c8e9e); no greedy fleet estimate.
    predecessor = [-1] * len(adjacency)

    def augment(left, seen):
        if deadline is not None and monotonic() >= deadline:
            raise TimeoutError("exact fleet matching time limit")
        for right in adjacency[left]:
            if right in seen:
                continue
            seen.add(right)
            if predecessor[right] == -1 or augment(predecessor[right], seen):
                predecessor[right] = left
                return True
        return False

    for left in range(len(adjacency)):
        augment(left, set())
    successor = [-1] * len(adjacency)
    for right, left in enumerate(predecessor):
        if left != -1:
            successor[left] = right
    return successor, predecessor


def assign_fleet(data, departures, seconds=2, settings=None, deadline=None):
    trips = []
    for direction in DIRECTIONS:
        for i, departure in enumerate(departures[direction]):
            arrival = departure + runtime_at(data["directions"][direction], departure)
            destination = "inbound" if direction == "outbound" else "outbound"
            trips.append(
                {
                    "trip_id": f"{direction}-{i + 1:03d}",
                    "direction": direction,
                    "departure": departure,
                    "arrival": arrival,
                    "ready": arrival + data["layover_minutes"][destination],
                }
            )
    trips.sort(key=lambda t: (t["departure"], t["trip_id"]))
    adjacency = []
    for t in trips:
        if deadline is not None and monotonic() >= deadline:
            return {"status": "SOLVER_LIMIT", "required_fleet": None, "trips": []}
        adjacency.append(
            [
                j
                for j, following in enumerate(trips)
                if t["direction"] != following["direction"] and t["ready"] <= following["departure"]
            ]
        )
    status = "EXACT"
    if "initial_vehicles" not in data:
        try:
            successor, predecessor = _matching(adjacency, deadline)
        except TimeoutError:
            return {"status": "SOLVER_LIMIT", "required_fleet": None, "trips": []}
    else:
        model = cp_model.CpModel()
        edges = {
            (i, j): model.new_bool_var(f"e{i}_{j}") for i, row in enumerate(adjacency) for j in row
        }
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for (i, j), variable in edges.items():
            if deadline is not None and monotonic() >= deadline:
                return {"status": "SOLVER_LIMIT", "required_fleet": None, "trips": []}
            outgoing[i].append(variable)
            incoming[j].append(variable)
        starts = []
        for i in range(len(trips)):
            start = model.new_bool_var(f"start{i}")
            model.add(sum(incoming[i]) + start == 1)
            model.add(sum(outgoing[i]) <= 1)
            starts.append(start)
        for direction in DIRECTIONS:
            model.add(
                sum(starts[i] for i, t in enumerate(trips) if t["direction"] == direction)
                <= data["initial_vehicles"][direction]
            )
        model.add(sum(starts) <= data["fleet_ceiling"])
        model.minimize(sum(starts))
        active = settings or {"solver_seconds": seconds}
        if deadline is not None:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return {"status": "SOLVER_LIMIT", "required_fleet": None, "trips": []}
            active = active | {"solver_seconds": min(active["solver_seconds"], remaining)}
        engine = solver(active)
        native = engine.solve(model)
        if native not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {
                "status": "INITIAL_STOCK_INFEASIBLE"
                if native == cp_model.INFEASIBLE
                else "SOLVER_LIMIT",
                "required_fleet": None,
                "trips": [],
            }
        if native != cp_model.OPTIMAL:
            # A feasible path cover is an upper bound, not an exact minimum fleet certificate.
            return {"status": "MINIMUM_FLEET_UNPROVED", "required_fleet": None, "trips": []}
        successor, predecessor = [-1] * len(trips), [-1] * len(trips)
        for (i, j), variable in edges.items():
            if engine.value(variable):
                successor[i], predecessor[j] = j, i
    starts = [i for i, previous in enumerate(predecessor) if previous == -1]
    chains = []
    for vehicle, start in enumerate(starts, 1):
        chain = []
        cursor = start
        while cursor != -1:
            trips[cursor]["vehicle_id"] = f"V{vehicle:03d}"
            chain.append(trips[cursor]["trip_id"])
            cursor = successor[cursor]
        chains.append(chain)
    initial = {d: sum(trips[i]["direction"] == d for i in starts) for d in DIRECTIONS}
    result = {
        "status": status,
        "required_fleet": len(starts),
        "initial_vehicles_required": initial,
        "chains": chains,
        "trips": trips,
        "within_fleet_ceiling": len(starts) <= data["fleet_ceiling"],
    }
    validate_chains(data, departures, result)
    return result


def validate_chains(data, departures, fleet):
    expected = {(d, t) for d in DIRECTIONS for t in departures[d]}
    actual = {(t["direction"], t["departure"]) for t in fleet["trips"]}
    by_id = {t["trip_id"]: t for t in fleet["trips"]}
    chained = [tid for chain in fleet["chains"] for tid in chain]
    if (
        actual != expected
        or len(fleet["trips"]) != len(expected)
        or len(by_id) != len(expected)
        or len(chained) != len(set(chained))
        or set(chained) != set(by_id)
    ):
        raise ValueError("fleet coverage/identity mismatch")
    if len(fleet["chains"]) != fleet["required_fleet"]:
        raise ValueError("fleet count differs from chain count")
    initial = dict.fromkeys(DIRECTIONS, 0)
    vehicles = set()
    for chain in fleet["chains"]:
        if not chain:
            raise ValueError("empty vehicle chain")
        initial[by_id[chain[0]]["direction"]] += 1
        previous = None
        vehicle = by_id[chain[0]]["vehicle_id"]
        if vehicle in vehicles:
            raise ValueError("vehicle belongs to two chains")
        vehicles.add(vehicle)
        for tid in chain:
            trip = by_id[tid]
            arrival = trip["departure"] + runtime_at(
                data["directions"][trip["direction"]], trip["departure"]
            )
            destination = "inbound" if trip["direction"] == "outbound" else "outbound"
            if (
                trip["arrival"] != arrival
                or trip["ready"] != arrival + data["layover_minutes"][destination]
                or trip["vehicle_id"] != vehicle
            ):
                raise ValueError("fleet runtime/arrival/vehicle mismatch")
            if previous and (
                previous["direction"] == trip["direction"] or previous["ready"] > trip["departure"]
            ):
                raise ValueError("vehicle continuity/terminal layover violation")
            previous = trip
    if "initial_vehicles" in data and any(
        initial[d] > data["initial_vehicles"][d] for d in DIRECTIONS
    ):
        raise ValueError("initial terminal availability exceeded")
    if fleet["initial_vehicles_required"] != initial:
        raise ValueError("initial terminal reporting mismatch")

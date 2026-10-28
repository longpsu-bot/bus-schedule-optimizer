from copy import deepcopy

import pytest

from bus_schedule_engine.mvp.circulation import assign_fleet
from bus_schedule_engine.mvp.fleet_timespace import meal_policy, reconstruct


def fleet(trips, chains):
    rows = []
    for vehicle, chain in enumerate(chains, 1):
        for tid in chain:
            direction, departure, arrival = trips[tid]
            rows.append(
                dict(
                    trip_id=tid,
                    direction=direction,
                    departure=departure,
                    arrival=arrival,
                    ready=arrival + 5,
                    vehicle_id=f"V{vehicle:03d}",
                )
            )
    return dict(required_fleet=len(chains), chains=chains, trips=rows)


def sample():
    return fleet(
        {
            "a": ("outbound", 600, 660),
            "b": ("inbound", 750, 810),
            "c": ("outbound", 1000, 1060),
            "d": ("inbound", 1160, 1220),
        },
        [["a", "b", "c", "d"]],
    )


def at(result, minute):
    return next(r for r in result["snapshots"] if r["time"] == minute)


def test_conservation_equal_minute_readiness_and_terminal_continuity():
    f = fleet({"a": ("outbound", 600, 630), "b": ("inbound", 635, 665)}, [["a", "b"]])
    result = reconstruct(f, {"outbound": 1, "inbound": 0})
    assert result["audit"]["physical_conservation_pass"]
    assert at(result, 630)["terminal_B"] == 1
    assert at(result, 635)["travelling_inbound"] == 1
    assert at(result, 635)["terminal_B"] == 0
    assert result["audit"]["recovery_task_deficit_connections"] == 1
    assert all(
        r["physical_vehicles"]
        == r["terminal_A"] + r["terminal_B"] + r["travelling_outbound"] + r["travelling_inbound"]
        for r in result["snapshots"]
    )


def test_no_phantom_activation_or_missing_stock():
    with pytest.raises(ValueError, match="initial stock"):
        reconstruct(sample(), None)
    with pytest.raises(ValueError, match="initial stock"):
        reconstruct(sample(), {"outbound": 0, "inbound": 1})
    f = sample()
    f["trips"][1]["direction"] = "outbound"
    with pytest.raises(ValueError, match="continuity"):
        reconstruct(f, {"outbound": 1, "inbound": 0})


def test_first_departure_tasks_are_not_reported_ready():
    result = reconstruct(sample(), {"outbound": 1, "inbound": 0})
    assert at(result, 595)["terminal_ready"] == 0
    segment = next(s for s in result["segments"] if s["start"] == 595)
    assert segment["crew_activity"] == "PRE_DEPARTURE_TASKS"


def test_separate_continuous_meals_tasks_recovery_and_standdown_reactivation():
    result = reconstruct(
        sample(),
        {"outbound": 1, "inbound": 0},
        margins={"a": 10, "b": 0, "c": 20, "d": 0},
        standdown=True,
    )
    crew = result["crew"]["chains"][0]
    assert crew["meals"]["lunch"]["opportunity"] == [680, 710]
    assert crew["meals"]["dinner"]["opportunity"] == [1090, 1120]
    lunch_gap = next(r for r in result["opportunities"] if r["after_trip_id"] == "a")
    assert lunch_gap["earliest_reactivation"] == 715
    assert crew["duty_start"] == 595 and crew["duty_end"] == 1230
    assert crew["modeled_max_continuous_driving_minutes"] == 120
    assert at(result, 710)["temporarily_stood_down"] == 1
    assert at(result, 745)["temporarily_stood_down"] == 0
    assert at(result, 750)["travelling_inbound"] == 1
    assert at(result, 680)["crew_meal_break"] == 1
    assert at(result, 680)["terminal_ready"] == 0
    assert result["audit"]["parking_authority"] == "UNKNOWN"
    assert result["audit"]["operational_parking_feasibility"] == "UNVERIFIED"
    assert all(s["end"] > s["start"] for s in result["segments"])


def test_p75_arrivals_consume_margin_once():
    f = sample()
    nominal = reconstruct(f, {"outbound": 1, "inbound": 0}, margins={"a": 20})
    f["trips"][0]["arrival"] += 20
    stressed = reconstruct(f, {"outbound": 1, "inbound": 0}, margins={"a": 20}, runtime_basis="p75")
    assert nominal["crew"]["chains"][0]["meals"]["lunch"]["opportunity"] == [690, 720]
    assert stressed["crew"]["chains"][0]["meals"]["lunch"]["opportunity"] == [690, 720]
    assert (
        sum(
            s["end"] - s["start"]
            for s in stressed["segments"]
            if s["vehicle_state"] == "RECOVERY_RESERVED"
        )
        == 0
    )


def test_short_waits_do_not_add_up_to_one_meal():
    f = fleet(
        {
            "a": ("outbound", 600, 660),
            "b": ("inbound", 690, 720),
            "c": ("outbound", 750, 780),
            "d": ("inbound", 810, 850),
        },
        [["a", "b", "c", "d"]],
    )
    result = reconstruct(f, {"outbound": 1, "inbound": 0})
    assert result["crew"]["lunch_covered"] == 0
    assert result["crew"]["lunch_required"] == 1


def test_15minute_buckets_integrate_exact_subminute_events():
    f = fleet({"a": ("outbound", 600, 607.5)}, [["a"]])
    result = reconstruct(f, {"outbound": 1, "inbound": 0}, horizon=(600, 630))
    row = result["utilization"][0]
    assert row["in_passenger_service_mean"] == 0.5
    assert row["in_passenger_service_max"] == 1
    assert result["metrics"]["passenger_vehicle_hours"] == 0.125


def test_unused_stock_is_physical_and_morning_evening_activation_differs():
    result = reconstruct(sample(), {"outbound": 1, "inbound": 1})
    assert result["metrics"]["unique_vehicles_required"] == 1
    assert result["metrics"]["physical_vehicles_in_scenario"] == 2
    assert at(result, 600)["terminal_B"] == 1
    assert any(
        s["vehicle_state"] == "NOT_YET_DEPLOYED" and s["vehicle_id"] == "U001"
        for s in result["segments"]
    )


def test_exact_arrival_before_departure_and_distinct_peak_activation():
    f = fleet(
        {
            "a": ("outbound", 600, 630),
            "b": ("inbound", 630, 660),
            "c": ("inbound", 1000, 1060),
            "d": ("outbound", 1005, 1070),
        },
        [["a", "c"], ["b", "d"]],
    )
    result = reconstruct(f, {"outbound": 1, "inbound": 1})
    same_minute = [e["event"] for e in result["ledger"] if e["time"] == 630 and e["stock_delta"]]
    assert same_minute == ["ARRIVAL", "DEPARTURE"]
    assert at(result, 600)["in_passenger_service"] == 1
    assert at(result, 1005)["in_passenger_service"] == 2


def test_invalid_policy_and_overlapping_assignment_are_rejected():
    policy = meal_policy()
    policy["minutes"] = 0
    with pytest.raises(ValueError, match="policy"):
        reconstruct(sample(), {"outbound": 1, "inbound": 0}, policy=policy)
    f = sample()
    f["trips"][1]["departure"] = 650
    with pytest.raises(ValueError, match="continuity"):
        reconstruct(f, {"outbound": 1, "inbound": 0})


def test_fixed_chains_fail_but_existing_exact_reassignment_is_feasible():
    data = {
        "fleet_ceiling": 3,
        "layover_minutes": dict.fromkeys(("outbound", "inbound"), 5),
        "directions": {d: {"runtime_minutes": 20} for d in ("outbound", "inbound")},
    }
    times = {"outbound": [600, 660], "inbound": [625, 685]}
    nominal = assign_fleet(data, times)
    stress = deepcopy(data)
    stress["directions"]["outbound"]["runtime_minutes"] = 30
    reassigned = assign_fleet(stress, times)
    assert nominal["required_fleet"] == 1
    assert reassigned["required_fleet"] == 2
    stressed_fixed = deepcopy(nominal)
    for t in stressed_fixed["trips"]:
        if t["direction"] == "outbound":
            t["arrival"] += 10
    with pytest.raises(ValueError, match="continuity"):
        reconstruct(stressed_fixed, {"outbound": 1, "inbound": 0}, runtime_basis="p75")

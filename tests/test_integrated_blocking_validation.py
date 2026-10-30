"""Hand-derived witnesses: deliberately independent of model opportunity calculations."""

from copy import deepcopy

import pytest

from bus_schedule_engine.mvp.integrated_blocking_validation import (
    validate_assignment,
    validate_request,
)


def request(clocks, *, duty=600, meals=False, driving=False, general=False):
    counts = dict(outbound=0, inbound=0)
    trips, profiles = [], dict(outbound=[], inbound=[])
    for direction, departure, arrival in clocks:
        counts[direction] += 1
        trips.append(
            dict(
                trip_id=f"{direction}-{counts[direction]:03d}",
                direction=direction,
                departure=departure,
                source_pointer="hand oracle",
            )
        )
        profiles[direction].append(
            dict(start=departure, end=departure + 1, minutes=arrival - departure)
        )
    # Exact synthetic profiles remain contiguous, including gaps with no departures.
    for periods in profiles.values():
        for left, right in zip(periods, periods[1:], strict=False):
            left["end"] = right["start"]
    return dict(
        schema_version="integrated_blocking_v1",
        route_id="synthetic",
        terminals=["A", "B"],
        source=dict(authority="EXPERIMENTAL_DECLARED", provenance="hand-checked synthetic fixture"),
        timetable=dict(trips=trips, departure_sha256=None),
        runtime_scenario=dict(id="p50", directions=profiles),
        terminal_policy=dict(technical=5, post=5, pre=5),
        recovery_policy=dict(
            runtime_basis="p50",
            reserve_by_arriving_trip={t["trip_id"]: 0 for t in trips},
            provenance="explicit zero; no additional traffic reserve",
        ),
        crew_policy=dict(
            assignment="FIXED_SYNCHRONIZED_DRIVER_ATTENDANT",
            duty=dict(mode="ENFORCED", limit=duty),
            total_driving=dict(mode="DISABLED_EXPERIMENTAL", limit=duty),
            driving=dict(
                mode="ENFORCED" if driving else "DISABLED_EXPERIMENTAL", limit=240, reset_minutes=30
            ),
            meals=dict(
                eligibility="SUSTAINED_WINDOW_DUTY",
                duty_threshold=360,
                overlap_threshold=60,
                windows=[
                    dict(
                        name=n,
                        start=lo,
                        end=u,
                        minutes=30,
                        mode="ENFORCED" if meals else "DISABLED_EXPERIMENTAL",
                    )
                    for n, lo, u in [("lunch", 660, 840), ("dinner", 1020, 1200)]
                ],
            ),
            general_rest=dict(
                mode="ENFORCED" if general else "DISABLED_EXPERIMENTAL",
                duty_threshold=360,
                minutes=30,
            ),
        ),
        stock=dict(
            mode="RESOURCE_SIZING_UNCONFIRMED",
            initial_vehicles=None,
            authority="EXPERIMENTAL_DECLARED",
            provenance="hypothetical initial stationing",
        ),
        resource_cap=None,
        search=dict(
            seed=0,
            workers=1,
            deterministic_seconds=2,
            wall_seconds=10,
            memory_mb=1024,
            max_edges=5151,
        ),
        operating_date=None,
        operational_evidence=[],
    )


def blocks(req, chains, rests=None):
    ids = [t["trip_id"] for t in req["timetable"]["trips"]]
    return [
        dict(
            block_id=f"B{k}",
            vehicle_id=f"V{k}",
            team_id=f"T{k}",
            driver_id=f"D{k}",
            attendant_id=f"A{k}",
            trip_ids=[ids[i] for i in chain],
            rests=(rests or {}).get(k, []),
        )
        for k, chain in enumerate(chains, 1)
    ]


def rest(req, after, before, start, end, kind="protected"):
    trips = req["timetable"]["trips"]
    return dict(
        after_trip=trips[after]["trip_id"],
        before_trip=trips[before]["trip_id"],
        start=start,
        end=end,
        terminal="B" if trips[after]["direction"] == "outbound" else "A",
        kind=kind,
    )


def test_final_technical_not_charged_but_post_and_pre_are():
    r = request([("outbound", 600, 1070)], duty=480)
    r["recovery_policy"]["reserve_by_arriving_trip"]["outbound-001"] = 20
    checked = validate_assignment(r, blocks(r, [[0]]))
    assert checked["blocks"][0]["duty_start"] == 595
    assert checked["blocks"][0]["duty_end"] == 1075
    assert checked["blocks"][0]["duty_span"] == 480
    r["crew_policy"]["duty"]["limit"] = 479
    with pytest.raises(ValueError, match="duty"):
        validate_assignment(r, blocks(r, [[0]]))


def test_shared_meal_general_and_reset_count_physical_rest_once():
    r = request(
        [("outbound", 480, 660), ("inbound", 705, 885)], meals=True, driving=True, general=True
    )
    witness = blocks(r, [[0, 1]], {1: [rest(r, 0, 1, 670, 700), rest(r, 0, 1, 670, 700, "lunch")]})
    checked = validate_assignment(r, witness)
    b = checked["blocks"][0]
    assert (
        b["duty_span"],
        b["total_driving"],
        b["max_continuous_driving"],
        b["protected_minutes"],
    ) == (415, 360, 180, 30)
    assert b["meals"]["lunch"]["required"] and b["meals"]["lunch"]["covered"]
    assert b["general_rest"] == dict(required=True, covered=True, qualifying_intervals=[[670, 700]])
    assert b["connections"][0]["other_wait"] == 0
    assert all(row["A"] + row["B"] + row["in_transit"] == 1 for row in checked["inventory"])


def test_general_rest_independent_of_meal_windows_and_fragmentation():
    r = request(
        [("outbound", 60, 180), ("inbound", 210, 330), ("outbound", 360, 480)], general=True
    )
    with pytest.raises(ValueError, match="general rest"):
        validate_assignment(
            r, blocks(r, [[0, 1, 2]], {1: [rest(r, 0, 1, 190, 205), rest(r, 1, 2, 340, 355)]})
        )
    r["timetable"]["trips"][1]["departure"] = 225
    r["runtime_scenario"]["directions"]["inbound"][0].update(start=225, end=226, minutes=105)
    checked = validate_assignment(r, blocks(r, [[0, 1, 2]], {1: [rest(r, 0, 1, 190, 220)]}))
    assert checked["blocks"][0]["general_rest"]["covered"]


@pytest.mark.parametrize("start,end", [(669, 700), (670, 701), (660, 690), (700, 730)])
def test_rest_cannot_overlap_technical_tasks_recovery_or_preparation(start, end):
    r = request([("outbound", 480, 660), ("inbound", 705, 885)])
    with pytest.raises(ValueError, match="free interval"):
        validate_assignment(r, blocks(r, [[0, 1]], {1: [rest(r, 0, 1, start, end)]}))


def test_reserve_does_not_double_as_rest():
    r = request([("outbound", 600, 660), ("inbound", 705, 765)], meals=True)
    r["crew_policy"]["meals"]["eligibility"] = "DUTY_INTERSECTS_WINDOW"
    r["recovery_policy"]["reserve_by_arriving_trip"]["outbound-001"] = 5
    with pytest.raises(ValueError, match="free interval"):
        validate_assignment(r, blocks(r, [[0, 1]], {1: [rest(r, 0, 1, 670, 700, "lunch")]}))


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "missing",
        "vehicle",
        "team",
        "driver",
        "attendant",
        "same_direction",
        "arrival",
        "late_start",
    ],
)
def test_rejects_forged_identity_and_physical_witnesses(mutation):
    r = request([("outbound", 480, 500), ("inbound", 515, 535), ("outbound", 550, 570)])
    b = blocks(r, [[0, 1], [2]])
    if mutation == "duplicate":
        b[1]["trip_ids"] = [b[0]["trip_ids"][0]]
    elif mutation == "missing":
        b.pop()
    elif mutation in ("vehicle", "team", "driver", "attendant"):
        b[1][mutation + "_id"] = b[0][mutation + "_id"]
    elif mutation == "same_direction":
        b = blocks(r, [[0, 2], [1]])
    elif mutation == "arrival":
        b[0]["arrival"] = 500
    else:
        b[1]["initial_terminal"] = "B"
    with pytest.raises(ValueError):
        validate_assignment(r, b)


def test_exact_half_open_connection_and_stock_already_present_for_late_starts():
    r = request([("outbound", 600, 660), ("inbound", 675, 735), ("outbound", 1100, 1160)])
    checked = validate_assignment(r, blocks(r, [[0, 1], [2]]))
    assert checked["initial_vehicles_required"] == dict(A=2, B=0)
    r["stock"].update(mode="EXPERIMENTAL_CAPS", initial_vehicles=dict(A=1, B=1))
    with pytest.raises(ValueError, match="stock"):
        validate_assignment(r, blocks(r, [[0, 1], [2]]))


@pytest.mark.parametrize(
    "field,value", [("technical", True), ("post", -1), ("pre", 1.5), ("technical", float("inf"))]
)
def test_integer_tasks_only(field, value):
    r = request([("outbound", 600, 660)])
    r["terminal_policy"][field] = value
    with pytest.raises(ValueError):
        validate_request(r)


@pytest.mark.parametrize(
    "mutation",
    [
        "authority",
        "mode",
        "beta",
        "continuous",
        "reserve",
        "unknown",
        "final_reserve",
        "threshold",
        "profile",
    ],
)
def test_contract_rejects_unsupported_or_incomplete_policy(mutation):
    r = request([("outbound", 600, 660)])
    if mutation == "authority":
        del r["source"]["authority"]
    elif mutation == "mode":
        del r["crew_policy"]["driving"]["mode"]
    elif mutation == "beta":
        r["crew_policy"]["driving"]["reset_minutes"] = 0
    elif mutation == "continuous":
        r["crew_policy"]["driving"]["limit"] = 0
    elif mutation == "reserve":
        r["recovery_policy"]["reserve_by_arriving_trip"] = {}
    elif mutation == "unknown":
        r["crew_policy"]["relief"] = True
    elif mutation == "final_reserve":
        r["recovery_policy"]["final_reserve"] = 5
    elif mutation == "threshold":
        r["crew_policy"]["meals"]["overlap_threshold"] = -1
    else:
        r["runtime_scenario"]["directions"]["outbound"][0]["end"] = 600
    with pytest.raises(ValueError):
        validate_request(r)


def test_meal_labels_and_actual_required_windows_are_independent():
    r = request(
        [
            ("outbound", 600, 660),
            ("inbound", 720, 780),
            ("outbound", 900, 960),
            ("inbound", 975, 1035),
        ],
        meals=True,
    )
    r["crew_policy"]["meals"]["eligibility"] = "DUTY_INTERSECTS_WINDOW"
    b = blocks(r, [[0, 1, 2, 3]], {1: [rest(r, 0, 1, 670, 700, "lunch")]})
    with pytest.raises(ValueError, match="dinner"):
        validate_assignment(r, b)
    b[0]["rests"][0]["kind"] = "dinner"
    with pytest.raises(ValueError, match="window"):
        validate_assignment(r, b)


def test_request_is_immutable_and_fractional_witness_rejected():
    r = request([("outbound", 600, 660), ("inbound", 705, 765)])
    before = deepcopy(r)
    validate_request(r)
    assert r == before
    b = blocks(r, [[0, 1]], {1: [rest(r, 0, 1, 670.5, 700.5)]})
    with pytest.raises(ValueError):
        validate_assignment(r, b)


@pytest.mark.parametrize(
    "span,overlap,required", [(359, 60, False), (360, 59, False), (360, 60, True), (361, 61, True)]
)
def test_sustained_thresholds_are_inclusive(span, overlap, required):
    # Set final end to 660+overlap and derive start to give the literal span.
    end = 660 + overlap
    r = request([("outbound", end - span + 5, end - 5)], meals=True)
    if required:
        with pytest.raises(ValueError, match="lunch"):
            validate_assignment(r, blocks(r, [[0]]))
    else:
        b = validate_assignment(r, blocks(r, [[0]]))["blocks"][0]
        assert b["meals"]["lunch"]["required"] is False


def test_general_rest_required_even_when_no_meal_is_applicable_and_no_rest_selected():
    r = request(
        [("outbound", 60, 180), ("inbound", 225, 345), ("outbound", 390, 450)],
        general=True,
        meals=True,
    )
    with pytest.raises(ValueError, match="general rest"):
        validate_assignment(r, blocks(r, [[0, 1, 2]]))


def test_driver_cannot_be_reused_as_attendant_on_another_vehicle():
    r = request([("outbound", 600, 660), ("inbound", 600, 660)])
    b = blocks(r, [[0], [1]])
    b[1]["attendant_id"] = b[0]["driver_id"]
    with pytest.raises(ValueError, match="person reused"):
        validate_assignment(r, b)

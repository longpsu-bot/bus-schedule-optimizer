"""Pinned P0 adapter: read evidence and runtime observations, never compile a timetable."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import file_digest
from pathlib import Path

from .circulation import assign_fleet
from .external_import import import_external_workbook
from .input import DIRECTIONS, runtime_at
from .integrated_blocking_validation import digest, validate_request
from .route10_fleet_pilot import audit_fleet
from .route10_pilot import WORKBOOK_SHA256, planning_bundle, runtime_scenarios

FROZEN_SHA256 = "1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3"
DEPARTURE_SHA256 = "d20e26cc05c48a9d4c06c4937b1fc97e835be24d9f7c0f7dda46849c19f257a9"


def frozen_rows(path):
    """Read only bundle/comparison/id from the pinned pretty-printed MVP-6A JSON.

    The 394 MB file includes large unrelated search traces. Its bytes are SHA-locked
    by the caller; line indentation is that existing export's serialization contract.
    No trace is parsed or rerun, and retained memory is bounded by one comparison.
    """
    rows = {}
    row = None
    active = False
    with Path(path).open(encoding="utf-8") as lines:
        for line in lines:
            if line.startswith('  "scenarios": ['):
                active = True
                continue
            if not active:
                continue
            if line.startswith("  ]"):
                break
            if line.startswith("    {"):
                row = {}
            elif line.startswith("    }"):
                if row is not None and row.get("id") in {"report_p50", "report_p75"}:
                    if row["id"] in rows:
                        raise ValueError("duplicate frozen scenario")
                    rows[row["id"]] = row
                row = None
            elif row is not None:
                for key in ("bundle", "comparison", "id"):
                    prefix = f'      "{key}": '
                    if not line.startswith(prefix):
                        continue
                    value = line[len(prefix) :].rstrip().removesuffix(",")
                    if value in ("{", "["):
                        closing = "      }" if value == "{" else "      ]"
                        chunks = [value + "\n"]
                        for inner in lines:
                            chunks.append(
                                inner.rstrip().removesuffix(",")
                                if inner.startswith(closing)
                                else inner
                            )
                            if inner.startswith(closing):
                                break
                        value = "".join(chunks)
                    row[key] = json.loads(value)
                    break
    if set(rows) != {"report_p50", "report_p75"} or any(
        not {"bundle", "comparison"} <= set(row) for row in rows.values()
    ):
        raise ValueError("missing frozen P0/runtime evidence")
    return rows


def experimental_request(departures, profiles, scenario, duty, provenance):
    trips = [
        dict(
            trip_id=f"{d}-{i:03d}",
            direction=d,
            departure=t,
            source_pointer="scenarios[id=report_p50].comparison.C.departures." + d + f"[{i - 1}]",
        )
        for d in DIRECTIONS
        for i, t in enumerate(departures[d], 1)
    ]
    return dict(
        schema_version="integrated_blocking_v1",
        route_id="10",
        terminals=["A", "B"],
        source=dict(authority="EXPERIMENTAL_DECLARED", provenance=provenance),
        timetable=dict(trips=trips, departure_sha256=DEPARTURE_SHA256),
        runtime_scenario=dict(id=scenario, directions=deepcopy(profiles)),
        terminal_policy=dict(technical=5, post=5, pre=5),
        recovery_policy=dict(
            runtime_basis=scenario,
            reserve_by_arriving_trip={t["trip_id"]: 0 for t in trips},
            provenance="Explicit zero; selected runtime already contains scenario traffic stress",
        ),
        crew_policy=dict(
            assignment="FIXED_SYNCHRONIZED_DRIVER_ATTENDANT",
            duty=dict(mode="ENFORCED", limit=duty),
            total_driving=dict(mode="ENFORCED", limit=duty),
            driving=dict(mode="ENFORCED", limit=240, reset_minutes=30),
            meals=dict(
                eligibility="SUSTAINED_WINDOW_DUTY",
                duty_threshold=360,
                overlap_threshold=60,
                windows=[
                    dict(name=name, start=start, end=end, minutes=30, mode="ENFORCED")
                    for name, start, end in (("lunch", 660, 840), ("dinner", 1020, 1200))
                ],
            ),
            general_rest=dict(mode="ENFORCED", duty_threshold=360, minutes=30),
        ),
        stock=dict(
            mode="RESOURCE_SIZING_UNCONFIRMED",
            initial_vehicles=None,
            authority="EXPERIMENTAL_DECLARED",
            provenance="Size hypothetical vehicles stationed at each first-trip terminal; all late starts already present initially",
        ),
        resource_cap=None,
        search=dict(
            seed=0,
            workers=1,
            deterministic_seconds=10,
            wall_seconds=60,
            memory_mb=1024,
            max_edges=5151,
        ),
        operating_date=None,
        operational_evidence=[
            "Operating date and applicable labour/transport/night/overtime rules unverified",
            "Driver/attendant identities are hypothetical; qualifications, availability and weekly duties unverified",
            "Initial A/B stock, parking, terminal task standards and authority to protect all free intervals unverified",
            "p50/p75 are descriptive report-clock scenarios, not runtime reliability guarantees",
            "No relief, substitution, vehicle reuse, depot, deadheading, crew transfer or repositioning modeled",
        ],
    )


def route10_requests(workbook, evidence):
    workbook, evidence = Path(workbook), Path(evidence)
    for path, expected in ((workbook, WORKBOOK_SHA256), (evidence, FROZEN_SHA256)):
        with path.open("rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"{path.name}: frozen SHA-256 mismatch")
    rows = frozen_rows(evidence)
    departures = rows["report_p50"]["comparison"]["C"]["departures"]
    if digest(departures) != DEPARTURE_SHA256 or any(len(departures[d]) != 51 for d in DIRECTIONS):
        raise ValueError("P0 departure hash/count mismatch")
    source = import_external_workbook(workbook)
    definitions = {s["id"]: s for s in runtime_scenarios(source)}
    requests = []
    for scenario, workload, technical in (("p50", 11010, 14), ("p75", 11376, 15)):
        bundle = planning_bundle(source, definitions[f"report_{scenario}"])
        if bundle != rows[f"report_{scenario}"]["bundle"]:
            raise ValueError("frozen runtime bundle differs from source observations")
        if (
            sum(runtime_at(bundle["directions"][d], t) for d in DIRECTIONS for t in departures[d])
            != workload
        ):
            raise ValueError("frozen driving workload mismatch")
        for allowance, minimum in ((5, technical), (15, 16)):
            derived = deepcopy(bundle)
            derived["layover_minutes"] = dict.fromkeys(DIRECTIONS, allowance)
            cover = assign_fleet(derived, departures)
            if audit_fleet(derived, departures, cover) != minimum:
                raise ValueError("frozen path-cover benchmark mismatch")
        provenance = f"PO conditional approval 2026-10-30: all terminal/crew/search assumptions EXPERIMENTAL_DECLARED. Workbook SHA256={WORKBOOK_SHA256}; frozen evidence SHA256={FROZEN_SHA256}; P0 SHA256={DEPARTURE_SHA256}; runtime basis={scenario}. No statutory-compliance claim."
        profiles = {d: bundle["directions"][d]["runtime_periods"] for d in DIRECTIONS}
        for duty in (480, 600):
            requests.append(
                validate_request(
                    experimental_request(departures, profiles, scenario, duty, provenance)
                )
            )
    return requests

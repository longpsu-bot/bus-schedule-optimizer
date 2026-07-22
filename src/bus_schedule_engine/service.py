from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from .c_config import SCENARIO_B_DISPLAY_NAME, ScenarioCConfig
from .c_generator import analyze_baseline_regularity
from .comparator import load_scoring_config, score_scenario
from .demand import blocks_needing_more_trips, evaluate_scenario
from .fingerprint import timetable_fingerprint
from .fleet import assign_fleet
from .generator import generate_recommendations
from .importer import ImportedWorkbook, InputDataError
from .models import AnalysisBundle, GeneratedScenario, ScenarioParameters, ScenarioResult, Trip
from .validator import validate_schedule


def _build_result(
    name: str,
    parameters: ScenarioParameters,
    trips: list[Trip],
    demand,
    scoring_config,
    reason: str = "",
    strategy_id: str = "",
    resource_fleet_limit: int | None = None,
    generated: GeneratedScenario | None = None,
) -> ScenarioResult:
    validation = validate_schedule(trips, parameters)
    if parameters.vehicle_capacity_passengers is None:
        raise InputDataError(f"Scenario {name} thiếu sức chứa phương tiện")
    fleet = assign_fleet(trips, parameters)
    evaluation = evaluate_scenario(name, trips, demand, parameters, validation)
    score = score_scenario(evaluation, fleet, validation, parameters, scoring_config)
    return ScenarioResult(
        name=name,
        parameters=parameters,
        trips=trips,
        validation=validation,
        evaluation=evaluation,
        fleet=fleet,
        score=score,
        recommendation_reason=reason,
        strategy_id=strategy_id,
        resource_fleet_limit=resource_fleet_limit,
        display_name=generated.display_name if generated else "",
        active_vehicle_count=generated.active_vehicle_count if generated else None,
        active_vehicle_ids=generated.active_vehicle_ids if generated else (),
        generation_status=generated.generation_status if generated else None,
        headway_regimes=list(generated.headway_regimes) if generated else [],
        trip_traces=list(generated.trip_traces) if generated else [],
        regularity=generated.regularity if generated else None,
        optimization_log=generated.optimization_log if generated else None,
        timetable_fingerprint=(
            generated.timetable_fingerprint if generated else timetable_fingerprint(trips)
        ),
        source_timetable_fingerprint=(generated.source_timetable_fingerprint if generated else ""),
        generation_config=dict(generated.generation_config) if generated else {},
    )


def run_analysis(imported: ImportedWorkbook) -> AnalysisBundle:
    scoring = load_scoring_config()
    c_config = ScenarioCConfig.from_mapping(imported.configuration)
    results: list[ScenarioResult] = []
    if imported.parameters_a is not None and imported.trips_a:
        results.append(
            _build_result("A", imported.parameters_a, imported.trips_a, imported.demand, scoring)
        )
    result_b = _build_result("B", imported.parameters_b, imported.trips_b, imported.demand, scoring)
    available_fleet_b = max(
        result_b.fleet.minimum_vehicles,
        len({trip.vehicle_id for trip in imported.trips_b if trip.vehicle_id}),
    )
    result_b.display_name = SCENARIO_B_DISPLAY_NAME
    result_b.active_vehicle_count = available_fleet_b
    declared_vehicle_ids = sorted({trip.vehicle_id for trip in imported.trips_b if trip.vehicle_id})
    derived_vehicle_ids = [
        str(summary["vehicle_id"]) for summary in result_b.fleet.vehicle_summaries
    ]
    active_ids = declared_vehicle_ids or derived_vehicle_ids
    next_index = 1
    while len(active_ids) < available_fleet_b:
        candidate = f"XE-{next_index:03d}"
        next_index += 1
        if candidate not in active_ids:
            active_ids.append(candidate)
    result_b.active_vehicle_ids = tuple(active_ids[:available_fleet_b])
    result_b.regularity = analyze_baseline_regularity(result_b.trips, result_b.parameters, c_config)
    result_b.timetable_fingerprint = timetable_fingerprint(result_b.trips)
    immutable_b = deepcopy(result_b)
    results.append(result_b)
    generation = generate_recommendations(
        imported.parameters_b,
        imported.trips_b,
        imported.demand,
        available_fleet_b,
        imported.configuration,
    )
    for generated in generation.scenarios:
        results.append(
            _build_result(
                generated.name,
                generated.parameters,
                generated.trips,
                imported.demand,
                scoring,
                generated.reason,
                generated.strategy_id,
                generated.resource_fleet_limit,
                generated,
            )
        )
    result_c = next((result for result in results if result.name == "C"), None)
    if result_c is not None:
        active_vehicle_count = result_b.active_vehicle_count or 0
        if result_c.fleet.minimum_vehicles > active_vehicle_count:
            raise InputDataError(
                "Scenario C cần "
                f"{result_c.fleet.minimum_vehicles} xe nhưng Scenario B chỉ khóa "
                f"{active_vehicle_count} xe hoạt động. Ứng viên C này phải bị loại; "
                "hãy chạy lại ứng dụng để nạp đồng bộ bộ sinh Scenario C."
            )
        result_c.active_vehicle_ids = result_b.active_vehicle_ids
        _inherit_active_vehicle_ids(result_c)
    if result_b != immutable_b:
        raise AssertionError("Scenario B đã bị thay đổi trong quá trình tạo Scenario C")
    if result_c is not None:
        _assert_c_resource_locks(result_b, result_c)
    source_blocks = result_c.evaluation.blocks if result_c else result_b.evaluation.blocks
    generation.blocks_requiring_more_trips = blocks_needing_more_trips(source_blocks)
    limitations = sorted(
        {limitation for result in results for limitation in result.evaluation.limitations}
    )
    return AnalysisBundle(results, generation, limitations)


def _assert_c_resource_locks(result_b: ScenarioResult, result_c: ScenarioResult) -> None:
    if result_b.trips is result_c.trips:
        raise AssertionError("B và C đang dùng chung list chuyến")
    if {id(trip) for trip in result_b.trips} & {id(trip) for trip in result_c.trips}:
        raise AssertionError("B và C đang dùng chung object chuyến")
    if result_b.parameters != result_c.parameters:
        raise AssertionError("C đã thay đổi tham số khóa của B")
    if len(result_b.trips) != len(result_c.trips):
        raise AssertionError("C đã thay đổi tổng chuyến của B")
    for direction in {trip.direction for trip in result_b.trips}:
        if sum(trip.direction == direction for trip in result_b.trips) != sum(
            trip.direction == direction for trip in result_c.trips
        ):
            raise AssertionError("C đã thay đổi tổng chuyến theo chiều")
    source_ids = [trip.source_b_trip_id for trip in result_c.trips]
    if None in source_ids or len(source_ids) != len(set(source_ids)):
        raise AssertionError("Ánh xạ chuyến B → C không phải một-một")
    if set(source_ids) != {trip.trip_id for trip in result_b.trips}:
        raise AssertionError("C không truy vết đủ toàn bộ chuyến nguồn B")
    source_by_id = {trip.trip_id: trip for trip in result_b.trips}
    default_runtime = result_b.parameters.default_trip_runtime_minutes
    for trip_c in result_c.trips:
        trip_b = source_by_id[trip_c.source_b_trip_id]
        b_runtime = trip_b.resolved_arrival_seconds(default_runtime) - trip_b.departure_seconds
        c_runtime = trip_c.resolved_arrival_seconds(default_runtime) - trip_c.departure_seconds
        if c_runtime != b_runtime:
            raise AssertionError(
                f"C đã thay đổi thời gian hành trình của chuyến nguồn {trip_b.trip_id}"
            )
    if result_c.active_vehicle_count != result_b.active_vehicle_count:
        raise AssertionError("C không giữ số xe hoạt động của B")
    if result_c.active_vehicle_ids != result_b.active_vehicle_ids:
        raise AssertionError("C không kế thừa đúng danh sách xe hoạt động của B")
    if result_c.fleet.minimum_vehicles > (result_b.active_vehicle_count or 0):
        raise AssertionError("C cần nhiều xe hơn đội xe hoạt động của B")
    for direction in {trip.direction for trip in result_b.trips}:
        b_times = sorted(
            trip.departure_seconds for trip in result_b.trips if trip.direction == direction
        )
        c_times = sorted(
            trip.departure_seconds for trip in result_c.trips if trip.direction == direction
        )
        if b_times[0] != c_times[0] or b_times[-1] != c_times[-1]:
            raise AssertionError("C đã thay đổi chuyến đầu hoặc chuyến cuối đã khóa")
    if timetable_fingerprint(result_c.trips) != result_c.timetable_fingerprint:
        raise AssertionError("Fingerprint lịch C không khớp object authoritative")


def _inherit_active_vehicle_ids(result_c: ScenarioResult) -> None:
    used_ids = sorted({assignment.vehicle_id for assignment in result_c.fleet.assignments})
    if len(used_ids) > len(result_c.active_vehicle_ids):
        raise InputDataError(
            "Không thể ánh xạ đội xe Scenario C: bộ gán xe tạo "
            f"{len(used_ids)} xe nhưng chỉ có {len(result_c.active_vehicle_ids)} "
            "ID xe hoạt động được kế thừa từ Scenario B."
        )
    mapping = dict(zip(used_ids, result_c.active_vehicle_ids, strict=False))
    result_c.fleet.assignments = [
        replace(assignment, vehicle_id=mapping[assignment.vehicle_id])
        for assignment in result_c.fleet.assignments
    ]
    result_c.fleet.vehicle_summaries = [
        {**summary, "vehicle_id": mapping[str(summary["vehicle_id"])]}
        for summary in result_c.fleet.vehicle_summaries
    ]

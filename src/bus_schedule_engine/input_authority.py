from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .contracts_v1.adapters import NormalizationOptions
from .contracts_v1.models import (
    DemandConfidence,
    DemandResponseMode,
    DemandSourceType,
    InputSourceType,
    OperatingDayType,
)
from .contracts_v1.terminal_occupancy import (
    TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,
)
from .importer import ImportedWorkbook
from .models import Direction

AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION = "AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION"
AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_FLEET_FEASIBILITY = (
    "AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_FLEET_FEASIBILITY"
)
OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION = "OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION"
VEHICLE_CAPACITY_REQUIRED_FOR_DEMAND_EVALUATION = "VEHICLE_CAPACITY_REQUIRED_FOR_DEMAND_EVALUATION"
VEHICLE_CAPACITY_REQUIRED_FOR_OPTIMIZATION = "VEHICLE_CAPACITY_REQUIRED_FOR_OPTIMIZATION"
TURNAROUND_AUTHORITY_REQUIRED_FOR_COMPLIANCE = "TURNAROUND_AUTHORITY_REQUIRED_FOR_COMPLIANCE"
DIRECTIONAL_DEMAND_REQUIRED_FOR_DIRECTIONAL_OPTIMIZATION = (
    "DIRECTIONAL_DEMAND_REQUIRED_FOR_DIRECTIONAL_OPTIMIZATION"
)
DEMAND_DATA_REQUIRED_FOR_DEMAND_EVALUATION = "DEMAND_DATA_REQUIRED_FOR_DEMAND_EVALUATION"
SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED = "SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED"
ARRIVAL_OR_RUNTIME_AUTHORITY_REQUIRED_FOR_REVIEW = (
    "ARRIVAL_OR_RUNTIME_AUTHORITY_REQUIRED_FOR_REVIEW"
)
SCENARIO_A_AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION = (
    "SCENARIO_A_AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION"
)
SCENARIO_A_VEHICLE_CAPACITY_REQUIRED_FOR_OPTIMIZATION = (
    "SCENARIO_A_VEHICLE_CAPACITY_REQUIRED_FOR_OPTIMIZATION"
)
SCENARIO_A_OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION = (
    "SCENARIO_A_OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION"
)
DEMAND_SOURCE_TYPE_REQUIRED_FOR_OPTIMIZATION = "DEMAND_SOURCE_TYPE_REQUIRED_FOR_OPTIMIZATION"
DEMAND_CONFIDENCE_REQUIRED_FOR_OPTIMIZATION = "DEMAND_CONFIDENCE_REQUIRED_FOR_OPTIMIZATION"
DEMAND_RESPONSE_MODE_REQUIRED_FOR_OPTIMIZATION = "DEMAND_RESPONSE_MODE_REQUIRED_FOR_OPTIMIZATION"


class DataAuthorityCapabilityV1(StrEnum):
    TIMETABLE_REVIEW = "TIMETABLE_REVIEW"
    TURNAROUND_COMPLIANCE = "TURNAROUND_COMPLIANCE"
    DEMAND_EVALUATION = "DEMAND_EVALUATION"
    FLEET_FEASIBILITY = "FLEET_FEASIBILITY"
    OPTIMIZATION = "OPTIMIZATION"
    TERMINAL_CAPACITY = "TERMINAL_CAPACITY"


class CapabilityReadinessStatusV1(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CapabilityReadinessV1:
    capability: DataAuthorityCapabilityV1
    status: CapabilityReadinessStatusV1
    ready: bool
    missing_authority_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LayeredDataAuthorityReadinessV1:
    capabilities: tuple[CapabilityReadinessV1, ...]

    def for_capability(self, capability: DataAuthorityCapabilityV1) -> CapabilityReadinessV1:
        return next(item for item in self.capabilities if item.capability == capability)

    @property
    def all_missing_authority_codes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    code
                    for capability in self.capabilities
                    for code in capability.missing_authority_codes
                }
            )
        )


@dataclass(frozen=True, slots=True)
class WorkbookInputReadinessV1:
    import_ready: bool
    optimization_ready: bool
    blocking_import_codes: tuple[str, ...]
    missing_optimization_authority_codes: tuple[str, ...]
    optional_limitations: tuple[str, ...]


class WorkbookOptimizationAuthorityError(ValueError):
    """Raised before Contract V1 normalization when workbook authority is incomplete."""

    def __init__(self, codes: tuple[str, ...]) -> None:
        self.codes = tuple(sorted(set(codes)))
        joined = ", ".join(self.codes)
        super().__init__(
            "Có thể đọc và kiểm tra dữ liệu, nhưng chưa thể tối ưu vì thiếu thẩm quyền "
            f"đầu vào bắt buộc: {joined}"
        )


def _terminal_capacity_limitations(imported: ImportedWorkbook) -> tuple[str, ...]:
    parameters = imported.parameters_b
    terminal_1 = parameters.terminal_1_max_occupancy_vehicles
    terminal_2 = parameters.terminal_2_max_occupancy_vehicles
    if terminal_1 is None and terminal_2 is None:
        return (TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,)
    if terminal_1 is None:
        return (TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED,)
    if terminal_2 is None:
        return (TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,)
    return ()


def assess_workbook_input_readiness_v1(
    imported: ImportedWorkbook,
) -> WorkbookInputReadinessV1:
    """Assess imported facts without mutation, inference, normalization, or solving."""

    missing: list[str] = []
    parameters_b = imported.parameters_b
    if parameters_b.vehicle_capacity_passengers is None:
        missing.append(VEHICLE_CAPACITY_REQUIRED_FOR_OPTIMIZATION)
    if parameters_b.available_fleet_limit is None:
        missing.append(AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION)
    if parameters_b.operating_day_type is None:
        missing.append(OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION)

    if imported.parameters_a is not None:
        if imported.parameters_a.vehicle_capacity_passengers is None:
            missing.append(SCENARIO_A_VEHICLE_CAPACITY_REQUIRED_FOR_OPTIMIZATION)
        if imported.parameters_a.available_fleet_limit is None:
            missing.append(SCENARIO_A_AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION)
        if imported.parameters_a.operating_day_type is None:
            missing.append(SCENARIO_A_OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION)

    if imported.demand:
        metadata = imported.authority_metadata
        if metadata.demand_source_type is None:
            missing.append(DEMAND_SOURCE_TYPE_REQUIRED_FOR_OPTIMIZATION)
        if metadata.demand_confidence is None:
            missing.append(DEMAND_CONFIDENCE_REQUIRED_FOR_OPTIMIZATION)
        if metadata.demand_response_mode is None:
            missing.append(DEMAND_RESPONSE_MODE_REQUIRED_FOR_OPTIMIZATION)

    missing_codes = tuple(sorted(set(missing)))
    limitations = tuple(sorted(set(_terminal_capacity_limitations(imported))))
    return WorkbookInputReadinessV1(
        import_ready=True,
        optimization_ready=not missing_codes,
        blocking_import_codes=(),
        missing_optimization_authority_codes=missing_codes,
        optional_limitations=limitations,
    )


def _capability(
    capability: DataAuthorityCapabilityV1,
    *,
    status: CapabilityReadinessStatusV1,
    missing: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
) -> CapabilityReadinessV1:
    return CapabilityReadinessV1(
        capability=capability,
        status=status,
        ready=status == CapabilityReadinessStatusV1.READY,
        missing_authority_codes=tuple(sorted(set(missing))),
        limitation_codes=tuple(sorted(set(limitations))),
    )


def _arrivals_are_resolvable(imported: ImportedWorkbook) -> bool:
    parameters = imported.parameters_b
    return bool(parameters.runtime_options) and all(
        trip.arrival_seconds is not None or parameters.default_trip_runtime_minutes > 0
        for trip in imported.trips_b
    )


def _directional_demand_is_supplied(imported: ImportedWorkbook) -> bool:
    directions = {record.direction for record in imported.demand}
    return {
        Direction.TERMINAL_1_TO_2,
        Direction.TERMINAL_2_TO_1,
    }.issubset(directions)


def assess_layered_data_authority_v1(
    imported: ImportedWorkbook,
) -> LayeredDataAuthorityReadinessV1:
    """Assess each review capability without inferring or mutating workbook authority."""

    parameters = imported.parameters_b
    arrivals_resolvable = _arrivals_are_resolvable(imported)
    timetable_missing = (
        () if arrivals_resolvable else (ARRIVAL_OR_RUNTIME_AUTHORITY_REQUIRED_FOR_REVIEW,)
    )
    timetable = _capability(
        DataAuthorityCapabilityV1.TIMETABLE_REVIEW,
        status=(
            CapabilityReadinessStatusV1.READY
            if not timetable_missing
            else CapabilityReadinessStatusV1.BLOCKED
        ),
        missing=timetable_missing,
    )

    turnaround_missing = []
    if parameters.minimum_layover_minutes is None:
        turnaround_missing.append(TURNAROUND_AUTHORITY_REQUIRED_FOR_COMPLIANCE)
    if not arrivals_resolvable:
        turnaround_missing.append(ARRIVAL_OR_RUNTIME_AUTHORITY_REQUIRED_FOR_REVIEW)
    turnaround = _capability(
        DataAuthorityCapabilityV1.TURNAROUND_COMPLIANCE,
        status=(
            CapabilityReadinessStatusV1.READY
            if not turnaround_missing
            else CapabilityReadinessStatusV1.BLOCKED
        ),
        missing=tuple(turnaround_missing),
    )

    demand_missing = []
    if parameters.vehicle_capacity_passengers is None:
        demand_missing.append(VEHICLE_CAPACITY_REQUIRED_FOR_DEMAND_EVALUATION)
    if not imported.demand:
        demand_missing.append(DEMAND_DATA_REQUIRED_FOR_DEMAND_EVALUATION)
    else:
        metadata = imported.authority_metadata
        if metadata.demand_source_type is None:
            demand_missing.append(DEMAND_SOURCE_TYPE_REQUIRED_FOR_OPTIMIZATION)
        if metadata.demand_confidence is None:
            demand_missing.append(DEMAND_CONFIDENCE_REQUIRED_FOR_OPTIMIZATION)
        if metadata.demand_response_mode is None:
            demand_missing.append(DEMAND_RESPONSE_MODE_REQUIRED_FOR_OPTIMIZATION)
        if not _directional_demand_is_supplied(imported):
            demand_missing.append(DIRECTIONAL_DEMAND_REQUIRED_FOR_DIRECTIONAL_OPTIMIZATION)
    directional_only_gap = set(demand_missing) == {
        DIRECTIONAL_DEMAND_REQUIRED_FOR_DIRECTIONAL_OPTIMIZATION
    }
    demand = _capability(
        DataAuthorityCapabilityV1.DEMAND_EVALUATION,
        status=(
            CapabilityReadinessStatusV1.READY
            if not demand_missing
            else CapabilityReadinessStatusV1.PARTIAL
            if directional_only_gap
            else CapabilityReadinessStatusV1.BLOCKED
        ),
        missing=tuple(demand_missing),
    )

    fleet_missing = []
    if parameters.available_fleet_limit is None:
        fleet_missing.append(AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_FLEET_FEASIBILITY)
    if parameters.minimum_layover_minutes is None:
        fleet_missing.append(TURNAROUND_AUTHORITY_REQUIRED_FOR_COMPLIANCE)
    if not arrivals_resolvable:
        fleet_missing.append(ARRIVAL_OR_RUNTIME_AUTHORITY_REQUIRED_FOR_REVIEW)
    fleet = _capability(
        DataAuthorityCapabilityV1.FLEET_FEASIBILITY,
        status=(
            CapabilityReadinessStatusV1.READY
            if not fleet_missing
            else CapabilityReadinessStatusV1.BLOCKED
        ),
        missing=tuple(fleet_missing),
    )

    strict_readiness = assess_workbook_input_readiness_v1(imported)
    optimization = _capability(
        DataAuthorityCapabilityV1.OPTIMIZATION,
        status=(
            CapabilityReadinessStatusV1.READY
            if strict_readiness.optimization_ready
            else CapabilityReadinessStatusV1.BLOCKED
        ),
        missing=strict_readiness.missing_optimization_authority_codes,
        limitations=strict_readiness.optional_limitations,
    )

    terminal_1 = parameters.terminal_1_max_occupancy_vehicles
    terminal_2 = parameters.terminal_2_max_occupancy_vehicles
    terminal_limitations = _terminal_capacity_limitations(imported)
    terminal = _capability(
        DataAuthorityCapabilityV1.TERMINAL_CAPACITY,
        status=(
            CapabilityReadinessStatusV1.READY
            if terminal_1 is not None and terminal_2 is not None
            else CapabilityReadinessStatusV1.PARTIAL
            if terminal_1 is not None or terminal_2 is not None
            else CapabilityReadinessStatusV1.BLOCKED
        ),
        missing=terminal_limitations,
    )
    return LayeredDataAuthorityReadinessV1(
        capabilities=(timetable, turnaround, demand, fleet, optimization, terminal)
    )


def _operating_day_type(value: str | None) -> OperatingDayType | None:
    return None if value is None else OperatingDayType(value)


def normalization_options_from_workbook_v1(
    imported: ImportedWorkbook,
    *,
    source_id: str,
    imported_at: datetime,
    source_type: InputSourceType = InputSourceType.XLSX,
) -> NormalizationOptions:
    """Build strict Contract V1 options only from declared workbook and runtime authority."""

    if not isinstance(source_id, str):
        raise TypeError("source_id must be a string")
    clean_source_id = source_id.strip()
    if not clean_source_id:
        raise ValueError("source_id must be a non-empty string")

    readiness = assess_workbook_input_readiness_v1(imported)
    if not readiness.optimization_ready:
        raise WorkbookOptimizationAuthorityError(readiness.missing_optimization_authority_codes)

    metadata = imported.authority_metadata
    demand_options: dict[str, object] = {}
    if metadata.demand_source_type is not None:
        demand_options["demand_source_type"] = DemandSourceType(metadata.demand_source_type)
    if metadata.demand_confidence is not None:
        demand_options["demand_confidence"] = DemandConfidence(metadata.demand_confidence)
    if metadata.demand_response_mode is not None:
        demand_options["demand_response_mode"] = DemandResponseMode(metadata.demand_response_mode)

    parameters_a = imported.parameters_a
    return NormalizationOptions(
        source_id=clean_source_id,
        imported_at=imported_at,
        source_type=source_type,
        operating_day_type_b=_operating_day_type(imported.parameters_b.operating_day_type),
        available_fleet_limit_b=imported.parameters_b.available_fleet_limit,
        approved_active_fleet_b=imported.parameters_b.approved_active_fleet,
        operating_day_type_a=(
            _operating_day_type(parameters_a.operating_day_type)
            if parameters_a is not None
            else None
        ),
        available_fleet_limit_a=(
            parameters_a.available_fleet_limit if parameters_a is not None else None
        ),
        approved_active_fleet_a=(
            parameters_a.approved_active_fleet if parameters_a is not None else None
        ),
        terminal_1_max_occupancy_vehicles_b=(
            imported.parameters_b.terminal_1_max_occupancy_vehicles
        ),
        terminal_2_max_occupancy_vehicles_b=(
            imported.parameters_b.terminal_2_max_occupancy_vehicles
        ),
        source_notes=metadata.source_notes,
        demand_dataset_id=metadata.demand_dataset_id or clean_source_id,
        **demand_options,
    )

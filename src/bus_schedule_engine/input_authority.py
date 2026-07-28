from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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

AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION = "AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION"
OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION = "OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION"
SCENARIO_A_AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION = (
    "SCENARIO_A_AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION"
)
SCENARIO_A_OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION = (
    "SCENARIO_A_OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION"
)
DEMAND_SOURCE_TYPE_REQUIRED_FOR_OPTIMIZATION = "DEMAND_SOURCE_TYPE_REQUIRED_FOR_OPTIMIZATION"
DEMAND_CONFIDENCE_REQUIRED_FOR_OPTIMIZATION = "DEMAND_CONFIDENCE_REQUIRED_FOR_OPTIMIZATION"
DEMAND_RESPONSE_MODE_REQUIRED_FOR_OPTIMIZATION = "DEMAND_RESPONSE_MODE_REQUIRED_FOR_OPTIMIZATION"


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
    if parameters_b.available_fleet_limit is None:
        missing.append(AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION)
    if parameters_b.operating_day_type is None:
        missing.append(OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION)

    if imported.parameters_a is not None:
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

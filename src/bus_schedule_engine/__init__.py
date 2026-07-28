"""Bus Schedule Engine MVP."""

from .importer import ImportedWorkbook, WorkbookAuthorityMetadata
from .input_authority import (
    WorkbookInputReadinessV1,
    WorkbookOptimizationAuthorityError,
    assess_workbook_input_readiness_v1,
    normalization_options_from_workbook_v1,
)
from .models import (
    AnalysisBundle,
    DemandRecord,
    Direction,
    RouteType,
    ScenarioParameters,
    Trip,
)
from .optimization_service import (
    BusScheduleOptimizationResult,
    OptimizationAction,
    SolverChoice,
    SolverComparisonV1,
    analyze_and_optimize_schedule_v1,
    select_optimization_action,
)
from .side_by_side_validation import (
    ComparisonCategoryV1,
    ComparisonDispositionV1,
    ComparisonRuleV1,
    ComparisonStatusV1,
    FactComparisonRecordV1,
    LegacyPathSnapshotV1,
    SideBySideValidationReportV1,
    TimetableSnapshotV1,
    TimetableTripSnapshotV1,
    UnifiedPathSnapshotV1,
    run_side_by_side_validation_v1,
    side_by_side_report_to_dict,
)

__all__ = [
    "AnalysisBundle",
    "BusScheduleOptimizationResult",
    "ComparisonCategoryV1",
    "ComparisonDispositionV1",
    "ComparisonRuleV1",
    "ComparisonStatusV1",
    "DemandRecord",
    "Direction",
    "FactComparisonRecordV1",
    "ImportedWorkbook",
    "LegacyPathSnapshotV1",
    "OptimizationAction",
    "RouteType",
    "ScenarioParameters",
    "SideBySideValidationReportV1",
    "SolverComparisonV1",
    "SolverChoice",
    "TimetableSnapshotV1",
    "TimetableTripSnapshotV1",
    "Trip",
    "UnifiedPathSnapshotV1",
    "WorkbookAuthorityMetadata",
    "WorkbookInputReadinessV1",
    "WorkbookOptimizationAuthorityError",
    "analyze_and_optimize_schedule_v1",
    "assess_workbook_input_readiness_v1",
    "normalization_options_from_workbook_v1",
    "run_side_by_side_validation_v1",
    "select_optimization_action",
    "side_by_side_report_to_dict",
]

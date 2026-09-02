"""Offline review artifacts for deterministic V3 demand regimes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .contracts_v1 import (
    DEFAULT_DEMAND_REGIME_CONFIG_V1,
    DemandRegimeDetectorConfigV1,
    DemandRegimeModelSelectionResultV1,
    DerivedDemandObservationV1,
    NormalizationOptions,
    RegimeModelSelectionStatusV1,
    ScenarioBInput,
    ScenarioCOptimizationModeV1,
    demand_regime_model_selection_to_dict_v1,
    derive_demand_profile_v1,
    normalize_multi_period_profile_v1,
    select_demand_regime_model_v1,
)
from .input_authority import normalization_options_from_workbook_v1
from .raw_daily_demand import (
    RawDailyDemandImportResultV1,
    RawDailyDemandRouteV1,
    RawDemandReconciliationV1,
    import_t06_t10_daily_demand_v1,
    raw_daily_demand_to_dict_v1,
    reconcile_raw_daily_demand_v1,
)
from .time_utils import format_hhmm
from .v3_workbook import ImportedV3WorkbookV1, import_v3_multi_period_workbook_v1

DEMAND_REGIME_REVIEW_PROFILE_V1 = "demand_regime_review_v1"


@dataclass(frozen=True, slots=True)
class DemandRegimeReviewV1:
    input_path: Path
    route_id: str
    route_name: str
    model_selection: DemandRegimeModelSelectionResultV1
    demand_observations: tuple[DerivedDemandObservationV1, ...]
    source_period_observation_days: int
    scenario_b: ScenarioBInput
    raw_source_path: Path | None = None
    raw_import: RawDailyDemandImportResultV1 | None = None
    raw_route: RawDailyDemandRouteV1 | None = None
    reconciliation: RawDemandReconciliationV1 | None = None


def _normalization_options(
    path: Path,
    imported: ImportedV3WorkbookV1,
) -> NormalizationOptions:
    content_fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    base = normalization_options_from_workbook_v1(
        imported.base_workbook,
        source_id=f"v3-workbook-sha256:{content_fingerprint}",
        imported_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
    )
    return replace(
        base,
        optimization_mode=ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE,
    )


def build_v3_demand_regime_review_v1(
    input_path: str | Path,
    *,
    profile_id: str | None = None,
    config: DemandRegimeDetectorConfigV1 = DEFAULT_DEMAND_REGIME_CONFIG_V1,
    raw_demand_path: str | Path | None = None,
) -> DemandRegimeReviewV1:
    """Load, derive, and segment a V3 workbook without running a solver."""

    path = Path(input_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    imported = import_v3_multi_period_workbook_v1(path)
    selected_profile = profile_id or imported.multi_period_demand.default_profile_id
    if selected_profile is None or not selected_profile.strip():
        raise ValueError("No demand profile was selected and the workbook has no default profile")
    derivation = derive_demand_profile_v1(
        imported.multi_period_demand,
        selected_profile.strip(),
    )
    normalized = normalize_multi_period_profile_v1(
        imported.base_workbook,
        imported.multi_period_demand,
        derivation.profile,
        _normalization_options(path, imported),
    )
    raw_path: Path | None = None
    raw_import: RawDailyDemandImportResultV1 | None = None
    raw_route: RawDailyDemandRouteV1 | None = None
    reconciliation: RawDemandReconciliationV1 | None = None
    daily_observations = ()
    observed_dates = None
    if raw_demand_path is not None:
        raw_path = Path(raw_demand_path).expanduser().resolve()
        period_lookup = {item.period_id: item for item in imported.multi_period_demand.periods}
        included_periods = tuple(
            period_lookup[item] for item in derivation.profile.included_period_ids
        )
        raw_import = import_t06_t10_daily_demand_v1(
            raw_path,
            derivation.profile,
            period_start=min(item.period_start for item in included_periods),
            period_end=max(item.period_end for item in included_periods),
            route_ids=(normalized.scenario_b.route_id,),
        )
        raw_route = next(
            (item for item in raw_import.routes if item.route_id == normalized.scenario_b.route_id),
            None,
        )
        if raw_route is None:
            raise ValueError(
                f"Raw demand source does not contain route {normalized.scenario_b.route_id}"
            )
        reconciliation = reconcile_raw_daily_demand_v1(
            raw_route,
            derivation.profile,
        )
        daily_observations = raw_route.daily_observations
        observed_dates = raw_route.observed_dates
    model_selection = select_demand_regime_model_v1(
        derivation.profile,
        daily_observations,
        config,
        scenario_b=normalized.scenario_b,
        observed_dates=observed_dates,
    )
    return DemandRegimeReviewV1(
        input_path=path,
        route_id=normalized.scenario_b.route_id,
        route_name=normalized.scenario_b.route_name,
        model_selection=model_selection,
        demand_observations=derivation.profile.derived_observations,
        source_period_observation_days=derivation.profile.total_observation_days,
        scenario_b=normalized.scenario_b,
        raw_source_path=raw_path,
        raw_import=raw_import,
        raw_route=raw_route,
        reconciliation=reconciliation,
    )


def demand_regime_review_to_dict_v1(review: DemandRegimeReviewV1) -> dict[str, object]:
    model_selection = demand_regime_model_selection_to_dict_v1(review.model_selection)
    raw_source: dict[str, object] | None = None
    if review.raw_import is not None and review.raw_route is not None:
        raw_source = {
            "source_file": review.raw_import.source_file,
            "source_sha256": review.raw_import.source_sha256,
            "sheet_name": review.raw_import.sheet_name,
            "sheet_row_count": review.raw_import.sheet_row_count,
            "sheet_column_count": review.raw_import.sheet_column_count,
            "source_minimum_date": review.raw_import.source_minimum_date.isoformat(),
            "source_maximum_date": review.raw_import.source_maximum_date.isoformat(),
            "source_route_ids": list(review.raw_import.source_route_ids),
            "selected_period_start": review.raw_import.selected_period_start.isoformat(),
            "selected_period_end": review.raw_import.selected_period_end.isoformat(),
            "raw_time_granularity_seconds": review.raw_import.raw_time_granularity_seconds,
            "unknown_direction_row_count": review.raw_import.unknown_direction_row_count,
            "route_id": review.raw_route.route_id,
            "route_names": list(review.raw_route.route_names),
            "observed_dates": [item.isoformat() for item in review.raw_route.observed_dates],
            "direction_audits": [
                raw_daily_demand_to_dict_v1(item) for item in review.raw_route.direction_audits
            ],
        }
    return {
        "review_profile": DEMAND_REGIME_REVIEW_PROFILE_V1,
        "input_file": review.input_path.name,
        "route_id": review.route_id,
        "route_name": review.route_name,
        "demand_semantics": review.model_selection.scope.value,
        "source_period_observation_days": review.source_period_observation_days,
        "raw_daily_source": raw_source,
        "raw_v3_reconciliation": (
            raw_daily_demand_to_dict_v1(review.reconciliation)
            if review.reconciliation is not None
            else None
        ),
        "model_selection": model_selection,
    }


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6f}"


def render_demand_regime_review_markdown_v1(review: DemandRegimeReviewV1) -> str:
    result = review.model_selection
    lines = [
        f"# Demand regime review: route {review.route_id}",
        "",
        f"- Route: {review.route_name}",
        f"- Input: `{review.input_path.name}`",
        f"- Demand profile: `{result.demand_profile_id}`",
        f"- Demand semantics: `{result.scope.value}`",
        f"- Status: `{result.status.value}`",
        "- Candidate algorithm: exact-K normalized duration-weighted SSE dynamic programming",
        "- Selection method: deterministic leave-one-day-out cross-validation + "
        "one-standard-error rule",
        "- Tie-break: lower fit error within epsilon; then fewer regimes; then "
        "lexicographically earlier canonical boundaries",
        "- Interval contract: every demand regime is `[start, end)`; boundaries are "
        "policy changes, not mandatory departures",
        f"- Configuration: target_min_regime_minutes="
        f"{result.config.target_min_regime_minutes}, "
        f"min_validation_days={result.config.min_validation_days}, "
        f"cost_tie_epsilon={result.config.cost_tie_epsilon}, "
        f"legacy_complexity_penalty_diagnostic={result.config.complexity_penalty}",
        f"- Source periods represent **{review.source_period_observation_days}** days, but "
        "only date-keyed daily profiles count as observed validation days.",
    ]
    if review.raw_import is not None and review.raw_route is not None:
        lines.extend(
            [
                "",
                "## RAW DAILY DEMAND AUDIT",
                "",
                f"- Source: `{review.raw_import.source_file}`",
                f"- Sheet: `{review.raw_import.sheet_name}` "
                f"({review.raw_import.sheet_row_count:,} data rows × "
                f"{review.raw_import.sheet_column_count} columns)",
                f"- Full source date range: {review.raw_import.source_minimum_date.isoformat()} "
                f"to {review.raw_import.source_maximum_date.isoformat()}",
                f"- Routes found: {', '.join(review.raw_import.source_route_ids)}",
                f"- Selected raw period: {review.raw_import.selected_period_start.isoformat()} "
                f"to {review.raw_import.selected_period_end.isoformat()}",
                f"- Raw departure-time granularity: "
                f"{review.raw_import.raw_time_granularity_seconds // 60} minute(s)",
                "- Demand grain: trip-level `date × route × explicit Hướng đi × "
                "departure time × Tổng vé`.",
                "- Demand time: `Giờ đi HT`; deterministic fallback to `Giờ đi KH`.",
                "- Direction: exact route-specific `Hướng đi` and `Đầu bến` evidence; "
                "Scenario B departure times are not used.",
                "- Empty canonical buckets are observed zero only on dates whose complete "
                "trip-row manifest matches the raw modal daily count.",
                f"- Evidence status: `{'DAILY_VALIDATED' if result.status == RegimeModelSelectionStatusV1.SUCCESS else 'NOT_DAILY_VALIDATED'}`",
                "",
                "| Direction | Raw rows | Raw dates | Expected trips/day | Complete | "
                "Incomplete | Source duplicates | Invalid demand/time | Fallback | "
                "Off-grid | Multirow bucket groups | Observed-zero buckets |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for audit in review.raw_route.direction_audits:
            lines.append(
                f"| {audit.direction.value} | {audit.raw_row_count} | "
                f"{audit.raw_date_count} | "
                f"{audit.expected_trip_rows_per_complete_date or 'n/a'} | "
                f"{audit.complete_date_count} | {len(audit.incomplete_dates)} | "
                f"{audit.duplicate_source_row_count} | "
                f"{audit.invalid_demand_row_count}/{audit.invalid_time_row_count} | "
                f"{audit.fallback_to_planned_time_row_count} | "
                f"{audit.off_grid_row_count} | {audit.multirow_bucket_group_count} | "
                f"{audit.observed_zero_bucket_count} |"
            )
        if review.reconciliation is not None:
            lines.extend(
                [
                    "",
                    "### Raw-to-V3 reconciliation",
                    "",
                    f"Compared buckets: **{review.reconciliation.compared_bucket_count}**",
                    f"Maximum absolute difference: "
                    f"**{review.reconciliation.maximum_absolute_difference:.12f}**",
                    f"Maximum relative difference: "
                    f"**{review.reconciliation.maximum_relative_difference:.12%}**",
                    f"Buckets outside reconciliation epsilon: "
                    f"**{review.reconciliation.mismatched_bucket_count}**",
                ]
            )
    lines.extend(
        [
            "",
            "## Demand coverage",
            "",
            "| Direction | Service window | Grid | Observed / expected | Coverage |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for item in result.coverage:
        service_window = (
            f"{format_hhmm(item.service_start)}–{format_hhmm(item.service_end)}"
            if item.service_start is not None and item.service_end is not None
            else "n/a"
        )
        lines.append(
            f"| {item.direction.value} | {service_window} | "
            f"{item.bucket_granularity_minutes or 'n/a'} min | "
            f"{item.observed_bucket_count} / {item.expected_bucket_count or 'n/a'} | "
            f"{item.coverage_ratio:.1%} |"
        )
    if result.status == RegimeModelSelectionStatusV1.INSUFFICIENT_DEMAND_COVERAGE:
        lines.extend(
            [
                "",
                f"Failure: `{result.failure_code}` — {result.failure_message}",
                "",
            ]
        )
        return "\n".join(lines)

    for selection in result.selections:
        lines.extend(
            [
                "",
                f"## REGIME MODEL SELECTION — {selection.direction.value}",
                "",
                "Method: **Leave-one-day-out cross-validation + one-standard-error rule**",
                f"Selection status: `{selection.selection_status.value}`",
                f"Observed date-keyed days: **{selection.total_observed_days}**",
                f"Eligible folds: **{selection.eligible_validation_days}**",
                f"Excluded days: **{len(selection.excluded_days)}**",
                f"Natural maximum K: **{selection.natural_max_regimes}**",
                "Legacy penalty-selected K (diagnostic only): "
                f"**{selection.legacy_penalty_selected_regime_count}**",
                "",
                "| K | Full fit | CV mean | CV SE | Folds | Within 1-SE | Boundaries |",
                "|---:|---:|---:|---:|---:|:---:|---|",
            ]
        )
        candidates = {item.regime_count: item for item in selection.candidate_frontier.candidates}
        for score in selection.model_scores:
            boundaries = (
                ", ".join(format_hhmm(item) for item in candidates[score.regime_count].boundaries)
                or "n/a"
            )
            within = (
                "YES"
                if score.within_one_se is True
                else "NO"
                if score.within_one_se is False
                else "n/a"
            )
            lines.append(
                f"| {score.regime_count} | {score.full_data_fit_error:.6f} | "
                f"{_number(score.mean_validation_error)} | "
                f"{_number(score.validation_standard_error)} | "
                f"{score.eligible_fold_count} | {within} | {boundaries} |"
            )
        if selection.excluded_days:
            lines.extend(
                [
                    "",
                    "### Excluded daily profiles",
                    "",
                    "| Date | Reason | Observed / expected | Coverage | Missing intervals |",
                    "|---|---|---:|---:|---|",
                ]
            )
            for item in selection.excluded_days:
                missing = (
                    ", ".join(
                        f"{format_hhmm(start)}–{format_hhmm(end)}"
                        for start, end in item.missing_intervals
                    )
                    or "n/a"
                )
                lines.append(
                    f"| {item.observation_date.isoformat()} | `{item.reason_code}` | "
                    f"{item.observed_bucket_count} / {item.expected_bucket_count} | "
                    f"{item.coverage_ratio:.1%} | {missing} |"
                )
        if selection.selection_status != RegimeModelSelectionStatusV1.SUCCESS:
            lines.extend(
                [
                    "",
                    f"Failure: `{selection.failure_code}` — {selection.failure_message}",
                    "",
                    "No predictive-best K, one-SE-selected K, final boundaries, or final "
                    "RegimePlan is published because the workbook does not contain enough "
                    "date-keyed daily demand profiles.",
                ]
            )
            continue
        lines.extend(
            [
                "",
                f"Best predictive K: **{selection.best_validation_regime_count}**",
                f"Best CV mean: **{_number(selection.best_mean_validation_error)}**",
                f"Best CV SE: **{_number(selection.best_standard_error)}**",
                f"One-SE threshold: **{_number(selection.one_se_threshold)}**",
                f"Selected simplest credible K: **{selection.selected_regime_count}**",
            ]
        )
        plan = selection.final_plan
        if plan is None:  # pragma: no cover - success contract invariant
            raise AssertionError("successful model selection requires a final plan")
        lines.extend(
            [
                "",
                f"## FINAL REGIMES — {selection.direction.value}",
                "",
                "| Regime | Start | End | Duration | Buckets | Demand mean | Demand share | "
                "B trips | B median headway | B max headway |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for regime in plan.regimes:
            lines.append(
                f"| {regime.regime_id} | {format_hhmm(regime.start_time)} | "
                f"{format_hhmm(regime.end_time)} | {regime.duration_minutes} min | "
                f"{regime.bucket_count} | {regime.demand_mean:.2f} | "
                f"{regime.demand_share:.1%} | {regime.current_b_trip_count} | "
                f"{regime.current_b_median_headway if regime.current_b_median_headway is not None else 'n/a'} | "
                f"{regime.current_b_max_headway if regime.current_b_max_headway is not None else 'n/a'} |"
            )
        if plan.current_b_exact_timetable_trip_count is not None:
            lines.extend(
                [
                    "",
                    "Scenario B half-open reconciliation: "
                    f"regimes={plan.current_b_regime_trip_count}, "
                    f"service-window total={plan.current_b_service_window_trip_count}, "
                    f"exact directional timetable total={plan.current_b_exact_timetable_trip_count}, "
                    f"outside service-demand window="
                    f"{plan.current_b_outside_service_window_trip_count}, "
                    f"reconciled={'yes' if plan.current_b_service_window_reconciled else 'no'}.",
                ]
            )
        lines.extend(
            [
                "",
                f"## BOUNDARY STABILITY — {selection.direction.value}",
                "",
                "| Boundary | Exact support | ±1 bucket support |",
                "|---:|---:|---:|",
            ]
        )
        final_stability = [item for item in selection.boundary_stability if item.is_final_boundary]
        if not final_stability:
            lines.append("| n/a | n/a | n/a |")
        for item in final_stability:
            lines.append(
                f"| {format_hhmm(item.boundary_time)} | "
                f"{item.exact_support_count}/{item.eligible_fold_count} "
                f"({item.exact_boundary_frequency:.1%}) | "
                f"{item.neighbor_support_count}/{item.eligible_fold_count} "
                f"({item.neighbor_boundary_frequency:.1%}) |"
            )
    lines.extend(
        [
            "",
            "> Scenario B statistics are review evidence only and do not affect segmentation.",
            "",
        ]
    )
    return "\n".join(lines)


def build_demand_regime_figure_v1(review: DemandRegimeReviewV1) -> go.Figure:
    selections = review.model_selection.selections
    if not selections:
        return go.Figure()
    figure = make_subplots(
        rows=len(selections),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[item.direction.value for item in selections],
    )
    colors = ("rgba(31,119,180,0.10)", "rgba(255,127,14,0.10)")
    for row, selection in enumerate(selections, start=1):
        plan = selection.final_plan
        observations = sorted(
            (item for item in review.demand_observations if item.direction == selection.direction),
            key=lambda item: (item.interval_start, item.interval_end),
        )
        figure.add_trace(
            go.Scatter(
                x=[(item.interval_start + item.interval_end) / 7200 for item in observations],
                y=[item.average_daily_passengers for item in observations],
                mode="lines+markers",
                name=f"{selection.direction.value} demand",
            ),
            row=row,
            col=1,
        )
        for index, regime in enumerate(plan.regimes if plan is not None else ()):
            figure.add_vrect(
                x0=regime.start_time / 3600,
                x1=regime.end_time / 3600,
                fillcolor=colors[index % len(colors)],
                line_width=0,
                row=row,
                col=1,
            )
    figure.update_layout(
        title=f"Route {review.route_id} deterministic demand regimes",
        xaxis_title="Service-day hour",
        yaxis_title="Average daily passengers per bucket",
        template="plotly_white",
        height=max(420, 320 * len(selections)),
    )
    return figure


def write_demand_regime_review_v1(
    review: DemandRegimeReviewV1,
    output_directory: str | Path,
) -> tuple[Path, Path, Path]:
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"route_{review.route_id}_demand_regimes.json"
    markdown_path = output / f"route_{review.route_id}_demand_regimes.md"
    html_path = output / f"route_{review.route_id}_demand_regimes.html"
    json_path.write_text(
        json.dumps(
            demand_regime_review_to_dict_v1(review),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_demand_regime_review_markdown_v1(review),
        encoding="utf-8",
    )
    build_demand_regime_figure_v1(review).write_html(
        html_path,
        include_plotlyjs="cdn",
        full_html=True,
    )
    return json_path, markdown_path, html_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect and review demand regimes without running a timetable solver.",
    )
    parser.add_argument("--input", required=True, type=Path, action="append")
    parser.add_argument("--raw-demand", type=Path)
    parser.add_argument("--profile")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--target-min-regime-minutes", type=int, default=90)
    parser.add_argument("--complexity-penalty", type=float, default=0.05)
    parser.add_argument("--cost-tie-epsilon", type=float, default=1e-12)
    parser.add_argument("--min-validation-days", type=int, default=7)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = DemandRegimeDetectorConfigV1(
            target_min_regime_minutes=args.target_min_regime_minutes,
            complexity_penalty=args.complexity_penalty,
            cost_tie_epsilon=args.cost_tie_epsilon,
            min_validation_days=args.min_validation_days,
        )
        for input_path in args.input:
            review = build_v3_demand_regime_review_v1(
                input_path,
                profile_id=args.profile,
                config=config,
                raw_demand_path=args.raw_demand,
            )
            paths = write_demand_regime_review_v1(review, args.output_dir)
            print(
                f"route {review.route_id}: {review.model_selection.status.value}; "
                f"directions={len(review.model_selection.selections)} -> {paths[1].name}"
            )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Demand regime review failed: {exc}", file=sys.stderr)
        return 2
    return 0


__all__ = [
    "DEMAND_REGIME_REVIEW_PROFILE_V1",
    "DemandRegimeReviewV1",
    "build_demand_regime_figure_v1",
    "build_v3_demand_regime_review_v1",
    "demand_regime_review_to_dict_v1",
    "main",
    "render_demand_regime_review_markdown_v1",
    "write_demand_regime_review_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())

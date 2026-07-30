"""Pure, fail-closed Contract V1 artifacts for Streamlit Page 05."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from pathlib import Path

import plotly
import plotly.io as pio

from .unified_diagram import (
    build_unified_demand_supply_figure_for_direction_v1,
    build_unified_departure_figure_v1,
)
from .unified_presentation import (
    PRESENTATION_MODE_VALIDATION_ONLY,
    UnifiedPresentationBundleV1,
    UnifiedPresentationConsistencyError,
    verify_unified_presentation_integrity_v1,
)
from .unified_result_exporter import read_unified_export_metadata_bytes_v1

UNIFIED_PAGE5_XLSX_FILENAME = "Bus_Schedule_Contract_V1_Result.xlsx"
UNIFIED_PAGE5_HTML_FILENAME = "Bus_Schedule_Contract_V1_Charts.html"
UNIFIED_PAGE5_PNG_FILENAME = "Bus_Schedule_Contract_V1_Overview.png"

_OVERVIEW_DIV_ID = "contract-v1-demand-supply"
_DEPARTURE_DIV_ID = "contract-v1-departures"
_PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
}


class UnifiedPage5ArtifactError(ValueError):
    """The aligned unified Page 05 bundle could not be built safely."""


class UnifiedPage5SemanticIntegrityError(UnifiedPage5ArtifactError):
    """Stored Page 05 evidence does not align with the verified presentation."""


@dataclass(frozen=True, slots=True)
class UnifiedPage5ArtifactsV1:
    selected_direction: str
    demand_supply_figure: object
    departure_figure: object
    xlsx_bytes: bytes
    html_bytes: bytes
    png_bytes: bytes
    presentation_fingerprint: str
    b_fingerprint: str
    accepted_solution_fingerprint: str | None
    xlsx_filename: str
    html_filename: str
    png_filename: str


def _figure_metadata(figure: object) -> Mapping[str, object]:
    try:
        metadata = figure.layout.meta
    except (AttributeError, TypeError) as exc:
        raise UnifiedPage5SemanticIntegrityError("stored unified figure has no metadata") from exc
    if isinstance(metadata, Mapping):
        return metadata
    try:
        return dict(metadata)
    except (TypeError, ValueError) as exc:
        raise UnifiedPage5SemanticIntegrityError(
            "stored unified figure metadata is malformed"
        ) from exc


def _verify_stored_figure(
    presentation: UnifiedPresentationBundleV1,
    figure: object,
    *,
    artifact_name: str,
) -> None:
    metadata = _figure_metadata(figure)
    expected = {
        "presentation_mode": presentation.presentation_mode,
        "presentation_fingerprint": presentation.presentation_fingerprint,
        "source_b_fingerprint": presentation.source_b_fingerprint,
        "accepted_solution_fingerprint": presentation.accepted_solution_fingerprint,
        "accepted_c_exists": presentation.outcome.accepted_c_exists,
        "scenario_c_authority": presentation.outcome.accepted_c_authority,
        "cutover_blocked": presentation.cutover_blocked,
        "blocking_discrepancy_codes": list(presentation.blocking_discrepancy_codes),
        "expert_review_required_codes": list(presentation.expert_review_required_codes),
        "demand_grain": "EXACT_CONTRACT_BLOCKS_NO_AGGREGATION",
    }
    mismatches = sorted(
        key for key, expected_value in expected.items() if metadata.get(key) != expected_value
    )
    if mismatches:
        raise UnifiedPage5SemanticIntegrityError(
            f"{artifact_name} metadata does not align with presentation: {mismatches}"
        )


def _verify_stored_departure_figure_contents(
    stored_departure_figure: object,
    canonical_departure_figure: object,
) -> None:
    try:
        stored_json = stored_departure_figure.to_plotly_json()
        canonical_json = canonical_departure_figure.to_plotly_json()
    except (AttributeError, TypeError, ValueError) as exc:
        raise UnifiedPage5SemanticIntegrityError(
            "stored departure figure contents cannot be verified"
        ) from exc
    if stored_json != canonical_json:
        raise UnifiedPage5SemanticIntegrityError(
            "stored departure figure contents do not match the verified presentation"
        )


def _verify_accepted_c_shape(presentation: UnifiedPresentationBundleV1) -> None:
    accepted_fingerprint = presentation.accepted_solution_fingerprint
    outcome = presentation.outcome
    scenario_c = presentation.scenario("C")
    if accepted_fingerprint is None:
        c_fields = (
            "c_actual_trip_count",
            "c_nominal_capacity",
            "c_load_factor",
            "c_shortage",
            "c_status",
            "c_allocation_reason",
        )
        has_c_block_fact = any(
            getattr(block, field_name) is not None
            for block in presentation.blocks
            for field_name in c_fields
        )
        if (
            outcome.accepted_c_exists
            or outcome.accepted_c_authority is not None
            or scenario_c is not None
            or presentation.initial_fleet is not None
            or presentation.fleet_assignments
            or presentation.headway_regimes
            or has_c_block_fact
        ):
            raise UnifiedPage5SemanticIntegrityError(
                "accepted-C facts must remain absent without an accepted-C fingerprint"
            )
        return

    if not (
        outcome.accepted_c_exists
        and outcome.accepted_c_authority
        and outcome.accepted_solution_fingerprint == accepted_fingerprint
        and scenario_c is not None
        and scenario_c.source_fingerprint == accepted_fingerprint
    ):
        raise UnifiedPage5SemanticIntegrityError(
            "accepted-C facts do not align with the accepted fingerprint"
        )


def _escape_text(value: object) -> str:
    return escape(str(value), quote=True)


def _build_html_bytes(
    presentation: UnifiedPresentationBundleV1,
    demand_supply_figure: object,
    departure_figure: object,
    *,
    selected_direction: str,
) -> bytes:
    overview_html = pio.to_html(
        demand_supply_figure,
        config=_PLOTLY_CONFIG,
        auto_play=False,
        include_plotlyjs="inline",
        full_html=False,
        div_id=_OVERVIEW_DIV_ID,
        validate=True,
    )
    departure_html = pio.to_html(
        departure_figure,
        config=_PLOTLY_CONFIG,
        auto_play=False,
        include_plotlyjs=False,
        full_html=False,
        div_id=_DEPARTURE_DIV_ID,
        validate=True,
    )
    accepted_fingerprint = (
        presentation.accepted_solution_fingerprint
        if presentation.accepted_solution_fingerprint is not None
        else "Không có Scenario C được chấp nhận"
    )
    expert_codes = "".join(
        f"<li><code>{_escape_text(code)}</code></li>"
        for code in presentation.expert_review_required_codes
    )
    expert_status = (
        "Yêu cầu chuyên gia rà soát"
        if presentation.requires_expert_review
        else "Không có mã bắt buộc chuyên gia rà soát"
    )
    departure_heading = (
        "Giờ xuất bến A/B và Scenario C được chấp nhận"
        if presentation.outcome.accepted_c_exists
        else "Giờ xuất bến A/B; không có Scenario C được chấp nhận"
    )
    document = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contract V1 · {_escape_text(presentation.route_id)}</title>
<style>
body{{font-family:Arial,sans-serif;margin:24px;color:#172033}}
main{{max-width:1600px;margin:0 auto}}
dt{{font-weight:700}}dd{{margin:0 0 8px}}
.notice{{padding:12px 16px;background:#fff4ce;border-left:4px solid #c47f00}}
code{{overflow-wrap:anywhere}}
</style>
</head>
<body>
<main>
<h1>Biểu đồ xác thực Contract V1</h1>
<p><strong>Tuyến:</strong> {_escape_text(presentation.route_id)} · {_escape_text(presentation.route_name)}</p>
<dl>
<dt>Chế độ trình bày</dt><dd>{_escape_text(presentation.presentation_mode)}</dd>
<dt>Chiều block hiển thị</dt><dd>{_escape_text(selected_direction)} · EXACT_DIRECTION_SUBSET</dd>
<dt>Presentation fingerprint</dt><dd><code>{_escape_text(presentation.presentation_fingerprint)}</code></dd>
<dt>Normalized-B fingerprint</dt><dd><code>{_escape_text(presentation.source_b_fingerprint)}</code></dd>
<dt>Accepted-C fingerprint</dt><dd><code>{_escape_text(accepted_fingerprint)}</code></dd>
<dt>Trạng thái cutover</dt><dd>Không bị chặn</dd>
<dt>Trạng thái rà soát</dt><dd>{_escape_text(expert_status)}</dd>
</dl>
<ul>{expert_codes}</ul>
<p class="notice">Kết quả này là bằng chứng xác thực phục vụ chuyên gia rà soát; không phải phê duyệt khai thác.</p>
<section>
<h2>Đối chiếu nhu cầu và số chuyến theo block chính xác</h2>
{overview_html}
</section>
<section>
<h2>{_escape_text(departure_heading)}</h2>
{departure_html}
</section>
</main>
</body>
</html>
"""
    return document.encode("utf-8")


def _build_png_bytes(demand_supply_figure: object) -> bytes:
    source = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    target = Path(tempfile.gettempdir()) / "bus_schedule_contract_v1_plotly.min.js"
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copyfile(source, target)
    pio.kaleido.scope.plotlyjs = str(target)
    content = pio.to_image(
        demand_supply_figure,
        format="png",
        width=1600,
        height=900,
        scale=1,
        validate=True,
        engine="kaleido",
    )
    if not isinstance(content, bytes) or not content:
        raise UnifiedPage5ArtifactError("PNG renderer returned no bytes")
    return content


def build_unified_page5_artifacts_v1(
    presentation: UnifiedPresentationBundleV1,
    stored_demand_supply_figure: object,
    stored_departure_figure: object,
    xlsx_bytes: bytes,
    *,
    selected_direction: str,
) -> UnifiedPage5ArtifactsV1:
    """Build one all-or-nothing Page 05 bundle from aligned stored evidence."""
    try:
        if not isinstance(presentation, UnifiedPresentationBundleV1):
            raise TypeError("presentation must be a UnifiedPresentationBundleV1")
        if not isinstance(xlsx_bytes, bytes):
            raise TypeError("xlsx_bytes must be bytes")
        verify_unified_presentation_integrity_v1(presentation)
        if presentation.presentation_mode != PRESENTATION_MODE_VALIDATION_ONLY:
            raise UnifiedPage5SemanticIntegrityError(
                "presentation mode must remain VALIDATION_ONLY"
            )
        if presentation.cutover_blocked or presentation.blocking_discrepancy_codes:
            raise UnifiedPage5SemanticIntegrityError(
                "blocking discrepancies prohibit unified Page 05"
            )
        _verify_accepted_c_shape(presentation)
        canonical_departure_figure = build_unified_departure_figure_v1(presentation)
        _verify_stored_figure(
            presentation,
            stored_demand_supply_figure,
            artifact_name="stored demand/supply figure",
        )
        _verify_stored_figure(
            presentation,
            stored_departure_figure,
            artifact_name="stored departure figure",
        )
        _verify_stored_departure_figure_contents(
            stored_departure_figure,
            canonical_departure_figure,
        )

        try:
            workbook_metadata = read_unified_export_metadata_bytes_v1(xlsx_bytes)
        except Exception as exc:
            raise UnifiedPage5SemanticIntegrityError(
                "stored unified XLSX metadata cannot be verified"
            ) from exc
        expected_workbook_metadata = {
            "presentation_fingerprint": presentation.presentation_fingerprint,
            "b_fingerprint": presentation.source_b_fingerprint,
            "accepted_solution_fingerprint": presentation.accepted_solution_fingerprint,
            "source_id": presentation.source_id,
            "presentation_mode": PRESENTATION_MODE_VALIDATION_ONLY,
            "cutover_blocked": False,
        }
        workbook_mismatches = sorted(
            key
            for key, expected in expected_workbook_metadata.items()
            if getattr(workbook_metadata, key) != expected
        )
        if workbook_mismatches:
            raise UnifiedPage5SemanticIntegrityError(
                f"unified XLSX metadata does not align with presentation: {workbook_mismatches}"
            )

        selected_figure = build_unified_demand_supply_figure_for_direction_v1(
            presentation,
            selected_direction,
        )
        html_bytes = _build_html_bytes(
            presentation,
            selected_figure,
            canonical_departure_figure,
            selected_direction=selected_direction,
        )
        png_bytes = _build_png_bytes(selected_figure)
    except UnifiedPage5ArtifactError:
        raise
    except UnifiedPresentationConsistencyError as exc:
        raise UnifiedPage5SemanticIntegrityError(str(exc)) from exc
    except Exception as exc:
        raise UnifiedPage5ArtifactError(
            f"unified Page 05 artifact construction failed: {exc}"
        ) from exc

    return UnifiedPage5ArtifactsV1(
        selected_direction=selected_direction,
        demand_supply_figure=selected_figure,
        departure_figure=canonical_departure_figure,
        xlsx_bytes=xlsx_bytes,
        html_bytes=html_bytes,
        png_bytes=png_bytes,
        presentation_fingerprint=presentation.presentation_fingerprint,
        b_fingerprint=presentation.source_b_fingerprint,
        accepted_solution_fingerprint=presentation.accepted_solution_fingerprint,
        xlsx_filename=UNIFIED_PAGE5_XLSX_FILENAME,
        html_filename=UNIFIED_PAGE5_HTML_FILENAME,
        png_filename=UNIFIED_PAGE5_PNG_FILENAME,
    )


__all__ = [
    "UNIFIED_PAGE5_HTML_FILENAME",
    "UNIFIED_PAGE5_PNG_FILENAME",
    "UNIFIED_PAGE5_XLSX_FILENAME",
    "UnifiedPage5ArtifactError",
    "UnifiedPage5ArtifactsV1",
    "UnifiedPage5SemanticIntegrityError",
    "build_unified_page5_artifacts_v1",
]

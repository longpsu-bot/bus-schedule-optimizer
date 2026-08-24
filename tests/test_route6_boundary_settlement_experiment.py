from __future__ import annotations

import importlib.util
import json
import sys
from datetime import time
from pathlib import Path

from openpyxl import Workbook


def _load_experiment_module():
    path = Path(__file__).parents[1] / "scripts/route6_boundary_settlement_experiment.py"
    spec = importlib.util.spec_from_file_location("route6_boundary_settlement_experiment", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


experiment = _load_experiment_module()


def _seconds(hour: int, minute: int) -> int:
    return (hour * 60 + minute) * 60


def test_residual_detection_and_deterministic_strict_enumeration() -> None:
    human = tuple(
        _seconds(hour, minute)
        for hour, minute in (
            (16, 52),
            (17, 0),
            (17, 8),
            (17, 16),
            (17, 30),
            (17, 45),
            (18, 0),
            (18, 15),
        )
    )
    residuals = experiment.detect_settlement_residuals(human)
    assert len(residuals) == 1
    assert (
        residuals[0].left_headway,
        residuals[0].residual_gap,
        residuals[0].right_headway,
    ) == (8, 14, 15)

    first = experiment.enumerate_strict_local_candidates(
        left_anchor=human[0],
        right_anchor=human[-1],
        gap_count=7,
        h_left=8,
        h_right=15,
    )
    second = experiment.enumerate_strict_local_candidates(
        left_anchor=human[0],
        right_anchor=human[-1],
        gap_count=7,
        h_left=8,
        h_right=15,
    )
    assert first == second
    assert not [item for item in first if item.family == "TWO_RHYTHM"]
    expected_gaps = (8, 10, 10, 10, 15, 15, 15)
    expected = next(item for item in first if item.gaps == expected_gaps)
    assert expected.departures[0] == human[0]
    assert expected.departures[-1] == human[-1]
    assert len(expected.gaps) == 7
    assert expected.bridge_gap_count == 3
    assert expected.bridge_gap_count != 1
    assert len({item.departures for item in first}) == len(first)


def test_reference_labels_never_claim_project_engine_lineage() -> None:
    assert experiment.REFERENCE_LABELS == ("CURRENT", "EXTERNAL_AI", "HUMAN_FINAL")
    serialized = json.dumps({"labels": experiment.REFERENCE_LABELS})
    assert "EXTERNAL_AI" in serialized
    assert "ENGINE_AI" not in serialized
    assert "OUR_AI" not in serialized
    assert "SCENARIO_C_FROM_ENGINE" not in serialized


def test_discovered_workbook_layout_parses_explicit_direction_columns(tmp_path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    before = [295 + (1010 - 295) * index // 59 for index in range(60)]
    witness_minutes = [1020, 1028, 1036, 1050, 1065, 1080]
    after = [1095 + (1260 - 1095) * index // 11 for index in range(12)]
    departures = before + witness_minutes + after
    assert len(departures) == 78
    assert departures == sorted(set(departures))
    for sheet_name in ("06 hiện hữu", "06 AI", "06 final"):
        sheet = workbook.create_sheet(sheet_name)
        sheet["B4"] = "Đi BX buýt Chợ Lớn"
        sheet["F4"] = "Đi ĐH Nông Lâm"
        for minute, row in zip(departures, range(5, 83), strict=True):
            value = time(minute // 60, minute % 60)
            sheet[f"B{row}"] = value
            sheet[f"F{row}"] = value
    path = tmp_path / "reference.xlsx"
    workbook.save(path)

    parsed = experiment.parse_route6_reference_workbook(path)
    assert parsed["reference_sheet_names"] == {
        "CURRENT": "06 hiện hữu",
        "EXTERNAL_AI": "06 AI",
        "HUMAN_FINAL": "06 final",
    }
    assert len(parsed["references"]["CURRENT"]["outbound"]) == 78

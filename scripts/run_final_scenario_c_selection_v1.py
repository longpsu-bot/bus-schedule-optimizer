"""Build the immutable-evidence final Scenario C selection manifest."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = (
    _REPO_ROOT / "src" / "bus_schedule_engine" / "contracts_v1" / "final_scenario_c_selection.py"
)
_SPEC = importlib.util.spec_from_file_location("final_scenario_c_selection_v1", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load final selector from {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
build_final_selection_manifest = _MODULE.build_final_selection_manifest

_DEFAULT_OUTPUT = (
    _REPO_ROOT
    / "outputs"
    / "final_scenario_c_selection_v1_20260821"
    / "selection_product_manifest_v1.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    payload = build_final_selection_manifest(args.repo_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    for route in ("6", "10"):
        selected = payload["product_routes"][route]["selected"]
        print(
            f"route {route}: {selected['candidate_pair']} "
            f"fleet={selected['fleet_required']} "
            f"mismatch={selected['combined_demand_mismatch']}"
        )
    print(f"selection manifest -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

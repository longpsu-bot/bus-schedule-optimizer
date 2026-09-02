"""Run deterministic demand regime review for one or more V3 workbooks."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bus_schedule_engine.demand_regime_review import main  # noqa: E402, I001


if __name__ == "__main__":
    raise SystemExit(main())

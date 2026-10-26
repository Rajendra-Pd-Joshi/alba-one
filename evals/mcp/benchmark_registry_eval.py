"""Per-server MCP Evaluation Script for `benchmark_registry` (`evals/mcp/benchmark_registry_eval.py`).

Usage:
  uv run python evals/mcp/benchmark_registry_eval.py --allow-draft
"""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[2]
_BOOTSTRAP = _ROOT / "apps" / "api" / "tests" / "unit" / "_bootstrap.py"
if _BOOTSTRAP.is_file():
    exec(_BOOTSTRAP.read_text(encoding="utf-8"), {"__file__": str(_BOOTSTRAP)})
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evals.mcp.engine import run_server_eval_cli


if __name__ == "__main__":
    raise SystemExit(run_server_eval_cli("benchmark_registry"))

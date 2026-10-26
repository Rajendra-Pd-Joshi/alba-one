"""Shared Deterministic Calculator Base, Regulatory Param Loader & Unit/Locale Converter (`mcp_servers/calculators_base.py`).

Per Phase 6 User Answer 3:
- The LLM must never do arithmetic or invent numeric bounds.
- Every calculator returns a structured `CalcResult` (`value`, `low`/`base`/`high` scenario table,
  `unit`, `method`, `formula_id`, `version`, `inputs`, `assumptions`, `data_window`, `sample_size`,
  `uncertainty_range`, `status`, `disclaimer`, `warnings`).
- Legal, regulatory, tax, and safety parameters are loaded from `config/regulatory_params.yaml`
  and refuse to run (`status="parameters_not_verified"`) while `verified_by` starts with `TODO(owner)`
  or is empty.
- Explicit unit and locale conversions (`JPY`, `Asia/Tokyo` timestamps, `tonnes`, `TEU`/`FEU`, `knots`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from alba_one.kb.indexer import find_repo_root

CalcStatusType = Literal["ok", "insufficient_data", "parameters_not_verified"]

JST = timezone(timedelta(hours=9), name="Asia/Tokyo")

LEGAL_DISCLAIMER_JA = (
    "本計算結果は意思決定支援用の参考値であり、法的助言または安全保証ではありません。"
    "人事・法務・安全管理責任者の確認が必要です。"
)
LEGAL_DISCLAIMER_EN = (
    "Decision support only, not legal or safety advice; requires HR, legal, or safety owner review."
)


@dataclass(frozen=True)
class ScenarioBound:
    """Single row (`low` | `base` | `high`) in a calculator sensitivity table."""

    scenario: Literal["low", "base", "high"]
    input_summary: str
    value: float
    unit: str


@dataclass(frozen=True)
class CalcResult:
    """Canonical output of every deterministic ALBA ONE domain calculator."""

    formula_id: str
    version: str
    status: CalcStatusType
    value: float | None
    unit: str
    method: str
    inputs: dict[str, Any]
    assumptions: list[str]
    scenarios: list[ScenarioBound] = field(default_factory=list)
    data_window: str | None = None
    sample_size: int | None = None
    uncertainty_range: tuple[float, float] | None = None
    warnings: list[str] = field(default_factory=list)
    disclaimer: str = LEGAL_DISCLAIMER_EN

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary for MCP tool envelopes and the Evidence Ledger."""
        return asdict(self)


def load_regulatory_params(
    config_path: str | Path | None = None,
    *,
    verified_overrides: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Load `config/regulatory_params.yaml` and apply optional test-time `verified_by` overrides."""
    if config_path is None:
        path = find_repo_root() / "config" / "regulatory_params.yaml"
    else:
        path = Path(config_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    params: dict[str, dict[str, Any]] = dict(raw.get("parameters", {}))
    if verified_overrides:
        for k, verifier in verified_overrides.items():
            if k in params:
                params[k] = {**params[k], "verified_by": verifier}
    return params


def check_param_verified(
    param_key: str,
    params: dict[str, dict[str, Any]],
) -> tuple[bool, dict[str, Any] | None, str]:
    """Check whether `param_key` exists and has a non-TODO `verified_by` sign-off."""
    entry = params.get(param_key)
    if entry is None:
        return False, None, f"Parameter '{param_key}' not found in config/regulatory_params.yaml."
    verified_by = str(entry.get("verified_by", "")).strip()
    if not verified_by or verified_by.upper().startswith("TODO"):
        return (
            False,
            entry,
            f"Parameter '{param_key}' is unverified (verified_by='{verified_by}'). "
            "Fill in verified_by in config/regulatory_params.yaml after HR/legal/safety review.",
        )
    return True, entry, ""


# ==============================================================================
# Explicit Unit & Locale Conversion Helpers
# ==============================================================================


def convert_currency_jpy(amount: float, from_currency: str, fx_usdjpy: float = 151.45) -> float:
    """Convert `amount` in `JPY` or `USD` to `JPY` (`round(..., 2)`)."""
    cur = from_currency.upper().strip()
    if cur == "JPY":
        return round(float(amount), 2)
    if cur == "USD":
        if fx_usdjpy <= 0:
            raise ValueError("fx_usdjpy must be positive.")
        return round(float(amount) * fx_usdjpy, 2)
    raise ValueError(f"Unsupported currency '{from_currency}'. Use JPY or USD.")


def convert_mass_tonnes(value: float, from_unit: str) -> float:
    """Convert mass (`tonnes` | `t` | `kg` | `lbs`) to metric tonnes (`tonnes`)."""
    u = from_unit.lower().strip()
    if u in ("tonnes", "tonne", "t", "mt"):
        return round(float(value), 4)
    if u == "kg":
        return round(float(value) / 1000.0, 4)
    if u in ("lb", "lbs"):
        return round(float(value) * 0.00045359237, 4)
    raise ValueError(f"Unsupported mass unit '{from_unit}'.")


def convert_containers_to_teu(count: float, container_type: str = "TEU") -> float:
    """Convert container count (`TEU` = 20ft, `FEU` = 40ft = 2 TEU) to TEU."""
    kind = container_type.upper().strip()
    if kind in ("TEU", "20FT"):
        return round(float(count), 2)
    if kind in ("FEU", "40FT"):
        return round(float(count) * 2.0, 2)
    raise ValueError(f"Unsupported container unit '{container_type}'.")


def convert_speed_knots_to_kmh(knots: float) -> float:
    """Convert maritime vessel speed in knots (`kt`) to `km/h` (`1 knot = 1.852 km/h`)."""
    return round(float(knots) * 1.852, 3)


def to_asia_tokyo_iso(dt_or_iso: str | datetime) -> str:
    """Normalize a datetime or ISO-8601 string to `Asia/Tokyo` (`+09:00`)."""
    if isinstance(dt_or_iso, str):
        cleaned = dt_or_iso.strip()
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
    else:
        dt = dt_or_iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).isoformat()

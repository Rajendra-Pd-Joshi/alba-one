"""Pure i18n, glossary verification, and Asia/Tokyo locale formatting helpers (Principle 7)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TOKYO_TZ = ZoneInfo("Asia/Tokyo")

CANONICAL_GLOSSARY_PAIRS: dict[str, tuple[str, str]] = {
    "decision_os": ("意思決定OS", "Decision OS"),
    "hypothesis": ("仮説", "hypothesis"),
    "evidence": ("根拠", "evidence"),
    "confidence": ("確信度", "confidence"),
    "approval": ("承認", "approval"),
    "rejection": ("差し戻し", "rejection"),
    "outcome_review": ("成果レビュー", "outcome review"),
    "knowledge_base": ("ナレッジベース", "knowledge base"),
    "guardrail": ("ガードレール", "guardrail"),
}

CANONICAL_PILLARS: tuple[tuple[str, str], ...] = (
    ("業務の意味とデータの接続", "Business meaning and data"),
    ("業務ごとの判断支援", "Workflow-specific decision support"),
    ("結果と知識の運用", "Outcome and knowledge operations"),
)


def flatten_message_keys(obj: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten nested JSON message dictionary into dot-separated key paths."""
    items: dict[str, str] = {}
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            items.update(flatten_message_keys(value, full_key))
        else:
            items[full_key] = str(value)
    return items


def check_message_catalog_parity(
    ja_catalog: dict[str, Any],
    en_catalog: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Return `(missing_in_en, missing_in_ja)` dot-path keys between JP and EN catalogs."""
    ja_flat = flatten_message_keys(ja_catalog)
    en_flat = flatten_message_keys(en_catalog)
    missing_in_en = sorted(set(ja_flat.keys()) - set(en_flat.keys()))
    missing_in_ja = sorted(set(en_flat.keys()) - set(ja_flat.keys()))
    return missing_in_en, missing_in_ja


def verify_glossary_file(glossary_path: str | Path) -> list[str]:
    """Validate that `i18n/glossary.json` contains all verbatim terms and 3 product pillars."""
    path = Path(glossary_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    terms = data.get("terms", {})
    for key, (expected_ja, expected_en) in CANONICAL_GLOSSARY_PAIRS.items():
        actual = terms.get(key)
        if not isinstance(actual, dict):
            errors.append(f"Missing glossary term key: '{key}'")
            continue
        if actual.get("ja") != expected_ja or actual.get("en") != expected_en:
            errors.append(
                f"Glossary mismatch for '{key}': expected ({expected_ja}, {expected_en}), "
                f"got ({actual.get('ja')}, {actual.get('en')})"
            )

    pillars = data.get("pillars", [])
    actual_pillars = [(p.get("ja"), p.get("en")) for p in pillars if isinstance(p, dict)]
    for expected_pair in CANONICAL_PILLARS:
        if expected_pair not in actual_pillars:
            errors.append(f"Missing exact product pillar pair: {expected_pair}")

    return errors


def format_jpy(amount: int | float, lang: str = "ja") -> str:
    """Format a numeric amount in Japanese Yen (JPY) for `ja` or `en` locales."""
    rounded = int(round(amount))
    if lang == "ja":
        return f"¥{rounded:,}"
    return f"JPY {rounded:,}"


def format_tokyo_timestamp(dt: datetime, lang: str = "ja") -> str:
    """Format a datetime in `Asia/Tokyo` timezone according to `ja` or `en` conventions."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tokyo_dt = dt.astimezone(TOKYO_TZ)
    if lang == "ja":
        return tokyo_dt.strftime("%Y年%m月%d日 %H:%M JST")
    return tokyo_dt.strftime("%Y-%m-%d %H:%M JST")

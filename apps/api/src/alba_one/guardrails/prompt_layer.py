"""Layer 1: Prompt Guardrail (`guardrails/prompt_layer.py`).

Loads versioned bilingual prompts from `prompts/<name>/<version>.md` and verifies:
1. No leaked credentials/secrets (`AKIA...`, `sk-...`, `BEGIN PRIVATE KEY`, `xoxb-...`).
2. Mandatory hardening markers (`<retrieved_data>`, `<tool_output>`, Instruction Hierarchy).
3. Formats untrusted retrieved chunks and tool outputs inside explicit XML data tags so
   they are treated strictly as passive data, never as instructions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from alba_one.guardrails.types import GuardrailContext, GuardrailResult, build_guardrail_result
from alba_one.kb.indexer import find_repo_root

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("private_key_pem", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    ("slack_bot_token", re.compile(r"\bxoxb-[0-9]{10,}-[0-9A-Za-z-]+")),
)

REQUIRED_HARDENING_MARKERS: tuple[str, ...] = (
    "<retrieved_data>",
    "<tool_output>",
    "Instruction Hierarchy",
)


def scan_for_secrets(text: str) -> list[str]:
    """Return list of secret pattern names found in `text`."""
    found: list[str] = []
    for name, pat in _SECRET_PATTERNS:
        if pat.search(text or ""):
            found.append(name)
    return found


def load_versioned_prompt(
    prompt_name: str = "decision_system",
    version: str = "v1.0",
    *,
    repo_root: str | Path | None = None,
) -> str:
    """Load `prompts/<prompt_name>/<version>.md` from disk."""
    root = Path(repo_root) if repo_root else find_repo_root()
    path = root / "prompts" / prompt_name / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Versioned system prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def wrap_untrusted_context_as_data(
    *,
    retrieved_chunks: list[dict[str, Any]] | None = None,
    tool_outputs: list[dict[str, Any]] | None = None,
) -> str:
    """Wrap retrieved chunks and tool outputs inside `<retrieved_data>` and `<tool_output>` tags."""
    sections: list[str] = []
    if retrieved_chunks:
        lines = [
            f"[{c.get('chunk_id', 'unknown')}] {c.get('text', '')}" for c in retrieved_chunks
        ]
        sections.append("<retrieved_data>\n" + "\n".join(lines) + "\n</retrieved_data>")
    if tool_outputs:
        lines = [
            f"[{t.get('tool_call_id', 'tool')}] {t.get('result_summary', '')}"
            for t in tool_outputs
        ]
        sections.append("<tool_output>\n" + "\n".join(lines) + "\n</tool_output>")
    return "\n\n".join(sections)


def check(payload: dict[str, Any] | str, ctx: GuardrailContext) -> GuardrailResult:
    """Layer 1 `check(payload, ctx) -> GuardrailResult`: validate system prompt integrity & secrets."""
    if isinstance(payload, str):
        prompt_text = payload
    else:
        prompt_text = str(
            payload.get("prompt_text")
            or load_versioned_prompt(
                str(payload.get("prompt_name", "decision_system")),
                str(payload.get("version", "v1.0")),
            )
        )

    leaked = scan_for_secrets(prompt_text)
    if leaked:
        return build_guardrail_result(
            layer="prompt",
            raw_action="block",
            policy="prompt_secret_leak_check",
            ctx=ctx,
            details={"leaked_secret_types": leaked},
        )

    missing_markers = [m for m in REQUIRED_HARDENING_MARKERS if m not in prompt_text]
    if missing_markers:
        return build_guardrail_result(
            layer="prompt",
            raw_action="block",
            policy="prompt_hardening_hierarchy_check",
            ctx=ctx,
            details={"missing_hardening_markers": missing_markers},
        )

    return build_guardrail_result(
        layer="prompt",
        raw_action="pass",
        policy="prompt_hardening_hierarchy_check",
        ctx=ctx,
        sanitized_payload=prompt_text,
    )

"""Pure bilingual error definitions and payload builder (stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ERROR_TEMPLATES: dict[str, dict[str, str]] = {
    "MISSING_CONFIG": {
        "ja": "必須の環境変数または設定が不足しています: {variable}",
        "en": "Required environment variable or configuration is missing: {variable}",
    },
    "UNAUTHORIZED": {
        "ja": "認証情報が無効、または権限が不足しています。",
        "en": "Authentication credentials are invalid or insufficient permissions.",
    },
    "TENANT_MISMATCH": {
        "ja": "テナント境界を越えるアクセスは拒否されました。",
        "en": "Cross-tenant access is denied.",
    },
    "RATE_LIMIT_EXCEEDED": {
        "ja": "リクエスト上限に達しました。{retry_after}秒後に再試行してください。",
        "en": "Rate limit exceeded. Retry after {retry_after} seconds.",
    },
    "INSUFFICIENT_EVIDENCE": {
        "ja": "根拠が不足しているため推奨判断を確定できません。",
        "en": "Insufficient evidence to finalize a recommendation.",
    },
    "GUARDRAIL_BLOCKED": {
        "ja": "ガードレールポリシー（{policy}）により処理がブロックされました。",
        "en": "Blocked by guardrail policy ({policy}).",
    },
    "INTERNAL_ERROR": {
        "ja": "システム内部エラーが発生しました（トレースID: {trace_id}）。",
        "en": "An internal system error occurred (trace ID: {trace_id}).",
    },
}


@dataclass(frozen=True)
class AlbaError(Exception):
    """Domain exception carrying bilingual (JA/EN) messages and HTTP status code."""

    code: str
    status_code: int = 400
    lang: str = "ja"
    params: dict[str, Any] | None = None

    def to_dict(self, trace_id: str | None = None) -> dict[str, Any]:
        """Serialize error into a structured bilingual JSON response payload."""
        fmt_params = dict(self.params or {})
        fmt_params.setdefault("trace_id", trace_id or "unknown")
        template = ERROR_TEMPLATES.get(self.code, ERROR_TEMPLATES["INTERNAL_ERROR"])
        msg_ja = template["ja"].format(**fmt_params)
        msg_en = template["en"].format(**fmt_params)
        localized = msg_ja if self.lang == "ja" else msg_en
        return {
            "error": {
                "code": self.code,
                "message": localized,
                "message_ja": msg_ja,
                "message_en": msg_en,
                "trace_id": trace_id,
            }
        }

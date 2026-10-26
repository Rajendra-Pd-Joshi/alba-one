"""PII redaction and deterministic tokenisation before text leaves on-prem (`kb/pii.py`).

Redacts Japanese and English PII patterns before sending chunk text to external
embedding or LLM providers:
- Japanese phone numbers (`03-xxxx-xxxx`, `090-xxxx-xxxx`, `+81-...`, full-width digits)
- Japanese postal codes (`〒100-0001`, `Postal: 100-0001`, `郵便番号100-0001`)
- Individual Number / マイナンバー (12-digit numbers in `xxxx-xxxx-xxxx` or `xxxxxxxxxxxx` format)
- Email addresses
- Configurable Japanese and English personal names (`[PERSON_1]`, `[PERSON_2]`, ...)
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

# Email address pattern
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Japanese Individual Number (マイナンバー / 12-digit personal ID):
# Matches 4-4-4 grouped digits or 12 contiguous digits not part of a longer number.
_MYNUMBER_GROUPED_RE = re.compile(r"(?<!\d)\d{4}[-\s]\d{4}[-\s]\d{4}(?!\d)")
_MYNUMBER_CONTIGUOUS_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")

# Japanese phone numbers (landline 03/06/045..., mobile 070/080/090, toll-free 0120/0800, +81)
_JP_PHONE_RE = re.compile(
    r"(?:(?:\+81[-\s]?|0)\d{1,4}[-\s()（）]\d{1,4}[-\s()（）]\d{3,4})"
)

# Japanese postal code: 〒NNN-NNNN or contextual (郵便番号 / Postal) NNN-NNNN
_JP_POSTAL_SYMBOL_RE = re.compile(r"〒\s*\d{3}-\d{4}")
_JP_POSTAL_CONTEXT_RE = re.compile(
    r"(?P<prefix>(?:郵便番号|Postal(?:\s*Code)?)\s*[:：]?\s*)(?P<code>\d{3}-\d{4})",
    re.IGNORECASE,
)

DEFAULT_CONFIGURABLE_NAMES: tuple[str, ...] = (
    "渡辺 剛",
    "渡辺剛",
    "Tsuyoshi Watanabe",
    "伊藤 裕子",
    "伊藤裕子",
    "Yuko Ito",
    "中村 恒一",
    "中村恒一",
    "Koichi Nakamura",
    "佐藤 健一",
    "佐藤健一",
    "Kenichi Sato",
    "高橋 美咲",
    "高橋美咲",
    "Misaki Takahashi",
    "鈴木 誠",
    "鈴木誠",
    "Makoto Suzuki",
    "山本 彩",
    "山本彩",
    "Aya Yamamoto",
)


@dataclass(frozen=True)
class PIIRedactionResult:
    """Output of PII scrubbing containing redacted text and counts by PII category."""

    redacted_text: str
    counts: dict[str, int] = field(default_factory=dict)
    total_redactions: int = 0

    @property
    def contains_pii(self) -> bool:
        return self.total_redactions > 0


class PIIRedactor:
    """Configurable bilingual PII redactor/tokeniser for on-premise pre-embedding scrubbing."""

    def __init__(self, person_names: Sequence[str] | None = None) -> None:
        raw_names = DEFAULT_CONFIGURABLE_NAMES if person_names is None else tuple(person_names)
        # Sort longest first so "渡辺 剛" matches before a shorter substring
        self._person_names = sorted({n.strip() for n in raw_names if n.strip()}, key=len, reverse=True)

    def redact(self, text: str) -> PIIRedactionResult:
        """Normalize full-width digits in numeric patterns and replace all PII with tokens."""
        if not text:
            return PIIRedactionResult(redacted_text="", counts={}, total_redactions=0)

        # Convert full-width ASCII digits/hyphens to half-width for reliable regex detection
        working = unicodedata.normalize("NFKC", text)
        counts: dict[str, int] = {}

        def _bump(category: str, n: int = 1) -> None:
            if n > 0:
                counts[category] = counts.get(category, 0) + n

        # 1. Configurable person names (deterministic token per configured name)
        for name in self._person_names:
            if name in working:
                occurrences = working.count(name)
                working = working.replace(name, "[PII_PERSON]")
                _bump("person_name", occurrences)

        # 2. Email addresses
        working, n_email = _EMAIL_RE.subn("[PII_EMAIL]", working)
        _bump("email", n_email)

        # 3. Japanese My Number (マイナンバー 12 digits)
        working, n_my1 = _MYNUMBER_GROUPED_RE.subn("[PII_MYNUMBER]", working)
        working, n_my2 = _MYNUMBER_CONTIGUOUS_RE.subn("[PII_MYNUMBER]", working)
        _bump("mynumber", n_my1 + n_my2)

        # 4. Japanese phone numbers
        working, n_phone = _JP_PHONE_RE.subn("[PII_PHONE]", working)
        _bump("phone_jp", n_phone)

        # 5. Japanese postal codes
        working, n_post1 = _JP_POSTAL_SYMBOL_RE.subn("[PII_POSTAL_JP]", working)
        working, n_post2 = _JP_POSTAL_CONTEXT_RE.subn(r"\g<prefix>[PII_POSTAL_JP]", working)
        _bump("postal_jp", n_post1 + n_post2)

        total = sum(counts.values())
        return PIIRedactionResult(redacted_text=working, counts=counts, total_redactions=total)

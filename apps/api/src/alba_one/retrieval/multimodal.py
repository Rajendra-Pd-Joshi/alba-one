"""Stage 5: Multimodal RAG Ingestion & Text-Proxy Retrieval (`retrieval/multimodal.py`).

Handles images, tables, and PDFs behind the feature flag `ENABLE_MULTIMODAL_RAG`:
- Stores the raw binary asset reference on-premise (`onprem_asset_uri`).
- Extracts or captions the asset into a bilingual text proxy (`text_proxy`) via an
  injectable `VisionCaptionerPort` (or table structure linearizer).
- Indexes and retrieves the asset through its text proxy while linking back to the
  on-premise asset URI.

Documented Limits:
- Maximum file size per asset: 20 MB (`MAX_MULTIMODAL_BYTES = 20 * 1024 * 1024`).
- Supported MIME types: `image/png`, `image/jpeg`, `application/pdf`, `text/csv`, `text/markdown`.
- Disabled by default (`ENABLE_MULTIMODAL_RAG=false`) so text-only tenants incur zero vision token cost.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

MAX_MULTIMODAL_BYTES = 20 * 1024 * 1024
SUPPORTED_MULTIMODAL_MIMES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "application/pdf", "text/csv", "text/markdown"}
)


@dataclass(frozen=True)
class MultimodalAssetRecord:
    """On-premise multimodal asset paired with its searchable text proxy."""

    asset_id: str
    tenant_id: str
    modality: Literal["image", "table", "pdf"]
    mime_type: str
    onprem_asset_uri: str
    text_proxy: str
    entity_ids: list[str]
    acl_tags: list[str]
    lang: str = "ja"
    metadata: dict[str, Any] = field(default_factory=dict)


class VisionCaptionerPort(Protocol):
    """Protocol for captioning/extracting images, tables, or PDFs into a text proxy."""

    def extract_text_proxy(
        self,
        *,
        modality: str,
        onprem_asset_uri: str,
        raw_caption_or_table: str,
        lang: str,
    ) -> str: ...


class DefaultDeterministicCaptioner:
    """# STUB: Deterministic text-proxy builder for offline multimodal ingestion tests."""

    def extract_text_proxy(
        self,
        *,
        modality: str,
        onprem_asset_uri: str,
        raw_caption_or_table: str,
        lang: str,
    ) -> str:
        prefix = f"[Multimodal:{modality.upper()} | URI:{onprem_asset_uri}]"
        return f"{prefix} {raw_caption_or_table.strip()}"


def ingest_multimodal_asset(
    *,
    tenant_id: str,
    modality: Literal["image", "table", "pdf"],
    mime_type: str,
    onprem_asset_uri: str,
    raw_caption_or_table: str,
    entity_ids: list[str],
    acl_tags: list[str],
    size_bytes: int,
    enabled: bool = False,
    lang: str = "ja",
    captioner: VisionCaptionerPort | None = None,
) -> MultimodalAssetRecord | None:
    """Convert an image, table, or PDF into a `MultimodalAssetRecord` when `enabled=True`."""
    if not enabled:
        return None
    if size_bytes > MAX_MULTIMODAL_BYTES:
        raise ValueError(
            f"Multimodal asset exceeds 20 MB limit ({size_bytes} bytes > {MAX_MULTIMODAL_BYTES})."
        )
    if mime_type not in SUPPORTED_MULTIMODAL_MIMES:
        raise ValueError(f"Unsupported multimodal MIME type '{mime_type}'.")

    cap = captioner or DefaultDeterministicCaptioner()
    proxy = cap.extract_text_proxy(
        modality=modality,
        onprem_asset_uri=onprem_asset_uri,
        raw_caption_or_table=raw_caption_or_table,
        lang=lang,
    )
    digest = hashlib.sha256(f"{tenant_id}|{onprem_asset_uri}|{lang}".encode()).hexdigest()[:12]
    return MultimodalAssetRecord(
        asset_id=f"mm_{modality}_{digest}",
        tenant_id=tenant_id,
        modality=modality,
        mime_type=mime_type,
        onprem_asset_uri=onprem_asset_uri,
        text_proxy=proxy,
        entity_ids=list(entity_ids),
        acl_tags=list(acl_tags),
        lang=lang,
    )

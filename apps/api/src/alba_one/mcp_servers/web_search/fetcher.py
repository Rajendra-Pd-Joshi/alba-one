"""SSRF-Hardened Page Fetcher (`mcp_servers/web_search/fetcher.py`).

Implements `fetch_page(url)` as a separate tool from search providers (User Answer 1):
- Default engine: `httpx` + HTML-to-text extraction (`html.parser` / BeautifulSoup).
- Optional Firecrawl scrape implementation behind the same `PageFetcherPort`.
- Mandatory SSRF & domain controls on initial URL AND on every HTTP redirect hop:
  1. Only `http` and `https` schemes allowed.
  2. Resolves hostname via DNS (`socket.getaddrinfo` or injected `dns_resolver`) and
     blocks private, loopback, link-local, multicast, and cloud metadata (`169.254.169.254`) IPs.
  3. Re-validates every `301/302/303/307/308` redirect target (`max_redirects=3`) before following.
  4. Enforces `FETCH_DOMAIN_POLICY=allowlist|denylist|open_public` (default `denylist`).
  5. Enforces content-type allowlist (`text/html`, `text/plain`, `application/xhtml+xml`),
     max response size (`max_bytes=262_144`), and request timeout (`timeout_seconds=10.0`).
  6. Passes extracted text through `RetrieverGuardrailStub` (PII redaction + prompt-injection scan).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import socket
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx

from alba_one.guardrails.tool_layer import ALLOWED_EXTERNAL_DOMAINS
from alba_one.retrieval.guardrail_stub import RetrieverGuardrailStub
from alba_one.retrieval.ports import ExternalResult

FetchDomainPolicy = Literal["allowlist", "denylist", "open_public"]

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"text/html", "text/plain", "application/xhtml+xml"}
)
DEFAULT_DENIED_DOMAINS: frozenset[str] = frozenset(
    {"metadata.google.internal", "169.254.169.254", "localhost", "internal.albaconnect.local"}
)


class _SimpleHTMLTextExtractor(HTMLParser):
    """Lightweight stdlib HTML-to-text extractor stripping `<script>` and `<style>` tags."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in ("script", "style", "noscript"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("script", "style", "noscript") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self._chunks)


def _default_dns_resolver(hostname: str) -> list[str]:
    """Resolve `hostname` to IP strings using `socket.getaddrinfo`."""
    try:
        ipaddress.ip_address(hostname)
        return [hostname]
    except ValueError:
        pass
    infos = socket.getaddrinfo(hostname, None)
    return list({str(info[4][0]) for info in infos if info[4]})


def validate_url_ssrf_and_domain_policy(
    url: str,
    *,
    domain_policy: FetchDomainPolicy = "denylist",
    allowed_domains: Sequence[str] = tuple(ALLOWED_EXTERNAL_DOMAINS),
    denied_domains: Sequence[str] = tuple(DEFAULT_DENIED_DOMAINS),
    dns_resolver: Callable[[str], list[str]] = _default_dns_resolver,
) -> str:
    """Validate URL scheme, domain policy, and resolved DNS IP addresses against SSRF."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise PermissionError(f"SSRF blocked: invalid scheme '{parsed.scheme}' in '{url}'.")
    host = (parsed.hostname or "").lower().strip()
    if not host or host in ("localhost", "0.0.0.0") or host.endswith(".local") or host.endswith(".internal"):
        raise PermissionError(f"SSRF blocked: forbidden local/internal hostname '{host}'.")

    if domain_policy == "allowlist":
        if not any(host == d or host.endswith(f".{d}") for d in allowed_domains):
            raise PermissionError(f"Domain '{host}' is not in FETCH_DOMAIN_POLICY allowlist.")
    elif domain_policy == "denylist":
        if any(host == d or host.endswith(f".{d}") for d in denied_domains):
            raise PermissionError(f"Domain '{host}' is blocked by FETCH_DOMAIN_POLICY denylist.")

    resolved_ips = dns_resolver(host)
    if not resolved_ips:
        raise PermissionError(f"SSRF blocked: DNS resolution returned no IPs for '{host}'.")

    for ip_str in resolved_ips:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise PermissionError(
                f"SSRF blocked: host '{host}' resolved to non-public IP '{ip}'."
            )
    return url.strip()


def fetch_page_safely(
    url: str,
    *,
    lang: str = "ja",
    domain_policy: FetchDomainPolicy = "denylist",
    max_bytes: int = 262_144,
    max_redirects: int = 3,
    timeout_seconds: float = 10.0,
    dns_resolver: Callable[[str], list[str]] = _default_dns_resolver,
    http_client: httpx.Client | None = None,
    guardrail: RetrieverGuardrailStub | None = None,
) -> dict[str, Any]:
    """Fetch `url` with redirect-hop SSRF re-verification, extract text, and scrub via retriever guardrail."""
    current_url = validate_url_ssrf_and_domain_policy(
        url, domain_policy=domain_policy, dns_resolver=dns_resolver
    )
    client = http_client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
    close_after = http_client is None

    try:
        redirects = 0
        while True:
            resp = client.get(current_url, follow_redirects=False)
            if resp.status_code in (301, 302, 303, 307, 308):
                redirects += 1
                if redirects > max_redirects:
                    raise PermissionError(f"Too many redirects (>{max_redirects}) fetching '{url}'.")
                location = resp.headers.get("location", "")
                if not location:
                    raise PermissionError("Redirect response missing Location header.")
                next_url = urljoin(current_url, location)
                # Mandatory re-check of DNS and SSRF on every redirect target!
                current_url = validate_url_ssrf_and_domain_policy(
                    next_url, domain_policy=domain_policy, dns_resolver=dns_resolver
                )
                continue
            break

        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "text/html").split(";")[0].strip().lower()
        if ctype not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"Blocked content-type '{ctype}'. Allowed: {sorted(ALLOWED_CONTENT_TYPES)}")

        raw_bytes = resp.content
        if len(raw_bytes) > max_bytes:
            raise ValueError(f"Response size ({len(raw_bytes)} bytes) exceeds limit ({max_bytes} bytes).")

        decoded = raw_bytes.decode("utf-8", errors="replace")
        if ctype == "text/plain":
            extracted_text = decoded.strip()
        else:
            parser = _SimpleHTMLTextExtractor()
            parser.feed(decoded)
            extracted_text = parser.get_text()
    finally:
        if close_after:
            client.close()

    now_iso = datetime.now(timezone.utc).isoformat()
    ext_item = ExternalResult(
        text=extracted_text or "(empty page)",
        source_url=current_url,
        retrieved_at=now_iso,
        source_kind="web",
        external=True,
    )
    gr = guardrail or RetrieverGuardrailStub()
    cleaned_list, stats = gr.filter_external_results([ext_item])
    if not cleaned_list:
        raise PermissionError(f"Fetched page from '{current_url}' blocked by retriever guardrail: {stats.events}")

    clean = cleaned_list[0]
    return {
        "source_url": clean.source_url,
        "retrieved_at": clean.retrieved_at,
        "external": True,
        "text": clean.text,
        "guardrail_events": stats.events,
    }

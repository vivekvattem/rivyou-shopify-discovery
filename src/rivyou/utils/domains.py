"""URL/domain normalization helpers."""

from __future__ import annotations

import html
import re
from urllib.parse import urlsplit

import tldextract

_MARKDOWN_LINK = re.compile(r"^\s*\[[^]]+\]\(([^)]+)\)\s*$")
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.I)
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())


def normalize_domain(value: str | None) -> str | None:
    """Return a canonical HTTPS origin or None for a malformed/public-suffix-less URL."""
    if not value or not isinstance(value, str):
        return None
    raw = html.unescape(value).strip().strip("<>\"'")
    match = _MARKDOWN_LINK.match(raw)
    if match:
        raw = match.group(1).strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        raw = f"https://{raw}"
    try:
        parsed = urlsplit(raw)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if hostname.startswith("www."):
            hostname = hostname[4:]
        hostname = hostname.encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        return None
    if not hostname or any(not _HOST_LABEL.match(label) for label in hostname.split(".")):
        return None
    extracted = _EXTRACT(hostname)
    if not extracted.domain or not extracted.suffix:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    port_text = f":{port}" if port and port not in (80, 443) else ""
    return f"https://{hostname}{port_text}"


def registered_domain(value: str | None) -> str | None:
    normalized = normalize_domain(value)
    if not normalized:
        return None
    host = urlsplit(normalized).hostname or ""
    if host.endswith(".myshopify.com"):
        return host
    extracted = _EXTRACT(host)
    return extracted.top_domain_under_public_suffix or None


def same_registered_domain(left: str, right: str) -> bool:
    return registered_domain(left) == registered_domain(right)

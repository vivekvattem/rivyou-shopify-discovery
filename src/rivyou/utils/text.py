"""Small text-cleaning and structured-data helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from bs4 import BeautifulSoup


def clean_text(value: str | None, max_length: int | None = None) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if max_length and len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    return clean_text(soup.get_text(" ", strip=True))


def iter_json_ld(html: str) -> Iterator[dict]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = tag.string or tag.get_text()
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        values = parsed if isinstance(parsed, list) else [parsed]
        for value in values:
            if isinstance(value, dict) and isinstance(value.get("@graph"), list):
                yield from (item for item in value["@graph"] if isinstance(item, dict))
            if isinstance(value, dict):
                yield value


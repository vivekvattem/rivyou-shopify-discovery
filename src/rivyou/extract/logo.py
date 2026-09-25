"""Brand-logo extraction that explicitly excludes favicon/app/payment assets."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from rivyou.crawler import CrawledPage
from rivyou.utils.text import iter_json_ld

REJECT_LOGO_RE = re.compile(
    r"(?:favicon|apple-touch-icon|payment|visa|mastercard|amex|paypal|shopify-pay|google-pay|app-icon)", re.I
)


def _image_url(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        candidate = value.get("url") or value.get("contentUrl")
        return candidate if isinstance(candidate, str) else None
    return None


def _valid_logo(url: str, tag: object | None = None) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    path = parsed.path.lower()
    if not path or path.endswith("favicon.ico") or REJECT_LOGO_RE.search(path):
        return False
    if tag is not None and hasattr(tag, "get"):
        try:
            width = int(str(tag.get("width", "0")).replace("px", "") or 0)
            height = int(str(tag.get("height", "0")).replace("px", "") or 0)
            if width and height and width <= 32 and height <= 32:
                return False
        except ValueError:
            pass
    return True


def extract_logo(pages: Iterable[CrawledPage]) -> str | None:
    for page in pages:
        if not page.html:
            continue
        for item in iter_json_ld(page.html):
            kind = item.get("@type", "")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(value in {"Organization", "Brand", "LocalBusiness", "Store"} for value in kinds):
                raw = _image_url(item.get("logo"))
                if raw:
                    url = urljoin(page.final_url, raw)
                    if _valid_logo(url):
                        return url
    candidates: list[tuple[int, str]] = []
    for page in pages:
        if not page.html:
            continue
        soup = BeautifulSoup(page.html, "lxml")
        for image in soup.select("img[src], img[data-src]"):
            raw = image.get("src") or image.get("data-src")
            if not raw:
                continue
            url = urljoin(page.final_url, raw)
            semantic = " ".join((image.get("alt", ""), image.get("class", []).__str__(), image.get("id", ""), raw)).lower()
            score = 0
            if image.find_parent("header") and "logo" in semantic:
                score = 90
            elif "logo" in semantic:
                score = 75
            elif image.find_parent("header"):
                score = 45
            if score and _valid_logo(url, image):
                candidates.append((score, url))
        og = soup.select_one('meta[property="og:image"][content]')
        if og:
            url = urljoin(page.final_url, og.get("content", ""))
            if _valid_logo(url):
                candidates.append((10, url))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]

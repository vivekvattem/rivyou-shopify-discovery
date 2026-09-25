"""Extract concise merchant-authored descriptions."""

from __future__ import annotations

from collections.abc import Iterable

from bs4 import BeautifulSoup

from rivyou.crawler import CrawledPage
from rivyou.utils.text import clean_text, iter_json_ld

BLOCKLIST = ("cookie policy", "accept cookies", "enable javascript", "skip to content")


def _acceptable(value: str | None) -> str | None:
    text = clean_text(value, 500)
    if len(text) < 20 or any(phrase in text.lower() for phrase in BLOCKLIST):
        return None
    return text


def extract_description(pages: Iterable[CrawledPage]) -> str | None:
    available = [page for page in pages if page.html]
    for selector, attribute in (("meta[name='description']", "content"), ("meta[property='og:description']", "content")):
        for page in available:
            tag = BeautifulSoup(page.html, "lxml").select_one(selector)
            if tag and (value := _acceptable(tag.get(attribute))):
                return value
    for page in available:
        for item in iter_json_ld(page.html):
            if value := _acceptable(item.get("description") if isinstance(item.get("description"), str) else None):
                return value
    if available:
        soup = BeautifulSoup(available[0].html, "lxml")
        for selector in ("main h1 + p", "section[class*='hero'] p", "main p"):
            tag = soup.select_one(selector)
            if tag and (value := _acceptable(tag.get_text(" ", strip=True))):
                return value
    for page in available[1:]:
        if "about" in page.final_url.lower():
            soup = BeautifulSoup(page.html, "lxml")
            main = soup.select_one("main, article")
            if main and (value := _acceptable(main.get_text(" ", strip=True))):
                return value
    return None


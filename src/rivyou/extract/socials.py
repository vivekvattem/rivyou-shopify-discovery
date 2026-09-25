"""Merchant social-profile URL extraction."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from rivyou.crawler import CrawledPage
from rivyou.models import empty_socials

HOST_TO_PLATFORM = {
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "linkedin.com": "linkedin",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
}
REJECT_PATHS = re.compile(
    r"/(?:share|sharer|sharer\.php|dialog/share|intent|shareArticle|sharing|watch|p|reel|reels|status|posts)(?:/|$)", re.I
)
GENERIC_PATHS = {"", "/", "/home", "/login", "/signup"}


def normalize_social_url(raw_url: str, base_url: str = "") -> tuple[str, str] | None:
    url = urljoin(base_url, raw_url.strip())
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    platform = next((name for domain, name in HOST_TO_PLATFORM.items() if host == domain or host.endswith(f".{domain}")), None)
    path = parsed.path.rstrip("/")
    if not platform or path.lower() in GENERIC_PATHS or REJECT_PATHS.search(path):
        return None
    lowered = path.lower()
    if "shopify" in lowered or lowered.startswith(("/hashtag/", "/search")):
        return None
    if platform == "twitter" and lowered.startswith(("/intent", "/share", "/home")):
        return None
    if platform == "linkedin" and not lowered.startswith(("/company/", "/in/", "/school/")):
        return None
    if platform == "youtube" and not lowered.startswith(("/@", "/channel/", "/c/", "/user/")):
        return None
    canonical_host = "x.com" if platform == "twitter" else host
    return platform, urlunsplit(("https", canonical_host, path, "", ""))


def extract_socials(pages: Iterable[CrawledPage]) -> dict[str, str | None]:
    result = empty_socials()
    for page in pages:
        if not page.html:
            continue
        soup = BeautifulSoup(page.html, "lxml")
        for tag in soup.select("a[href]"):
            normalized = normalize_social_url(tag.get("href", ""), page.final_url)
            if normalized:
                platform, url = normalized
                result[platform] = result[platform] or url
    return result

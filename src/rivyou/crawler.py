"""Polite, bounded asynchronous HTML crawler."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from rivyou.config import SETTINGS, Settings
from rivyou.utils.domains import same_registered_domain

LOGGER = logging.getLogger(__name__)


class RetryableHTTPError(Exception):
    pass


@dataclass(slots=True)
class CrawledPage:
    requested_url: str
    final_url: str
    status_code: int
    html: str
    headers: dict[str, str] = field(default_factory=dict)
    redirect_history: list[str] = field(default_factory=list)
    error: str | None = None


PAGE_PRIORITIES = {
    "contact-us": 100,
    "contact": 95,
    "about-us": 90,
    "our-story": 85,
    "about": 80,
    "shipping": 65,
    "delivery": 60,
    "returns": 55,
    "refund": 50,
    "privacy": 35,
    "terms": 30,
}


def discover_important_links(homepage: CrawledPage, limit: int = 4) -> list[str]:
    """Rank relevant same-site links without recursively spidering."""
    soup = BeautifulSoup(homepage.html, "lxml")
    scored: dict[str, int] = {}
    for anchor in soup.select("a[href]"):
        raw_href = anchor.get("href", "").strip()
        if not raw_href or raw_href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(homepage.final_url, raw_href).split("#", 1)[0]
        if not same_registered_domain(homepage.final_url, url):
            continue
        haystack = f"{urlsplit(url).path} {anchor.get_text(' ', strip=True)}".lower().replace("_", "-")
        score = max((weight for phrase, weight in PAGE_PRIORITIES.items() if phrase in haystack), default=0)
        if score:
            scored[url] = max(score, scored.get(url, 0))
    return [url for url, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0]))[:limit]]


class AsyncCrawler:
    def __init__(self, settings: Settings = SETTINGS, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.request_timeout,
            headers={"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml"},
            transport=transport,
        )
        self._robots: dict[str, RobotFileParser] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}

    async def __aenter__(self) -> "AsyncCrawler":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _robots_parser(self, url: str) -> RobotFileParser:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        lock = self._robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin in self._robots:
                return self._robots[origin]
            robots_url = f"{origin}/robots.txt"
            parser = RobotFileParser(robots_url)
            try:
                async with self._semaphore:
                    response = await self._client.get(robots_url)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:
                    parser.parse([])
            except httpx.HTTPError:
                parser.parse([])
            self._robots[origin] = parser
            return parser

    async def allowed(self, url: str) -> bool:
        parser = await self._robots_parser(url)
        return parser.can_fetch(self.settings.user_agent, url)

    async def fetch(self, url: str, *, check_robots: bool = True) -> CrawledPage:
        if check_robots and not await self.allowed(url):
            return CrawledPage(url, url, 0, "", error="blocked by robots.txt")
        try:
            return await self._fetch_with_retry(url)
        except (httpx.HTTPError, RetryableHTTPError) as exc:
            LOGGER.warning("[CRAWL] %s failed: %s", url, exc)
            return CrawledPage(url, url, 0, "", error=f"{type(exc).__name__}: {exc}")

    def _retry_decorator(self):
        return retry(
            retry=retry_if_exception_type((httpx.TransportError, RetryableHTTPError)),
            stop=stop_after_attempt(max(1, self.settings.retry_count)),
            wait=wait_exponential(multiplier=0.25, min=0.25, max=2),
            reraise=True,
        )

    async def _fetch_with_retry(self, url: str) -> CrawledPage:
        @self._retry_decorator()
        async def request() -> CrawledPage:
            async with self._semaphore:
                async with self._client.stream("GET", url) as response:
                    if response.status_code == 429 or response.status_code >= 500:
                        raise RetryableHTTPError(f"HTTP {response.status_code}")
                    content_type = response.headers.get("content-type", "").lower()
                    history = [str(item.url) for item in response.history]
                    if response.status_code >= 400:
                        return CrawledPage(url, str(response.url), response.status_code, "", dict(response.headers), history,
                                           f"HTTP {response.status_code}")
                    if "html" not in content_type:
                        return CrawledPage(url, str(response.url), response.status_code, "", dict(response.headers), history,
                                           f"non-HTML content type: {content_type or 'unknown'}")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.settings.max_response_bytes:
                            return CrawledPage(url, str(response.url), response.status_code, "", dict(response.headers), history,
                                               "response exceeded size limit")
                        chunks.append(chunk)
                    encoding = response.encoding or "utf-8"
                    html = b"".join(chunks).decode(encoding, errors="replace")
                    return CrawledPage(url, str(response.url), response.status_code, html, dict(response.headers), history)

        return await request()

    async def crawl_store(self, homepage_url: str) -> list[CrawledPage]:
        homepage = await self.fetch(homepage_url)
        if not homepage.html:
            return [homepage]
        secondary_limit = max(0, self.settings.max_pages_per_site - 1)
        links = discover_important_links(homepage, secondary_limit)
        secondary = await asyncio.gather(*(self.fetch(link) for link in links))
        return [homepage, *secondary]

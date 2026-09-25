import httpx
import pytest

from rivyou.config import SETTINGS
from rivyou.crawler import AsyncCrawler, CrawledPage, discover_important_links


def test_important_links_are_ranked_and_bounded():
    page = CrawledPage(
        "https://brand.in", "https://brand.in", 200,
        '<a href="/about-us">About</a><a href="/contact-us">Contact</a>'
        '<a href="/collections/all">Shop</a><a href="https://other.com/contact">Other</a>',
    )
    assert discover_important_links(page, 1) == ["https://brand.in/contact-us"]


@pytest.mark.asyncio
async def test_crawler_uses_mocked_html_response_and_robots():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /", headers={"content-type": "text/plain"})
        return httpx.Response(200, text="<html><title>Brand</title></html>", headers={"content-type": "text/html"})

    settings = SETTINGS.with_overrides(retry_count=1)
    async with AsyncCrawler(settings, transport=httpx.MockTransport(handler)) as crawler:
        page = await crawler.fetch("https://brand.in")
    assert page.status_code == 200
    assert "Brand" in page.html


@pytest.mark.asyncio
async def test_crawler_respects_mocked_robots_disallow():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nDisallow: /private", headers={"content-type": "text/plain"})

    async with AsyncCrawler(SETTINGS, transport=httpx.MockTransport(handler)) as crawler:
        page = await crawler.fetch("https://brand.in/private")
    assert page.error == "blocked by robots.txt"

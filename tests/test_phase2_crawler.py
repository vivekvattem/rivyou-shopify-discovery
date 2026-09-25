import time

import httpx
import pytest

from rivyou.config import SETTINGS
from rivyou.crawler import AsyncCrawler
from rivyou.storage.cache import SQLiteHTTPCache
from rivyou.storage.sqlite_store import SQLiteStore


@pytest.mark.asyncio
async def test_per_host_requests_are_spaced():
    times = []

    async def handler(request):
        times.append(time.monotonic())
        return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})

    settings = SETTINGS.with_overrides(per_host_delay_seconds=0.05, retry_count=1)
    async with AsyncCrawler(settings, transport=httpx.MockTransport(handler)) as crawler:
        await crawler.fetch("https://brand.in/a", check_robots=False)
        await crawler.fetch("https://brand.in/b", check_robots=False)
    assert times[1] - times[0] >= 0.045


@pytest.mark.asyncio
async def test_cache_hit_avoids_second_network_request(tmp_path):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<html>cached</html>", headers={"content-type": "text/html"})

    cache = SQLiteHTTPCache(SQLiteStore(tmp_path / "cache.db"), 24)
    settings = SETTINGS.with_overrides(per_host_delay_seconds=0, retry_count=1)
    async with AsyncCrawler(settings, transport=httpx.MockTransport(handler), cache=cache) as crawler:
        first = await crawler.fetch("https://brand.in", check_robots=False)
        second = await crawler.fetch("https://brand.in", check_robots=False)
    assert calls == 1
    assert not first.from_cache and second.from_cache


@pytest.mark.asyncio
async def test_cache_can_be_bypassed(tmp_path):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<html>fresh</html>", headers={"content-type": "text/html"})

    cache = SQLiteHTTPCache(SQLiteStore(tmp_path / "cache.db"), 24)
    cache.set("https://brand.in", "https://brand.in", 200, "text/html", b"<html>old</html>", {})
    settings = SETTINGS.with_overrides(per_host_delay_seconds=0, retry_count=1)
    async with AsyncCrawler(settings, transport=httpx.MockTransport(handler), cache=cache, use_cache=False) as crawler:
        page = await crawler.fetch("https://brand.in", check_robots=False)
    assert calls == 1
    assert "fresh" in page.html

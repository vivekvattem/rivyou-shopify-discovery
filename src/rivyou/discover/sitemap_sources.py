"""Optional, bounded sitemap inspection for already-known candidate domains."""

from __future__ import annotations

from urllib.parse import urljoin
from xml.etree import ElementTree

from rivyou.crawler import AsyncCrawler
from rivyou.utils.domains import same_registered_domain


async def sample_sitemap_urls(domain: str, crawler: AsyncCrawler, limit: int = 10) -> list[str]:
    page = await crawler.fetch(urljoin(domain, "/sitemap.xml"), accepted_content_types=("html", "xml"))
    if not page.html:
        return []
    try:
        root = ElementTree.fromstring(page.html)
    except ElementTree.ParseError:
        return []
    urls: list[str] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "loc" or not node.text:
            continue
        url = node.text.strip()
        if same_registered_domain(domain, url) and any(part in url.lower() for part in ("/products", "/collections", "/pages")):
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls

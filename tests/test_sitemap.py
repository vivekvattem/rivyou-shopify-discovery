import pytest

from rivyou.crawler import CrawledPage
from rivyou.discover.sitemap_sources import sample_sitemap_urls


class SitemapCrawler:
    async def fetch(self, url, **kwargs):
        xml = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://brand.in/products/a</loc></url>
        <url><loc>https://brand.in/blogs/news</loc></url>
        <url><loc>https://other.in/products/b</loc></url></urlset>"""
        return CrawledPage(url, url, 200, xml)


@pytest.mark.asyncio
async def test_sitemap_sampling_keeps_relevant_internal_urls_only():
    assert await sample_sitemap_urls("https://brand.in", SitemapCrawler()) == ["https://brand.in/products/a"]

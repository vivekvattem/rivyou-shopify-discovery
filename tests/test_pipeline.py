import json

import pytest

from rivyou.crawler import CrawledPage
from rivyou.models import StoreCandidate
from rivyou.pipeline import StorePipeline, write_outputs


class FakeCrawler:
    async def fetch(self, url: str):
        if "contact" in url:
            html = '<p>Registered Office: MG Road, Bengaluru, Karnataka 560001, India</p><a href="tel:+919876543210">Call</a>'
        else:
            html = '''<html><head><meta name="description" content="Handmade Indian jewellery for everyday celebrations."></head>
            <body><script>Shopify.theme={}; ShopifyAnalytics={}</script><header><img class="logo" src="/logo.svg"></header>
            <a href="/contact-us">Contact</a><h1>Jewellery</h1></body></html>'''
        return CrawledPage(url, url, 200, html, {"content-type": "text/html"})


@pytest.mark.asyncio
async def test_small_pipeline_smoke_and_outputs(tmp_path):
    candidate = StoreCandidate(original_url="brand.in", normalized_domain="https://brand.in")
    pipeline = StorePipeline(crawler=FakeCrawler())
    records = await pipeline.run([candidate])
    assert len(records) == 1
    assert records[0].state == "Karnataka"
    assert records[0].phones == ["+919876543210"]
    write_outputs(records, pipeline.debug_records, tmp_path)
    rows = json.loads((tmp_path / "indian_shopify_stores.json").read_text())
    assert rows[0]["domain_url"] == "https://brand.in"

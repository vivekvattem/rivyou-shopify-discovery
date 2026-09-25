"""Practical Common Crawl URL-index discovery and external export ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from rivyou.discover.domain_sources import CSVDiscoveryProvider
from rivyou.models import CandidateProvenance, CandidateRecord
from rivyou.utils.domains import normalize_domain

COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"


class CommonCrawlImportProvider(CSVDiscoveryProvider):
    name = "commoncrawl-import"

    def __init__(self, path: str | Path):
        super().__init__(path, source_name=self.name)


class CommonCrawlIndexProvider:
    """Query URL patterns only; Common Crawl's index is not a global full-text search API."""

    name = "commoncrawl-index"

    def __init__(self, index_api: str | None = None, timeout: float = 30.0):
        self.index_api = index_api
        self.timeout = timeout
        self.raw_count = 0

    async def _resolve_index(self, client: httpx.AsyncClient) -> str:
        if self.index_api:
            return self.index_api
        response = await client.get(COLLINFO_URL)
        response.raise_for_status()
        collections = response.json()
        if not collections:
            raise RuntimeError("Common Crawl returned no indexes")
        return collections[0]["cdx-api"]

    async def discover(self, limit: int | None = None) -> list[CandidateRecord]:
        maximum = limit or 1000
        async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "RivyouDiscovery/1.0"}) as client:
            index_api = await self._resolve_index(client)
            response = await client.get(index_api, params={
                "url": "*.myshopify.com/*", "output": "json", "filter": "status:200", "collapse": "urlkey",
                "pageSize": min(maximum, 1000),
            })
            response.raise_for_status()
        records: list[CandidateRecord] = []
        for line in response.text.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            original = item.get("url", "")
            self.raw_count += 1
            normalized = normalize_domain(original)
            if not normalized:
                continue
            provenance = CandidateProvenance(
                source=self.name, source_url=index_api, signal="myshopify.com",
            )
            records.append(CandidateRecord(
                normalized_domain=normalized, original_url=original, discovery_source=self.name,
                source_url=index_api, signals=["myshopify.com"], provenance=[provenance],
            ))
            if len(records) >= maximum:
                break
        return records


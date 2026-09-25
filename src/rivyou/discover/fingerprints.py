"""Cheap homepage-only Shopify plausibility filter."""

from __future__ import annotations

from pydantic import BaseModel, Field

from rivyou.crawler import AsyncCrawler
from rivyou.models import VerificationEvidence
from rivyou.verify.shopify import verify_shopify


class PreFilterResult(BaseModel):
    plausible: bool
    score: int
    evidence: list[VerificationEvidence] = Field(default_factory=list)
    error: str | None = None


async def prefilter_shopify(domain: str, crawler: AsyncCrawler, threshold: int = 2) -> PreFilterResult:
    page = await crawler.fetch(domain)
    if not page.html:
        return PreFilterResult(plausible=False, score=0, error=page.error or "homepage unavailable")
    result = verify_shopify([page], threshold=threshold)
    return PreFilterResult(plausible=result.score >= threshold, score=result.score, evidence=result.evidence)


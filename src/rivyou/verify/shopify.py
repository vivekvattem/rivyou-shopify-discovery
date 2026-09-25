"""Multi-signal Shopify verification."""

from __future__ import annotations

import re
from collections.abc import Iterable

from rivyou.config import SHOPIFY_SCORE_THRESHOLD
from rivyou.crawler import CrawledPage
from rivyou.models import Confidence, ShopifyVerificationResult, VerificationEvidence


SIGNALS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("shopify_theme", re.compile(r"\bShopify\.theme\b", re.I), 3),
    ("shopify_cdn", re.compile(r"(?:cdn\.shopify\.com|/cdn/shop/)", re.I), 3),
    ("shopify_analytics", re.compile(r"\bShopifyAnalytics\b", re.I), 2),
    ("myshopify_reference", re.compile(r"[a-z0-9-]+\.myshopify\.com", re.I), 2),
    ("shopify_section", re.compile(r"shopify-section", re.I), 1),
    ("powered_by_shopify", re.compile(r"powered\s+by\s+shopify", re.I), 1),
)


def _confidence(score: int, threshold: int) -> Confidence:
    if score >= max(7, threshold + 3):
        return Confidence.HIGH
    if score >= threshold:
        return Confidence.MEDIUM
    return Confidence.LOW


def verify_shopify(
    pages: Iterable[CrawledPage], threshold: int = SHOPIFY_SCORE_THRESHOLD
) -> ShopifyVerificationResult:
    evidence: list[VerificationEvidence] = []
    found: set[str] = set()
    for page in pages:
        if not page.html:
            continue
        header_text = " ".join(f"{key}:{value}" for key, value in page.headers.items())
        searchable = f"{header_text}\n{page.html}"
        for signal, pattern, weight in SIGNALS:
            if signal not in found and (match := pattern.search(searchable)):
                found.add(signal)
                evidence.append(
                    VerificationEvidence(signal=signal, weight=weight, source_url=page.final_url, value=match.group(0)[:150])
                )
        powered_header = page.headers.get("x-shopid") or page.headers.get("x-shopify-stage")
        if powered_header and "shopify_header" not in found:
            found.add("shopify_header")
            evidence.append(
                VerificationEvidence(signal="shopify_header", weight=3, source_url=page.final_url, value=powered_header[:150])
            )
    score = sum(item.weight for item in evidence)
    return ShopifyVerificationResult(
        is_shopify=score >= threshold,
        score=score,
        confidence=_confidence(score, threshold),
        evidence=evidence,
    )


def add_product_json_evidence(
    result: ShopifyVerificationResult, source_url: str, is_shopify_json: bool, threshold: int = SHOPIFY_SCORE_THRESHOLD
) -> ShopifyVerificationResult:
    """Optionally add an active /products.json check made by a caller."""
    if not is_shopify_json or any(item.signal == "shopify_product_json" for item in result.evidence):
        return result
    evidence = [*result.evidence, VerificationEvidence(
        signal="shopify_product_json", weight=2, source_url=source_url, value="Shopify-like products JSON"
    )]
    score = sum(item.weight for item in evidence)
    return ShopifyVerificationResult(
        is_shopify=score >= threshold, score=score, confidence=_confidence(score, threshold), evidence=evidence
    )


"""Orchestration for verification, enrichment, deduplication, and output."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

import pandas as pd

from rivyou.config import SETTINGS, Settings
from rivyou.crawler import AsyncCrawler, CrawledPage, discover_important_links
from rivyou.discover.seeds import load_candidates
from rivyou.extract.category import classify_category
from rivyou.extract.contacts import extract_contacts
from rivyou.extract.description import extract_description
from rivyou.extract.logo import extract_logo
from rivyou.extract.socials import extract_socials
from rivyou.models import StoreCandidate, StoreRecord, empty_socials
from rivyou.utils.dedupe import dedupe_records
from rivyou.utils.domains import normalize_domain
from rivyou.verify.india import verify_india
from rivyou.verify.shopify import verify_shopify

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


def _safe_extract(name: str, function: Callable[[], T], fallback: T, errors: list[str]) -> T:
    try:
        return function()
    except Exception as exc:  # Field-level resilience is intentional at the pipeline boundary.
        errors.append(f"{name}: {type(exc).__name__}: {exc}")
        LOGGER.warning("[EXTRACT] %s failed: %s", name, exc)
        return fallback


class StorePipeline:
    def __init__(self, settings: Settings = SETTINGS, crawler: AsyncCrawler | None = None):
        self.settings = settings
        self._crawler = crawler
        self.debug_records: list[dict[str, Any]] = []

    async def _process_candidate(self, candidate: StoreCandidate, crawler: AsyncCrawler) -> StoreRecord | None:
        LOGGER.info("[CRAWL] %s", candidate.normalized_domain)
        homepage = await crawler.fetch(candidate.normalized_domain)
        debug: dict[str, Any] = {
            "candidate": candidate.model_dump(),
            "accepted": False,
            "homepage": {
                "final_url": homepage.final_url,
                "status_code": homepage.status_code,
                "error": homepage.error,
                "redirect_history": homepage.redirect_history,
            },
        }
        if not homepage.html:
            debug["rejection_reason"] = homepage.error or "homepage unavailable"
            self.debug_records.append(debug)
            LOGGER.info("[REJECT] %s: %s", candidate.normalized_domain, debug["rejection_reason"])
            return None

        shopify = verify_shopify([homepage], self.settings.shopify_score_threshold)
        debug["shopify"] = shopify.model_dump(mode="json")
        LOGGER.info("[SHOPIFY] %s score=%s confidence=%s", candidate.normalized_domain, shopify.score, shopify.confidence.value)
        if not shopify.is_shopify:
            debug["rejection_reason"] = "Shopify score below threshold"
            self.debug_records.append(debug)
            LOGGER.info("[REJECT] %s: Shopify score %s", candidate.normalized_domain, shopify.score)
            return None

        links = discover_important_links(homepage, max(0, self.settings.max_pages_per_site - 1))
        secondary = await asyncio.gather(*(crawler.fetch(link) for link in links))
        pages = [homepage, *secondary]
        # Secondary pages sometimes contain extra platform assets; retain the stronger complete result.
        shopify = verify_shopify(pages, self.settings.shopify_score_threshold)
        india = verify_india(pages, self.settings.india_score_threshold)
        debug["shopify"] = shopify.model_dump(mode="json")
        debug["india"] = india.model_dump(mode="json")
        debug["crawled_pages"] = [page.final_url for page in pages]
        LOGGER.info("[INDIA] %s score=%s confidence=%s", candidate.normalized_domain, india.score, india.confidence.value)
        if not india.is_indian:
            debug["rejection_reason"] = "India score below threshold"
            self.debug_records.append(debug)
            LOGGER.info("[REJECT] %s: India score %s", candidate.normalized_domain, india.score)
            return None

        errors: list[str] = []
        emails, phones = _safe_extract("contacts", lambda: extract_contacts(pages), ([], []), errors)
        socials = _safe_extract("socials", lambda: extract_socials(pages), empty_socials(), errors)
        description = _safe_extract("description", lambda: extract_description(pages), None, errors)
        logo = _safe_extract("logo", lambda: extract_logo(pages), None, errors)
        category = _safe_extract("category", lambda: classify_category(pages, description), "Other", errors)
        final_domain = normalize_domain(homepage.final_url) or candidate.normalized_domain
        record = StoreRecord(
            domain_url=final_domain,
            emails=emails,
            phones=phones,
            socials=socials,
            category=category,
            tagline_or_description=description,
            logo_url=logo,
            state=india.detected_state,
            shopify_score=shopify.score,
            india_score=india.score,
            shopify_confidence=shopify.confidence,
            india_confidence=india.confidence,
            shopify_evidence=shopify.evidence,
            india_evidence=india.evidence,
            crawled_pages=[page.final_url for page in pages if page.html],
            redirect_history=[url for page in pages for url in page.redirect_history],
            extraction_errors=errors,
        )
        debug["accepted"] = True
        debug["record"] = record.model_dump(mode="json")
        self.debug_records.append(debug)
        LOGGER.info("[ACCEPT] %s", final_domain)
        return record

    async def run(self, candidates: list[StoreCandidate]) -> list[StoreRecord]:
        self.debug_records = []
        if self._crawler is not None:
            records = await asyncio.gather(*(self._process_candidate(item, self._crawler) for item in candidates))
        else:
            async with AsyncCrawler(self.settings) as crawler:
                records = await asyncio.gather(*(self._process_candidate(item, crawler) for item in candidates))
        return dedupe_records(record for record in records if record is not None)


def write_outputs(records: list[StoreRecord], debug_records: list[dict[str, Any]], output_dir: str | Path) -> None:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_rows = [record.model_dump(mode="json") for record in records]
    (target / "indian_shopify_stores.json").write_text(
        json.dumps(json_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    debug_target = target.parent / "intermediate" if target.name == "output" else target
    debug_target.mkdir(parents=True, exist_ok=True)
    (debug_target / "pipeline_debug.json").write_text(
        json.dumps(debug_records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    csv_rows = [
        {
            "domain_url": record.domain_url,
            "contacts": json.dumps({"emails": record.emails, "phones": record.phones}, ensure_ascii=False),
            "socials": json.dumps(record.socials, ensure_ascii=False),
            "category": record.category,
            "tagline_or_description": record.tagline_or_description,
            "logo_url": record.logo_url,
            "state": record.state,
            "shopify_score": record.shopify_score,
            "india_score": record.india_score,
            "shopify_confidence": record.shopify_confidence.value,
            "india_confidence": record.india_confidence.value,
        }
        for record in records
    ]
    columns = [
        "domain_url", "contacts", "socials", "category", "tagline_or_description", "logo_url", "state",
        "shopify_score", "india_score", "shopify_confidence", "india_confidence",
    ]
    pd.DataFrame(csv_rows, columns=columns).to_csv(target / "indian_shopify_stores.csv", index=False)


async def run_from_file(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    settings: Settings = SETTINGS,
    limit: int | None = None,
) -> list[StoreRecord]:
    candidates = load_candidates(input_path, limit)
    LOGGER.info("[DISCOVER] loaded %s unique candidates", len(candidates))
    pipeline = StorePipeline(settings)
    records = await pipeline.run(candidates)
    write_outputs(records, pipeline.debug_records, output_dir)
    return records

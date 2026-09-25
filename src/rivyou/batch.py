"""Resumable SQLite-backed batch processing."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

from rivyou.config import SETTINGS, Settings
from rivyou.crawler import AsyncCrawler
from rivyou.discover.fingerprints import PreFilterResult, prefilter_shopify
from rivyou.models import CandidateRecord, CandidateStatus, StoreCandidate, StoreRecord
from rivyou.pipeline import StorePipeline
from rivyou.storage.cache import SQLiteHTTPCache
from rivyou.storage.sqlite_store import SQLiteStore

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BatchOutcome:
    run_id: int
    selected: int
    prefilter_passed: int
    shopify_verified: int
    india_verified: int
    accepted: int
    rejected_shopify: int
    rejected_india: int
    retry: int
    failed: int
    runtime_seconds: float
    domains_per_minute: float
    accepted_per_minute: float
    average_shopify_score: float | None
    average_india_score: float | None


def normalize_retry_reason(error: str | None) -> str:
    """Map varying transport messages to stable operational retry categories."""
    value = (error or "").lower()
    if "robots.txt" in value:
        return "ROBOTS_BLOCKED"
    if "429" in value:
        return "HTTP_429"
    match = re.search(r"http\s+(5\d\d)", value)
    if match:
        return "HTTP_5XX"
    if "timeout" in value or "timed out" in value:
        return "TIMEOUT"
    if any(token in value for token in ("name or service not known", "nodename nor servname", "dns", "getaddrinfo")):
        return "DNS_ERROR"
    if any(token in value for token in ("ssl", "certificate", "tls")):
        return "SSL_ERROR"
    if any(token in value for token in ("connect", "network", "transporterror")):
        return "CONNECTION_ERROR"
    return "OTHER_TRANSIENT"


class BatchRunner:
    def __init__(self, store: SQLiteStore, settings: Settings = SETTINGS, use_cache: bool = True):
        self.store = store
        self.settings = settings
        self.use_cache = use_cache

    async def run(
        self,
        statuses: list[CandidateStatus],
        limit: int,
        recover_stale_minutes: int | None = None,
        wave: str | None = None,
    ) -> BatchOutcome:
        started = time.perf_counter()
        if recover_stale_minutes is not None:
            recovered = self.store.recover_stale(recover_stale_minutes)
            LOGGER.info("[RECOVER] moved %s stale candidates to RETRY", recovered)
        candidates = self.store.list_candidates(statuses, limit)
        run_id = self.store.create_run(",".join(status.value for status in statuses), limit, wave=wave)
        counts = {"accepted": 0, "rejected_shopify": 0, "rejected_india": 0, "retry": 0, "failed": 0}
        processing: list[CandidateRecord] = []
        for candidate in candidates:
            if candidate.attempt_count >= self.settings.max_candidate_attempts:
                self.store.transition(
                    candidate.normalized_domain, CandidateStatus.FAILED,
                    error=f"Retry budget exhausted after {candidate.attempt_count} attempts",
                    retry_reason=candidate.retry_reason or "RETRY_BUDGET_EXHAUSTED",
                )
                counts["failed"] += 1
                continue
            self.store.transition(candidate.normalized_domain, CandidateStatus.PROCESSING, increment_attempt=True)
            processing.append(candidate)
        cache = SQLiteHTTPCache(self.store, self.settings.cache_ttl_hours)
        prefilter_passed = shopify_verified = india_verified = 0
        shopify_scores: list[int] = []
        india_scores: list[int] = []
        try:
            async with AsyncCrawler(self.settings, cache=cache, use_cache=self.use_cache) as crawler:
                checks = await asyncio.gather(*(
                    prefilter_shopify(item.normalized_domain, crawler, self.settings.prefilter_score_threshold)
                    for item in processing
                ), return_exceptions=True)
                plausible: list[CandidateRecord] = []
                for candidate, check in zip(processing, checks):
                    if isinstance(check, Exception):
                        error = str(check)
                        self.store.transition(
                            candidate.normalized_domain, CandidateStatus.RETRY, error=error,
                            retry_reason=normalize_retry_reason(error),
                        )
                        counts["retry"] += 1
                    elif check.error:
                        self.store.set_prefilter(candidate.normalized_domain, check.model_dump(mode="json"))
                        self.store.transition(
                            candidate.normalized_domain, CandidateStatus.RETRY, error=check.error,
                            retry_reason=normalize_retry_reason(check.error),
                        )
                        counts["retry"] += 1
                    elif not check.plausible:
                        shopify_scores.append(check.score)
                        payload = check.model_dump(mode="json")
                        self.store.set_prefilter(candidate.normalized_domain, payload)
                        self.store.transition(
                            candidate.normalized_domain, CandidateStatus.REJECTED_SHOPIFY,
                            error="Homepage pre-filter found insufficient Shopify evidence", evidence={"prefilter": payload},
                            shopify_score=check.score,
                        )
                        counts["rejected_shopify"] += 1
                    else:
                        self.store.set_prefilter(candidate.normalized_domain, check.model_dump(mode="json"))
                        plausible.append(candidate)
                prefilter_passed = len(plausible)

                if plausible:
                    pipeline = StorePipeline(self.settings, crawler=crawler)
                    await pipeline.run([
                        StoreCandidate(original_url=item.original_url, normalized_domain=item.normalized_domain)
                        for item in plausible
                    ])
                    debug_by_domain = {
                        item["candidate"]["normalized_domain"]: item for item in pipeline.debug_records
                    }
                    for candidate in plausible:
                        debug = debug_by_domain.get(candidate.normalized_domain)
                        if not debug:
                            self.store.transition(candidate.normalized_domain, CandidateStatus.FAILED, error="Missing pipeline result")
                            counts["failed"] += 1
                            continue
                        shopify = debug.get("shopify", {})
                        india = debug.get("india", {})
                        if shopify.get("score") is not None:
                            shopify_scores.append(int(shopify["score"]))
                        if india.get("score") is not None:
                            india_scores.append(int(india["score"]))
                        if debug.get("accepted") and debug.get("record"):
                            shopify_verified += 1
                            india_verified += 1
                            record = StoreRecord.model_validate(debug["record"])
                            self.store.save_store_result(candidate.normalized_domain, record)
                            self.store.transition(
                                candidate.normalized_domain, CandidateStatus.ACCEPTED, evidence=debug,
                                shopify_score=record.shopify_score, india_score=record.india_score,
                            )
                            counts["accepted"] += 1
                        elif "Shopify" in debug.get("rejection_reason", ""):
                            self.store.transition(
                                candidate.normalized_domain, CandidateStatus.REJECTED_SHOPIFY,
                                error=debug.get("rejection_reason"), evidence=debug, shopify_score=shopify.get("score"),
                            )
                            counts["rejected_shopify"] += 1
                        elif "India" in debug.get("rejection_reason", ""):
                            shopify_verified += 1
                            self.store.transition(
                                candidate.normalized_domain, CandidateStatus.REJECTED_INDIA,
                                error=debug.get("rejection_reason"), evidence=debug,
                                shopify_score=shopify.get("score"), india_score=india.get("score"),
                            )
                            counts["rejected_india"] += 1
                        else:
                            error = debug.get("rejection_reason", "Transient pipeline failure")
                            self.store.transition(
                                candidate.normalized_domain, CandidateStatus.RETRY,
                                error=error, retry_reason=normalize_retry_reason(error), evidence=debug,
                            )
                            counts["retry"] += 1
        except Exception as exc:
            LOGGER.exception("[BATCH] run failed")
            for candidate in processing:
                current = self.store.get_candidate(candidate.normalized_domain)
                if current and current.status == CandidateStatus.PROCESSING:
                    self.store.transition(candidate.normalized_domain, CandidateStatus.FAILED, error=str(exc))
                    counts["failed"] += 1
        finally:
            elapsed = time.perf_counter() - started
            self.store.finish_run(
                run_id, len(candidates), counts["accepted"], verification_seconds=elapsed, total_seconds=elapsed,
                funnel={
                    "prefilter_passed": prefilter_passed,
                    "shopify_verified": shopify_verified,
                    "india_verified": india_verified,
                    **counts,
                    "average_shopify_score": sum(shopify_scores) / len(shopify_scores) if shopify_scores else None,
                    "average_india_score": sum(india_scores) / len(india_scores) if india_scores else None,
                },
            )
        minutes = elapsed / 60 if elapsed else 0.0
        return BatchOutcome(
            run_id=run_id, selected=len(candidates), prefilter_passed=prefilter_passed,
            shopify_verified=shopify_verified, india_verified=india_verified, **counts, runtime_seconds=elapsed,
            domains_per_minute=len(candidates) / minutes if minutes else 0.0,
            accepted_per_minute=counts["accepted"] / minutes if minutes else 0.0,
            average_shopify_score=sum(shopify_scores) / len(shopify_scores) if shopify_scores else None,
            average_india_score=sum(india_scores) / len(india_scores) if india_scores else None,
        )

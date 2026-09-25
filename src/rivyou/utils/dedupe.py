"""Stable candidate and record deduplication."""

from __future__ import annotations

from collections.abc import Iterable

from rivyou.models import StoreCandidate, StoreRecord
from rivyou.utils.domains import registered_domain


def dedupe_candidates(candidates: Iterable[StoreCandidate]) -> list[StoreCandidate]:
    seen: set[str] = set()
    result: list[StoreCandidate] = []
    for candidate in candidates:
        key = registered_domain(candidate.normalized_domain)
        if key and key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def dedupe_records(records: Iterable[StoreRecord]) -> list[StoreRecord]:
    best: dict[str, StoreRecord] = {}
    order: list[str] = []
    for record in records:
        key = registered_domain(record.domain_url)
        if not key:
            continue
        if key not in best:
            order.append(key)
            best[key] = record
        elif record.shopify_score + record.india_score > best[key].shopify_score + best[key].india_score:
            best[key] = record
    return [best[key] for key in order]

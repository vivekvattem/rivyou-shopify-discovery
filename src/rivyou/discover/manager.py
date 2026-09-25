"""Discovery provider orchestration and provenance-aware persistence."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from rivyou.discover.base import DiscoveryProvider
from rivyou.discover.provenance import calculate_priority
from rivyou.storage.sqlite_store import SQLiteStore


@dataclass(slots=True)
class DiscoveryStats:
    rows_read: int = 0
    raw_urls: int = 0
    normalized_domains: int = 0
    new_unique_domains: int = 0
    existing_domains: int = 0
    duplicates: int = 0
    invalid_rows: int = 0
    source_breakdown: Counter[str] = field(default_factory=Counter)


class DiscoveryManager:
    def __init__(self, store: SQLiteStore):
        self.store = store

    async def run(self, providers: list[DiscoveryProvider], limit: int | None = None) -> DiscoveryStats:
        stats = DiscoveryStats()
        seen: set[str] = set()
        for provider in providers:
            remaining = None if limit is None else max(0, limit - stats.normalized_domains)
            if remaining == 0:
                break
            records = await provider.discover(remaining)
            raw_count = getattr(provider, "raw_count", len(records))
            stats.rows_read += getattr(provider, "rows_read", raw_count)
            stats.raw_urls += raw_count
            stats.invalid_rows += getattr(provider, "invalid_count", max(0, raw_count - len(records)))
            stats.normalized_domains += len(records)
            for record in records:
                stats.source_breakdown[provider.name] += 1
                outcome = self.store.upsert_candidate(record)
                if record.normalized_domain in seen:
                    stats.duplicates += 1
                elif outcome.created:
                    stats.new_unique_domains += 1
                else:
                    stats.existing_domains += 1
                seen.add(record.normalized_domain)
                merged = self.store.get_candidate(record.normalized_domain)
                if merged:
                    self.store.update_priority(record.normalized_domain, calculate_priority(merged))
        return stats

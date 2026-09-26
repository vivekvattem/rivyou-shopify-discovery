"""Terminal/JSON quality and funnel reporting."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

from rivyou.models import CandidateStatus
from rivyou.storage.sqlite_store import SQLiteStore
from rivyou.utils.dedupe import dedupe_records


def build_report(store: SQLiteStore) -> dict[str, Any]:
    counts = store.status_counts()
    records = dedupe_records(store.accepted_records())
    total = len(records)

    def missing(attribute: str) -> float:
        return round(100 * sum(not getattr(item, attribute) for item in records) / total, 1) if total else 0.0

    def with_rates(row: dict[str, Any]) -> dict[str, Any]:
        candidates = row["candidates"]
        acceptance_rate = round(100 * row["accepted"] / candidates, 1) if candidates else 0.0
        return {
            **row,
            "acceptance_rate": acceptance_rate,
            "shopify_rejection_rate": round(100 * row["rejected_shopify"] / candidates, 1) if candidates else 0.0,
            "india_rejection_rate": round(100 * row["rejected_india"] / candidates, 1) if candidates else 0.0,
            "failure_rate": round(100 * row["failed"] / candidates, 1) if candidates else 0.0,
            "sample_size_label": (
                "high_volume" if candidates >= 30 else "meaningful" if candidates >= 10 else "tiny"
            ),
            "high_volume_high_yield": candidates >= 30 and acceptance_rate >= 75.0,
        }

    sources = [with_rates(row) for row in store.source_stats()]
    query_families = []
    for row in store.query_family_stats():
        location = row["location"]
        if location and '"' in location:
            quoted = [value for value in re.findall(r'"([^"]+)"', location) if value != row["signal"]]
            location = quoted[0] if quoted else location
        family = "/".join(filter(None, (row["source"], row["signal"], location)))
        query_families.append(with_rates({**row, "location": location, "query_family": family or row["source"]}))
    query_quality = [with_rates(row) for row in store.query_stats()]
    location_quality = [with_rates(row) for row in store.location_stats()]
    category_hint_quality = [with_rates(row) for row in store.category_hint_stats()]
    quality_sets = {
        "sources": sources,
        "query_families": query_families,
        "exact_queries": query_quality,
        "locations": location_quality,
        "category_hints": category_hint_quality,
    }
    return {
        "total_candidates": sum(counts.values()),
        "status_counts": {status.value: counts.get(status.value, 0) for status in CandidateStatus},
        "acceptance_funnel": {
            **store.aggregate_stats(),
            "accepted": counts.get(CandidateStatus.ACCEPTED.value, 0),
            "usable_final_records": total,
        },
        "top_discovery_sources": sources,
        "query_family_quality": query_families,
        "query_quality": query_quality,
        "location_quality": location_quality,
        "category_hint_quality": category_hint_quality,
        "high_volume_high_yield_highlights": {
            name: [row for row in rows if row["high_volume_high_yield"]]
            for name, rows in quality_sets.items()
        },
        "retry_reason_counts": store.retry_reason_counts(),
        "shopify_rejection_rate": round(100 * counts.get("REJECTED_SHOPIFY", 0) / sum(counts.values()), 1) if counts else 0.0,
        "india_rejection_rate": round(100 * counts.get("REJECTED_INDIA", 0) / sum(counts.values()), 1) if counts else 0.0,
        "missing_field_percentages": {
            "emails": round(100 * sum(not item.emails for item in records) / total, 1) if total else 0.0,
            "phones": round(100 * sum(not item.phones for item in records) / total, 1) if total else 0.0,
            "socials": round(100 * sum(not any(item.socials.values()) for item in records) / total, 1) if total else 0.0,
            "category": missing("category"), "description": missing("tagline_or_description"),
            "logo": missing("logo_url"), "state": missing("state"),
        },
        "state_distribution": dict(Counter(item.state or "Unknown" for item in records)),
        "category_distribution": dict(Counter(item.category or "Other" for item in records)),
        "duplicate_reduction": store.aggregate_stats()["raw_discoveries"] - store.aggregate_stats()["total"],
        "recent_runs": store.latest_runs(10),
    }

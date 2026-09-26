"""Terminal/JSON quality and funnel reporting."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

from rivyou.models import CandidateStatus
from rivyou.storage.sqlite_store import SQLiteStore


def build_report(store: SQLiteStore) -> dict[str, Any]:
    counts = store.status_counts()
    records = store.accepted_records()
    total = len(records)

    def missing(attribute: str) -> float:
        return round(100 * sum(not getattr(item, attribute) for item in records) / total, 1) if total else 0.0

    def with_rates(row: dict[str, Any]) -> dict[str, Any]:
        candidates = row["candidates"]
        return {
            **row,
            "acceptance_rate": round(100 * row["accepted"] / candidates, 1) if candidates else 0.0,
            "shopify_rejection_rate": round(100 * row["rejected_shopify"] / candidates, 1) if candidates else 0.0,
            "india_rejection_rate": round(100 * row["rejected_india"] / candidates, 1) if candidates else 0.0,
        }

    sources = store.source_stats()
    query_families = []
    for row in store.query_family_stats():
        location = row["location"]
        if location and '"' in location:
            quoted = [value for value in re.findall(r'"([^"]+)"', location) if value != row["signal"]]
            location = quoted[0] if quoted else location
        family = "/".join(filter(None, (row["source"], row["signal"], location)))
        query_families.append(with_rates({**row, "location": location, "query_family": family or row["source"]}))
    return {
        "total_candidates": sum(counts.values()),
        "status_counts": {status.value: counts.get(status.value, 0) for status in CandidateStatus},
        "acceptance_funnel": {
            **store.aggregate_stats(),
            "accepted": counts.get(CandidateStatus.ACCEPTED.value, 0),
            "usable_final_records": total,
        },
        "top_discovery_sources": [with_rates(row) for row in sources],
        "query_family_quality": query_families,
        "query_quality": [with_rates(row) for row in store.query_stats()],
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

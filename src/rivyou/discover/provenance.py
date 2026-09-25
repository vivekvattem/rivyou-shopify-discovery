"""Discovery-only priority scoring."""

from __future__ import annotations

from urllib.parse import urlsplit

from rivyou.extract.location import CITY_TO_STATE, INDIAN_STATES_AND_UTS
from rivyou.models import CandidateRecord

STRONG_DISCOVERY_SIGNALS = {
    "cdn.shopify.com", "/cdn/shop/", "shopify.theme", "shopifyanalytics", "myshopify.com"
}


def calculate_priority(candidate: CandidateRecord) -> int:
    """Rank processing order only; this score is never verification evidence."""
    score = 0
    normalized_signals = {signal.lower() for signal in candidate.signals}
    if normalized_signals & STRONG_DISCOVERY_SIGNALS:
        score += 3
    independent_sources = {item.source for item in candidate.provenance}
    if len(independent_sources) >= 2:
        score += 2
    provenance_text = " ".join(item.query or "" for item in candidate.provenance).lower()
    locations = [*INDIAN_STATES_AND_UTS, *CITY_TO_STATE]
    if any(location.lower() in provenance_text for location in locations):
        score += 2
    host = (urlsplit(candidate.normalized_domain).hostname or "").lower()
    if host.endswith(".in"):
        score += 1
    if candidate.discovery_count > 1:
        score += 1
    return score


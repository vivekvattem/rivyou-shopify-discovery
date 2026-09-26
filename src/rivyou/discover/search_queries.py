"""Search query generation and manual/API result ingestion."""

from __future__ import annotations

import csv
from pathlib import Path

from rivyou.extract.location import CITY_TO_STATE, INDIAN_STATES_AND_UTS
from rivyou.models import CandidateProvenance, CandidateRecord
from rivyou.utils.domains import normalize_domain

SHOPIFY_SIGNALS = (
    '"cdn.shopify.com"', '"/cdn/shop/"', '"Shopify.theme"', '"shopify-section"', '"Powered by Shopify"'
)
MAJOR_COMMERCIAL_CITIES = (
    "Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad", "Pune", "Ahmedabad", "Surat", "Jaipur",
    "Kolkata", "Kochi", "Noida", "Gurugram", "Lucknow", "Indore", "Coimbatore", "Chandigarh",
    "Nagpur", "Vadodara", "Bhubaneswar", "Guwahati", "Patna", "Nashik", "Jodhpur", "Panaji",
)
PRIORITY_CITIES = (
    "Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad", "Pune", "Ahmedabad", "Surat", "Jaipur",
    "Kolkata", "Gurugram", "Noida", "Kochi", "Coimbatore", "Indore", "Lucknow",
)
CATEGORY_HINTS = (
    "clothing", "fashion", "jewellery", "skincare", "beauty", "home decor", "food", "footwear",
    "accessories", "fitness", "kids", "furniture",
)
SIGNAL_PRIORITY = {
    "Powered by Shopify": 5,
    "cdn.shopify.com": 5,
    "/cdn/shop/": 5,
    "Shopify.theme": 3,
    "shopify-section": 2,
}


def generate_search_queries() -> list[dict[str, str | int]]:
    locations: list[tuple[str, int]] = [(city, 3) for city in MAJOR_COMMERCIAL_CITIES]
    known = {city.lower() for city in MAJOR_COMMERCIAL_CITIES}
    locations.extend((state, 2) for state in INDIAN_STATES_AND_UTS if state.lower() not in known)
    queries: list[dict[str, str | int]] = []
    for location, location_priority in locations:
        for signal in SHOPIFY_SIGNALS:
            clean_signal = signal.strip('"')
            queries.append({
                "query": f'{signal} "{location}"',
                "priority": location_priority + SIGNAL_PRIORITY[clean_signal],
                "location": location,
                "shopify_signal": clean_signal,
                "category_hint": "",
            })
    high_yield_signals = SHOPIFY_SIGNALS[0], SHOPIFY_SIGNALS[1], SHOPIFY_SIGNALS[-1]
    for index, city in enumerate(PRIORITY_CITIES):
        category = CATEGORY_HINTS[index % len(CATEGORY_HINTS)]
        for signal in high_yield_signals:
            clean_signal = signal.strip('"')
            queries.append({
                "query": f'{signal} "{city}" {category}',
                "priority": 10 + SIGNAL_PRIORITY[clean_signal],
                "location": city,
                "shopify_signal": clean_signal,
                "category_hint": category,
            })
    for index, category in enumerate(CATEGORY_HINTS):
        signal = high_yield_signals[index % len(high_yield_signals)]
        clean_signal = signal.strip('"')
        queries.append({
            "query": f'{signal} "India" {category}',
            "priority": 12 + SIGNAL_PRIORITY[clean_signal],
            "location": "India",
            "shopify_signal": clean_signal,
            "category_hint": category,
        })
    return sorted(queries, key=lambda row: (-int(row["priority"]), str(row["location"]), str(row["shopify_signal"])))


def export_search_queries(path: str | Path) -> int:
    rows = generate_search_queries()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["query", "priority", "shopify_signal", "location", "category_hint"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


class SearchResultsCSVProvider:
    name = "search-csv"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.raw_count = 0
        self.rows_read = 0
        self.invalid_count = 0

    async def discover(self, limit: int | None = None) -> list[CandidateRecord]:
        records: list[CandidateRecord] = []
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fields = {field.lower(): field for field in (reader.fieldnames or [])}
            if "query" not in fields or "result_url" not in fields:
                raise ValueError("Search result CSV must contain query,result_url")
            for row in reader:
                self.rows_read += 1
                original = (row.get(fields["result_url"]) or "").strip()
                query = (row.get(fields["query"]) or "").strip()
                if not original:
                    self.invalid_count += 1
                    continue
                self.raw_count += 1
                normalized = normalize_domain(original)
                if not normalized:
                    self.invalid_count += 1
                    continue
                signal = next((value.strip('"') for value in SHOPIFY_SIGNALS if value.strip('"').lower() in query.lower()), None)
                location = (row.get(fields.get("location", "")) or "").strip() or None
                category_hint = (row.get(fields.get("category_hint", "")) or "").strip() or None
                provenance = CandidateProvenance(
                    source=self.name, query=query or None, location=location, source_url=str(self.path), signal=signal,
                    category_hint=category_hint,
                )
                records.append(CandidateRecord(
                    normalized_domain=normalized, original_url=original, discovery_source=self.name,
                    discovery_query=query or None, source_url=str(self.path), signals=[signal] if signal else [],
                    provenance=[provenance],
                ))
                if limit is not None and len(records) >= limit:
                    break
        return records

"""Accepted-store field-completeness diagnostics."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from rivyou.models import StoreRecord
from rivyou.storage.sqlite_store import SQLiteStore

FIELDS = ("emails", "phones", "socials", "category", "description", "logo", "state")


def missing_fields_for_record(record) -> list[str]:
    missing: list[str] = []
    if not record.emails:
        missing.append("emails")
    if not record.phones:
        missing.append("phones")
    if not any(record.socials.values()):
        missing.append("socials")
    if not record.category:
        missing.append("category")
    if not record.tagline_or_description:
        missing.append("description")
    if not record.logo_url:
        missing.append("logo")
    if not record.state:
        missing.append("state")
    return missing


def write_missing_fields_report(store: SQLiteStore, path: str | Path) -> dict[str, float]:
    records = store.accepted_records()
    counts = {field: 0 for field in FIELDS}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["domain", "missing_fields", "shopify_score", "india_score"])
        writer.writeheader()
        for record in records:
            missing = missing_fields_for_record(record)
            for field in missing:
                counts[field] += 1
            if missing:
                writer.writerow({
                    "domain": record.domain_url,
                    "missing_fields": ",".join(missing),
                    "shopify_score": record.shopify_score,
                    "india_score": record.india_score,
                })
    total = len(records)
    return {field: round(100 * count / total, 1) if total else 0.0 for field, count in counts.items()}


def render_missing_fields_markdown(records: Iterable[StoreRecord]) -> str:
    rows = list(records)
    total = len(rows)
    counts = {
        "Domain": sum(not item.domain_url for item in rows),
        "Contacts": sum(not item.emails and not item.phones for item in rows),
        "Email": sum(not item.emails for item in rows),
        "Phone": sum(not item.phones for item in rows),
        "Socials": sum(not any(item.socials.values()) for item in rows),
        "Category": sum(not item.category for item in rows),
        "Description": sum(not item.tagline_or_description for item in rows),
        "Logo": sum(not item.logo_url for item in rows),
        "State": sum(not item.state for item in rows),
    }
    lines = [
        "# Final export completeness", "", f"Based on {total} exported records.", "",
        "| Field | Missing count | Missing % |", "|---|---:|---:|",
    ]
    for field, count in counts.items():
        percentage = 100 * count / total if total else 0.0
        lines.append(f"| {field} | {count} | {percentage:.1f}% |")
    lines.extend([
        "", "An empty optional field means no qualifying value was found in the bounded static pages; values are not guessed.",
        "Phone and social rows count only normalized telephone numbers and validated merchant-profile URLs respectively.",
        "State remains empty when the available evidence cannot identify a business location safely.", "",
    ])
    return "\n".join(lines)


def write_missing_fields_markdown(records: Iterable[StoreRecord], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_missing_fields_markdown(records), encoding="utf-8")
    return target

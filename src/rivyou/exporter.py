"""Export public assignment fields separately from debug evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from rivyou.audit.diagnostics import write_missing_fields_markdown
from rivyou.storage.sqlite_store import SQLiteStore
from rivyou.utils.dedupe import dedupe_records


def export_accepted(store: SQLiteStore, output_dir: str | Path) -> int:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    records = dedupe_records(store.accepted_records())
    public_rows = [{
        "domain_url": item.domain_url,
        "contacts": {"emails": item.emails, "phones": item.phones},
        "socials": item.socials,
        "category": item.category,
        "tagline_or_description": item.tagline_or_description,
        "logo_url": item.logo_url,
        "state": item.state,
        "shopify_score": item.shopify_score,
        "india_score": item.india_score,
    } for item in records]
    (target / "indian_shopify_stores.json").write_text(
        json.dumps(public_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    csv_rows = [{
        **row,
        "contacts": json.dumps(row["contacts"], ensure_ascii=False),
        "socials": json.dumps(row["socials"], ensure_ascii=False),
    } for row in public_rows]
    columns = [
        "domain_url", "contacts", "socials", "category", "tagline_or_description", "logo_url", "state",
        "shopify_score", "india_score",
    ]
    pd.DataFrame(csv_rows, columns=columns).to_csv(target / "indian_shopify_stores.csv", index=False)
    (target / "store_debug.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in records], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_missing_fields_markdown(records, target / "missing_fields.md")
    return len(records)

"""Generate blank manual-review worksheets from pipeline status strata."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from rivyou.models import CandidateStatus
from rivyou.storage.sqlite_store import SQLiteStore

AUDIT_COLUMNS = (
    "domain", "pipeline_status", "shopify_score", "india_score", "category", "state", "logo_url",
    "emails", "phones", "socials", "shopify_evidence", "india_evidence",
    "manual_shopify_correct", "manual_india_correct", "manual_logo_correct", "manual_state_correct",
    "manual_contacts_correct", "manual_notes",
)


def create_audit_sample(
    store: SQLiteStore,
    output_dir: str | Path,
    accepted: int = 30,
    rejected_shopify: int = 10,
    rejected_india: int = 10,
) -> Path:
    rows: list[dict[str, object]] = []
    for status, limit in (
        (CandidateStatus.ACCEPTED, accepted),
        (CandidateStatus.REJECTED_SHOPIFY, rejected_shopify),
        (CandidateStatus.REJECTED_INDIA, rejected_india),
    ):
        for source in store.candidate_detail_rows(status, limit):
            try:
                verification = json.loads(source.get("verification_json") or "{}")
            except json.JSONDecodeError:
                verification = {}
            record = verification.get("record") or {}
            rows.append({
                "domain": source["domain"],
                "pipeline_status": source["status"],
                "shopify_score": source.get("shopify_score") or "",
                "india_score": source.get("india_score") or "",
                "category": record.get("category", ""),
                "state": record.get("state", ""),
                "logo_url": record.get("logo_url", ""),
                "emails": json.dumps(record.get("emails", []), ensure_ascii=False),
                "phones": json.dumps(record.get("phones", []), ensure_ascii=False),
                "socials": json.dumps(record.get("socials", {}), ensure_ascii=False),
                "shopify_evidence": json.dumps(verification.get("shopify", verification.get("prefilter", {})), ensure_ascii=False),
                "india_evidence": json.dumps(verification.get("india", {}), ensure_ascii=False),
                "manual_shopify_correct": "",
                "manual_india_correct": "",
                "manual_logo_correct": "",
                "manual_state_correct": "",
                "manual_contacts_correct": "",
                "manual_notes": "",
            })
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"audit_{timestamp}.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return target

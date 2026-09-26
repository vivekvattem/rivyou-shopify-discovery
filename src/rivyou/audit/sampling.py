"""Generate blank manual-review worksheets from pipeline status strata."""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from rivyou.models import CandidateStatus
from rivyou.audit.automated import AUTO_AUDIT_COLUMNS, MANUAL_COLUMNS
from rivyou.storage.sqlite_store import SQLiteStore

AUDIT_COLUMNS = (
    "domain", "pipeline_status", "shopify_score", "india_score", "category", "state", "logo_url",
    "emails", "phones", "socials", "shopify_evidence", "india_evidence",
    "manual_shopify_correct", "manual_india_correct", "manual_logo_correct", "manual_state_correct",
    "manual_contacts_correct", "manual_notes",
)

TARGETED_AUDIT_COLUMNS = (*AUTO_AUDIT_COLUMNS, "selection_reason")


def create_targeted_accepted_sample(
    auto_audit_path: str | Path,
    output_dir: str | Path,
    *,
    target: int = 15,
    seed: int = 3,
    review_all_limit: int = 30,
) -> Path:
    """Select accepted stores that expose quality risk, then fill with random HIGH rows.

    LOW-confidence rows are always considered first.  When the combined LOW and
    MEDIUM set is small enough to review reasonably, include all of it; otherwise
    use the available worksheet capacity for LOW rows before sampling MEDIUM rows.
    """
    with Path(auto_audit_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    selected: dict[str, dict[str, str]] = {}
    reasons: dict[str, list[str]] = {}

    def add(row: dict[str, str], reason: str) -> None:
        domain = row["domain"]
        if domain not in selected and len(selected) >= target:
            return
        selected.setdefault(domain, row)
        reasons.setdefault(domain, [])
        if reason not in reasons[domain]:
            reasons[domain].append(reason)

    def score(row: dict[str, str], field: str) -> int:
        try:
            return int(row.get(field) or 0)
        except ValueError:
            return 0

    low = [row for row in rows if row.get("auto_audit_confidence") == "LOW"]
    medium = [row for row in rows if row.get("auto_audit_confidence") == "MEDIUM"]
    uncertain = [*low, *medium]
    if len(uncertain) <= min(target, review_all_limit):
        for row in uncertain:
            add(row, f"all_{row['auto_audit_confidence'].lower()}_confidence")
    else:
        for row in low:
            add(row, "sample_low_confidence")
        for row in medium:
            add(row, "sample_medium_confidence")

    for row in sorted(rows, key=lambda item: (score(item, "shopify_score"), item["domain"]))[:2]:
        add(row, "lowest_shopify_score")
    for row in sorted(rows, key=lambda item: (score(item, "india_score"), item["domain"]))[:2]:
        add(row, "lowest_india_score")

    missing_fields = (
        ("state", "missing_state"),
        ("tagline_or_description", "missing_description"),
        ("logo_url", "missing_logo"),
    )
    for field, reason in missing_fields:
        missing = next((row for row in rows if not (row.get(field) or "").strip()), None)
        if missing:
            add(missing, reason)

    unusual = [
        row for row in rows
        if row.get("auto_contacts_check") != "PASS" or row.get("auto_socials_check") in {"FAIL", "UNCERTAIN"}
    ]
    for row in unusual[:2]:
        add(row, "unusual_contact_or_social")

    high = [row for row in rows if row.get("auto_audit_confidence") == "HIGH"]
    random.Random(seed).shuffle(high)
    for row in high:
        add(row, "random_high_confidence")
        if len(selected) >= target:
            break
    for row in rows:
        add(row, "random_accepted_fill")
        if len(selected) >= target:
            break

    output_rows: list[dict[str, str]] = []
    for domain, source in selected.items():
        row = {column: source.get(column, "") for column in AUTO_AUDIT_COLUMNS}
        for column in MANUAL_COLUMNS:
            row[column] = ""
        row["selection_reason"] = ";".join(reasons[domain])
        output_rows.append(row)

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_path = target_dir / f"targeted_accepted_audit_{timestamp}.csv"
    with target_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TARGETED_AUDIT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)
    return target_path


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

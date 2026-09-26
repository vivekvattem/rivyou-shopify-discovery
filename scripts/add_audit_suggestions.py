#!/usr/bin/env python3
"""Add evidence-derived suggestions to an audit worksheet without touching manual fields."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

SUGGESTION_COLUMNS = (
    "suggested_shopify",
    "suggested_india",
    "suggested_logo",
    "suggested_state",
    "suggested_contacts",
    "suggested_notes",
    "review_priority",
)
MANUAL_COLUMNS = (
    "manual_shopify_correct",
    "manual_india_correct",
    "manual_logo_correct",
    "manual_state_correct",
    "manual_contacts_correct",
    "manual_notes",
)
VERDICT_SUGGESTIONS = {
    "PASS": "yes",
    "FAIL": "no",
    "MISSING": "missing",
    "UNCERTAIN": "uncertain",
}


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def suggest(row: dict[str, str]) -> dict[str, str]:
    result = {
        "suggested_shopify": VERDICT_SUGGESTIONS[row["auto_shopify_check"]],
        "suggested_india": VERDICT_SUGGESTIONS[row["auto_india_check"]],
        "suggested_logo": VERDICT_SUGGESTIONS[row["auto_logo_check"]],
        "suggested_state": VERDICT_SUGGESTIONS[row["auto_state_check"]],
        "suggested_contacts": VERDICT_SUGGESTIONS[row["auto_contacts_check"]],
    }
    notes: list[str] = []

    if not row.get("state", "").strip() and row["auto_state_check"] in {"MISSING", "UNCERTAIN"}:
        result["suggested_state"] = "missing"
        notes.append("state absent; no reliable contextual business state in automated evidence")

    emails = _json_list(row.get("emails", ""))
    phones = _json_list(row.get("phones", ""))
    if not emails and not phones:
        result["suggested_contacts"] = "missing"
        notes.append("no stored merchant contacts")
    elif len(phones) > 5 or any(email.lower().endswith(".comin") for email in emails):
        result["suggested_contacts"] = "uncertain"
        notes.append("extracted contact set is anomalous and needs manual ownership review")
    elif row["auto_contacts_check"] == "PASS":
        notes.append("stored contacts were confirmed on merchant pages")
    else:
        notes.append("stored contacts could not be reconfirmed")

    if result["suggested_logo"] == "no":
        notes.append("automated logo evidence reports a conflicting or invalid asset")
    elif result["suggested_logo"] == "missing":
        notes.append("no stored logo URL")
    if result["suggested_india"] == "uncertain":
        notes.append("India evidence is unavailable or lacks strong business-location support")
    elif result["suggested_india"] == "yes":
        notes.append("automated India evidence includes a strong signal")

    suggestions = tuple(result.values())
    if (
        row["auto_audit_confidence"] == "LOW"
        or "no" in suggestions
        or result["suggested_shopify"] == "uncertain"
        or result["suggested_india"] == "uncertain"
        or result["suggested_contacts"] == "uncertain"
    ):
        priority = "HIGH"
    elif row["auto_audit_confidence"] == "MEDIUM" or any(
        value in {"missing", "uncertain"} for value in suggestions
    ):
        priority = "MEDIUM"
    else:
        priority = "LOW"

    result["suggested_notes"] = "; ".join(notes)
    result["review_priority"] = priority
    return result


def create_suggested_worksheet(source: Path, target: Path) -> None:
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        source_columns = reader.fieldnames or []
    if any(column not in source_columns for column in MANUAL_COLUMNS):
        raise ValueError("source worksheet is missing required manual columns")

    output_rows = [{**row, **suggest(row)} for row in rows]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*source_columns, *SUGGESTION_COLUMNS])
        writer.writeheader()
        writer.writerows(output_rows)

    for before, after in zip(rows, output_rows, strict=True):
        if any(before[column] != after[column] for column in MANUAL_COLUMNS):
            raise AssertionError(f"manual column changed for {before.get('domain', 'unknown row')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    create_suggested_worksheet(args.source, args.target)
    print(f"Suggested worksheet written to {args.target}")

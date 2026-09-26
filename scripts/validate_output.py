#!/usr/bin/env python3
"""Validate output uniqueness, URLs, field coverage, and confidence distribution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.extract.logo import REJECT_LOGO_RE  # noqa: E402
from rivyou.config import INDIA_SCORE_THRESHOLD, SHOPIFY_SCORE_THRESHOLD  # noqa: E402
from rivyou.submission import SHARE_URL_RE  # noqa: E402
from rivyou.utils.domains import normalize_domain, registered_domain  # noqa: E402


def percentage(count: int, total: int) -> str:
    return f"{(100 * count / total if total else 0):.1f}%"


def missing_json_field(series: pd.Series, field: str | None = None) -> int:
    count = 0
    for value in series.fillna(""):
        try:
            parsed = json.loads(value)
            target = parsed.get(field) if field else parsed
            missing = not target or (isinstance(target, dict) and not any(target.values()))
        except (json.JSONDecodeError, TypeError, AttributeError):
            missing = True
        count += int(missing)
    return count


def validate(path: str | Path) -> int:
    frame = pd.read_csv(path, dtype=str).fillna("")
    total = len(frame)
    domains = frame.get("domain_url", pd.Series(dtype=str))
    keys = [registered_domain(value) for value in domains]
    duplicate_count = len([key for index, key in enumerate(keys) if key and key in keys[:index]])
    invalid_domains = [value for value in domains if not normalize_domain(value)]
    logos = frame.get("logo_url", pd.Series(dtype=str))
    invalid_logos = [
        value for value in logos
        if value and (
            urlsplit(value).path.lower().endswith("favicon.ico")
            or REJECT_LOGO_RE.search(urlsplit(value).path)
        )
    ]
    malformed_json = duplicate_contacts = share_urls = invalid_scores = 0
    missing_all_contacts = 0
    for _, row in frame.iterrows():
        try:
            contacts_value = json.loads(row.get("contacts", ""))
            socials_value = json.loads(row.get("socials", ""))
            emails = contacts_value.get("emails", [])
            phones = contacts_value.get("phones", [])
            missing_all_contacts += int(not emails and not phones)
            duplicate_contacts += int(len(emails) != len(set(emails)) or len(phones) != len(set(phones)))
            share_urls += sum(bool(url and SHARE_URL_RE.search(url)) for url in socials_value.values())
        except (json.JSONDecodeError, TypeError, AttributeError):
            malformed_json += 1
        if "shopify_score" in frame.columns and "india_score" in frame.columns:
            try:
                invalid_scores += int(
                    int(row["shopify_score"]) < SHOPIFY_SCORE_THRESHOLD or int(row["india_score"]) < INDIA_SCORE_THRESHOLD
                )
            except (TypeError, ValueError):
                invalid_scores += 1

    print(f"TOTAL STORES: {total}")
    print(f"duplicate domains: {duplicate_count}")
    contacts = frame.get("contacts", pd.Series([""] * total))
    socials = frame.get("socials", pd.Series([""] * total))
    print(f"missing emails: {percentage(missing_json_field(contacts, 'emails'), total)}")
    print(f"missing phones: {percentage(missing_json_field(contacts, 'phones'), total)}")
    print(f"missing contacts: {percentage(missing_all_contacts, total)}")
    print(f"missing socials: {percentage(missing_json_field(socials), total)}")
    for column, label in (
        ("category", "category"), ("tagline_or_description", "description"), ("logo_url", "logo"), ("state", "state")
    ):
        missing = int((frame.get(column, pd.Series([""] * total)) == "").sum())
        print(f"missing {label}: {percentage(missing, total)}")
    for column, label in (("shopify_confidence", "Shopify"), ("india_confidence", "India")):
        distribution = frame.get(column, pd.Series(dtype=str)).value_counts().to_dict()
        print(f"{label} confidence distribution: {distribution}")
    print(f"invalid domain URLs: {len(invalid_domains)}")
    print(f"forbidden favicon/icon logo URLs: {len(invalid_logos)}")
    print(f"malformed JSON-in-CSV rows: {malformed_json}")
    print(f"rows with duplicate contacts: {duplicate_contacts}")
    print(f"social share URLs: {share_urls}")
    print(f"rows below verification thresholds: {invalid_scores}")
    valid = not any((duplicate_count, invalid_domains, invalid_logos, malformed_json, duplicate_contacts, share_urls, invalid_scores))
    print(f"validation: {'PASS' if valid else 'FAIL'}")
    return 0 if valid else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated store output")
    parser.add_argument("path", nargs="?", default="data/output/indian_shopify_stores.csv")
    args = parser.parse_args()
    raise SystemExit(validate(args.path))


if __name__ == "__main__":
    main()

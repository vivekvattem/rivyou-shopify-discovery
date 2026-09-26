"""Final assignment artifact readiness checks."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from rivyou.config import INDIA_SCORE_THRESHOLD, SHOPIFY_SCORE_THRESHOLD
from rivyou.extract.logo import REJECT_LOGO_RE
from rivyou.utils.domains import normalize_domain, registered_domain

REQUIRED_COLUMNS = (
    "domain_url", "contacts", "socials", "category", "tagline_or_description", "logo_url", "state"
)
README_MARKERS = (
    "candidate discovery", "shopify", "india", "false-positive", "deduplication", "contacts",
    "social", "category", "description", "logo", "state", "manual precision", "scaling",
    "observed", "runtime", "10x", "100x", "more time",
)
SHARE_URL_RE = re.compile(r"/(?:share|sharer|intent|sharearticle|dialog/share)(?:/|\?|$)", re.I)
SOCIAL_HOSTS = {
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.com"),
    "twitter": ("twitter.com", "x.com"),
    "linkedin": ("linkedin.com",),
    "youtube": ("youtube.com", "youtu.be"),
}


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def check_submission(project_root: str | Path, minimum_rows: int = 1000) -> list[CheckResult]:
    root = Path(project_root)
    readme = root / "README.md"
    requirements = root / "requirements.txt"
    csv_path = root / "data/output/indian_shopify_stores.csv"
    json_path = root / "data/output/indian_shopify_stores.json"
    results = [
        CheckResult("README", readme.is_file()),
        CheckResult("Requirements", requirements.is_file()),
        CheckResult("Final CSV", csv_path.is_file()),
        CheckResult("Final JSON", json_path.is_file()),
    ]
    readme_text = readme.read_text(encoding="utf-8").lower() if readme.is_file() else ""
    missing_sections = [marker for marker in README_MARKERS if marker not in readme_text]
    results.append(CheckResult(
        "README methodology", not missing_sections,
        "missing: " + ", ".join(missing_sections) if missing_sections else "all required topics found",
    ))
    if not csv_path.is_file():
        return results
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            columns = reader.fieldnames or []
    except (OSError, csv.Error) as exc:
        results.append(CheckResult("CSV readable", False, str(exc)))
        return results
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in columns]
    results.append(CheckResult("Required columns", not missing_columns, ", ".join(missing_columns)))
    results.append(CheckResult("CSV row count", len(rows) >= minimum_rows, f"{len(rows)} rows; target >= {minimum_rows}"))
    domains = [row.get("domain_url", "").strip() for row in rows]
    results.append(CheckResult("Non-empty domains", all(domains), f"{sum(not item for item in domains)} empty"))
    invalid_urls = [item for item in domains if not normalize_domain(item)]
    results.append(CheckResult("Valid domain URLs", not invalid_urls, f"{len(invalid_urls)} invalid"))
    keys = [registered_domain(item) for item in domains]
    results.append(CheckResult("Unique domains", len([item for item in keys if item]) == len(set(item for item in keys if item))))
    bad_logos = [row.get("logo_url", "") for row in rows if row.get("logo_url") and (
        row["logo_url"].lower().endswith("favicon.ico") or REJECT_LOGO_RE.search(row["logo_url"])
    )]
    results.append(CheckResult("Logo validation", not bad_logos, f"{len(bad_logos)} forbidden icons"))
    malformed_json = duplicate_contacts = bad_socials = 0
    for row in rows:
        try:
            contacts = json.loads(row.get("contacts", ""))
            socials = json.loads(row.get("socials", ""))
            emails = contacts.get("emails", [])
            phones = contacts.get("phones", [])
            duplicate_contacts += int(len(emails) != len(set(emails)) or len(phones) != len(set(phones)))
            for platform, url in socials.items():
                if not url:
                    continue
                parsed = urlsplit(url)
                host = (parsed.hostname or "").lower().removeprefix("www.")
                path = parsed.path.strip("/").lower()
                expected_hosts = SOCIAL_HOSTS.get(platform, ())
                if (
                    parsed.scheme not in {"http", "https"}
                    or not expected_hosts
                    or not any(host == item or host.endswith(f".{item}") for item in expected_hosts)
                    or not path
                    or path in {"login", "settings", "share", "intent"}
                    or SHARE_URL_RE.search(url)
                ):
                    bad_socials += 1
        except (json.JSONDecodeError, TypeError, AttributeError):
            malformed_json += 1
    results.append(CheckResult("JSON-in-CSV fields", malformed_json == 0, f"{malformed_json} malformed rows"))
    results.append(CheckResult("Deduplicated contacts", duplicate_contacts == 0, f"{duplicate_contacts} affected rows"))
    results.append(CheckResult("Social profile URLs", bad_socials == 0, f"{bad_socials} share URLs"))
    if "shopify_score" in columns and "india_score" in columns:
        invalid_scores = 0
        for row in rows:
            try:
                invalid_scores += int(
                    int(row["shopify_score"]) < SHOPIFY_SCORE_THRESHOLD or int(row["india_score"]) < INDIA_SCORE_THRESHOLD
                )
            except (TypeError, ValueError):
                invalid_scores += 1
        results.append(CheckResult("Verification thresholds", invalid_scores == 0, f"{invalid_scores} invalid rows"))
    if json_path.is_file():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            valid_json = isinstance(payload, list) and len(payload) == len(rows)
            detail = f"{len(payload) if isinstance(payload, list) else 'non-list'} JSON rows"
            missing_json_fields = sum(
                1 for item in payload if not isinstance(item, dict) or any(field not in item for field in REQUIRED_COLUMNS)
            ) if isinstance(payload, list) else 1
        except (json.JSONDecodeError, OSError) as exc:
            valid_json, detail, missing_json_fields = False, str(exc), 1
        results.append(CheckResult("JSON matches CSV", valid_json, detail))
        results.append(CheckResult(
            "JSON required fields", missing_json_fields == 0, f"{missing_json_fields} incomplete rows"
        ))
    return results


def render_checks(results: list[CheckResult]) -> str:
    lines = [f"{item.name:.<32}{'PASS' if item.passed else 'FAIL'}{f'  {item.detail}' if item.detail else ''}" for item in results]
    lines.append("")
    lines.append(f"FINAL STATUS: {'READY' if results and all(item.passed for item in results) else 'NOT READY'}")
    return "\n".join(lines)

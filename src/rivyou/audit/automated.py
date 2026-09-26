"""Machine pre-review for accepted stores without impersonating human verification."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from rivyou.config import SETTINGS, Settings
from rivyou.crawler import AsyncCrawler, CrawledPage
from rivyou.extract.contacts import extract_contacts, normalize_email
from rivyou.extract.logo import REJECT_LOGO_RE, extract_logo
from rivyou.extract.socials import extract_socials, normalize_social_url
from rivyou.models import StoreRecord
from rivyou.storage.cache import SQLiteHTTPCache
from rivyou.storage.sqlite_store import SQLiteStore
from rivyou.verify.india import verify_india
from rivyou.verify.shopify import verify_shopify

VERDICTS = {"PASS", "FAIL", "UNCERTAIN", "MISSING"}
STRONG_INDIA_SIGNALS = {
    "gstin", "india_phone", "explicit_india_address", "india_pincode",
    "clear_indian_physical_address",
}
OBVIOUS_NON_LOGO_RE = re.compile(
    r"(?:/products?/|(?:^|[/_-])(?:social|instagram|facebook|twitter|youtube|whatsapp)[_-]?(?:icon|button)(?:[/_.-]|$)|(?:^|[/_-])(?:icon|button)[_-]?(?:instagram|facebook|twitter|youtube|whatsapp)(?:[/_.-]|$))",
    re.I,
)
MANUAL_COLUMNS = (
    "manual_shopify_correct", "manual_india_correct", "manual_logo_correct",
    "manual_state_correct", "manual_contacts_correct", "manual_notes",
)
AUTO_AUDIT_COLUMNS = (
    "domain", "pipeline_status", "shopify_score", "india_score", "category", "state", "logo_url",
    "emails", "phones", "socials", "shopify_evidence", "india_evidence",
    "auto_shopify_check", "auto_india_check", "auto_logo_check", "auto_state_check",
    "auto_contacts_check", "auto_socials_check", "auto_audit_confidence", "auto_audit_notes",
    *MANUAL_COLUMNS,
)


@dataclass(frozen=True, slots=True)
class Check:
    verdict: str
    note: str

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"Unsupported auto-audit verdict: {self.verdict}")


@dataclass(frozen=True, slots=True)
class AutoAuditSummary:
    path: Path
    total: int
    confidence_counts: dict[str, int]
    check_counts: dict[str, dict[str, int]]
    needs_human_review: tuple[str, ...]


def _available(pages: list[CrawledPage]) -> bool:
    return bool(pages and pages[0].html)


def check_shopify(record: StoreRecord, pages: list[CrawledPage], settings: Settings = SETTINGS) -> Check:
    if not _available(pages):
        return Check("UNCERTAIN", f"homepage unavailable: {pages[0].error if pages else 'no response'}")
    current = verify_shopify(pages, settings.shopify_score_threshold)
    signals = sorted(item.signal for item in current.evidence)
    stored = sorted(item.signal for item in record.shopify_evidence)
    comparison = f"current score {current.score}, signals {','.join(signals) or 'none'}; stored {','.join(stored) or 'none'}"
    if current.is_shopify and len(signals) >= 2:
        return Check("PASS", comparison)
    if current.score > 0:
        return Check("UNCERTAIN", f"weak current Shopify evidence; {comparison}")
    return Check("FAIL", f"reachable homepage has no current Shopify evidence; {comparison}")


def check_india(record: StoreRecord, pages: list[CrawledPage], settings: Settings = SETTINGS) -> Check:
    if not _available(pages):
        return Check("UNCERTAIN", f"India evidence unavailable: {pages[0].error if pages else 'no response'}")
    current = verify_india(pages, settings.india_score_threshold)
    signals = sorted(item.signal for item in current.evidence)
    strong = sorted(set(signals) & STRONG_INDIA_SIGNALS)
    if current.detected_state:
        strong.append(f"contextual_business_state:{current.detected_state}")
    detail = f"current score {current.score}; strong evidence {','.join(strong) or 'none'}; all signals {','.join(signals) or 'none'}"
    if current.is_indian and strong:
        return Check("PASS", detail)
    if current.score > 0:
        return Check("UNCERTAIN", f"only weak/insufficient current India evidence; {detail}")
    return Check("FAIL", f"reachable pages have no current India evidence; {detail}")


def _asset_key(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", ""))


def _stored_logo_size(pages: list[CrawledPage], stored_url: str) -> tuple[int, int] | None:
    key = _asset_key(stored_url)
    for page in pages:
        if not page.html:
            continue
        soup = BeautifulSoup(page.html, "lxml")
        for image in soup.select("img[src], img[data-src]"):
            raw = image.get("src") or image.get("data-src") or ""
            from urllib.parse import urljoin
            if _asset_key(urljoin(page.final_url, raw)) != key:
                continue
            try:
                width = int(str(image.get("width", "0")).replace("px", "") or 0)
                height = int(str(image.get("height", "0")).replace("px", "") or 0)
            except ValueError:
                return None
            return width, height
    return None


def check_logo(record: StoreRecord, pages: list[CrawledPage]) -> Check:
    if not record.logo_url:
        return Check("MISSING", "no stored logo URL")
    path = urlsplit(record.logo_url).path.lower()
    if not record.logo_url.startswith(("http://", "https://")) or REJECT_LOGO_RE.search(path):
        return Check("FAIL", "stored logo is a favicon, app, payment, or malformed asset")
    if OBVIOUS_NON_LOGO_RE.search(path):
        return Check("FAIL", "stored logo URL appears to be a product or social asset")
    if not _available(pages):
        return Check("UNCERTAIN", "stored logo could not be rechecked because the homepage is unavailable")
    dimensions = _stored_logo_size(pages, record.logo_url)
    if dimensions and dimensions[0] and dimensions[1] and dimensions[0] <= 32 and dimensions[1] <= 32:
        return Check("FAIL", f"stored logo has tiny declared dimensions {dimensions[0]}x{dimensions[1]}")
    current = extract_logo(pages)
    if current and _asset_key(current) == _asset_key(record.logo_url):
        return Check("PASS", "stored logo matches the current semantic logo candidate")
    searchable = "\n".join(page.html for page in pages if page.html)
    if record.logo_url in searchable or _asset_key(record.logo_url) in searchable:
        return Check("UNCERTAIN", "stored logo remains in page markup but visual brand matching is unresolved")
    return Check("UNCERTAIN", "stored logo is plausible but no longer matches the current semantic candidate")


def check_state(record: StoreRecord, pages: list[CrawledPage], settings: Settings = SETTINGS) -> Check:
    if not _available(pages):
        return Check("UNCERTAIN", "business state could not be rechecked because the homepage is unavailable")
    current = verify_india(pages, settings.india_score_threshold)
    detected = current.detected_state
    if not record.state:
        if not detected:
            return Check("MISSING", "no stored state and no current contextual business state")
        return Check("FAIL", f"stored state is empty but current business-location evidence indicates {detected}")
    if detected == record.state:
        return Check("PASS", f"stored state matches current contextual business-location evidence: {detected}")
    if detected:
        return Check("FAIL", f"stored state {record.state} conflicts with current contextual state {detected}")
    return Check("UNCERTAIN", f"stored state {record.state} has no current contextual confirmation")


def check_contacts(record: StoreRecord, pages: list[CrawledPage]) -> Check:
    if not _available(pages):
        return Check("UNCERTAIN", "stored contacts could not be rechecked because the homepage is unavailable")
    invalid_emails = [email for email in record.emails if normalize_email(email) != email.lower()]
    current_emails, current_phones = extract_contacts(pages)
    missing_emails = sorted(set(map(str.lower, record.emails)) - set(current_emails))
    missing_phones = sorted(set(record.phones) - set(current_phones))
    if invalid_emails or missing_emails or missing_phones:
        issues = []
        if invalid_emails:
            issues.append(f"invalid/platform emails: {','.join(invalid_emails)}")
        if missing_emails:
            issues.append(f"stored emails not found: {','.join(missing_emails)}")
        if missing_phones:
            issues.append(f"stored phones not found: {','.join(missing_phones)}")
        return Check("FAIL", "; ".join(issues))
    if not record.emails and not record.phones:
        return Check("UNCERTAIN", "no stored contacts to confirm")
    return Check("PASS", f"confirmed {len(record.emails)} email(s) and {len(record.phones)} phone(s) on merchant pages")


def check_socials(record: StoreRecord, pages: list[CrawledPage]) -> Check:
    stored = {platform: url for platform, url in record.socials.items() if url}
    if not stored:
        return Check("MISSING", "no stored social profile URLs")
    invalid = []
    canonical: dict[str, str] = {}
    for platform, url in stored.items():
        normalized = normalize_social_url(url)
        if not normalized or normalized[0] != platform:
            invalid.append(url)
        else:
            canonical[platform] = normalized[1]
    if invalid:
        return Check("FAIL", f"invalid/share/generic social URLs: {','.join(invalid)}")
    if not _available(pages):
        return Check("UNCERTAIN", "stored social profiles could not be rechecked because the homepage is unavailable")
    current = extract_socials(pages)
    missing = [url for platform, url in canonical.items() if current.get(platform) != url]
    if missing:
        return Check("UNCERTAIN", f"valid stored profile URL(s) not found on current merchant pages: {','.join(missing)}")
    return Check("PASS", f"confirmed {len(canonical)} merchant-page social profile link(s)")


def aggregate_confidence(checks: dict[str, Check], site_available: bool = True) -> str:
    if not site_available or any(item.verdict == "FAIL" for item in checks.values()):
        return "LOW"
    if any(item.verdict == "UNCERTAIN" for item in checks.values()):
        return "MEDIUM"
    if (
        checks["shopify"].verdict == "PASS"
        and checks["india"].verdict == "PASS"
        and checks["contacts"].verdict == "PASS"
        and checks["logo"].verdict in {"PASS", "MISSING"}
        and checks["state"].verdict in {"PASS", "MISSING"}
    ):
        return "HIGH"
    return "MEDIUM"


def audit_record(record: StoreRecord, pages: list[CrawledPage]) -> dict[str, object]:
    checks = {
        "shopify": check_shopify(record, pages),
        "india": check_india(record, pages),
        "logo": check_logo(record, pages),
        "state": check_state(record, pages),
        "contacts": check_contacts(record, pages),
        "socials": check_socials(record, pages),
    }
    confidence = aggregate_confidence(checks, _available(pages))
    notes = " | ".join(f"{name}: {check.note}" for name, check in checks.items())
    return {
        "domain": record.domain_url,
        "pipeline_status": "ACCEPTED",
        "shopify_score": record.shopify_score,
        "india_score": record.india_score,
        "category": record.category or "",
        "state": record.state or "",
        "logo_url": record.logo_url or "",
        "emails": json.dumps(record.emails, ensure_ascii=False),
        "phones": json.dumps(record.phones, ensure_ascii=False),
        "socials": json.dumps(record.socials, ensure_ascii=False),
        "shopify_evidence": json.dumps([item.model_dump(mode="json") for item in record.shopify_evidence], ensure_ascii=False),
        "india_evidence": json.dumps([item.model_dump(mode="json") for item in record.india_evidence], ensure_ascii=False),
        **{f"auto_{name}_check": check.verdict for name, check in checks.items()},
        "auto_audit_confidence": confidence,
        "auto_audit_notes": notes,
        **{column: "" for column in MANUAL_COLUMNS},
    }


async def run_auto_audit(
    store: SQLiteStore,
    output_dir: str | Path,
    *,
    settings: Settings = SETTINGS,
    use_cache: bool = True,
) -> AutoAuditSummary:
    records = store.accepted_records()
    cache = SQLiteHTTPCache(store, settings.cache_ttl_hours)
    rows: list[dict[str, object]] = []
    async with AsyncCrawler(settings, cache=cache, use_cache=use_cache) as crawler:
        for record in records:
            pages = await crawler.crawl_store(record.domain_url)
            rows.append(audit_record(record, pages))
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"auto_audit_{timestamp}.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUTO_AUDIT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    confidence_counts = Counter(str(row["auto_audit_confidence"]) for row in rows)
    check_counts = {
        name: dict(Counter(str(row[f"auto_{name}_check"]) for row in rows))
        for name in ("shopify", "india", "logo", "state", "contacts", "socials")
    }
    needs_review = tuple(str(row["domain"]) for row in rows if row["auto_audit_confidence"] != "HIGH")
    return AutoAuditSummary(
        path=target,
        total=len(rows),
        confidence_counts=dict(confidence_counts),
        check_counts=check_counts,
        needs_human_review=needs_review,
    )

import pytest
import csv
import asyncio

from rivyou.audit.automated import (
    Check,
    aggregate_confidence,
    audit_record,
    check_contacts,
    check_india,
    check_logo,
    check_shopify,
    check_socials,
    check_state,
    run_auto_audit,
)
from rivyou.crawler import CrawledPage
from rivyou.models import StoreRecord
from rivyou.audit.sampling import create_targeted_accepted_sample
from rivyou.storage.sqlite_store import SQLiteStore


def page(html, url="https://brand.in", error=None):
    return CrawledPage(url, url, 200 if html else 0, html, error=error)


def record(**changes):
    return StoreRecord(
        domain_url="https://brand.in",
        emails=["care@brand.in"],
        shopify_score=8,
        india_score=8,
    ).model_copy(update=changes)


def test_auto_shopify_passes_multiple_strong_signals():
    pages = [page('<script>Shopify.theme={}; ShopifyAnalytics={}</script><img src="/cdn/shop/logo.png">')]
    assert check_shopify(record(), pages).verdict == "PASS"


def test_temporary_unreachable_is_uncertain_not_fail():
    pages = [page("", error="ConnectTimeout")]
    audited = audit_record(record(), pages)
    assert audited["auto_shopify_check"] == "UNCERTAIN"
    assert audited["auto_india_check"] == "UNCERTAIN"
    assert audited["auto_audit_confidence"] == "LOW"
    assert all(audited[column] == "" for column in (
        "manual_shopify_correct", "manual_india_correct", "manual_logo_correct",
        "manual_state_correct", "manual_contacts_correct", "manual_notes",
    ))


def test_inr_only_india_evidence_does_not_pass():
    assert check_india(record(), [page("<p>Price ₹999</p>")]).verdict != "PASS"


def test_weak_india_bundle_without_business_location_does_not_pass():
    html = "<p>Mumbai customers: Price ₹999. We ship across India.</p>"
    assert check_india(record(), [page(html)]).verdict != "PASS"


def test_favicon_logo_fails():
    candidate = record(logo_url="https://brand.in/favicon.ico")
    assert check_logo(candidate, [page("<html></html>")]).verdict == "FAIL"


def test_exported_whatsapp_named_header_image_can_be_a_logo():
    url = "https://brand.in/cdn/shop/files/WhatsApp_Image_2026.jpg?width=500"
    html = f'<header><img class="header__heading-logo" alt="Brand" width="120" height="60" src="{url}"></header>'
    assert check_logo(record(logo_url=url), [page(html)]).verdict == "PASS"


def test_missing_legitimate_state_is_missing():
    assert check_state(record(state=None), [page("<p>Independent merchant</p>")]).verdict == "MISSING"


def test_wrong_state_fails_against_business_address():
    html = "<p>Registered office address: Bengaluru, Karnataka 560001, India</p>"
    result = check_state(record(state="Maharashtra"), [page(html)])
    assert result.verdict == "FAIL"
    assert "Karnataka" in result.note


def test_valid_merchant_contact_passes():
    assert check_contacts(record(), [page('<a href="mailto:care@brand.in">Email us</a>')]).verdict == "PASS"


def test_unrelated_platform_contact_fails():
    candidate = record(emails=["support@shopify.com"])
    result = check_contacts(candidate, [page("Contact support@shopify.com")])
    assert result.verdict == "FAIL"
    assert "platform" in result.note


def test_social_share_link_fails():
    candidate = record(socials={"facebook": "https://facebook.com/sharer/sharer.php?u=x"})
    assert check_socials(candidate, [page("<html></html>")]).verdict == "FAIL"


@pytest.mark.parametrize(
    ("checks", "available", "expected"),
    [
        ({
            "shopify": Check("PASS", ""), "india": Check("PASS", ""),
            "logo": Check("MISSING", ""), "state": Check("MISSING", ""),
            "contacts": Check("PASS", ""), "socials": Check("MISSING", ""),
        }, True, "HIGH"),
        ({
            "shopify": Check("PASS", ""), "india": Check("PASS", ""),
            "logo": Check("UNCERTAIN", ""), "state": Check("PASS", ""),
            "contacts": Check("PASS", ""), "socials": Check("PASS", ""),
        }, True, "MEDIUM"),
        ({
            "shopify": Check("PASS", ""), "india": Check("FAIL", ""),
            "logo": Check("PASS", ""), "state": Check("PASS", ""),
            "contacts": Check("PASS", ""), "socials": Check("PASS", ""),
        }, True, "LOW"),
    ],
)
def test_audit_confidence_aggregation(checks, available, expected):
    assert aggregate_confidence(checks, available) == expected


def test_targeted_sample_covers_risks_and_keeps_manual_fields_blank(tmp_path):
    rows = []
    for index in range(20):
        rows.append({
            "domain": f"https://brand{index}.in", "pipeline_status": "ACCEPTED",
            "shopify_score": str(4 + index), "india_score": str(5 + index),
            "category": "Apparel", "tagline_or_description": "" if index == 2 else "Brand",
            "state": "" if index == 3 else "Karnataka",
            "logo_url": "" if index == 4 else "https://brand.in/logo.png",
            "auto_contacts_check": "UNCERTAIN" if index == 5 else "PASS",
            "auto_socials_check": "FAIL" if index == 6 else "PASS",
            "auto_audit_confidence": "MEDIUM" if index < 2 else "HIGH",
        })
    source = tmp_path / "auto.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    path = create_targeted_accepted_sample(source, tmp_path, target=15, seed=7)
    with path.open(newline="", encoding="utf-8") as handle:
        sampled = list(csv.DictReader(handle))
    assert len(sampled) == 15
    assert {"https://brand2.in", "https://brand3.in", "https://brand4.in"} <= {row["domain"] for row in sampled}
    assert all(not row[column] for row in sampled for column in (
        "manual_shopify_correct", "manual_india_correct", "manual_logo_correct",
        "manual_state_correct", "manual_contacts_correct", "manual_notes",
    ))
    assert all(row["selection_reason"] for row in sampled)


def test_targeted_sample_prioritizes_low_before_medium_when_uncertain_set_is_large(tmp_path):
    rows = []
    for index, confidence in enumerate(["MEDIUM"] * 8 + ["LOW"] * 4 + ["HIGH"] * 8):
        rows.append({
            "domain": f"https://brand{index}.in",
            "pipeline_status": "ACCEPTED",
            "shopify_score": "8",
            "india_score": "8",
            "auto_contacts_check": "PASS",
            "auto_socials_check": "PASS",
            "auto_audit_confidence": confidence,
        })
    source = tmp_path / "auto.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)

    path = create_targeted_accepted_sample(
        source, tmp_path, target=6, seed=7, review_all_limit=6
    )
    with path.open(newline="", encoding="utf-8") as handle:
        sampled = list(csv.DictReader(handle))

    assert len(sampled) == 6
    sampled_domains = {row["domain"] for row in sampled}
    assert {f"https://brand{index}.in" for index in range(8, 12)} <= sampled_domains
    assert all(not row[column] for row in sampled for column in (
        "manual_shopify_correct", "manual_india_correct", "manual_logo_correct",
        "manual_state_correct", "manual_contacts_correct", "manual_notes",
    ))


@pytest.mark.asyncio
async def test_full_auto_audit_processes_stores_concurrently(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "state.db")
    for index in range(4):
        domain = f"https://brand{index}.in"
        store.save_store_result(domain, record(domain_url=domain))

    class TrackingCrawler:
        active = 0
        maximum = 0

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def crawl_store(self, domain):
            type(self).active += 1
            type(self).maximum = max(type(self).maximum, type(self).active)
            await asyncio.sleep(0.01)
            type(self).active -= 1
            return [page("", url=domain, error="offline")]

    monkeypatch.setattr("rivyou.audit.automated.AsyncCrawler", TrackingCrawler)
    summary = await run_auto_audit(store, tmp_path)
    assert summary.total == 4
    assert TrackingCrawler.maximum > 1


@pytest.mark.asyncio
async def test_full_auto_audit_records_store_timeout_as_low_confidence(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "state.db")
    store.save_store_result("https://slow.in", record(domain_url="https://slow.in"))

    class SlowCrawler:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def crawl_store(self, domain):
            await asyncio.sleep(1)
            return [page("", url=domain, error="unreachable")]

    monkeypatch.setattr("rivyou.audit.automated.AsyncCrawler", SlowCrawler)
    summary = await run_auto_audit(store, tmp_path, store_timeout_seconds=0.01)
    with summary.path.open(newline="", encoding="utf-8") as handle:
        [audited] = list(csv.DictReader(handle))

    assert audited["auto_audit_confidence"] == "LOW"
    assert "auto-audit store timeout" in audited["auto_audit_notes"]

import pytest

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
)
from rivyou.crawler import CrawledPage
from rivyou.models import StoreRecord


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

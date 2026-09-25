from conftest import make_page
from rivyou.extract.contacts import extract_contacts


def test_extracts_and_deduplicates_emails():
    html = '<a href="mailto:HELLO@Brand.com">email</a><p>hello@brand.com</p>'
    emails, _ = extract_contacts([make_page(html)])
    assert emails == ["hello@brand.com"]


def test_rejects_example_and_image_emails():
    emails, _ = extract_contacts([make_page("example@example.com hero@image.png")])
    assert emails == []


def test_extracts_and_normalizes_indian_phone():
    _, phones = extract_contacts([make_page('<a href="tel:+919123456789">Call</a>')])
    assert phones == ["+919123456789"]


def test_extracts_json_ld_contacts():
    html = '<script type="application/ld+json">{"@type":"Organization","email":"care@brand.in","telephone":"+91 91234 56789"}</script>'
    emails, phones = extract_contacts([make_page(html)])
    assert emails == ["care@brand.in"]
    assert phones == ["+919123456789"]


def test_rejects_real_world_placeholder_contacts():
    emails, phones = extract_contacts([make_page("contact@yourbrand.com +91 98765 43210")])
    assert emails == []
    assert phones == []


def test_rejects_platform_noreply_email():
    emails, _ = extract_contacts([make_page("noreply@shopify.com")])
    assert emails == []

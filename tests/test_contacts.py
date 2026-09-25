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
    _, phones = extract_contacts([make_page('<a href="tel:+919876543210">Call</a>')])
    assert phones == ["+919876543210"]


def test_extracts_json_ld_contacts():
    html = '<script type="application/ld+json">{"@type":"Organization","email":"care@brand.in","telephone":"+91 98765 43210"}</script>'
    emails, phones = extract_contacts([make_page(html)])
    assert emails == ["care@brand.in"]
    assert phones == ["+919876543210"]


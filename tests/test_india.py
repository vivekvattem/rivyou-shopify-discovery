from conftest import make_page
from rivyou.verify.india import verify_india


def test_clear_indian_address_is_accepted():
    html = "<p>Registered Office: 12 MG Road, Bengaluru, Karnataka 560001, India</p>"
    result = verify_india([make_page(html)])
    assert result.is_indian
    assert result.detected_state == "Karnataka"
    assert result.detected_pincodes == ["560001"]


def test_dot_in_alone_is_not_accepted():
    result = verify_india([make_page("<p>Welcome to our store</p>", "https://brand.in")])
    assert not result.is_indian
    assert result.score == 1


def test_inr_alone_is_not_accepted():
    result = verify_india([make_page("<p>Price ₹999</p>", "https://brand.com")])
    assert not result.is_indian
    assert result.score == 1


def test_gstin_is_strong_but_thresholded():
    result = verify_india([make_page("GSTIN: 27AAPFU0939F1ZV", "https://brand.com")])
    assert result.score == 3
    assert not result.is_indian


def test_phone_and_state_support_acceptance():
    result = verify_india([make_page("Contact +91 98765 43210 at our Mumbai store", "https://brand.in")])
    assert result.is_indian
    assert result.detected_state == "Maharashtra"


def test_structured_postal_address_drives_state():
    html = '''<script type="application/ld+json">{"@type":"Organization","address":{"@type":"PostalAddress",
    "streetAddress":"MG Road","addressLocality":"Bengaluru","addressRegion":"Karnataka","postalCode":"560001","addressCountry":"IN"}}</script>'''
    result = verify_india([make_page(html, "https://brand.com")])
    assert result.detected_state == "Karnataka"


def test_stockist_location_does_not_become_business_state_without_address_context():
    result = verify_india([make_page("Stockists: Panipat, Haryana; Ahmedabad, Gujarat. Call +91 96499 06415", "https://brand.in")])
    assert result.detected_state is None


def test_address_pincode_is_selected_after_irrelevant_earlier_number():
    html = "<p>Product reference 123456</p><footer>Address: Near Shantaram Industries, Pune, Maharashtra 411018, India</footer>"
    result = verify_india([make_page(html, "https://brand.com")])
    assert result.is_indian
    assert result.detected_state == "Maharashtra"
    assert any(item.signal == "clear_indian_physical_address" for item in result.evidence)

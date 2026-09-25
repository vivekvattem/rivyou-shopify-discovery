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


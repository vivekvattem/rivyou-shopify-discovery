from conftest import make_page
from rivyou.extract.socials import extract_socials, normalize_social_url


def test_extracts_supported_social_profiles():
    html = '<a href="https://instagram.com/mybrand/?utm_source=x">IG</a><a href="https://linkedin.com/company/mybrand/">LI</a>'
    result = extract_socials([make_page(html)])
    assert result["instagram"] == "https://instagram.com/mybrand"
    assert result["linkedin"] == "https://linkedin.com/company/mybrand"


def test_rejects_facebook_share_link():
    assert normalize_social_url("https://facebook.com/sharer/sharer.php?u=x") is None


def test_rejects_twitter_intent_link():
    assert normalize_social_url("https://twitter.com/intent/tweet?url=x") is None


def test_rejects_shopify_platform_account():
    assert normalize_social_url("https://instagram.com/shopify") is None


def test_normalizes_twitter_to_x():
    assert normalize_social_url("https://twitter.com/mybrand/") == ("twitter", "https://x.com/mybrand")


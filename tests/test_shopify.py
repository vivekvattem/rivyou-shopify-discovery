from conftest import make_page
from rivyou.models import Confidence
from rivyou.verify.shopify import verify_shopify


def test_strong_shopify_signals_are_accepted():
    result = verify_shopify([make_page('<script>Shopify.theme={}; ShopifyAnalytics={}</script>')])
    assert result.is_shopify
    assert result.score == 5
    assert result.confidence == Confidence.MEDIUM


def test_cdn_signal_meets_threshold_with_section():
    result = verify_shopify([make_page('<img src="//cdn.shopify.com/a.png"><div class="shopify-section">')])
    assert result.is_shopify
    assert result.score == 4


def test_powered_by_shopify_alone_is_rejected():
    result = verify_shopify([make_page("<footer>Powered by Shopify</footer>")])
    assert not result.is_shopify
    assert result.score == 1


def test_repeated_signal_only_scores_once():
    result = verify_shopify([make_page("Shopify.theme Shopify.theme"), make_page("Shopify.theme")])
    assert result.score == 3


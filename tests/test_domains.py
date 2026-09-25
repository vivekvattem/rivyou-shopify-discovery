import pytest

from rivyou.models import StoreCandidate, StoreRecord
from rivyou.utils.dedupe import dedupe_candidates, dedupe_records
from rivyou.utils.domains import normalize_domain, registered_domain


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.Example.com/products/test", "https://example.com"),
        ("http://example.com/", "https://example.com"),
        ("[www.example.com](http://www.example.com)", "https://example.com"),
        ("example.com?abc=1", "https://example.com"),
        ("https://example.com./foo#bar", "https://example.com"),
    ],
)
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("raw", ["", "not a domain", "http://localhost", "https://exa_mple.com", "https://a.com:bad"])
def test_rejects_malformed_domain(raw):
    assert normalize_domain(raw) is None


def test_registered_domain_and_myshopify_special_case():
    assert registered_domain("shop.example.co.in") == "example.co.in"
    assert registered_domain("alpha.myshopify.com") == "alpha.myshopify.com"


def test_deduplicate_candidates_by_registered_domain():
    values = [
        StoreCandidate(original_url="a", normalized_domain="https://shop.example.com"),
        StoreCandidate(original_url="b", normalized_domain="https://example.com"),
    ]
    assert len(dedupe_candidates(values)) == 1


def test_deduplicate_records_prefers_higher_score():
    low = StoreRecord(domain_url="https://shop.example.com", shopify_score=4, india_score=4)
    high = StoreRecord(domain_url="https://example.com", shopify_score=7, india_score=8)
    assert dedupe_records([low, high]) == [high]


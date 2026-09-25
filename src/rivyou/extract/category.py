"""Transparent keyword-based store category classifier."""

from __future__ import annotations

from collections.abc import Iterable

from bs4 import BeautifulSoup

from rivyou.crawler import CrawledPage

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Women's Apparel", ("women's clothing", "women wear", "saree", "sari", "kurti", "lehenga", "dress")),
    ("Men's Apparel", ("men's clothing", "menswear", "men wear", "shirts for men", "kurta for men")),
    ("Jewellery", ("jewellery", "jewelry", "necklace", "earrings", "rings")),
    ("Beauty & Skincare", ("skincare", "skin care", "cosmetics", "beauty", "makeup")),
    ("Home Decor", ("home decor", "home décor", "cushion", "wall art", "decorative")),
    ("Furniture", ("furniture", "sofa", "dining table", "chair")),
    ("Food & Beverage", ("snacks", "beverage", "coffee", "tea", "chocolate", "food")),
    ("Footwear", ("footwear", "shoes", "sandals", "sneakers", "slippers")),
    ("Accessories", ("accessories", "handbag", "wallet", "sunglasses", "watch")),
    ("Electronics", ("electronics", "gadgets", "charger", "headphones", "smartphone")),
    ("Health & Wellness", ("wellness", "supplement", "ayurveda", "nutrition", "health")),
    ("Sports & Fitness", ("fitness", "sports", "gym", "yoga mat", "activewear")),
    ("Kids & Baby", ("baby", "kids", "children", "toys", "infant")),
    ("Pet Supplies", ("pet supplies", "dog", "cat food", "pet care")),
    ("Stationery", ("stationery", "notebook", "journal", "planner", "pens")),
    ("Fashion", ("fashion", "clothing", "apparel", "ethnic wear")),
)


def classify_category(pages: Iterable[CrawledPage], description: str | None = None) -> str:
    texts = [description or ""]
    for page in pages:
        if not page.html:
            continue
        soup = BeautifulSoup(page.html, "lxml")
        texts.append(" ".join(tag.get_text(" ", strip=True) for tag in soup.select("title, h1, nav, [class*='collection']")[:30]))
    haystack = " ".join(texts).lower()
    scores = [(sum(haystack.count(word) for word in words), category) for category, words in CATEGORY_RULES]
    score, category = max(scores, default=(0, "Other"), key=lambda item: item[0])
    return category if score else "Other"

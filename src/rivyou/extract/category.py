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
    ("Kids & Baby", ("baby", "kids", "kidswear", "childrenswear", "children", "little rani", "toys", "infant")),
    ("Pet Supplies", ("pet supplies", "dog", "cat food", "pet care")),
    ("Stationery", ("stationery", "notebook", "journal", "planner", "pens")),
    ("Fashion", ("fashion", "clothing", "apparel", "ethnic wear")),
)


def classify_category(pages: Iterable[CrawledPage], description: str | None = None) -> str:
    weighted_texts = [((description or "").lower(), 3)]
    for page in pages:
        if not page.html:
            continue
        soup = BeautifulSoup(page.html, "lxml")
        headline = " ".join(tag.get_text(" ", strip=True) for tag in soup.select("title, h1")[:8]).lower()
        navigation = " ".join(tag.get_text(" ", strip=True) for tag in soup.select("nav, [class*='collection']")[:30]).lower()
        weighted_texts.extend(((headline, 4), (navigation, 1)))
    scores = [
        (sum(text.count(word) * weight * (2 if " " in word else 1)
             for text, weight in weighted_texts for word in words), category)
        for category, words in CATEGORY_RULES
    ]
    score, category = max(scores, default=(0, "Other"), key=lambda item: item[0])
    return category if score else "Other"

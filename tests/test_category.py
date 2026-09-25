from conftest import make_page
from rivyou.extract.category import classify_category


def test_title_outweighs_incidental_navigation_category():
    html = "<title>Rani Kidswear</title><h1>Clothing for Kids</h1><nav>Accessories Accessories Accessories</nav>"
    assert classify_category([make_page(html)]) == "Kids & Baby"


def test_little_rani_collection_identifies_kids_store():
    html = "<title>Rani The Studio</title><nav>Ethnic Wear Little Rani Accessories</nav>"
    assert classify_category([make_page(html)]) == "Kids & Baby"

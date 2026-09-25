from conftest import make_page
from rivyou.extract.logo import extract_logo


def test_json_ld_logo_has_priority():
    html = '''<script type="application/ld+json">{"@type":"Organization","logo":"/brand.svg"}</script>
    <header><img alt="logo" src="/header.png"></header>'''
    assert extract_logo([make_page(html)]) == "https://brand.in/brand.svg"


def test_header_semantic_logo_selected():
    html = '<header><img class="site-logo" width="180" height="60" src="/logo.png"></header>'
    assert extract_logo([make_page(html)]) == "https://brand.in/logo.png"


def test_favicon_is_rejected():
    html = '<header><img class="logo" src="/favicon.ico"></header>'
    assert extract_logo([make_page(html)]) is None


def test_tiny_icon_is_rejected():
    html = '<header><img class="logo" width="16" height="16" src="/brand.png"></header>'
    assert extract_logo([make_page(html)]) is None


def test_og_image_is_weak_fallback():
    html = '<meta property="og:image" content="/share.jpg">'
    assert extract_logo([make_page(html)]) == "https://brand.in/share.jpg"


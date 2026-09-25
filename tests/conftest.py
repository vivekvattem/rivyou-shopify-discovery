from rivyou.crawler import CrawledPage


def make_page(html: str, url: str = "https://brand.in", headers: dict[str, str] | None = None) -> CrawledPage:
    return CrawledPage(url, url, 200, html, headers or {})


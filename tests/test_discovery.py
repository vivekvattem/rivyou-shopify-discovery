import csv
from pathlib import Path

import pytest

from rivyou.discover.domain_sources import CSVDiscoveryProvider, DirectoryCSVDiscoveryProvider
from rivyou.discover.fingerprints import prefilter_shopify
from rivyou.discover.manager import DiscoveryManager
from rivyou.discover.provenance import calculate_priority
from rivyou.discover.search_queries import SearchResultsCSVProvider, generate_search_queries
from rivyou.models import CandidateProvenance, CandidateRecord
from rivyou.storage.sqlite_store import SQLiteStore


@pytest.mark.asyncio
@pytest.mark.parametrize("column", ["domain", "url", "website", "site", "domain_url"])
async def test_flexible_csv_domain_columns(tmp_path, column):
    path = tmp_path / "domains.csv"
    path.write_text(f"{column}\nhttps://www.Brand.in/products/a\n")
    records = await CSVDiscoveryProvider(path).discover()
    assert records[0].normalized_domain == "https://brand.in"


@pytest.mark.asyncio
async def test_search_result_csv_import_preserves_query(tmp_path):
    path = tmp_path / "search.csv"
    path.write_text('query,result_url\n"""cdn.shopify.com"" ""Mumbai""",https://brand.in/product\n')
    records = await SearchResultsCSVProvider(path).discover()
    assert records[0].discovery_query
    assert records[0].provenance[0].source == "search-csv"


def test_search_query_generation_is_unique_and_bounded():
    rows = generate_search_queries()
    queries = [row["query"] for row in rows]
    assert len(rows) < 500
    assert len(queries) == len(set(queries))
    assert any("Mumbai" in query for query in queries)
    assert any("Andaman and Nicobar Islands" in query for query in queries)
    assert all(set(row) == {"query", "priority", "shopify_signal", "location", "category_hint"} for row in rows)
    assert any(row["category_hint"] == "jewellery" for row in rows)
    powered_mumbai = next(row for row in rows if row["query"] == '"Powered by Shopify" "Mumbai"')
    assert powered_mumbai["priority"] >= 8


@pytest.mark.asyncio
async def test_master_csv_preserves_row_provenance_and_counts_invalid(tmp_path):
    path = tmp_path / "candidates_master.csv"
    path.write_text(
        "url,domain,query,source,location\n"
        ",brand.in,powered mumbai,manual-search,Mumbai\n"
        "not a url,,,,\n"
    )
    provider = CSVDiscoveryProvider(path)
    records = await provider.discover()
    assert provider.rows_read == 2
    assert provider.invalid_count == 1
    assert records[0].provenance[0].source == "manual-search"
    assert records[0].provenance[0].query == "powered mumbai"
    assert records[0].provenance[0].location == "Mumbai"
    assert records[0].provenance[0].source_url == str(path)


@pytest.mark.asyncio
async def test_directory_ingestion_deduplicates_globally_and_keeps_filename(tmp_path):
    imports = tmp_path / "imports"
    imports.mkdir()
    (imports / "search_delhi.csv").write_text("url\nbrand.in\n")
    (imports / "search_mumbai.csv").write_text("website\nhttps://brand.in/about\nhttps://other.in\n")
    store = SQLiteStore(tmp_path / "state.db")
    stats = await DiscoveryManager(store).run([DirectoryCSVDiscoveryProvider(imports)])
    assert stats.rows_read == 3
    assert stats.normalized_domains == 3
    assert stats.new_unique_domains == 2
    assert stats.duplicates == 1
    provenance_files = {Path(item.source_url).name for item in store.get_provenance("https://brand.in")}
    assert provenance_files == {"search_delhi.csv", "search_mumbai.csv"}


def test_priority_score_combines_discovery_only_factors():
    record = CandidateRecord(
        normalized_domain="https://brand.in", original_url="brand.in", discovery_source="csv",
        discovery_count=2, signals=["cdn.shopify.com"],
        provenance=[
            CandidateProvenance(source="csv"),
            CandidateProvenance(source="search-csv", query='"Shopify" "Mumbai"'),
        ],
    )
    assert calculate_priority(record) == 9


def test_priority_does_not_imply_verification():
    record = CandidateRecord(normalized_domain="https://brand.in", original_url="brand.in", discovery_source="csv")
    assert calculate_priority(record) == 1
    assert record.status.value == "NEW"


@pytest.mark.asyncio
async def test_manager_merges_duplicate_candidates(tmp_path):
    csv_path = tmp_path / "domains.csv"
    csv_path.write_text("domain\nbrand.in\nhttps://www.brand.in/about\n")
    store = SQLiteStore(tmp_path / "state.db")
    stats = await DiscoveryManager(store).run([CSVDiscoveryProvider(csv_path)])
    assert stats.new_unique_domains == 1
    assert stats.duplicates == 1
    assert len(store.list_candidates()) == 1


class FakeCrawler:
    def __init__(self, html):
        self.html = html

    async def fetch(self, domain):
        from rivyou.crawler import CrawledPage
        return CrawledPage(domain, domain, 200, self.html)


@pytest.mark.asyncio
async def test_prefilter_detects_strong_fingerprint():
    result = await prefilter_shopify("https://brand.in", FakeCrawler('<img src="/cdn/shop/logo.png">'))
    assert result.plausible
    assert result.score == 3


@pytest.mark.asyncio
async def test_prefilter_rejects_weak_footer_only():
    result = await prefilter_shopify("https://brand.in", FakeCrawler("Powered by Shopify"))
    assert not result.plausible
    assert result.score == 1

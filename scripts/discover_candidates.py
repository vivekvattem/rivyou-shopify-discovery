#!/usr/bin/env python3
"""Ingest candidate leads and provenance into SQLite."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.config import SETTINGS  # noqa: E402
from rivyou.discover.commoncrawl import CommonCrawlImportProvider, CommonCrawlIndexProvider  # noqa: E402
from rivyou.discover.domain_sources import CSVDiscoveryProvider, DirectoryCSVDiscoveryProvider  # noqa: E402
from rivyou.discover.manager import DiscoveryManager  # noqa: E402
from rivyou.discover.search_queries import SearchResultsCSVProvider, export_search_queries  # noqa: E402
from rivyou.storage.sqlite_store import SQLiteStore  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover and persist unverified candidate domains")
    parser.add_argument(
        "--source", choices=("csv", "directory", "search", "search-csv", "commoncrawl", "all"), default="all"
    )
    parser.add_argument("--file", help="CSV source or imported Common Crawl export")
    parser.add_argument("--directory", default="data/discovery/imports", help="Directory of CSV discovery exports")
    parser.add_argument("--generate-queries", action="store_true")
    parser.add_argument("--output", default="data/discovery/generated_queries.csv")
    parser.add_argument("--database", default=SETTINGS.database_path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--commoncrawl-live", action="store_true", help="Query the public Common Crawl URL index")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    if args.generate_queries:
        count = export_search_queries(args.output)
        print(f"Generated {count} prioritized queries in {args.output}")
        if args.source == "search":
            return
    providers = []
    if args.source == "csv":
        if not args.file:
            raise SystemExit("--source csv requires --file")
        providers.append(CSVDiscoveryProvider(args.file))
    elif args.source == "directory":
        providers.append(DirectoryCSVDiscoveryProvider(args.directory))
    elif args.source == "search-csv":
        if not args.file:
            raise SystemExit("--source search-csv requires --file")
        providers.append(SearchResultsCSVProvider(args.file))
    elif args.source == "commoncrawl":
        providers.append(CommonCrawlImportProvider(args.file) if args.file else CommonCrawlIndexProvider())
    elif args.source == "search" and not args.generate_queries:
        path = args.file or "data/discovery/search_results.csv"
        providers.append(SearchResultsCSVProvider(path))
    elif args.source == "all":
        search_path = Path(args.file or "data/discovery/search_results.csv")
        if search_path.exists():
            providers.append(SearchResultsCSVProvider(search_path))
        generic = Path("data/discovery/domain_sources.csv")
        if generic.exists():
            providers.append(CSVDiscoveryProvider(generic))
        commoncrawl = Path("data/discovery/commoncrawl_domains.csv")
        if commoncrawl.exists():
            providers.append(CommonCrawlImportProvider(commoncrawl))
        if args.commoncrawl_live:
            providers.append(CommonCrawlIndexProvider())
        imports = Path(args.directory)
        if imports.is_dir():
            providers.append(DirectoryCSVDiscoveryProvider(imports))
    if not providers:
        print("No discovery inputs found; nothing to ingest.")
        return
    store = SQLiteStore(args.database)
    started = time.perf_counter()
    run_id = store.create_run("DISCOVERY", args.limit, {"sources": [provider.name for provider in providers]})
    stats = await DiscoveryManager(store).run(providers, args.limit)
    elapsed = time.perf_counter() - started
    store.finish_run(
        run_id, stats.normalized_domains, 0, discovery_seconds=elapsed, total_seconds=elapsed
    )
    print(f"rows read: {stats.rows_read}")
    print(f"valid domains: {stats.normalized_domains}")
    print(f"new domains: {stats.new_unique_domains}")
    print(f"existing domains: {stats.existing_domains}")
    print(f"invalid rows: {stats.invalid_rows}")
    print(f"duplicates: {stats.duplicates}")
    print(f"source breakdown: {dict(stats.source_breakdown)}")
    print(f"discovery runtime: {elapsed:.2f}s")
    print(f"domains/minute: {(stats.normalized_domains / (elapsed / 60)) if elapsed else 0:.2f}")
    print("top priority candidates:")
    for candidate in store.list_candidates(limit=10):
        print(f"  {candidate.priority_score:2d}  {candidate.status.value:18s}  {candidate.normalized_domain}")


if __name__ == "__main__":
    asyncio.run(run(arguments()))

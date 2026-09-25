#!/usr/bin/env python3
"""Run the Phase 1 enrichment pipeline from a seed CSV."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.config import SETTINGS  # noqa: E402
from rivyou.pipeline import run_from_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify and enrich candidate Indian Shopify stores")
    parser.add_argument("--input", default="data/seeds.csv", help="Seed CSV containing domain_url")
    parser.add_argument("--output", default="data/output", help="Directory for CSV/JSON output")
    parser.add_argument("--concurrency", type=int, help="Maximum concurrent HTTP requests")
    parser.add_argument("--limit", type=int, help="Maximum unique seed candidates")
    parser.add_argument("--verbose", action="store_true", help="Enable detailed logs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    settings = SETTINGS.with_overrides(
        max_concurrency=args.concurrency if args.concurrency is not None else SETTINGS.max_concurrency
    )
    records = asyncio.run(run_from_file(args.input, args.output, settings=settings, limit=args.limit))
    print(f"Accepted {len(records)} verified stores. Output written to {args.output}")


if __name__ == "__main__":
    main()


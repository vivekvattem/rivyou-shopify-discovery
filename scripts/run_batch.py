#!/usr/bin/env python3
"""Run a resumable candidate batch from SQLite."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.batch import BatchRunner  # noqa: E402
from rivyou.config import SETTINGS  # noqa: E402
from rivyou.models import CandidateStatus  # noqa: E402
from rivyou.storage.sqlite_store import SQLiteStore  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process highest-priority candidates from SQLite")
    parser.add_argument("--status", action="append", choices=[item.value for item in CandidateStatus], default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=SETTINGS.max_concurrency)
    parser.add_argument("--recover-stale", type=int, metavar="MINUTES")
    parser.add_argument("--wave", help="Operational wave label persisted with this run, e.g. wave-2")
    parser.add_argument("--database", default=SETTINGS.database_path)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = SQLiteStore(args.database)
    settings = SETTINGS.with_overrides(max_concurrency=args.concurrency)
    statuses = [CandidateStatus(value) for value in (args.status or [CandidateStatus.NEW.value])]
    outcome = await BatchRunner(store, settings, use_cache=not args.no_cache).run(
        statuses, args.limit, args.recover_stale, args.wave
    )
    print(f"run ID: {outcome.run_id}")
    print(f"selected: {outcome.selected}")
    print(f"prefilter passed: {outcome.prefilter_passed}")
    print(f"Shopify verified: {outcome.shopify_verified}")
    print(f"India verified: {outcome.india_verified}")
    print(f"accepted: {outcome.accepted}")
    print(f"rejected Shopify: {outcome.rejected_shopify}")
    print(f"rejected India: {outcome.rejected_india}")
    print(f"retry: {outcome.retry}")
    print(f"failed: {outcome.failed}")
    print(f"runtime: {outcome.runtime_seconds:.2f}s")
    print(f"domains/minute: {outcome.domains_per_minute:.2f}")
    print(f"accepted/minute: {outcome.accepted_per_minute:.2f}")
    print(f"average Shopify score: {outcome.average_shopify_score if outcome.average_shopify_score is not None else 'N/A'}")
    print(f"average India score: {outcome.average_india_score if outcome.average_india_score is not None else 'N/A'}")


if __name__ == "__main__":
    asyncio.run(run(arguments()))

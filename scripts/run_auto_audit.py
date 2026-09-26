#!/usr/bin/env python3
"""Run machine pre-review for every currently accepted store."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.audit.automated import run_auto_audit  # noqa: E402
from rivyou.config import SETTINGS  # noqa: E402
from rivyou.storage.sqlite_store import SQLiteStore  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Machine pre-review of accepted stores; never fills manual fields")
    parser.add_argument("--database", default=SETTINGS.database_path)
    parser.add_argument("--output", default="data/audits")
    parser.add_argument("--concurrency", type=int, default=SETTINGS.max_concurrency)
    parser.add_argument("--no-cache", action="store_true")
    return parser.parse_args()


async def main(args: argparse.Namespace) -> None:
    settings = SETTINGS.with_overrides(max_concurrency=args.concurrency)
    summary = await run_auto_audit(
        SQLiteStore(args.database), args.output, settings=settings, use_cache=not args.no_cache
    )
    print(f"Auto audit CSV: {summary.path}")
    print(f"total accepted stores: {summary.total}")
    for confidence in ("HIGH", "MEDIUM", "LOW"):
        print(f"{confidence} confidence: {summary.confidence_counts.get(confidence, 0)}")
    for name in ("shopify", "india", "logo", "state", "contacts", "socials"):
        counts = summary.check_counts[name]
        rendered = " ".join(f"{verdict}={counts.get(verdict, 0)}" for verdict in ("PASS", "FAIL", "UNCERTAIN", "MISSING"))
        print(f"{name}: {rendered}")
    print("\nNEEDS HUMAN REVIEW")
    if summary.needs_human_review:
        for domain in summary.needs_human_review:
            print(f"- {domain}")
    else:
        print("None")
    print("\nMachine results are pre-review only; manual_* fields remain blank.")


if __name__ == "__main__":
    asyncio.run(main(arguments()))

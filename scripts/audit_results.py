#!/usr/bin/env python3
"""Create a stratified manual precision-audit worksheet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.audit.sampling import create_audit_sample  # noqa: E402
from rivyou.config import SETTINGS  # noqa: E402
from rivyou.storage.sqlite_store import SQLiteStore  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sample pipeline outcomes for manual review")
    parser.add_argument("--accepted", type=int, default=30)
    parser.add_argument("--rejected-shopify", type=int, default=10)
    parser.add_argument("--rejected-india", type=int, default=10)
    parser.add_argument("--database", default=SETTINGS.database_path)
    parser.add_argument("--output", default="data/audits")
    args = parser.parse_args()
    path = create_audit_sample(
        SQLiteStore(args.database), args.output, args.accepted, args.rejected_shopify, args.rejected_india
    )
    print(f"Audit worksheet written to {path}")


#!/usr/bin/env python3
"""Export unique accepted records from SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.config import SETTINGS  # noqa: E402
from rivyou.exporter import export_accepted  # noqa: E402
from rivyou.storage.sqlite_store import SQLiteStore  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export accepted stores from SQLite")
    parser.add_argument("--database", default=SETTINGS.database_path)
    parser.add_argument("--output", default="data/output")
    args = parser.parse_args()
    count = export_accepted(SQLiteStore(args.database), args.output)
    print(f"Exported {count} unique accepted stores to {args.output}")


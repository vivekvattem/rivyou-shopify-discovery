#!/usr/bin/env python3
"""Print and optionally save the Phase 2 funnel/quality report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.audit.report import build_report  # noqa: E402
from rivyou.config import SETTINGS  # noqa: E402
from rivyou.storage.sqlite_store import SQLiteStore  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Report discovery funnel and output quality")
    parser.add_argument("--database", default=SETTINGS.database_path)
    parser.add_argument("--json-output")
    args = parser.parse_args()
    report = build_report(SQLiteStore(args.database))
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json_output:
        target = Path(args.json_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")

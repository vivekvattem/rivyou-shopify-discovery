#!/usr/bin/env python3
"""Write accepted-record missing-field diagnostics and print percentages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.audit.diagnostics import write_missing_fields_markdown, write_missing_fields_report  # noqa: E402
from rivyou.config import SETTINGS  # noqa: E402
from rivyou.storage.sqlite_store import SQLiteStore  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Report missing fields in accepted store records")
    parser.add_argument("--database", default=SETTINGS.database_path)
    parser.add_argument("--output", default="data/audits/missing_fields.csv")
    parser.add_argument("--markdown-output", default="data/output/missing_fields.md")
    args = parser.parse_args()
    store = SQLiteStore(args.database)
    percentages = write_missing_fields_report(store, args.output)
    write_missing_fields_markdown(store.accepted_records(), args.markdown_output)
    print(f"Missing-field report written to {args.output}")
    print(f"Markdown completeness table written to {args.markdown_output}")
    for field, percentage in percentages.items():
        print(f"missing {field}: {percentage:.1f}%")

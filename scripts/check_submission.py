#!/usr/bin/env python3
"""Check whether final assignment artifacts are ready for submission."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.submission import check_submission, render_checks  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate final submission artifacts and methodology")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--minimum-rows", type=int, default=1000)
    args = parser.parse_args()
    checks = check_submission(args.project_root, args.minimum_rows)
    print(render_checks(checks))
    raise SystemExit(0 if checks and all(item.passed for item in checks) else 1)

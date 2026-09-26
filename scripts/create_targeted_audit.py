#!/usr/bin/env python3
"""Create a risk-targeted accepted-store manual review worksheet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.audit.sampling import create_targeted_accepted_sample  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a targeted sample from an auto-audit CSV")
    parser.add_argument("auto_audit", help="Path to an auto_audit_*.csv file")
    parser.add_argument("--output", default="data/audits")
    parser.add_argument("--target", type=int, default=15)
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument(
        "--review-all-limit",
        type=int,
        default=30,
        help="Include all LOW/MEDIUM rows when their combined count is at most this limit",
    )
    args = parser.parse_args()
    path = create_targeted_accepted_sample(
        args.auto_audit,
        args.output,
        target=args.target,
        seed=args.seed,
        review_all_limit=args.review_all_limit,
    )
    print(f"Targeted audit worksheet written to {path}")

#!/usr/bin/env python3
"""Evaluate completed manual audit ratings without inventing missing values."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rivyou.audit.evaluate import evaluate_audit, format_evaluation  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate precision from a completed audit CSV")
    parser.add_argument("path")
    args = parser.parse_args()
    print(format_evaluation(evaluate_audit(args.path)))


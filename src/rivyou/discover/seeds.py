"""Load and normalize user-provided seed CSV files."""

from __future__ import annotations

import csv
from pathlib import Path

from rivyou.models import StoreCandidate
from rivyou.utils.dedupe import dedupe_candidates
from rivyou.utils.domains import normalize_domain


def load_candidates(path: str | Path, limit: int | None = None) -> list[StoreCandidate]:
    candidates: list[StoreCandidate] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "domain_url" not in reader.fieldnames:
            raise ValueError("Seed CSV must contain a domain_url column")
        for row in reader:
            original = (row.get("domain_url") or "").strip()
            normalized = normalize_domain(original)
            if normalized:
                candidates.append(StoreCandidate(original_url=original, normalized_domain=normalized))
    unique = dedupe_candidates(candidates)
    return unique[:limit] if limit is not None else unique


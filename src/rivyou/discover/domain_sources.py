"""Flexible importers for open lists, directories, and manual URL collections."""

from __future__ import annotations

import csv
from pathlib import Path

from rivyou.models import CandidateProvenance, CandidateRecord
from rivyou.utils.domains import normalize_domain

URL_COLUMNS = ("domain_url", "domain", "url", "website", "site", "result_url")


class CSVDiscoveryProvider:
    name = "csv"

    def __init__(self, path: str | Path, source_name: str | None = None):
        self.path = Path(path)
        self.source_name = source_name or f"csv:{self.path.name}"
        self.raw_count = 0
        self.rows_read = 0
        self.invalid_count = 0

    async def discover(self, limit: int | None = None) -> list[CandidateRecord]:
        records: list[CandidateRecord] = []
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            columns = {column.lower(): column for column in (reader.fieldnames or [])}
            available = [columns[name] for name in URL_COLUMNS if name in columns]
            if not available:
                raise ValueError(f"{self.path} needs one of these columns: {', '.join(URL_COLUMNS)}")
            for row in reader:
                self.rows_read += 1
                original = next(((row.get(column) or "").strip() for column in available if (row.get(column) or "").strip()), "")
                if not original:
                    self.invalid_count += 1
                    continue
                self.raw_count += 1
                normalized = normalize_domain(original)
                if not normalized:
                    self.invalid_count += 1
                    continue
                signal = (row.get(columns.get("signal", "")) or "").strip() or None
                source = (row.get(columns.get("source", "")) or "").strip() or self.source_name
                query = (row.get(columns.get("query", "")) or "").strip() or None
                location = (row.get(columns.get("location", "")) or "").strip() or None
                category_hint = (row.get(columns.get("category_hint", "")) or "").strip() or None
                provenance = CandidateProvenance(
                    source=source, query=query, location=location, source_url=str(self.path), signal=signal,
                    category_hint=category_hint,
                )
                records.append(CandidateRecord(
                    normalized_domain=normalized, original_url=original, discovery_source=source,
                    discovery_query=query, source_url=str(self.path), signals=[signal] if signal else [],
                    provenance=[provenance],
                ))
                if limit is not None and len(records) >= limit:
                    break
        return records


class DirectoryCSVDiscoveryProvider:
    """Read every CSV in a directory while retaining each input filename."""

    name = "directory"

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.raw_count = 0
        self.rows_read = 0
        self.invalid_count = 0
        self.file_count = 0

    async def discover(self, limit: int | None = None) -> list[CandidateRecord]:
        if not self.directory.is_dir():
            raise ValueError(f"Discovery directory does not exist: {self.directory}")
        records: list[CandidateRecord] = []
        for path in sorted(self.directory.glob("*.csv")):
            remaining = None if limit is None else max(0, limit - len(records))
            if remaining == 0:
                break
            provider = CSVDiscoveryProvider(path, source_name=f"directory:{path.name}")
            imported = await provider.discover(remaining)
            self.file_count += 1
            self.raw_count += provider.raw_count
            self.rows_read += provider.rows_read
            self.invalid_count += provider.invalid_count
            records.extend(imported)
        return records

"""SQLite persistence for candidates, provenance, cache, runs, and results."""

from __future__ import annotations

import json
import sqlite3
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from rivyou.models import CandidateProvenance, CandidateRecord, CandidateStatus, StoreRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    original_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW',
    priority_score INTEGER NOT NULL DEFAULT 0,
    discovery_count INTEGER NOT NULL DEFAULT 1,
    signals_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    retry_reason TEXT,
    prefilter_json TEXT,
    verification_json TEXT,
    shopify_score INTEGER,
    india_score INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candidates_status_priority
    ON candidates(status, priority_score DESC, updated_at ASC);

CREATE TABLE IF NOT EXISTS candidate_provenance (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    discovery_query TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    signal TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    UNIQUE(candidate_id, source, discovery_query, source_url, signal)
);
CREATE INDEX IF NOT EXISTS idx_provenance_source ON candidate_provenance(source);

CREATE TABLE IF NOT EXISTS crawl_cache (
    url TEXT PRIMARY KEY,
    status_code INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    body_zlib BLOB NOT NULL,
    fetched_at TEXT NOT NULL,
    etag TEXT,
    last_modified TEXT,
    final_url TEXT NOT NULL,
    headers_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    requested_status TEXT,
    requested_limit INTEGER,
    wave TEXT,
    processed_count INTEGER NOT NULL DEFAULT 0,
    prefilter_passed_count INTEGER NOT NULL DEFAULT 0,
    shopify_verified_count INTEGER NOT NULL DEFAULT 0,
    india_verified_count INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_shopify_count INTEGER NOT NULL DEFAULT 0,
    rejected_india_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    average_shopify_score REAL,
    average_india_score REAL,
    discovery_seconds REAL NOT NULL DEFAULT 0,
    verification_seconds REAL NOT NULL DEFAULT 0,
    total_seconds REAL NOT NULL DEFAULT 0,
    domains_per_minute REAL NOT NULL DEFAULT 0,
    accepted_per_minute REAL NOT NULL DEFAULT 0,
    acceptance_percentage REAL NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS store_results (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER REFERENCES candidates(id) ON DELETE SET NULL,
    domain TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

ALLOWED_TRANSITIONS: dict[CandidateStatus, set[CandidateStatus]] = {
    CandidateStatus.NEW: {CandidateStatus.QUEUED, CandidateStatus.PROCESSING, CandidateStatus.FAILED},
    CandidateStatus.QUEUED: {CandidateStatus.PROCESSING, CandidateStatus.RETRY, CandidateStatus.FAILED},
    CandidateStatus.PROCESSING: {
        CandidateStatus.ACCEPTED, CandidateStatus.REJECTED_SHOPIFY, CandidateStatus.REJECTED_INDIA,
        CandidateStatus.FAILED, CandidateStatus.RETRY,
    },
    CandidateStatus.RETRY: {CandidateStatus.QUEUED, CandidateStatus.PROCESSING, CandidateStatus.FAILED},
    CandidateStatus.FAILED: {CandidateStatus.RETRY, CandidateStatus.PROCESSING},
    CandidateStatus.REJECTED_SHOPIFY: {CandidateStatus.RETRY, CandidateStatus.PROCESSING},
    CandidateStatus.REJECTED_INDIA: {CandidateStatus.RETRY, CandidateStatus.PROCESSING},
    CandidateStatus.ACCEPTED: {CandidateStatus.RETRY, CandidateStatus.PROCESSING},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class UpsertOutcome:
    created: bool
    provenance_added: int


@dataclass(frozen=True, slots=True)
class CachedResponse:
    url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    fetched_at: datetime
    etag: str | None
    last_modified: str | None
    headers: dict[str, str]


class SQLiteStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(SCHEMA)
            self._ensure_columns(connection, "pipeline_runs", {
                "wave": "TEXT",
                "prefilter_passed_count": "INTEGER NOT NULL DEFAULT 0",
                "shopify_verified_count": "INTEGER NOT NULL DEFAULT 0",
                "india_verified_count": "INTEGER NOT NULL DEFAULT 0",
                "rejected_shopify_count": "INTEGER NOT NULL DEFAULT 0",
                "rejected_india_count": "INTEGER NOT NULL DEFAULT 0",
                "retry_count": "INTEGER NOT NULL DEFAULT 0",
                "failed_count": "INTEGER NOT NULL DEFAULT 0",
                "average_shopify_score": "REAL",
                "average_india_score": "REAL",
                "discovery_seconds": "REAL NOT NULL DEFAULT 0",
                "verification_seconds": "REAL NOT NULL DEFAULT 0",
                "total_seconds": "REAL NOT NULL DEFAULT 0",
                "domains_per_minute": "REAL NOT NULL DEFAULT 0",
                "accepted_per_minute": "REAL NOT NULL DEFAULT 0",
                "acceptance_percentage": "REAL NOT NULL DEFAULT 0",
            })
            self._ensure_columns(connection, "candidates", {"retry_reason": "TEXT"})
            self._ensure_columns(connection, "candidate_provenance", {"location": "TEXT NOT NULL DEFAULT ''"})
            connection.execute(
                """UPDATE candidates SET retry_reason = CASE
                   WHEN lower(COALESCE(last_error,'')) LIKE '%robots.txt%' THEN 'ROBOTS_BLOCKED'
                   WHEN lower(COALESCE(last_error,'')) LIKE '%429%' THEN 'HTTP_429'
                   WHEN lower(COALESCE(last_error,'')) GLOB '*http 5[0-9][0-9]*' THEN 'HTTP_5XX'
                   WHEN lower(COALESCE(last_error,'')) LIKE '%timeout%' THEN 'TIMEOUT'
                   WHEN lower(COALESCE(last_error,'')) LIKE '%dns%'
                     OR lower(COALESCE(last_error,'')) LIKE '%getaddrinfo%' THEN 'DNS_ERROR'
                   WHEN lower(COALESCE(last_error,'')) LIKE '%ssl%'
                     OR lower(COALESCE(last_error,'')) LIKE '%certificate%' THEN 'SSL_ERROR'
                   WHEN lower(COALESCE(last_error,'')) LIKE '%connect%' THEN 'CONNECTION_ERROR'
                   ELSE 'OTHER_TRANSIENT' END
                   WHERE status='RETRY' AND (retry_reason IS NULL OR retry_reason='')"""
            )

    @staticmethod
    def _ensure_columns(connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        """Apply additive migrations to databases created by an earlier project phase."""
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def upsert_candidate(self, candidate: CandidateRecord) -> UpsertOutcome:
        candidate.ensure_provenance()
        timestamp = _now()
        with self.connection() as connection:
            existing = connection.execute("SELECT id, signals_json FROM candidates WHERE domain = ?", (candidate.normalized_domain,)).fetchone()
            if existing:
                signals = sorted(set(json.loads(existing["signals_json"])) | set(candidate.signals))
                connection.execute(
                    """UPDATE candidates SET original_url = ?, discovery_count = discovery_count + ?,
                       signals_json = ?, notes = COALESCE(?, notes), updated_at = ? WHERE id = ?""",
                    (candidate.original_url, max(1, candidate.discovery_count), json.dumps(signals), candidate.notes, timestamp, existing["id"]),
                )
                candidate_id = existing["id"]
                created = False
            else:
                cursor = connection.execute(
                    """INSERT INTO candidates
                       (domain, original_url, status, priority_score, discovery_count, signals_json, notes, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (candidate.normalized_domain, candidate.original_url, candidate.status.value, candidate.priority_score,
                     max(1, candidate.discovery_count), json.dumps(sorted(set(candidate.signals))), candidate.notes, timestamp, timestamp),
                )
                candidate_id = cursor.lastrowid
                created = True
            added = 0
            for provenance in candidate.provenance:
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO candidate_provenance
                       (candidate_id, source, discovery_query, location, source_url, signal, observed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (candidate_id, provenance.source, provenance.query or "", provenance.location or "",
                     provenance.source_url or "", provenance.signal or "", provenance.observed_at.isoformat()),
                )
                added += cursor.rowcount
            return UpsertOutcome(created=created, provenance_added=added)

    def update_priority(self, domain: str, score: int) -> None:
        with self.connection() as connection:
            connection.execute("UPDATE candidates SET priority_score = ?, updated_at = ? WHERE domain = ?", (score, _now(), domain))

    def get_provenance(self, domain: str) -> list[CandidateProvenance]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT p.* FROM candidate_provenance p JOIN candidates c ON c.id = p.candidate_id
                   WHERE c.domain = ? ORDER BY p.observed_at""", (domain,),
            ).fetchall()
        return [CandidateProvenance(
            source=row["source"], query=row["discovery_query"] or None, location=row["location"] or None,
            source_url=row["source_url"] or None,
            signal=row["signal"] or None, observed_at=datetime.fromisoformat(row["observed_at"]),
        ) for row in rows]

    def get_candidate(self, domain: str) -> CandidateRecord | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM candidates WHERE domain = ?", (domain,)).fetchone()
        return self._candidate_from_row(row) if row else None

    def list_candidates(
        self, statuses: Sequence[CandidateStatus | str] | None = None, limit: int | None = None
    ) -> list[CandidateRecord]:
        params: list[Any] = []
        where = ""
        if statuses:
            values = [status.value if isinstance(status, CandidateStatus) else status for status in statuses]
            where = f"WHERE status IN ({','.join('?' for _ in values)})"
            params.extend(values)
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            params.append(limit)
        with self.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM candidates {where} ORDER BY priority_score DESC, created_at ASC{limit_sql}", params
            ).fetchall()
        return [self._candidate_from_row(row) for row in rows]

    def _candidate_from_row(self, row: sqlite3.Row) -> CandidateRecord:
        provenance = self.get_provenance(row["domain"])
        return CandidateRecord(
            normalized_domain=row["domain"], original_url=row["original_url"],
            discovery_source=provenance[0].source if provenance else "unknown",
            discovery_query=provenance[0].query if provenance else None,
            source_url=provenance[0].source_url if provenance else None,
            first_seen_at=datetime.fromisoformat(row["created_at"]), last_seen_at=datetime.fromisoformat(row["updated_at"]),
            discovery_count=row["discovery_count"], signals=json.loads(row["signals_json"]),
            priority_score=row["priority_score"], status=CandidateStatus(row["status"]), notes=row["notes"], provenance=provenance,
            attempt_count=row["attempt_count"], last_error=row["last_error"], retry_reason=row["retry_reason"],
        )

    def transition(
        self,
        domain: str,
        new_status: CandidateStatus,
        *,
        error: str | None = None,
        retry_reason: str | None = None,
        evidence: dict[str, Any] | None = None,
        shopify_score: int | None = None,
        india_score: int | None = None,
        increment_attempt: bool = False,
        force: bool = False,
    ) -> None:
        with self.connection() as connection:
            row = connection.execute("SELECT status FROM candidates WHERE domain = ?", (domain,)).fetchone()
            if not row:
                raise KeyError(domain)
            current = CandidateStatus(row["status"])
            if not force and new_status != current and new_status not in ALLOWED_TRANSITIONS[current]:
                raise ValueError(f"Invalid candidate transition: {current.value} -> {new_status.value}")
            connection.execute(
                """UPDATE candidates SET status = ?, last_error = ?, retry_reason = ?,
                   verification_json = COALESCE(?, verification_json),
                   shopify_score = COALESCE(?, shopify_score), india_score = COALESCE(?, india_score),
                   attempt_count = attempt_count + ?, updated_at = ? WHERE domain = ?""",
                (new_status.value, error, retry_reason, json.dumps(evidence) if evidence is not None else None,
                 shopify_score, india_score, int(increment_attempt), _now(), domain),
            )

    def set_prefilter(self, domain: str, evidence: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE candidates SET prefilter_json = ?, updated_at = ? WHERE domain = ?",
                (json.dumps(evidence), _now(), domain),
            )

    def recover_stale(self, minutes: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        with self.connection() as connection:
            cursor = connection.execute(
                """UPDATE candidates SET status = 'RETRY', last_error = 'Recovered stale PROCESSING candidate',
                   retry_reason = 'STALE_PROCESSING', updated_at = ?
                   WHERE status = 'PROCESSING' AND updated_at < ?""", (_now(), cutoff),
            )
            return cursor.rowcount

    def create_run(
        self, status: str, limit: int | None, metadata: dict[str, Any] | None = None, wave: str | None = None
    ) -> int:
        with self.connection() as connection:
            cursor = connection.execute(
                """INSERT INTO pipeline_runs
                   (started_at, requested_status, requested_limit, wave, metadata_json) VALUES (?, ?, ?, ?, ?)""",
                (_now(), status, limit, wave, json.dumps(metadata or {})),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        processed: int,
        accepted: int,
        *,
        discovery_seconds: float = 0.0,
        verification_seconds: float = 0.0,
        total_seconds: float = 0.0,
        funnel: dict[str, int | float | None] | None = None,
    ) -> None:
        minutes = total_seconds / 60 if total_seconds > 0 else 0.0
        funnel = funnel or {}
        with self.connection() as connection:
            connection.execute(
                """UPDATE pipeline_runs SET finished_at = ?, processed_count = ?, accepted_count = ?,
                   prefilter_passed_count = ?, shopify_verified_count = ?, india_verified_count = ?,
                   rejected_shopify_count = ?, rejected_india_count = ?, retry_count = ?, failed_count = ?,
                   average_shopify_score = ?, average_india_score = ?,
                   discovery_seconds = ?, verification_seconds = ?, total_seconds = ?,
                   domains_per_minute = ?, accepted_per_minute = ?, acceptance_percentage = ? WHERE id = ?""",
                (_now(), processed, accepted,
                 funnel.get("prefilter_passed", 0), funnel.get("shopify_verified", 0),
                 funnel.get("india_verified", accepted), funnel.get("rejected_shopify", 0),
                 funnel.get("rejected_india", 0), funnel.get("retry", 0), funnel.get("failed", 0),
                 funnel.get("average_shopify_score"), funnel.get("average_india_score"),
                 discovery_seconds, verification_seconds, total_seconds,
                 processed / minutes if minutes else 0.0, accepted / minutes if minutes else 0.0,
                 100 * accepted / processed if processed else 0.0, run_id),
            )

    def latest_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def save_store_result(self, domain: str, record: StoreRecord) -> None:
        timestamp = _now()
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
        with self.connection() as connection:
            candidate = connection.execute("SELECT id FROM candidates WHERE domain = ?", (domain,)).fetchone()
            connection.execute(
                """INSERT INTO store_results (candidate_id, domain, record_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(domain) DO UPDATE SET record_json = excluded.record_json, updated_at = excluded.updated_at""",
                (candidate["id"] if candidate else None, record.domain_url, payload, timestamp, timestamp),
            )

    def accepted_records(self) -> list[StoreRecord]:
        with self.connection() as connection:
            rows = connection.execute("SELECT record_json FROM store_results ORDER BY domain").fetchall()
        return [StoreRecord.model_validate_json(row["record_json"]) for row in rows]

    def candidate_detail_rows(self, status: CandidateStatus, limit: int) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT domain, status, shopify_score, india_score, verification_json
                   FROM candidates WHERE status = ? ORDER BY RANDOM() LIMIT ?""", (status.value, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def cache_get(self, url: str, ttl_hours: float) -> CachedResponse | None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM crawl_cache WHERE url = ?", (url,)).fetchone()
        if not row:
            return None
        fetched = datetime.fromisoformat(row["fetched_at"])
        if fetched < cutoff:
            return None
        return CachedResponse(
            url=url, final_url=row["final_url"], status_code=row["status_code"], content_type=row["content_type"],
            body=zlib.decompress(row["body_zlib"]), fetched_at=fetched, etag=row["etag"],
            last_modified=row["last_modified"], headers=json.loads(row["headers_json"]),
        )

    def cache_set(
        self, url: str, final_url: str, status_code: int, content_type: str, body: bytes, headers: dict[str, str]
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO crawl_cache
                   (url, status_code, content_type, body_zlib, fetched_at, etag, last_modified, final_url, headers_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET status_code=excluded.status_code, content_type=excluded.content_type,
                   body_zlib=excluded.body_zlib, fetched_at=excluded.fetched_at, etag=excluded.etag,
                   last_modified=excluded.last_modified, final_url=excluded.final_url, headers_json=excluded.headers_json""",
                (url, status_code, content_type, zlib.compress(body), _now(), headers.get("etag"),
                 headers.get("last-modified"), final_url, json.dumps(headers)),
            )

    def status_counts(self) -> dict[str, int]:
        with self.connection() as connection:
            rows = connection.execute("SELECT status, COUNT(*) count FROM candidates GROUP BY status").fetchall()
        return {row["status"]: row["count"] for row in rows}

    def source_stats(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT p.source, COUNT(DISTINCT p.candidate_id) candidates,
                   COUNT(DISTINCT CASE WHEN c.status='ACCEPTED' THEN p.candidate_id END) accepted,
                   COUNT(DISTINCT CASE WHEN c.status='REJECTED_SHOPIFY' THEN p.candidate_id END) rejected_shopify,
                   COUNT(DISTINCT CASE WHEN c.status='REJECTED_INDIA' THEN p.candidate_id END) rejected_india
                   FROM candidate_provenance p JOIN candidates c ON c.id=p.candidate_id
                   GROUP BY p.source ORDER BY candidates DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def query_stats(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT p.discovery_query query, COUNT(DISTINCT p.candidate_id) candidates,
                   COUNT(DISTINCT CASE WHEN c.status='ACCEPTED' THEN p.candidate_id END) accepted,
                   COUNT(DISTINCT CASE WHEN c.status='REJECTED_SHOPIFY' THEN p.candidate_id END) rejected_shopify,
                   COUNT(DISTINCT CASE WHEN c.status='REJECTED_INDIA' THEN p.candidate_id END) rejected_india
                   FROM candidate_provenance p JOIN candidates c ON c.id=p.candidate_id
                   WHERE p.discovery_query != '' GROUP BY p.discovery_query ORDER BY candidates DESC, query"""
            ).fetchall()
        return [dict(row) for row in rows]

    def query_family_stats(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT p.source, p.signal, p.location, COUNT(DISTINCT p.candidate_id) candidates,
                   COUNT(DISTINCT CASE WHEN c.status='ACCEPTED' THEN p.candidate_id END) accepted,
                   COUNT(DISTINCT CASE WHEN c.status='REJECTED_SHOPIFY' THEN p.candidate_id END) rejected_shopify,
                   COUNT(DISTINCT CASE WHEN c.status='REJECTED_INDIA' THEN p.candidate_id END) rejected_india
                   FROM candidate_provenance p JOIN candidates c ON c.id=p.candidate_id
                   GROUP BY p.source, p.signal, p.location ORDER BY candidates DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def retry_reason_counts(self) -> dict[str, int]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT COALESCE(retry_reason, 'UNCLASSIFIED') reason, COUNT(*) count
                   FROM candidates WHERE status='RETRY' GROUP BY reason ORDER BY count DESC"""
            ).fetchall()
        return {row["reason"]: row["count"] for row in rows}

    def aggregate_stats(self) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute(
                """SELECT COUNT(*) total, COALESCE(SUM(discovery_count),0) raw_discoveries,
                   COALESCE(SUM(CASE WHEN prefilter_json IS NOT NULL THEN 1 ELSE 0 END),0) homepage_prefiltered,
                   COALESCE(SUM(CASE WHEN prefilter_json LIKE '%\"plausible\": true%' THEN 1 ELSE 0 END),0) shopify_plausible,
                   COALESCE(SUM(CASE WHEN status IN ('REJECTED_INDIA','ACCEPTED') THEN 1 ELSE 0 END),0) shopify_verified,
                   COALESCE(SUM(CASE WHEN status='ACCEPTED' THEN 1 ELSE 0 END),0) indian_verified
                   FROM candidates"""
            ).fetchone()
        return dict(row)

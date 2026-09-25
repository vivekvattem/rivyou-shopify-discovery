import json
from datetime import datetime, timedelta, timezone

import pytest

from rivyou.models import CandidateProvenance, CandidateRecord, CandidateStatus, StoreRecord
from rivyou.storage.sqlite_store import SQLiteStore


def candidate(domain="https://brand.in", source="csv", signal=None):
    return CandidateRecord(
        normalized_domain=domain,
        original_url=domain,
        discovery_source=source,
        signals=[signal] if signal else [],
        provenance=[CandidateProvenance(source=source, signal=signal)],
    )


def test_database_initializes_all_tables(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    with store.connection() as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"candidates", "candidate_provenance", "crawl_cache", "pipeline_runs", "store_results"} <= names


def test_duplicate_candidate_upsert_is_unique_and_counted(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    assert store.upsert_candidate(candidate()).created
    assert not store.upsert_candidate(candidate()).created
    assert len(store.list_candidates()) == 1
    assert store.get_candidate("https://brand.in").discovery_count == 2


def test_candidate_provenance_merges_sources(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.upsert_candidate(candidate(source="csv"))
    store.upsert_candidate(candidate(source="search-csv", signal="cdn.shopify.com"))
    assert {item.source for item in store.get_provenance("https://brand.in")} == {"csv", "search-csv"}
    assert store.get_candidate("https://brand.in").signals == ["cdn.shopify.com"]


def test_valid_status_transitions_and_attempt_count(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.upsert_candidate(candidate())
    store.transition("https://brand.in", CandidateStatus.PROCESSING, increment_attempt=True)
    store.transition("https://brand.in", CandidateStatus.ACCEPTED)
    assert store.get_candidate("https://brand.in").status == CandidateStatus.ACCEPTED
    with store.connection() as connection:
        assert connection.execute("SELECT attempt_count FROM candidates").fetchone()[0] == 1


def test_invalid_status_transition_is_rejected(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.upsert_candidate(candidate())
    with pytest.raises(ValueError):
        store.transition("https://brand.in", CandidateStatus.ACCEPTED)


def test_stale_processing_recovery(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.upsert_candidate(candidate())
    store.transition("https://brand.in", CandidateStatus.PROCESSING)
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with store.connection() as connection:
        connection.execute("UPDATE candidates SET updated_at=?", (stale,))
    assert store.recover_stale(30) == 1
    assert store.get_candidate("https://brand.in").status == CandidateStatus.RETRY


def test_candidates_are_sorted_by_priority(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.upsert_candidate(candidate("https://low.in"))
    store.upsert_candidate(candidate("https://high.in"))
    store.update_priority("https://high.in", 9)
    assert store.list_candidates(limit=1)[0].normalized_domain == "https://high.in"


def test_cache_roundtrip_compresses_transparently(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.cache_set("https://brand.in", "https://brand.in", 200, "text/html", b"<h1>Brand</h1>", {"etag": "abc"})
    cached = store.cache_get("https://brand.in", 24)
    assert cached.body == b"<h1>Brand</h1>"
    assert cached.etag == "abc"


def test_expired_cache_is_a_miss(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.cache_set("https://brand.in", "https://brand.in", 200, "text/html", b"old", {})
    stale = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with store.connection() as connection:
        connection.execute("UPDATE crawl_cache SET fetched_at=?", (stale,))
    assert store.cache_get("https://brand.in", 24) is None


def test_store_result_upsert_remains_unique(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.upsert_candidate(candidate())
    record = StoreRecord(domain_url="https://brand.in", shopify_score=5, india_score=6)
    store.save_store_result("https://brand.in", record)
    store.save_store_result("https://brand.in", record.model_copy(update={"india_score": 7}))
    assert len(store.accepted_records()) == 1
    assert store.accepted_records()[0].india_score == 7


def test_verification_evidence_persists_on_rejection(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    store.upsert_candidate(candidate())
    store.transition("https://brand.in", CandidateStatus.PROCESSING)
    store.transition("https://brand.in", CandidateStatus.REJECTED_SHOPIFY, evidence={"shopify": {"score": 1}}, shopify_score=1)
    with store.connection() as connection:
        row = connection.execute("SELECT verification_json, shopify_score FROM candidates").fetchone()
    assert json.loads(row[0])["shopify"]["score"] == 1
    assert row[1] == 1


def test_pipeline_run_persists_wave_funnel_and_scores(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    run_id = store.create_run("NEW", 100, wave="wave-2")
    store.finish_run(run_id, 10, 4, total_seconds=30, funnel={
        "prefilter_passed": 8, "shopify_verified": 6, "india_verified": 4,
        "rejected_shopify": 4, "rejected_india": 2, "retry": 0, "failed": 0,
        "average_shopify_score": 4.2, "average_india_score": 5.5,
    })
    row = store.latest_runs(1)[0]
    assert row["wave"] == "wave-2"
    assert row["prefilter_passed_count"] == 8
    assert row["shopify_verified_count"] == 6
    assert row["average_india_score"] == 5.5

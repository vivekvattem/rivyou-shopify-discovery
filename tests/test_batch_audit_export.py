import csv
import json

import pytest

import rivyou.batch as batch_module
from rivyou.audit.report import build_report
from rivyou.audit.sampling import create_audit_sample
from rivyou.batch import BatchRunner, normalize_retry_reason
from rivyou.config import SETTINGS
from rivyou.discover.fingerprints import PreFilterResult
from rivyou.exporter import export_accepted
from rivyou.models import CandidateRecord, CandidateStatus, StoreRecord
from rivyou.storage.sqlite_store import SQLiteStore


def add_candidate(store, domain):
    store.upsert_candidate(CandidateRecord(
        normalized_domain=domain, original_url=domain, discovery_source="test"
    ))


class FakeAsyncCrawler:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakePipeline:
    def __init__(self, *args, **kwargs):
        self.debug_records = []

    async def run(self, candidates):
        for candidate in candidates:
            domain = candidate.normalized_domain
            base = {"candidate": candidate.model_dump(), "shopify": {"score": 5}}
            if "accepted" in domain:
                record = StoreRecord(domain_url=domain, shopify_score=5, india_score=8, state="Karnataka")
                self.debug_records.append({**base, "accepted": True, "india": {"score": 8}, "record": record.model_dump(mode="json")})
            elif "india" in domain:
                self.debug_records.append({**base, "accepted": False, "india": {"score": 1}, "rejection_reason": "India score below threshold"})
            else:
                self.debug_records.append({**base, "accepted": False, "rejection_reason": "Shopify score below threshold"})
        return []


@pytest.mark.asyncio
async def test_batch_persists_acceptance_and_rejections(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "state.db")
    for domain in ("https://accepted.in", "https://shopify-reject.in", "https://india-reject.in"):
        add_candidate(store, domain)

    async def plausible(*args, **kwargs):
        return PreFilterResult(plausible=True, score=3)

    monkeypatch.setattr(batch_module, "AsyncCrawler", FakeAsyncCrawler)
    monkeypatch.setattr(batch_module, "prefilter_shopify", plausible)
    monkeypatch.setattr(batch_module, "StorePipeline", FakePipeline)
    outcome = await BatchRunner(store, SETTINGS).run([CandidateStatus.NEW], 10)
    assert outcome.accepted == outcome.rejected_shopify == outcome.rejected_india == 1
    assert outcome.prefilter_passed == 3
    assert outcome.shopify_verified == 2
    assert outcome.india_verified == 1
    assert store.get_candidate("https://accepted.in").status == CandidateStatus.ACCEPTED
    assert store.get_candidate("https://shopify-reject.in").status == CandidateStatus.REJECTED_SHOPIFY
    assert store.get_candidate("https://india-reject.in").status == CandidateStatus.REJECTED_INDIA
    assert len(store.accepted_records()) == 1


def test_audit_sampling_leaves_manual_columns_blank(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    add_candidate(store, "https://brand.in")
    store.transition("https://brand.in", CandidateStatus.PROCESSING)
    store.transition("https://brand.in", CandidateStatus.REJECTED_SHOPIFY, evidence={"shopify": {"score": 1}})
    path = create_audit_sample(store, tmp_path / "audits", accepted=0, rejected_shopify=1, rejected_india=0)
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["manual_shopify_correct"] == ""
    assert rows[0]["manual_notes"] == ""


def test_export_is_unique_and_separates_debug(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    add_candidate(store, "https://brand.in")
    store.save_store_result("https://brand.in", StoreRecord(
        domain_url="https://brand.in", emails=["hi@brand.in"], shopify_score=5, india_score=7
    ))
    count = export_accepted(store, tmp_path / "output")
    public = json.loads((tmp_path / "output/indian_shopify_stores.json").read_text())
    debug = json.loads((tmp_path / "output/store_debug.json").read_text())
    assert count == len(public) == len(debug) == 1
    assert "shopify_evidence" not in public[0]
    assert "shopify_evidence" in debug[0]
    completeness = (tmp_path / "output/missing_fields.md").read_text()
    assert "| Contacts | 0 | 0.0% |" in completeness


def test_report_contains_funnel_and_source_rates(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    add_candidate(store, "https://brand.in")
    report = build_report(store)
    assert report["total_candidates"] == 1
    assert report["status_counts"]["NEW"] == 1
    assert report["top_discovery_sources"][0]["source"] == "test"
    assert report["retry_reason_counts"] == {}


@pytest.mark.parametrize("error,expected", [
    ("HTTP 429", "HTTP_429"),
    ("RetryableHTTPError: HTTP 503", "HTTP_5XX"),
    ("ConnectTimeout", "TIMEOUT"),
    ("certificate verify failed", "SSL_ERROR"),
    ("blocked by robots.txt", "ROBOTS_BLOCKED"),
])
def test_retry_reason_normalization(error, expected):
    assert normalize_retry_reason(error) == expected

import csv

from rivyou.audit.diagnostics import missing_fields_for_record, write_missing_fields_report
from rivyou.audit.evaluate import evaluate_audit, format_evaluation
from rivyou.audit.sampling import create_audit_sample
from rivyou.models import CandidateRecord, CandidateStatus, StoreRecord
from rivyou.storage.sqlite_store import SQLiteStore


def add_accepted(store, record):
    store.upsert_candidate(CandidateRecord(
        normalized_domain=record.domain_url, original_url=record.domain_url, discovery_source="test"
    ))
    store.transition(record.domain_url, CandidateStatus.PROCESSING)
    store.transition(
        record.domain_url, CandidateStatus.ACCEPTED,
        evidence={"shopify": {"score": record.shopify_score}, "india": {"score": record.india_score},
                  "record": record.model_dump(mode="json")},
        shopify_score=record.shopify_score, india_score=record.india_score,
    )
    store.save_store_result(record.domain_url, record)


def test_audit_sample_includes_extracted_and_manual_quality_fields(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    add_accepted(store, StoreRecord(
        domain_url="https://brand.in", emails=["care@brand.in"], phones=["+919876543210"],
        category="Jewellery", state="Karnataka", logo_url="https://brand.in/logo.svg",
        shopify_score=5, india_score=8,
    ))
    path = create_audit_sample(store, tmp_path, accepted=1, rejected_shopify=0, rejected_india=0)
    with path.open() as handle:
        row = next(csv.DictReader(handle))
    assert row["category"] == "Jewellery"
    assert row["state"] == "Karnataka"
    assert row["emails"] == '["care@brand.in"]'
    assert row["manual_logo_correct"] == row["manual_state_correct"] == row["manual_contacts_correct"] == ""


def test_audit_evaluation_uses_only_completed_ratings(tmp_path):
    path = tmp_path / "audit.csv"
    path.write_text(
        "manual_shopify_correct,manual_india_correct,manual_logo_correct,manual_state_correct,manual_contacts_correct\n"
        "yes,no,Y,,correct\nno,yes,N,,incorrect\n,,maybe,,\n"
    )
    metrics = evaluate_audit(path)
    assert metrics["shopify"].percentage == 50.0
    assert metrics["india"].percentage == 50.0
    assert metrics["logo"].percentage == 50.0
    assert metrics["state"].percentage is None
    assert metrics["logo"].invalid == 1


def test_blank_audit_does_not_invent_precision(tmp_path):
    path = tmp_path / "audit.csv"
    path.write_text(
        "manual_shopify_correct,manual_india_correct,manual_logo_correct,manual_state_correct,manual_contacts_correct\n,,,,\n"
    )
    output = format_evaluation(evaluate_audit(path))
    assert "Shopify precision: N/A" in output
    assert "0.0%" not in output


def test_missing_field_detection_treats_other_as_present_category():
    record = StoreRecord(domain_url="https://brand.in", category="Other", socials={"instagram": "https://instagram.com/brand"})
    missing = missing_fields_for_record(record)
    assert "category" not in missing
    assert "socials" not in missing
    assert "emails" in missing and "phones" in missing


def test_missing_fields_report_writes_only_incomplete_records(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    incomplete = StoreRecord(domain_url="https://missing.in", category="Fashion", shopify_score=5, india_score=7)
    complete = StoreRecord(
        domain_url="https://complete.in", emails=["hi@complete.in"], phones=["+919876543210"],
        socials={"instagram": "https://instagram.com/complete"}, category="Fashion",
        tagline_or_description="A sufficiently detailed merchant-authored description.",
        logo_url="https://complete.in/logo.svg", state="Delhi", shopify_score=5, india_score=7,
    )
    add_accepted(store, incomplete)
    add_accepted(store, complete)
    target = tmp_path / "missing.csv"
    percentages = write_missing_fields_report(store, target)
    rows = list(csv.DictReader(target.open()))
    assert [row["domain"] for row in rows] == ["https://missing.in"]
    assert percentages["emails"] == 50.0
    assert percentages["category"] == 0.0


def test_pipeline_run_metrics_are_persisted(tmp_path):
    store = SQLiteStore(tmp_path / "state.db")
    run_id = store.create_run("NEW", 25)
    store.finish_run(run_id, 20, 5, verification_seconds=120, total_seconds=120)
    run = store.latest_runs(1)[0]
    assert run["domains_per_minute"] == 10.0
    assert run["accepted_per_minute"] == 2.5
    assert run["verification_seconds"] == 120


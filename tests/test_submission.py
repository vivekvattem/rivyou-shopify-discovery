import csv
import json

from rivyou.submission import check_submission, render_checks


README_TOPICS = """Candidate Discovery Shopify India false-positive Deduplication Contacts Social Category Description
Logo State Manual Precision Scaling observed runtime 10x 100x more time"""


def make_project(tmp_path, row_overrides=None, json_override=None):
    (tmp_path / "data/output").mkdir(parents=True)
    (tmp_path / "README.md").write_text(README_TOPICS)
    (tmp_path / "requirements.txt").write_text("httpx\n")
    row = {
        "domain_url": "https://brand.in",
        "contacts": json.dumps({"emails": ["care@brand.in"], "phones": ["+919876543210"]}),
        "socials": json.dumps({"instagram": "https://instagram.com/brand"}),
        "category": "Fashion",
        "tagline_or_description": "Indian fashion brand.",
        "logo_url": "https://brand.in/logo.svg",
        "state": "Karnataka",
        "shopify_score": "5",
        "india_score": "7",
    }
    row.update(row_overrides or {})
    path = tmp_path / "data/output/indian_shopify_stores.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)
    payload = json_override if json_override is not None else [{"domain_url": row["domain_url"]}]
    (tmp_path / "data/output/indian_shopify_stores.json").write_text(json.dumps(payload))
    return tmp_path


def by_name(results, name):
    return next(result for result in results if result.name == name)


def test_submission_checker_can_pass_complete_fixture(tmp_path):
    results = check_submission(make_project(tmp_path), minimum_rows=1)
    assert all(result.passed for result in results)
    assert "FINAL STATUS: READY" in render_checks(results)


def test_submission_checker_fails_below_target_count(tmp_path):
    results = check_submission(make_project(tmp_path), minimum_rows=1000)
    assert not by_name(results, "CSV row count").passed
    assert "FINAL STATUS: NOT READY" in render_checks(results)


def test_submission_checker_rejects_favicon_and_weak_scores(tmp_path):
    root = make_project(tmp_path, {"logo_url": "https://brand.in/favicon.ico", "shopify_score": "1"})
    results = check_submission(root, minimum_rows=1)
    assert not by_name(results, "Logo validation").passed
    assert not by_name(results, "Verification thresholds").passed


def test_submission_checker_rejects_bad_social_and_duplicate_contacts(tmp_path):
    root = make_project(tmp_path, {
        "contacts": json.dumps({"emails": ["a@brand.in", "a@brand.in"], "phones": []}),
        "socials": json.dumps({"facebook": "https://facebook.com/sharer/sharer.php?u=x"}),
    })
    results = check_submission(root, minimum_rows=1)
    assert not by_name(results, "Deduplicated contacts").passed
    assert not by_name(results, "Social profile URLs").passed


def test_submission_checker_rejects_malformed_json_fields(tmp_path):
    results = check_submission(make_project(tmp_path, {"contacts": "not-json"}), minimum_rows=1)
    assert not by_name(results, "JSON-in-CSV fields").passed

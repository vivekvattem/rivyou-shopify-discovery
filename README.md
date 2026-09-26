# Rivyou Indian Shopify Discovery

Rivyou is an evidence-based Python pipeline for finding Indian Shopify merchants, verifying them independently, extracting assignment-ready business fields, and exporting a deduplicated dataset. Discovery only creates leads: no search query, `.in` domain, INR price, or “Powered by Shopify” footer can make a store pass by itself.

## Final result summary

These figures come from `data/state/rivyou.db`, `data/output/quality_report.json`, and the final CSV/JSON exports:

| Metric | Observed result |
|---|---:|
| Raw discovery observations across all waves | 3,034 |
| Unique candidates | 1,607 |
| Accepted candidate rows | 1,153 |
| Stored accepted result rows | 1,150 |
| Unique exported stores after final-domain deduplication | **1,143** |
| Rejected by Shopify verification | 130 |
| Rejected by India verification | 132 |
| Bounded failures | 192 |
| Remaining `NEW` / `RETRY` / `PROCESSING` | 0 / 0 / 0 |

The three-row difference between accepted candidates and stored results comes from candidate aliases converging on an existing canonical merchant result. Final submission size is always the **1,143 unique exported domains**, not the accepted-candidate count.

The production validator finds zero duplicate domains, invalid URLs, forbidden favicon logos, malformed serialized fields, duplicate contacts, social-share URLs, or rows below the unchanged verification thresholds. `python scripts/check_submission.py` is the authoritative submission-readiness gate and requires at least 1,000 unique rows.

## Pipeline overview

```text
attributable public search results / import CSVs
  -> normalize URLs and preserve provenance
  -> merge candidate domains in SQLite
  -> bounded, robots-aware crawl and homepage pre-filter
  -> independent Shopify evidence gate
  -> independent India-business evidence gate
  -> extract seven required public fields
  -> resolve redirects and deduplicate final merchant domains
  -> CSV, JSON, debug evidence, quality report, and audits
```

The queue, crawl cache, provenance, run metrics, and accepted records are persisted in SQLite, so interrupted batches can resume without clearing earlier waves.

## Candidate discovery and provenance

Candidates were collected from attributable public search results using combinations of Shopify footprints, Indian locations, and commercial categories. Examples of discovery footprints include `cdn.shopify.com`, `/cdn/shop/`, `Shopify.theme`, `shopify-section`, and “Powered by Shopify”. Locations covered India-wide searches, states, and cities such as Mumbai, Bengaluru, Delhi NCR, Chennai, Hyderabad, Pune, Ahmedabad, Kolkata, Jaipur, Kochi, Coimbatore, and Indore. Category hints included fashion, jewellery, beauty, skincare, home, furniture, food, footwear, fitness, and kids.

Every imported observation preserves:

```text
query,result_url,source,location,category_hint
```

Exact-query history and observed source/query yields were checked before expanding into new location/category combinations. The final acquisition wave contains 2,078 valid result rows in 28 files under `data/discovery/imports/final_wave/`; normalization produced 1,082 genuinely new candidates, 173 existing candidates, and 823 duplicate observations. Duplicate observations remain useful provenance but do not create duplicate candidates.

Search provenance is **not verification evidence**. Search results can contain directories, international storefronts, documentation, and stale pages. Every discovered domain still passes the same live/cached Shopify and India verification pipeline.

## Verification methodology

Both production thresholds remain **4**. They were not lowered to reach the row target.

### Shopify verification

The Shopify verifier scores independent storefront signals once per store:

- `Shopify.theme` and Shopify CDN paths: weight 3 each.
- Shopify response headers: weight 3.
- `ShopifyAnalytics` and a `myshopify.com` reference: weight 2 each.
- `shopify-section` and “Powered by Shopify”: weight 1 each.

A store must score at least 4. Consequently, “Powered by Shopify” alone cannot pass, and a search query containing a Shopify term contributes nothing to the verification score.

### India verification

The India verifier combines business-location evidence:

- Contextual Indian physical address: strongest signal, weight 4.
- GSTIN or explicit India address language: weight 3.
- `+91` merchant phone or an address-context Indian PIN: weight 2.
- Contextual state/city, India shipping, INR pricing, and `.in`: supporting signals, weight 1 each.

A store must score at least 4. A `.in` suffix or INR pricing alone is insufficient. City/state mentions from reviews, stockist lists, or generic shipping copy are not promoted to a business state without address context.

## Required field extraction

The public export contains all seven requested fields, plus the two verification scores:

| Field | Extraction approach |
|---|---|
| `domain_url` | Canonical HTTPS origin after redirects; normalized and deduplicated by registered/final merchant domain. |
| `contacts` | Emails and phones from visible text, `mailto:`, `tel:`, and JSON-LD; normalized, deduplicated, and filtered for examples/platform placeholders. |
| `socials` | Merchant profile links for Instagram, Facebook, X/Twitter, LinkedIn, and YouTube; share, intent, login, settings, platform-home, and Shopify-owned links are rejected. |
| `category` | Deterministic taxonomy using title/H1 first, then description and collection/navigation evidence; ambiguous stores become `Other`. |
| `tagline_or_description` | Meta description, OpenGraph, JSON-LD, concise hero text, then About-page text; merchant text only, capped at 500 characters. |
| `logo_url` | Organization/Brand JSON-LD, semantic header/logo imagery, then weak OpenGraph fallback; favicons, app/payment/trust icons, product/social assets, and tiny images are rejected. |
| `state` | Structured postal address or contextual address/PIN evidence, followed by conservative city/state mapping; unresolved values stay blank. |

Missing optional values are not pipeline errors when the merchant does not publish a qualifying value in the bounded static pages. The system leaves them blank rather than guessing.

## False-positive handling and judgment calls

- Discovery priority affects processing order only; it never changes a Shopify or India score.
- International stores displaying INR or shipping to India fail unless stronger Indian-business evidence exists.
- Marketplace, agency, directory, and documentation pages must pass the same storefront and business-location gates as any merchant.
- Contacts resembling examples, platform support, image filenames, or known placeholder numbers are discarded.
- Social sharing links and generic social homepages are not merchant profiles.
- A favicon is not accepted as a logo; an OpenGraph image is only a weak fallback.
- An Indian business on a `.com` domain can pass when address, GSTIN, PIN, or phone evidence is sufficient.
- A missing state, logo, contact, social profile, or description is preferable to an inferred value.

Confirmed generic fixes and their regression tests are documented in `DEVELOPMENT_NOTES.md`; merchant-specific exceptions are prohibited.

## Deduplication strategy

Candidate intake normalizes URLs and merges registered domains while retaining independent provenance rows. Distinct `*.myshopify.com` shops remain separate until redirect evidence identifies a branded destination. After crawling, the final redirected origin is preferred and accepted records are deduplicated again by canonical/registered domain, retaining the strongest verified record. This reduces 1,150 stored results to 1,143 public export rows.

## Crawling, robots.txt, and rate limiting

The crawler uses one reusable `httpx.AsyncClient`, a global concurrency semaphore, per-host locks, a configurable host delay, bounded exponential retries, `Retry-After` handling, redirect tracking, content-type checks, and a 5 MB response limit. It fetches a homepage plus at most four ranked contact/about/policy pages by default.

Network cache misses check `robots.txt` before fetching. A disallowed URL is not bypassed. Fresh cached responses may be analyzed locally without a new network or robots request because no fetch occurs. Persistent DNS, TLS, timeout, 429, 5xx, and robots outcomes are bounded by the candidate attempt budget and retained as explicit failure reasons rather than being mislabeled as verification rejects.

Final bounded failures were:

| Reason | Count |
|---|---:|
| `ROBOTS_BLOCKED` | 76 |
| `DNS_ERROR` | 63 |
| `SSL_ERROR` | 29 |
| `OTHER_TRANSIENT` | 17 |
| `TIMEOUT` | 3 |
| `HTTP_5XX` | 3 |
| `HTTP_429` | 1 |

## Final missing-field statistics

These counts come from the 1,143-row final export and `data/output/missing_fields.md`:

| Field | Missing count | Missing % |
|---|---:|---:|
| Domain URL | 0 | 0.0% |
| Any contact | 7 | 0.6% |
| Email | 41 | 3.6% |
| Phone | 71 | 6.2% |
| Socials | 215 | 18.8% |
| Category | 0 | 0.0% |
| Description | 23 | 2.0% |
| Logo | 34 | 3.0% |
| State | 110 | 9.6% |

## Audit methodology and observed results

### Automated audit

The final machine pre-review audited all 1,150 stored accepted results from the fresh policy-compliant cache. It recomputed Shopify, India, logo, state, contacts, and socials verdicts without filling manual fields.

| Check | PASS | FAIL | UNCERTAIN | MISSING |
|---|---:|---:|---:|---:|
| Shopify | 1,147 | 0 | 3 | 0 |
| India | 1,142 | 0 | 8 | 0 |
| Logo | 1,113 | 1 | 2 | 34 |
| State | 1,038 | 0 | 3 | 109 |
| Contacts | 1,140 | 0 | 10 | 0 |
| Socials | 930 | 0 | 3 | 217 |

Overall machine confidence was 1,134 HIGH, 12 MEDIUM, and 4 LOW. These are automated evidence checks, not human precision measurements.

### Manual precision and human review

The earlier clean pilot review covered all 24 accepted pilot stores and recorded reviewer-entered Shopify and India correctness of 24/24, logo 23/23 rated, state 22/22 rated, and contacts 23/23 rated. Missing/unrated values were excluded rather than treated as successes. This small early cohort is reported only as a pilot result.

The final reviewed worksheet contains 25 deliberately targeted edge cases: all 4 LOW, all 12 MEDIUM, and 9 HIGH records selected for low scores, missing fields, unusual contacts/socials, and control coverage. Its reviewer-entered worksheet results were Shopify 19/25 (76%), India 18/25 (72%), logo 20/25 (80%), state 14/25 (56%), and contacts 20/25 (80%). Because the sample intentionally oversampled uncertain and problematic records, these figures **must not be interpreted as random dataset-wide precision**. No precision figure is fabricated for unreviewed rows.

Relevant artifacts:

- `data/audits/auto_audit_20260926T163940Z.csv`
- `data/audits/auto_audit_20260926T082022Z_reviewed.csv`
- `data/audits/targeted_accepted_audit_20260926T174909Z_reviewed.csv`

## Installation and setup

Python 3.11 or newer is required.

```bash
git clone <repository-url>
cd rivyou-shopify-discovery
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Runtime configuration is environment-driven. The defaults include Shopify and India thresholds of 4, concurrency 10, request timeout 15 seconds, five pages per store, a one-second per-host delay, three HTTP attempts, three candidate attempts, and a 24-hour cache TTL. For real use, replace the example user-agent contact with a monitored address.

## Exact run commands

Ingest provenance-bearing import files without resetting history:

```bash
python scripts/discover_candidates.py \
  --source directory \
  --directory data/discovery/imports/final_wave
```

Process bounded stages and retries:

```bash
python scripts/run_batch.py --status NEW --limit 100 --concurrency 10 --wave final-wave-stage-1
python scripts/run_batch.py --status NEW --limit 250 --concurrency 10 --wave final-wave-stage-2
python scripts/run_batch.py --status NEW --limit 250 --concurrency 10 --wave final-wave-stage-3
python scripts/run_batch.py --status NEW --limit 1000 --concurrency 10 --wave final-wave-stage-4
python scripts/run_batch.py --status RETRY --limit 2000 --concurrency 10 --wave final-wave-retry-1
python scripts/run_batch.py --status RETRY --limit 2000 --concurrency 10 --wave final-wave-retry-2
```

Regenerate final artifacts and reporting:

```bash
python scripts/export_results.py --database data/state/rivyou.db --output data/output
python scripts/diagnose_missing_fields.py \
  --output data/audits/missing_fields.csv \
  --markdown-output data/output/missing_fields.md
python scripts/report_stats.py --json-output data/output/quality_report.json
```

Run the final automated and targeted audits:

```bash
python scripts/run_auto_audit.py --concurrency 10 --store-timeout 60 --cache-only
python scripts/create_targeted_audit.py \
  data/audits/auto_audit_20260926T163940Z.csv \
  --target 25 --review-all-limit 30 --output data/audits
python scripts/evaluate_audit.py \
  data/audits/targeted_accepted_audit_20260926T174909Z_reviewed.csv
```

Validate the submission:

```bash
python scripts/validate_output.py
python scripts/check_submission.py
pytest -q
```

## Output locations

| Artifact | Path |
|---|---|
| Required CSV | `data/output/indian_shopify_stores.csv` |
| Required JSON | `data/output/indian_shopify_stores.json` |
| Internal evidence/debug export | `data/output/store_debug.json` |
| Quality and yield report | `data/output/quality_report.json` |
| Missing-field table | `data/output/missing_fields.md` |
| Missing-row detail | `data/audits/missing_fields.csv` |
| Final automated audit | `data/audits/auto_audit_20260926T163940Z.csv` |
| Final targeted reviewed worksheet | `data/audits/targeted_accepted_audit_20260926T174909Z_reviewed.csv` |

CSV `contacts` and `socials` are serialized JSON objects; the JSON export preserves native arrays and dictionaries. Debug evidence is intentionally separate from the seven public assignment fields.

## Runtime and worklog

The final acquisition/processing wave recorded **1,898.62 seconds (31 minutes 38.62 seconds)** of measured discovery and batch runtime. Individual UTC run timestamps, throughput, score averages, and stage counters are stored in `pipeline_runs` and surfaced in the quality report. Automated audit wall time is not recorded as a pipeline-run metric and is therefore not estimated here.

`WORKLOG.md` is the source for time spent. Human development, discovery/collection, and manual-review durations remain blank until supplied by the people who performed them; the README does not invent those hours.

## Known limitations

- Public search coverage is incomplete and ranking-dependent; this is a verified dataset, not an exhaustive census of Indian Shopify stores.
- Static HTML can miss JavaScript-rendered contacts, social profiles, descriptions, or logos.
- Rule-based category assignment is imperfect for multi-category merchants.
- State extraction is conservative and can remain blank despite adequate country-level India evidence.
- Logo checks use markup semantics and dimensions, not full visual brand recognition.
- Websites change after collection; cached evidence is a time-bounded observation.
- Robots blocks and persistent network/TLS failures remain failures rather than being bypassed.
- The targeted 25-row human review is intentionally biased toward edge cases and cannot estimate dataset-wide precision.

With more time, the highest-value improvements would be a randomly sampled final human audit, richer structured-address and PIN-prefix resolution, incremental automated-audit output, stronger contact-ownership checks, and visual logo comparison for ambiguous assets.

## Scaling beyond this submission

### At 10x scale

The SQLite queue and bounded async crawler remain workable, but crawl-cache size, robots traffic, retry scheduling, query/source monitoring, audit CPU time, and manual-review throughput become operational bottlenecks. The next steps would be scheduled partitions, incremental audit output, cache pruning, per-source dashboards, and a labeled random audit alongside targeted review.

### At 100x scale

SQLite write contention, single-process parsing, storage growth, search acquisition throughput, third-party rate limits, DNS/TLS noise, and human audit cost become architectural constraints. A production design would use a distributed queue, separate fetch/parse workers, object storage for evidence, a relational analytics store, per-host distributed rate limiting, observability, and statistically designed audit sampling. JavaScript rendering should remain a selective fallback for a measured cohort rather than a default crawl mode.

## Explicit assumptions and judgment calls

- The accepted unit is a merchant storefront represented by its canonical final registered domain; aliases do not count twice.
- Current page evidence is treated as observational, not permanent truth.
- A strong phone or physical-address signal can establish Indian business presence for a `.com` store.
- India shipping and INR are supporting evidence only, because international merchants can expose both.
- Missing optional fields are valid output when no qualifying merchant-published value appears in the bounded pages.
- Conservative blanks are preferred over inferred states, logos, contacts, or socials.
- Automated confidence prioritizes review; it is not a substitute for human correctness labels.
- The submission-ready claim depends on the production checker passing with at least 1,000 unique export rows.

## Testing

Tests use static HTML and mocked HTTP responses rather than live merchant availability. Coverage includes URL normalization, redirect/domain deduplication, strong and weak Shopify/India signals, address/PIN/GSTIN/phone handling, cache and robots behavior, contact/social filtering, category weighting, logo rejection, state mapping, audits, reporting, exports, and submission checks.

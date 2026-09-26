# Rivyou Indian Shopify Discovery

An evidence-based, resumable Python system that discovers candidate domains, verifies Shopify and Indian-business signals, and extracts structured merchant records. It includes provenance-aware bulk intake, SQLite state, homepage pre-filtering, persistent HTTP caching, controlled wave processing, manual auditing, source/query yield reporting, and reproducible export. It does **not** claim to have discovered 1,000 stores.

## Problem statement

Common shortcuts produce false positives: a `.in` domain does not prove that a business is Indian, INR can be shown by international stores, “Powered by Shopify” is a weak platform signal, and a favicon is not a brand logo. This project gathers multiple independent signals, assigns explicit weights, and accepts a store only after both Shopify and India thresholds are met.

## Architecture

```text
discovery providers / seed CSV
  -> normalization, provenance merge, and registered-domain deduplication
  -> SQLite candidate queue ordered by discovery priority
  -> cached homepage Shopify pre-filter
  -> async homepage fetch (robots.txt, retries, redirect handling, size/type guards)
  -> Shopify evidence gate
  -> ranked important-page fetch (bounded to five pages by default)
  -> India evidence gate
  -> independent field extractors
  -> final-domain deduplication
  -> SQLite result persistence
  -> audited CSV + JSON export and separate debug evidence
```

The package is split by responsibility:

- `crawler.py`: reusable `httpx.AsyncClient`, concurrency control, robots policy, bounded HTML fetching, and important-link ranking.
- `verify/`: weighted Shopify and India decisions.
- `extract/`: contacts, socials, description, logo, state/location, and category logic.
- `utils/`: URL normalization, text helpers, and deduplication.
- `pipeline.py`: fault-isolated orchestration and output serialization.
- `discover/`: Phase 1 seeds plus generic/search/Common Crawl providers, query generation, fingerprints, provenance, and orchestration.
- `storage/`: SQLite candidate state and compressed HTTP cache.
- `batch.py`: recoverable priority-batch execution using the existing verifier/extractors.
- `audit/`: stratified manual-review samples and funnel/quality reporting.

The crawler returns a small `CrawledPage` abstraction. A future Playwright renderer can implement the same boundary for JavaScript-heavy pages without changing verification or extraction logic.

## Verification methodology

### Shopify

Signals are counted once per store and weighted by specificity. Strong evidence includes `Shopify.theme` and Shopify CDN paths (+3); supporting evidence includes `ShopifyAnalytics` and `myshopify.com` references (+2), `shopify-section`, and “Powered by Shopify” (+1). The default threshold is 4, so the weak footer text alone cannot pass. An optional product-JSON evidence helper exists for a later selective active check; the pipeline does not request `/products.json` indiscriminately.

### India

The verifier looks for GSTIN, explicit Indian business/contact address language, address-context PIN codes, `+91` numbers, known cities/states, India-specific shipping language, INR pricing, and `.in`. Strong address evidence carries more weight. The default threshold is 4; `.in` or INR alone scores only 1 and is rejected. Extracted state and city are retained with detected PIN codes in the debug JSON.

Thresholds and network limits are configurable through environment variables documented in `.env.example`.

## Why discovery is not verification

Discovery produces leads, not truth. A search result for `"cdn.shopify.com" "Mumbai"`, a `.in` hostname, a `myshopify.com` URL from Common Crawl, or even a homepage fingerprint can increase processing priority but cannot make a record accepted. Every candidate still passes the unchanged Shopify threshold, India threshold, and extraction pipeline. Discovery priority is stored separately from verification scores and is never added to either score.

## Candidate discovery

All providers implement the same asynchronous interface and return normalized `CandidateRecord` values with provenance. Duplicate domains are merged rather than copied, while independent source/query/signal observations remain in `candidate_provenance`.

- **Manual search/API exports:** `query,result_url` CSV ingestion is first-class. This is the recommended search workflow because it avoids scraping search engines or depending on a paid API.
- **Master CSV imports:** `data/discovery/candidates_master.csv` accepts `url`, `domain`, `website`, or `domain_url`; only one URL/domain value is required per row. Optional `source`, `query`, and `location` values are retained as provenance.
- **Bulk directory imports:** every CSV in `data/discovery/imports/` is ingested in filename order, with its filename retained in `source_url`. Domains are deduplicated globally while independent file observations remain attached as provenance.
- **Search query generator:** creates fewer than 500 ranked combinations of five Shopify footprints with all Indian states/UTs and major commercial cities. High-yield signal/location combinations rank first; a bounded set adds commercial category hints. Output columns are `query`, `priority`, `shopify_signal`, `location`, and `category_hint`.
- **Common Crawl import:** consumes externally produced Common Crawl domain CSVs using the generic normalization path.
- **Common Crawl URL index:** optional live mode queries indexed `*.myshopify.com` URLs. It is not run by default.
- **Sitemap sampling:** optionally samples a few internal product, collection, or page URLs for an already-known candidate. It never uses a sitemap to discover unrelated domains.

### Common Crawl limitations

Common Crawl's CDX index searches captured URLs and metadata; it is not a global full-text search engine for page bodies. It cannot directly answer “find every page containing `Shopify.theme`” without downstream WARC processing or an external derived index. The built-in provider therefore queries honest URL patterns such as `*.myshopify.com`, supports imported derived lists, and does not pretend that body-fingerprint search exists. Large-scale WARC processing is left as an optional future provider.

## Persistent architecture and resumability

`data/state/rivyou.db` is initialized automatically with five tables:

| Table | Purpose |
|---|---|
| `candidates` | One normalized domain, status, priority, attempts, errors, scores, and serialized evidence |
| `candidate_provenance` | Unique source/query/source-URL/signal observations per candidate |
| `crawl_cache` | Compressed response body, status, content type, timestamps, ETag, and Last-Modified |
| `pipeline_runs` | Run ID, UTC timestamps, optional wave, complete funnel counters, score averages, and measured runtime |
| `store_results` | One upserted full `StoreRecord` per final domain |

Candidate states are `NEW`, `QUEUED`, `PROCESSING`, `REJECTED_SHOPIFY`, `REJECTED_INDIA`, `ACCEPTED`, `FAILED`, and `RETRY`. Updates use unique constraints and transactions. `run_batch.py --recover-stale 30` moves candidates left in `PROCESSING` for more than 30 minutes to `RETRY`, allowing an interrupted run to resume safely. Retry reasons are normalized (`TIMEOUT`, `HTTP_429`, `HTTP_5XX`, `DNS_ERROR`, `SSL_ERROR`, `CONNECTION_ERROR`, `ROBOTS_BLOCKED`, or `OTHER_TRANSIENT`). HTTP requests have bounded internal retries, and candidates move to `FAILED` after `MAX_CANDIDATE_ATTEMPTS` rather than looping forever; they are not misclassified as Shopify/India rejections.

Priority favors strong discovery fingerprints, independent sources, Indian location terms in provenance, `.in`, and repeat discovery. It controls ordering only.

## Field extraction and false-positive controls

- Contacts combine `mailto:`/`tel:`, visible text, and JSON-LD. Emails are normalized and obvious examples/image false positives are rejected. Phone numbers are validated and formatted with `phonenumbers`.
- Social URLs support Instagram, Facebook, X/Twitter, LinkedIn, and YouTube. Share/intent URLs, generic pages, and Shopify-owned profiles are rejected; query tracking is removed.
- Description priority is meta description, OpenGraph description, JSON-LD, short homepage hero text, then About content. Text is never invented and is capped at 500 characters.
- Logo priority is Organization/Brand JSON-LD, semantic header imagery, other logo-marked images, then OpenGraph as a weak fallback. Favicons, app icons, payment/provider marks, and known tiny images are rejected.
- Location uses the complete Indian state/union-territory list, conservative abbreviations, and an explicit major-city mapping. Unknown stays null.
- Category is a deterministic, extensible keyword classifier; uncertain stores become `Other`.

## Deduplication and redirects

Seeds are deduplicated by normalized registered domain. Distinct `*.myshopify.com` shops remain distinct until redirects identify their branded destinations. After crawling, the final redirected origin is preferred and records are deduplicated again, retaining the record with the strongest combined verification score. Redirect history remains in JSON/debug output.

## Responsible crawling and caching

The crawler uses connection reuse, a global semaphore, per-host locks, a configurable minimum delay between requests to the same hostname, exponential retry for transport failures/429/5xx, numeric `Retry-After`, response-size protection, HTML-only processing, and a transparent user agent. It checks `robots.txt`, follows redirects, and fetches no more than approximately five ranked pages per store. Unrelated hosts can proceed concurrently.

Successful bounded HTML responses are compressed in SQLite and reused for `CACHE_TTL_HOURS` (24 by default). Use `--no-cache` when a genuinely fresh batch is needed. The cache does not bypass robots evaluation and does not store oversized responses.

## Installation

Python 3.11 or newer is required.

```bash
cd rivyou-shopify-discovery
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

For a real deployment, change the contact address in `USER_AGENT` to an actively monitored address.

## Phase 1 file-based usage

Place candidate URLs in `data/seeds.csv`:

```csv
domain_url
https://candidate.example
another-candidate.in
```

Run enrichment:

```bash
python scripts/run_pipeline.py --input data/seeds.csv --output data/output --limit 20
```

Optional flags are `--concurrency`, `--limit`, and `--verbose`. Environment values include `REQUEST_TIMEOUT`, `MAX_CONCURRENCY`, `MAX_PAGES_PER_SITE`, `USER_AGENT`, `SHOPIFY_SCORE_THRESHOLD`, `INDIA_SCORE_THRESHOLD`, `RETRY_COUNT`, `MAX_RESPONSE_BYTES`, `PER_HOST_DELAY_SECONDS`, `CACHE_TTL_HOURS`, `PREFILTER_SCORE_THRESHOLD`, and `DATABASE_PATH`.

Validate generated output:

```bash
python scripts/validate_output.py data/output/indian_shopify_stores.csv
```

## Candidate intake and controlled runs

Initialize the database and ingest a generic domain list:

```bash
python scripts/discover_candidates.py \
  --source csv \
  --file data/discovery/candidates_master.csv
```

The command prints rows read, valid domains, new domains, already-existing domains, invalid rows, and within-run duplicates. It never resets an existing candidate status.

To ingest every CSV dropped into the import directory:

```bash
python scripts/discover_candidates.py \
  --source directory \
  --directory data/discovery/imports
```

Generate the reusable manual-search worksheet:

```bash
python scripts/discover_candidates.py \
  --source search \
  --generate-queries \
  --output data/discovery/generated_queries.csv
```

Paste collected results into `data/discovery/search_results.csv` using `query,result_url`, then ingest them:

```bash
python scripts/discover_candidates.py \
  --source search-csv \
  --file data/discovery/search_results.csv
```

Import an externally generated Common Crawl list, or explicitly query the public URL index:

```bash
python scripts/discover_candidates.py --source commoncrawl --file commoncrawl_domains.csv
python scripts/discover_candidates.py --source commoncrawl --limit 1000
```

Finish the current queue without resetting accepted or rejected records. Retry the current retry set first, then process only remaining new candidates:

```bash
python scripts/run_batch.py --status RETRY --limit 100 --wave wave-1 --recover-stale 30
python scripts/run_batch.py --status NEW --limit 100 --wave wave-1
```

For later waves, ingest only newly collected inputs, label the run, and keep batches bounded:

```bash
python scripts/run_batch.py --status NEW --limit 100 --concurrency 15 --wave wave-2
```

Regenerate every derived artifact after a batch:

```bash
python scripts/export_results.py --database data/state/rivyou.db --output data/output

python scripts/diagnose_missing_fields.py \
  --output data/audits/missing_fields.csv \
  --markdown-output data/output/missing_fields.md

python scripts/report_stats.py --json-output data/audits/latest_report.json

python scripts/audit_results.py \
  --accepted 30 \
  --rejected-shopify 10 \
  --rejected-india 10

# After manually filling the audit columns:
python scripts/evaluate_audit.py data/audits/audit_<timestamp>.csv

```

The audit worksheet's manual columns remain blank until a human reviews them. `evaluate_audit.py` continues to print `N/A` for every metric with no completed rating. The export command creates public assignment CSV/JSON files, `missing_fields.md`, and a separate `store_debug.json` containing scores, confidence, evidence, crawl history, and extraction errors.

### Automated pre-review

Run a machine pre-review of every currently accepted store:

```bash
python scripts/run_auto_audit.py \
  --database data/state/rivyou.db \
  --output data/audits
```

The command safely revisits the homepage and bounded important pages through the existing crawler/cache, compares current evidence with stored acceptance evidence, and writes `auto_audit_<timestamp>.csv`. It reports `PASS`, `FAIL`, `UNCERTAIN`, or `MISSING` separately for Shopify, India, logo, state, contacts, and socials, plus an overall `HIGH`, `MEDIUM`, or `LOW` machine confidence. Inaccessible sites are uncertain rather than false failures. INR, `.in`, or India-shipping language alone cannot produce an automated India pass.

Create a fresh risk-targeted accepted-store worksheet from that output:

```bash
python scripts/create_targeted_audit.py \
  data/audits/auto_audit_<timestamp>.csv \
  --target 15 \
  --output data/audits
```

This deterministic sample prioritizes MEDIUM/LOW machine confidence, the lowest
accepted Shopify and India scores, missing state/description/logo cases, and
unusual contact/social results, then fills the target with seeded random HIGH
rows. It labels each selection reason and keeps every `manual_*` field blank.

This is a prioritization layer, not human verification. Every `manual_*` field in its output is deliberately blank. `HIGH` must never be converted automatically into a manual “yes”; human sampling is still required to measure precision.

The Wave 1 human review covered all 24 accepted stores. Shopify and India correctness were each 24/24 (100%). Logo correctness was 23/23 among records with a logo, with one missing logo. State correctness was 22/22 among records with a state, with two missing states in the reviewed worksheet. Contact correctness was 23/23 among records with contacts, with one missing-contact row. These are reviewer-entered results from `data/audits/auto_audit_20260926T082022Z_reviewed.csv`, not machine-inferred ratings.

After Wave 2, the 2026-09-26 automated pre-review audited all 126 accepted stores: 125 were `HIGH`, one was `MEDIUM`, and none were `LOW`. Shopify re-passed for 126/126; India passed for 125 with one uncertain live recheck; contacts passed for 126/126; 125 logos passed with one missing; 119 states passed with seven missing; and 100 stores had qualifying social profiles while 26 remained missing. This automated audit is only a prioritization layer. Its manual fields remain blank, as do the fields in the fresh 10-row stratified manual worksheet.

Wave 3 expanded the live database to 525 candidates. Its full automated audit
covered all 381 accepted result rows: 375 were `HIGH`, five `MEDIUM`, and one
`LOW`; Shopify re-passed for 381/381 and India passed for 380 with one
uncertain live recheck. The fresh targeted 15-row worksheet contains all six
non-HIGH rows plus low-score, missing-field, unusual contact/social, and seeded
random HIGH cases. The detailed check counts are in
`data/audits/wave3_summary.md`; manual fields remain blank, so no Wave 3 human
precision claim is made.

Run the final artifact gate with the assignment target, or a smaller pilot target while iterating:

```bash
python scripts/check_submission.py
python scripts/check_submission.py --minimum-rows 1
```

## Scaling strategy

A representative target funnel is:

```text
10,000 provenance-backed candidates
  -> cheap cached homepage pre-filter
  -> roughly 3,000 plausible Shopify sites
  -> full Shopify verification
  -> full India verification
  -> extraction and final-domain deduplication
  -> manual precision samples by outcome stratum
  -> 1,000+ usable records only if evidence supports them
```

The exact conversion rates must come from real runs, not assumed figures. Persistent cache/state makes it safe to gather candidates incrementally and inspect rejection bands without lowering thresholds.

Use these checkpoints:

| Wave | Candidate target | Required decision checkpoint |
|---|---:|---|
| 1 | Current ~33 | Finish RETRY/NEW and complete the initial manual audit. |
| 2 | 100 total | Audit at least 20 accepted, 5 Shopify rejections, and 5 India rejections. |
| 3 | 500 total | Audit a random accepted sample and compare observed source/query yield. |
| 4 | 2,000 total | Re-check field completeness and human-rated precision before continuing. |
| 5 | As needed | Continue acquisition until about 1,000 clean accepted stores, without lowering thresholds. |

Each `run_batch.py --wave ...` invocation persists the input count, prefilter passes, Shopify/India verified counts, all terminal/retry outcomes, acceptance percentage derivable from the counters, average scores, runtime, and domains/minute. `report_stats.py` reports observed acceptance and rejection rates by source, query family, and exact query. Low-yield sources are not deleted retroactively; the evidence only guides later acquisition.

## Manual precision auditing

`audit_results.py` independently samples accepted, Shopify-rejected, and India-rejected candidates. Its CSV includes stored scores/evidence and intentionally blank `manual_shopify_correct`, `manual_india_correct`, and `manual_notes` columns. Review results should guide signal improvements and identify false-positive/false-negative patterns; they should not be filled automatically by the pipeline.

The Phase 3 worksheet also includes category, state, logo URL, emails, phones, socials, plus blank logo/state/contact correctness fields. `evaluate_audit.py` calculates precision only for cells explicitly marked yes/no (also accepting `correct`/`incorrect`, `pass`/`fail`, and boolean-like forms). Blank cells produce `N/A`, never an invented zero or success rate.

## Observed final results

The first three waves produced 525 unique candidates and 380 deduplicated accepted records. The final acquisition wave then collected 2,078 attributable public-search result rows across 28 CSV files in `data/discovery/imports/final_wave/`. All 2,078 rows were structurally valid; ingestion normalized them to 1,082 genuinely new candidates, 173 existing candidates, and 823 within-import duplicate observations. The raw total exceeded the planned 1,200–1,400 range because acquisition continued until the hard requirement of at least 1,000 new normalized domains was measured. Every row retains its exact query, result URL, source, location, and category hint.

Final-wave processing used the unchanged Shopify and India score thresholds of 4. The required NEW stages and cumulative deduplicated export counts were:

| Stage | Selected | Accepted | Shopify rejects | India rejects | Retry | Runtime | Cumulative unique export |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 100 | 82 | 5 | 3 | 10 | 229.45 s | 462 |
| 2 | 250 | 191 | 28 | 4 | 27 | 430.59 s | 651 |
| 3 | 250 | 191 | 20 | 21 | 18 | 406.17 s | 841 |
| 4 remainder | 482 | 0 | 0 | 0 | 482 | 6.33 s | 841 |

Stage 4 encountered an environment-wide DNS denial, so all 482 candidates were safely moved to `RETRY` rather than misclassified. The first bounded retry processed those candidates plus 55 earlier transient cases: 308 were accepted, 40 failed Shopify verification, 69 failed India verification, and 120 remained transient. The final bounded retry converted 119 repeated transport failures to `FAILED` and one candidate to `REJECTED_SHOPIFY`; it accepted no additional stores. Across final discovery and processing, measured pipeline runtime was 1,898.62 seconds (31 minutes 38.62 seconds). Human development, collection, and review time remains intentionally blank in `WORKLOG.md` until supplied by the person performing those activities.

The final database has 1,607 candidates: 1,153 `ACCEPTED`, 130 `REJECTED_SHOPIFY`, 132 `REJECTED_INDIA`, and 192 `FAILED`. There are no `NEW`, `RETRY`, `QUEUED`, or `PROCESSING` candidates. Canonical registered-domain deduplication reduces the accepted rows to **1,143 unique public records**, exceeding the required 1,000 with a 143-record buffer.

Current final-export completeness is:

| Field | Missing |
|---|---:|
| Email | 3.6% |
| Phone | 6.2% |
| Any contact | 0.6% |
| Social profile | 18.8% |
| Category | 0.0% |
| Description | 2.0% |
| Logo | 3.0% |
| State | 9.6% |

Missing values are left blank rather than inferred. The reproducible lists are in `data/audits/missing_fields.csv` and `data/output/missing_fields.md`. The final failure reasons are retained explicitly: 76 `ROBOTS_BLOCKED`, 63 `DNS_ERROR`, 29 `SSL_ERROR`, 17 `OTHER_TRANSIENT`, three `TIMEOUT`, three `HTTP_5XX`, and one `HTTP_429`. The crawler did not bypass robots directives, disable TLS verification, or exceed the configured candidate attempt budget.

The automated audit covers all 1,150 accepted result records (three accepted candidate aliases have no separate result row) and records Shopify, India, logo, state, contacts, and socials verdicts without filling any manual field. It produced 1,134 HIGH, 12 MEDIUM, and four LOW rows. Shopify recheck results were 1,147 PASS and three UNCERTAIN; India results were 1,142 PASS and eight UNCERTAIN, with no FAIL verdicts in either verification dimension. The final run used the fresh policy-compliant crawl cache; cache misses were recorded as unavailable rather than fetched or treated as passes.

The 25-row targeted worksheet contains all four LOW and all 12 MEDIUM rows, plus lowest-score, missing-field, unusual-contact/social, and random HIGH-confidence cases. Its manual correctness cells remain blank, so `evaluate_audit.py` reports `N/A` until a human reviewer supplies ratings; no manual precision percentage is claimed.

The observed failure patterns, generic fixes, and anonymized/static regression coverage are recorded in `DEVELOPMENT_NOTES.md`. Verification thresholds were not lowered during scale-up.

## Extraction methodology and taxonomy

- Contacts come from visible text, `mailto:`/`tel:`, and JSON-LD. They are normalized and deduplicated; example/test/noreply platform addresses and known placeholder phone sequences are removed.
- Socials come from merchant anchors for Instagram, Facebook, X, LinkedIn, and YouTube. Share, intent, settings, login, platform-home, and Shopify-owned URLs are rejected.
- Category uses a deterministic taxonomy: Women's Apparel, Men's Apparel, Fashion, Jewellery, Beauty & Skincare, Home Decor, Furniture, Food & Beverage, Footwear, Accessories, Electronics, Health & Wellness, Sports & Fitness, Kids & Baby, Pet Supplies, Stationery, and Other. Title/H1 evidence outweighs incidental navigation, followed by description and collection/navigation terms.
- Description priority is meta description, OpenGraph, JSON-LD, homepage hero copy, then bounded About-page text. Nothing is generated.
- Logo priority is Organization/Brand JSON-LD, semantic header/logo images, then OpenGraph only as a weak fallback. Favicons, app/payment/trust icons, and tiny assets are prohibited.
- State prefers structured postal address or address/PIN context, then conservative city/state mapping. A city in customer reviews, stockist lists, or shipping copy is not promoted to the output state without business-address context.

## Real edge cases and decisions

- Indian brands on `.com` are accepted when address, PIN, GSTIN, or phone evidence passes; the pilot includes several.
- A foreign brand merely selling or shipping to India is not accepted from INR or India-shipping language alone.
- An Indian address on an international storefront is valid business evidence; international shipping does not negate it.
- Custom Shopify domains are verified through theme/CDN/global signals, not their suffix.
- `myshopify.com` candidates that redirect use the final branded domain. Multiple inputs converging on one registered final domain are deduplicated.
- Marketplace, agency, or directory pages are not treated as merchant storefronts merely because they discuss Shopify; they must pass the same platform/store and Indian-business evidence path.
- Stockist lists caused an early state ambiguity in the pilot. State output now prefers structured or address-context evidence rather than the first state name on a page.

## What changes at larger scale

At **10x** the pilot size, the current SQLite queue, cache, concurrency control, and batch recovery remain appropriate. Operational work shifts to expanding source diversity, reviewing rejection strata, retrying transient failures, and completing audits at each 100/500-candidate checkpoint.

At **100x** the pilot size, search-result acquisition throughput, network bandwidth, third-party rate limits, Common Crawl coverage lag, SQLite write contention, cache size, robots traffic, and manual audit cost become material. The next engineering steps would be partitioned discovery inputs, scheduled batches, cache pruning, per-source precision monitoring, and selective JavaScript rendering only for a measured failure cohort—not a wholesale Playwright crawl. This repository is an assignment-scale pipeline, not a claim of production-scale infrastructure.

With more time, the highest-value improvements would be PIN-prefix state resolution, richer structured-address parsing, image-dimension/content checks for ambiguous logos, better detection of script-rendered social profiles, and a manually labeled regression corpus from the audit sheets.

## Output schema

`data/output/indian_shopify_stores.csv` contains:

| Column | Meaning |
|---|---|
| `domain_url` | Canonical HTTPS origin after redirects |
| `contacts` | JSON string with `emails` and `phones` arrays |
| `socials` | JSON string keyed by supported platform |
| `category` | Rule-based assignment category |
| `tagline_or_description` | Merchant-authored description, up to 500 characters |
| `logo_url` | Best non-favicon brand-logo URL |
| `state` | Normalized Indian state/union territory or empty |
| `shopify_score`, `india_score` | Verification scores |
| `shopify_confidence`, `india_confidence` | `LOW`, `MEDIUM`, or `HIGH` |

`indian_shopify_stores.json` contains the same public fields while preserving contacts and socials as native arrays/dictionaries. `store_debug.json` contains verification evidence, confidence, crawled pages, redirects, and extraction errors. `missing_fields.md` is generated from the same final records and provides the README-ready missing-count table without guessing why optional values are absent.

## Time tracking

`WORKLOG.md` provides blank entries for actual approximate development, discovery/collection, and manual-audit time. Those human durations must be entered by the person who did the work. Only pipeline execution time is measured automatically in `pipeline_runs`; no historical hours are fabricated.

## Testing

Tests use static HTML and mocked HTTP responses rather than live merchants:

```bash
pytest -q
```

They cover URL normalization, deduplication, strong and weak verification signals, address/GSTIN/phone extraction, social share-link rejection, logo priority/favicon rejection, and city-to-state mapping.

## Current limitations

- Search result acquisition remains manual or API/export driven; the project does not scrape Google.
- Common Crawl's public URL index cannot search arbitrary response-body fingerprints. WARC-derived lists must be imported.
- Pure client-side sites may expose too little HTML. The abstraction allows a later Playwright fallback, but Playwright is not included now.
- Some merchants block research crawlers or disallow pages through robots.txt; those candidates are rejected rather than bypassed.
- State resolution is text/city based. PIN-prefix resolution and deeper address disambiguation are future improvements.
- Rule-based category classification can be ambiguous for multi-category stores.
- OpenGraph images are only a weak logo fallback and can occasionally be a campaign image; provenance is retained for future scoring improvements.

## Recommended first real collection

Generate the search queries, execute the highest-priority Mumbai/Delhi/Bengaluru/Chennai/Hyderabad combinations through manual search or a policy-compliant free search interface, paste the first 100 result URLs with their exact query into `search_results.csv`, ingest them, then run a 25-candidate batch. Audit all acceptances plus a sample of both rejection groups before processing the remaining 75. This establishes real precision and failure rates before scaling discovery breadth.

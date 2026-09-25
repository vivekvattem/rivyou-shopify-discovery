# Rivyou Indian Shopify Discovery — Phase 1

An evidence-based Python pipeline that verifies and enriches supplied candidate domains into structured records for Indian Shopify merchants. Phase 1 deliberately optimizes correctness and auditability over volume; it does **not** claim to have discovered 1,000 stores.

## Problem statement

Common shortcuts produce false positives: a `.in` domain does not prove that a business is Indian, INR can be shown by international stores, “Powered by Shopify” is a weak platform signal, and a favicon is not a brand logo. This project gathers multiple independent signals, assigns explicit weights, and accepts a store only after both Shopify and India thresholds are met.

## Architecture

```text
seed CSV
  -> normalization and registered-domain deduplication
  -> async homepage fetch (robots.txt, retries, redirect handling, size/type guards)
  -> Shopify evidence gate
  -> ranked important-page fetch (bounded to five pages by default)
  -> India evidence gate
  -> independent field extractors
  -> final-domain deduplication
  -> CSV + JSON + debug evidence JSON
```

The package is split by responsibility:

- `crawler.py`: reusable `httpx.AsyncClient`, concurrency control, robots policy, bounded HTML fetching, and important-link ranking.
- `verify/`: weighted Shopify and India decisions.
- `extract/`: contacts, socials, description, logo, state/location, and category logic.
- `utils/`: URL normalization, text helpers, and deduplication.
- `pipeline.py`: fault-isolated orchestration and output serialization.
- `discover/seeds.py`: Phase 1 seed ingestion. Broad discovery belongs to Phase 2.

The crawler returns a small `CrawledPage` abstraction. A future Playwright renderer can implement the same boundary for JavaScript-heavy pages without changing verification or extraction logic.

## Verification methodology

### Shopify

Signals are counted once per store and weighted by specificity. Strong evidence includes `Shopify.theme` and Shopify CDN paths (+3); supporting evidence includes `ShopifyAnalytics` and `myshopify.com` references (+2), `shopify-section`, and “Powered by Shopify” (+1). The default threshold is 4, so the weak footer text alone cannot pass. An optional product-JSON evidence helper exists for a later selective active check; the pipeline does not request `/products.json` indiscriminately.

### India

The verifier looks for GSTIN, explicit Indian business/contact address language, address-context PIN codes, `+91` numbers, known cities/states, India-specific shipping language, INR pricing, and `.in`. Strong address evidence carries more weight. The default threshold is 4; `.in` or INR alone scores only 1 and is rejected. Extracted state and city are retained with detected PIN codes in the debug JSON.

Thresholds and network limits are configurable through environment variables documented in `.env.example`.

## Field extraction and false-positive controls

- Contacts combine `mailto:`/`tel:`, visible text, and JSON-LD. Emails are normalized and obvious examples/image false positives are rejected. Phone numbers are validated and formatted with `phonenumbers`.
- Social URLs support Instagram, Facebook, X/Twitter, LinkedIn, and YouTube. Share/intent URLs, generic pages, and Shopify-owned profiles are rejected; query tracking is removed.
- Description priority is meta description, OpenGraph description, JSON-LD, short homepage hero text, then About content. Text is never invented and is capped at 500 characters.
- Logo priority is Organization/Brand JSON-LD, semantic header imagery, other logo-marked images, then OpenGraph as a weak fallback. Favicons, app icons, payment/provider marks, and known tiny images are rejected.
- Location uses the complete Indian state/union-territory list, conservative abbreviations, and an explicit major-city mapping. Unknown stays null.
- Category is a deterministic, extensible keyword classifier; uncertain stores become `Other`.

## Deduplication and redirects

Seeds are deduplicated by normalized registered domain. Distinct `*.myshopify.com` shops remain distinct until redirects identify their branded destinations. After crawling, the final redirected origin is preferred and records are deduplicated again, retaining the record with the strongest combined verification score. Redirect history remains in JSON/debug output.

## Politeness and safety

The crawler uses connection reuse, a global semaphore (10 by default), exponential retry only for transport failures/429/5xx, response-size protection, HTML-only processing, and a transparent user agent. It checks `robots.txt`, follows redirects, and fetches no more than approximately five ranked pages per store. It never recursively spiders a site.

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

## Usage

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

Optional flags are `--concurrency`, `--limit`, and `--verbose`. Environment values include `REQUEST_TIMEOUT`, `MAX_CONCURRENCY`, `MAX_PAGES_PER_SITE`, `USER_AGENT`, `SHOPIFY_SCORE_THRESHOLD`, `INDIA_SCORE_THRESHOLD`, `RETRY_COUNT`, and `MAX_RESPONSE_BYTES`.

Validate generated output:

```bash
python scripts/validate_output.py data/output/indian_shopify_stores.csv
```

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

`indian_shopify_stores.json` preserves arrays, dictionaries, verification evidence, crawled pages, redirects, and extraction errors naturally. With the standard output path, `data/intermediate/pipeline_debug.json` also includes rejected candidates and rejection reasons (a custom non-`output` directory keeps the debug file beside the final files).

## Testing

Tests use static HTML and mocked HTTP responses rather than live merchants:

```bash
pytest -q
```

They cover URL normalization, deduplication, strong and weak verification signals, address/GSTIN/phone extraction, social share-link rejection, logo priority/favicon rejection, and city-to-state mapping.

## Current Phase 1 limitations

- Candidates must be supplied in a CSV; broad search/discovery is intentionally absent.
- Pure client-side sites may expose too little HTML. The abstraction allows a later Playwright fallback, but Playwright is not included now.
- Some merchants block research crawlers or disallow pages through robots.txt; those candidates are rejected rather than bypassed.
- State resolution is text/city based. PIN-prefix resolution and deeper address disambiguation are future improvements.
- Rule-based category classification can be ambiguous for multi-category stores.
- OpenGraph images are only a weak logo fallback and can occasionally be a campaign image; provenance is retained for future scoring improvements.

## Phase 2 recommendation and scaling

Next, add a candidate-discovery layer that collects attributable domains from multiple sources, records provenance, normalizes/deduplicates before crawling, and feeds this unchanged enrichment pipeline. Start with small batches and measure manual precision by score band before increasing throughput.

For 1,000+ candidates, add persistent crawl caching, resumable job state, per-host rate limits, a queue, metrics by rejection reason, and a selective Playwright fallback. Keep thresholds evidence-driven and periodically audit accepted/rejected samples instead of lowering them merely to increase count.

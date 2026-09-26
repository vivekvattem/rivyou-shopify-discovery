# Wave 3 execution and quality summary

Run date: 2026-09-26 (UTC timestamps are retained in `pipeline_runs`).

## Acquisition and deduplication

Wave 3 used attributable public web-search results stored in 13 CSV files under
`data/discovery/imports/wave3/`. Each row retains the exact query, result URL,
source label, location, Shopify footprint, and category hint.

| Metric | Count |
|---|---:|
| Raw rows acquired | 775 |
| Valid rows | 775 |
| Unique registered-domain candidates in the Wave 3 inputs | 409 |
| Genuinely new candidates | 359 |
| Candidates already present | 50 |
| Duplicate observations | 366 |
| Invalid rows | 0 |
| New provenance observations added | 510 |

The raw-row count exceeded the preferred 400–500 range because the first 514
rows produced only 247 new domains. Acquisition continued until the hard
requirement of at least 350 genuinely new candidates was reached. No database
reset was performed.

## Controlled processing

| Run | Selected | Accepted | Shopify reject | India reject | Retry | Failed | Acceptance |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stage 1 | 50 | 38 | 6 | 4 | 2 | 0 | 76.0% |
| Stage 2 | 100 | 55 | 17 | 17 | 11 | 0 | 55.0% |
| Stage 3 | 209 | 162 | 9 | 9 | 29 | 0 | 77.5% |
| Retry pass 1 | 42 | 0 | 0 | 0 | 42 | 0 | 0.0% |
| Retry pass 2 | 42 | 0 | 0 | 0 | 0 | 42 | 0.0% |

Final outcome for the 359 genuinely new Wave 3 domains: 255 accepted (71.0%),
32 Shopify rejections (8.9%), 30 India rejections (8.4%), and 42 bounded
failures (11.7%). All 42 Wave 3 failures ended as `DNS_ERROR` during the final
network pass; none was converted into a verifier rejection. There are no
remaining `NEW`, `RETRY`, `QUEUED`, or `PROCESSING` candidates.

Compared with Wave 2's 133 new-domain cohort, acceptance moved from 76.7% to
71.0% (-5.7 percentage points), Shopify rejection from 2.3% to 8.9% (+6.6),
India rejection from 2.3% to 8.4% (+6.1), and bounded failure from 18.8% to
11.7% (-7.1). The larger rejection bands match Wave 3's deliberately broader
`/cdn/shop/` and `cdn.shopify.com` searches; thresholds were not relaxed.

## Current database and export

| Outcome | Count |
|---|---:|
| Total unique candidates | 525 |
| Accepted candidate/result rows | 381 |
| Unique registered-domain records in public export | 380 |
| Shopify rejected | 36 |
| India rejected | 35 |
| Failed after bounded attempts | 73 |

`nicobar.com` and `global.nicobar.com` are the sole accepted pair collapsed by
final registered-domain deduplication.

## Yield observations

The complete machine-readable breakdown is in
`data/output/quality_report.json`, including every source, exact query family,
location, category hint, and failure reason. Selected observations:

- Wave 3 provenance covers 409 candidates with a 71.9% current acceptance rate
  when the 50 already-known candidates are included.
- High-yield larger location groups include Karnataka (95.0%), Tamil Nadu
  (90.9%), Noida (84.2%), Ahmedabad (82.6%), and Hyderabad (80.0%).
- Lower-yield groups include Surat (50.0%) and Kerala (52.4%). Surat's
  `cdn.shopify.com` family produced many Shopify false leads; Kerala produced a
  larger India-rejection band.
- Larger category-hint groups were strongest for jewellery (82.6%), beauty
  (82.3%), fitness (81.5%), skincare (77.2%), home decor (77.8%), and furniture
  (76.7%). Food was lowest at 54.9%, with both Shopify and India false leads.

## Completeness drift

The public export grew from 126 to 380 unique registered domains.

| Field | Wave 2 missing | Wave 3 missing | Change |
|---|---:|---:|---:|
| Email | 1.6% | 3.4% | +1.8 pp |
| Phone | 4.0% | 6.8% | +2.8 pp |
| Any contact | 0.0% | 1.1% | +1.1 pp |
| Social profile | 20.6% | 21.6% | +1.0 pp |
| Category | 0.0% | 0.0% | 0.0 pp |
| Description | 4.8% | 2.6% | -2.2 pp |
| Logo | 0.8% | 3.2% | +2.4 pp |
| State | 5.6% | 7.9% | +2.3 pp |

The drift is moderate and concentrated in optional contact, logo, and state
fields. No values were guessed to improve completeness.

## Audit status

The automated audit covers all 381 accepted result rows and remains a machine
pre-review only: 375 were `HIGH`, five `MEDIUM`, and one `LOW`. Shopify
re-passed for 381/381; India passed for 380 with one uncertain live recheck;
368 logos passed, one failed, and 12 were missing; 351 states passed and 30
were missing; contacts passed for 377 with four uncertain; and 299 stores had
qualifying social profiles while 82 were missing.

The fresh 15-row targeted accepted-store worksheet contains all five MEDIUM
and the one LOW row, nine HIGH rows, the lowest accepted Shopify and India
scores, missing state/description/logo cases, unusual contact/social cases,
and seeded random HIGH rows. Its `manual_*` fields are intentionally blank, so
no new human precision percentage is claimed.

## Scale decision

The repository has passed the 500-candidate Wave 3 checkpoint but is not a
complete 1,000-store submission: the public export contains 380 unique stores.
The next wave should favor the high-yield Powered-by-Shopify/location families
and reduce broad CDN-only food/Surat/Kerala searches unless better query terms
are available.

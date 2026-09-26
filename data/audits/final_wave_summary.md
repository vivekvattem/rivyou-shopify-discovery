# Final scale-run summary

Generated from the production database and final artifacts on 2026-09-26. Verification thresholds remained unchanged at Shopify score 4 and India score 4.

## Acquisition and ingestion

- Raw attributable final-wave result URLs: **2,078** across 28 files.
- Structurally valid rows: **2,078**; invalid rows: **0**.
- Genuinely new normalized candidates ingested: **1,082**.
- Existing candidates observed: **173**.
- Within-import duplicate observations: **823**.
- The raw range exceeded 1,400 because collection continued until the hard target of at least 1,000 genuinely new domains was measured.
- Final total candidate count, preserving Waves 1–3: **1,607**.

## Processing outcome

| Stage | Selected | Accepted | Shopify rejects | India rejects | Retry | Failed | Runtime | Cumulative unique export |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NEW 1 | 100 | 82 | 5 | 3 | 10 | 0 | 229.45 s | 462 |
| NEW 2 | 250 | 191 | 28 | 4 | 27 | 0 | 430.59 s | 651 |
| NEW 3 | 250 | 191 | 20 | 21 | 18 | 0 | 406.17 s | 841 |
| NEW 4 remainder | 482 | 0 | 0 | 0 | 482 | 0 | 6.33 s | 841 |
| Retry 1 | 537 | 308 | 40 | 69 | 120 | 0 | 747.73 s | 1,143 |
| Retry 2 | 120 | 0 | 1 | 0 | 0 | 119 | 67.69 s | 1,143 |

Stage 4 encountered an environment-wide DNS denial, so all records were conservatively queued for bounded retry. No candidate was rejected from that event. Final-wave discovery plus batch runtime was **1,898.62 seconds (31m 38.62s)**.

Final production statuses:

- Accepted candidate rows: **1,153**.
- Accepted store-result rows: **1,150**.
- Unique canonical/registered-domain export rows: **1,143**.
- Shopify rejects: **130**.
- India rejects: **132**.
- Failures: **192**.
- Final overall candidate acceptance rate: **71.7%** (1,153 / 1,607).
- Final-wave new-candidate acceptance rate: **71.3%** (772 / 1,082).
- Remaining NEW / RETRY / QUEUED / PROCESSING: **0 / 0 / 0 / 0**.

Failure reasons: 76 `ROBOTS_BLOCKED`, 63 `DNS_ERROR`, 29 `SSL_ERROR`, 17 `OTHER_TRANSIENT`, three `TIMEOUT`, three `HTTP_5XX`, and one `HTTP_429`. Robots, TLS, DNS, and attempt limits were not bypassed.

## Automated audit

The final audit analyzed all **1,150 accepted result records** from fresh policy-compliant cache entries. Cache misses were marked unavailable; manual fields were never filled.

| Check | PASS | FAIL | UNCERTAIN | MISSING |
|---|---:|---:|---:|---:|
| Shopify | 1,147 | 0 | 3 | 0 |
| India | 1,142 | 0 | 8 | 0 |
| Logo | 1,113 | 1 | 2 | 34 |
| State | 1,038 | 0 | 3 | 109 |
| Contacts | 1,140 | 0 | 10 | 0 |
| Socials | 930 | 0 | 3 | 217 |

Overall confidence: **1,134 HIGH, 12 MEDIUM, 4 LOW**.

- Full machine audit: `data/audits/auto_audit_20260926T163940Z.csv`
- Blank 25-row human worksheet: `data/audits/targeted_accepted_audit_20260926T171858Z.csv`
- Worksheet composition: 9 HIGH, all 12 MEDIUM, all 4 LOW.
- Manual precision: **N/A** until a human fills the manual columns.

## Final export completeness

| Field | Missing count | Missing % |
|---|---:|---:|
| Domain | 0 | 0.0% |
| Any contact | 7 | 0.6% |
| Email | 41 | 3.6% |
| Phone | 71 | 6.2% |
| Socials | 215 | 18.8% |
| Category | 0 | 0.0% |
| Description | 23 | 2.0% |
| Logo | 34 | 3.0% |
| State | 110 | 9.6% |

The final quality report contains source, query-family, exact-query, location, and category-hint funnels. Every cohort is labeled `tiny`, `meaningful`, or `high_volume`; the highlight section includes only cohorts with at least 30 candidates and at least 75% observed acceptance. Exact queries have no high-volume highlights because no exact query reached 30 candidates.

## Verification

- Final export validation: **PASS**.
- Full test suite: **128 passed**.
- Production submission checker: **READY**, with **1,143** unique rows against the unchanged 1,000-row minimum.
- Human review remains separate and incomplete by design.

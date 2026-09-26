# Development notes

Extraction and verification rules change only after a concrete real-record failure is reviewed. Each entry records the observed pattern, generic correction, and static regression coverage; merchant-specific exceptions are prohibited.

## Confirmed pilot issues

### Placeholder contacts accepted as merchant contacts

- Observed failure: theme/demo content exposed `contact@yourbrand.com` and `+91 98765 43210`, which appeared in extracted contacts.
- Generic correction: reject known example/test/platform email domains and well-known placeholder telephone sequences after normalization.
- Regression coverage: `tests/test_contacts.py::test_rejects_real_world_placeholder_contacts`.

### Non-profile Facebook URLs accepted

- Observed failure: generic settings and share-like Facebook paths were treated as merchant profiles.
- Generic correction: reject settings/login/share/intent paths and platform-home URLs without hardcoding a merchant domain.
- Regression coverage: parameterized cases in `tests/test_socials.py` and final-artifact checks in `tests/test_submission.py`.

### Kidswear classified too broadly

- Observed failure: strong kidswear phrases lost to incidental general-fashion terms.
- Generic correction: weight title/H1 and explicit kidswear phrases more strongly than incidental navigation text.
- Regression coverage: category fixtures in `tests/test_category.py`.

### First six-digit number mistaken for a business PIN

- Observed failure: an unrelated six-digit number appeared before the actual address PIN and weakened state/business-location resolution.
- Generic correction: evaluate all PIN candidates and require address context; structured `PostalAddress` evidence takes priority.
- Regression coverage: address-context cases in `tests/test_india.py`.

## Phase 4 queue completion

No new extractor or verifier rule was changed from the Phase 4 audit worksheet because its human correctness fields remain blank. Six inaccessible candidates consistently disallowed the crawler in `robots.txt`; this was handled operationally as `ROBOTS_BLOCKED`, not as evidence for a verifier rewrite.

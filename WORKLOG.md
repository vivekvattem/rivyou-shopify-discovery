# Worklog

Use this file for approximate human time only. Historical development or review time is intentionally not inferred.

| Activity | Actual approximate time | Notes |
|---|---:|---|
| Development time | _enter manually_ | Include implementation and debugging time. |
| Discovery/collection time | _enter manually_ | Include search and candidate curation time. |
| Pipeline execution time | Final wave: 31m 38.62s | Automatically measured discovery and batch runtime; per-run values remain in `pipeline_runs.total_seconds`. |
| Manual audit time | _enter manually_ | Include worksheet review time. |

To print recorded execution runs:

```bash
python scripts/report_stats.py --json-output data/audits/latest_report.json
```

The report's `recent_runs` entries contain UTC timestamps, wave labels, and measured runtime. Do not replace blank human-time entries with estimates unless the person who performed the work supplies them.

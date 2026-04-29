# Contribution Metrics

This dashboard is designed to make operator contribution visible: how many labels were processed, how many duplicate records were prevented, and how much manual entry time was likely saved.

## Metrics

- `total_records`: all uploaded records in the local database.
- `confirmed_count`: records with status `confirmed` or `submitted`.
- `submitted_count`: records with status `submitted`.
- `failed_count`: records with status `submission_failed`.
- `duplicates_caught`: records with status `duplicate`; each duplicate is treated as one avoided duplicate-entry error.
- `by_status`: count for every record status.
- `by_category`: count for categories `A`, `B`, and `C`.
- `daily_throughput`: per-day uploaded, confirmed, and submitted counts for the requested day window.
- `upload_to_confirm_seconds`: average time from upload creation to local confirmation for confirmed/submitted records.
- `confirm_to_submit_seconds`: average time from confirmation/update to SaaS submission timestamp for submitted records.
- `avg_confidence`: average OCR confidence over records with a confidence score.
- `high_confidence_pct`: share of scored records with confidence `>= 0.9`.
- `low_confidence_pct`: share of scored records with confidence `< 0.7`.
- `needs_review_count`: records requiring manual review.

## Estimated Savings

The current assumption is:

```text
manual entry baseline = config/settings.yaml metrics.manual_seconds
saved minutes = confirmed_count * (manual_seconds - average upload_to_confirm_seconds) / 60
```

The default baseline is 90 seconds per record. The result is an estimate, not an accounting figure. Use it as a transparent productivity indicator and keep the assumption visible in reports.

Example: if 10,000 records are confirmed and the measured average time is 0 seconds in a fast local test, the upper-bound estimate is:

```text
10,000 * 90 / 60 = 15,000 minutes = 250 hours
```

## API Snapshot

Export a current metrics snapshot:

```bash
curl -o contribution-metrics.json http://127.0.0.1:8000/api/metrics/all
```

With the mobile test server:

```bash
curl -o contribution-metrics.json http://127.0.0.1:8001/api/metrics/all
```

## How To Explain It

For management reporting, keep the wording factual:

- "Processed X machine-label records through the OCR intake workflow."
- "Prevented Y duplicate-entry attempts through VIN/SN duplicate detection."
- "Estimated Z hours of manual entry avoided using a 90-second-per-record baseline."
- "OCR quality averaged N%, with low-confidence records routed to review."

## Portfolio Use

The dashboard and JSON snapshot can be used as a portfolio artifact because the formulas are explicit and reproducible. A future multi-operator version should add `operator_id` and export per-operator snapshots; the current MVP tracks the whole local instance.

# sources

Job source ingestion. Collects raw job listings from external platforms and normalizes them into `LinkedInJobCard` models.

Currently implemented: **LinkedIn only**. Architecture supports adding new sources (Indeed, Greenhouse, etc.) as sibling packages.

## Structure

```
sources/
└── linkedin/
    ├── feed/          # Browser-based collection (keyword search + recommended feed)
    ├── alerts/        # Email-based collection (IMAP job alert parsing)
    └── scraper/       # Detail page scraping (full JD fetch)
```

### `linkedin/feed/`

Drives a CDP-connected Playwright browser through LinkedIn search results and recommended feed pages.

| File | Purpose |
|---|---|
| `run.py` | `run_linkedin_source()` — orchestrator: paginate, collect, dedupe, filter |
| `query.py` | URL builders for keyword search and recommended feed pagination |
| `collection.py` | `collect_job_cards_from_page()` — wait for render, expand scroll, extract cards |
| `expand.py` | `expand_result_list()` — scroll-to-load for lazy-rendered card lists |
| `extract.py` | `parse_row_card()`, `to_job_card()` — DOM element to structured job card |
| `dedupe.py` | `job_card_dedupe_key()` — composite key for duplicate detection |

### `linkedin/alerts/`

Fetches LinkedIn notification emails via IMAP.

| File | Purpose |
|---|---|
| `fetch.py` | `fetch_linkedin_job_alert_emails()`, `fetch_linkedin_application_confirmation_emails()` |
| `parse.py` | `extract_job_cards_from_email()`, `extract_application_confirmation_from_email()` |
| `connection_check.py` | `verify_linkedin_email_connection()` — IMAP config validation |

### `linkedin/scraper/`

Fetches full job description pages for jobs that passed title triage.

| File | Purpose |
|---|---|
| `run.py` | `fetch_linkedin_job_details()` — navigate to job page, extract all fields |
| `extract.py` | DOM extraction: description, work mode, applicant count, apply link, employment type |

### `linkedin/` helpers

| File | Purpose |
|---|---|
| `utils.py` | URL parsing, job ID extraction, work mode detection, Easy Apply detection |
| `debug.py` | Page inspection helpers for development (`selector_counts`, `selector_text_samples`) |
| `log_payloads.py` | Serialization helpers for structured logging |

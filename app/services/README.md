# services

Shared infrastructure layer. Provides I/O primitives that domain code calls but never implements directly.

## Submodules

### `llm/`

OpenAI-compatible LLM client targeting Google Gemini.

| File | Purpose |
|---|---|
| `config.py` | Dataclass configs per LLM operation (title triage, enrichment, ranking, question mapping) |
| `client.py` | `request_structured_chat_completion()` — single entry point for all LLM calls. Handles retries, JSON Schema response format, usage logging |

### `storage/`

SQLite persistence layer. Every table operation is a plain function taking a `sqlite3.Connection`.

| File | Purpose |
|---|---|
| `db.py` | `get_connection()`, schema creation, migrations. Tables: `jobs`, `job_observations`, `job_rankings`, `job_applications`, `job_application_questions` |
| `stages.py` | `JobStage` enum, `validate_stage_transition()`, `advance_job_stage()` — job lifecycle state machine |
| `jobs.py` | Insert/upsert job cards, record observations |
| `title_triage.py` | Load discovered jobs, save triage decisions |
| `job_details.py` | Load triaged jobs, save scraped detail pages |
| `enrichment.py` | Load detailed jobs, save LLM enrichment results |
| `ranking.py` | Load enriched jobs, save ranking scores |
| `applications.py` | Application session CRUD: create, update status, replace questions, mark applied |
| `email_confirmations.py` | Process confirmation emails with deduplication |
| `types.py` | `TypedDict` return types (`RankedJobRow`, `ApplicationRow`, etc.) |
| `_shared.py` | Common helpers: `now_iso()`, JSON serialization, generic stage-based loaders |

### Top-level

| File | Purpose |
|---|---|
| `browser.py` | `verify_linkedin_connection()` — CDP health check via Playwright |
| `email.py` | IMAP connection management with retry (`connect_imap_mailbox`) |

## Design notes

- Storage functions are stateless — connection is always passed in, never stored globally.
- LLM client enforces structured output via `response_format.json_schema` with `strict: True`.
- All retryable operations use `app.utils.retry.retry_with_backoff`.

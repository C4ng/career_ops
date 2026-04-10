# screening

LLM-powered screening pipeline. Takes raw job listings and progressively filters, enriches, and ranks them.

## Files

| File | Stage | What it does |
|---|---|---|
| `filter.py` | Title triage | `triage_linkedin_job_titles()` — LLM classifies titles as keep/discard based on role intent and signal lists |
| `enrich.py` | JD enrichment | `enrich_linkedin_job_descriptions()` — LLM extracts structured sections (requirements, benefits, scope) from raw descriptions |
| `rank.py` | Ranking | `rank_linkedin_jobs()` — LLM scores candidate fit on three orthogonal dimensions (role, level, preference) and recommends action (apply_focus / apply_auto / low_priority) |

## Flow

```
discovered jobs
  → filter.py  (keep/discard by title)
  → [detail fetch via sources/linkedin/scraper]
  → enrich.py  (structured JD extraction)
  → rank.py    (fit scoring + recommendation)
```

## Design notes

- Each function follows the same pattern: load config + prompt, call `request_structured_chat_completion`, parse and validate response.
- Prompts and JSON schemas are defined in `app/prompts/screening/`.
- All three functions are batch-oriented — they process a list of jobs and return a list of results.

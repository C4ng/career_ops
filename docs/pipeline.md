Pipeline
========

Config
------

- `config/app.yaml` — single global config file
- `config/app.template.yaml` — template with all sections documented

Major config sections:

- `logging`
- `system.linkedin.connection`, `system.linkedin.collection`, `system.linkedin.email`
- `system.llm.title_triage`, `system.llm.jd_enrichment`, `system.llm.ranking`
- `system.llm.application_question_mapping`
- `user.linkedin.sources`, `user.linkedin.email_notifications`
- `user.linkedin.title_triage`, `user.linkedin.ranking`
- `user.linkedin.application_assistant`

Scripts
-------

```
scripts/
├── pipeline.py                      # end-to-end pipeline (stages 1-6)
├── connection/
│   ├── browser.py                   # verify browser CDP connection
│   └── email.py                     # verify IMAP email connection
├── source/
│   ├── browser.py                   # collect jobs from browser feeds
│   └── email.py                     # collect jobs from email alerts
├── screening/
│   ├── title_triage.py              # LLM title filtering
│   ├── detail_fetch.py              # scrape full job pages
│   ├── jd_enrichment.py             # LLM JD structuring
│   └── ranking.py                   # LLM candidate fit scoring
├── easy_apply/
│   ├── probe.py                     # dev probe for single job
│   ├── preview_batch.py             # extract questions + LLM answers
│   ├── review.py                    # apply human-reviewed overrides
│   └── submit.py                    # submit from review_ready session
├── confirmation/
│   ├── ui.py                        # verify via LinkedIn UI
│   ├── email.py                     # verify via confirmation emails
│   └── watcher.py                   # periodic UI + email verification
├── external_apply/
│   ├── audit.py                     # audit external apply links
│   └── browser_use_probe.py         # dev spike for agentic external apply
└── storage/
    ├── init_db.py                   # initialize SQLite schema
    └── view_db.py                   # inspect database tables
```

Job State Transitions
---------------------

Source ingestion:
- writes `discovered`

Title triage:
- reads `discovered`
- writes `triaged` or `not_applicable`

Detail fetch:
- reads `triaged`
- writes `detailed` or `not_applicable`

JD enrichment:
- reads `detailed`
- writes `enriched`

Ranking:
- reads `enriched`
- writes to `job_rankings` table, sets `ranked` or `not_applicable`

Easy Apply:
- reads ranked `easy_apply` jobs
- writes to `job_applications` and `job_application_questions`
- pauses at review before final submit

Confirmation:
- reads `submitted_pending_confirmation` applications
- sets `applied` on confirmation

Run Commands
------------

Single stage:

```bash
conda run -n job-finding-agent python scripts/source/browser.py
```

End-to-end pipeline (stages 1-6):

```bash
conda run -n job-finding-agent python scripts/pipeline.py
```

Pipeline stages in order:

1. browser connection check
2. browser source ingestion
3. email source ingestion
4. title triage
5. detail fetch
6. JD enrichment
7. ranking

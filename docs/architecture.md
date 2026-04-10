Architecture
============

Code Structure
--------------

```
app/
├── models/              # Pydantic data models (job, candidate, application, screening)
├── prompts/             # LLM prompt templates and schemas
│   ├── screening/       #   triage, enrich, rank
│   └── application/     #   question mapping
├── screening/           # Screening orchestration (triage, enrich, rank)
├── application/         # Application workflows
│   ├── confirmation.py  #   verify applied status
│   ├── easy_apply/      #   LinkedIn Easy Apply pipeline
│   └── external/        #   external application handling
├── sources/             # Data source integrations
│   └── linkedin/        #   browser feeds, email alerts, scraper
├── services/            # Infrastructure services
│   ├── browser.py       #   Playwright connection verification
│   ├── email.py         #   IMAP client
│   ├── llm/             #   LLM client and config
│   └── storage/         #   SQLite schema, reads, writes
├── settings.py          # Config loading from config/app.yaml
├── logging_setup.py     # Structured logging setup
└── utils/               # Shared utilities (retry)

scripts/
├── pipeline.py          # End-to-end pipeline orchestrator
├── connection/          # Stage 1: verify browser + email connectivity
├── source/              # Stage 2: collect job listings
├── screening/           # Stages 3-6: triage, detail fetch, enrichment, ranking
├── easy_apply/          # Stage 7: application workflow
├── confirmation/        # Stage 8: verify submitted applications
├── external_apply/      # Stage 9: external application handling
└── storage/             # DB init and inspection utilities
```

Easy Apply Module
-----------------

`app/application/easy_apply/` is split by pipeline stage:

| File          | Responsibility                                            |
|---------------|-----------------------------------------------------------|
| `parse.py`    | Extract modal DOM into Pydantic models + text normalization |
| `classify.py` | Classify fields, build questions, propose fill actions    |
| `answers.py`  | Resolve answers: candidate dossier lookup + LLM           |
| `fill.py`     | Browser interactions: click, type, select                 |
| `navigate.py` | Walk multi-step form to review boundary                   |
| `review.py`   | Apply answer overrides + submit                           |

`parse_form.js` is the JS companion that scrapes the LinkedIn modal DOM.

Storage
-------

SQLite is the runtime state store. Key tables:

- `jobs` — job listings with stage tracking
- `job_rankings` — LLM ranking results per job
- `job_applications` — application session tracking
- `job_application_questions` — extracted questions and proposed answers

Stage transitions are enforced in `app/services/storage/stages.py`.

Models
------

All Pydantic models live in `app/models/`:

- `job.py` — job card and detail models
- `candidate.py` — candidate dossier (contact, auth, education, experience, preferences)
- `application.py` — form elements, questions, answer proposals, form steps
- `screening.py` — triage, enrichment, ranking results
- `linkedin_config.py` — connection and collection config
- `interfaces.py` — shared interfaces

Logging and Artifacts
---------------------

- Stage logs: `data/logs/`
- Easy Apply screenshots and review artifacts: `data/reviews/`
- Config: `config/app.yaml`

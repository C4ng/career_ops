Logging Contract
================

Purpose
-------

Every pipeline stage must write structured logs inside the repo.

Log Location
------------

- `data/logs/`

Log Rules
---------

- One `latest` log file per stage.
- One timestamped history file per run.
- Structured text with pretty-printed JSON payloads.
- Inputs, outputs, counts, and failures must all be explicit.

Required Stage Logs
-------------------

1. Source ingestion log

- config path
- source config
- requested limits
- offsets visited
- cards collected
- filtered-out items
- DB write summary
- failure list

2. Triage log

- LLM config
- triage config
- input batch
- model decisions
- DB stage updates
- counts
- failure list

3. Detail extraction log

- triaged input jobs
- successful detail records
- failed URLs
- extracted apply metadata
- DB stage updates

4. JD enrichment log

- LLM config
- detailed input jobs
- exact model input payload
- raw model output
- parsed enrichment payload
- DB stage updates

Failure Policy
--------------

- Do not silently swallow stage failures.
- If fallback logic is used, record:
  - fallback type
  - original error
  - affected job ids

Database Contract
-----------------

- Logs are for inspection and debugging.
- SQLite is the runtime state store.
- Jobs move through pipeline stages using:
  - `discovered`
  - `triaged`
  - `detailed`
  - `enriched`
  - `not_applicable`

Review Requirement
------------------

Before each implementation step, confirm:

- expected input
- expected output
- expected log file

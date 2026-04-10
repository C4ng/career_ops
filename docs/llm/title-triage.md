Title Triage LLM Stage
======================

Purpose
-------

Use an LLM to judge whether a discovered LinkedIn job should continue in the pipeline based on:

- title
- company
- location
- work mode

Current Runtime Version
-----------------------

- prompt version: `v1`
- model: configured in `system.llm.title_triage`

Current Behavior
----------------

- reads jobs at stage `discovered`
- writes jobs to:
  - `triaged`
  - `not_applicable`
- keeps `title_triage_model` as the audit field

Version Notes
-------------

- `v1`
  - broad AI title triage
  - favors recall over strict rejection
  - uses strong title cues plus location policy
  - keeps uncertain but plausible roles

Logging And Monitoring
----------------------

- normal runner logs in `data/logs/linkedin_title_triage.latest.log`
- shared LLM client logs:
  - response time
  - token usage when available from provider
  - request/response payload size
  - schema name and finish reason

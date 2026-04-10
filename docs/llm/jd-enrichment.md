JD Enrichment LLM Stage
=======================

Purpose
-------

Convert raw LinkedIn job descriptions into a structured job card extension.

Current Runtime Version
-----------------------

- prompt version: `v2`
- model: configured in `system.llm.jd_enrichment`

Current Behavior
----------------

- reads jobs at stage `detailed`
- writes jobs to:
  - `enriched`
- fills:
  - `company_intro`
  - `role_scope`
  - `requirements`
  - `benefits`
  - `application_details`
- may also refine:
  - `work_mode`
  - `salary_text`
  - `employment_type`

Version Notes
-------------

- `v1`
  - extracted the right themes but tended to rewrite large parts of the JD
  - company and role sections were too verbose

- `v2`
  - favors compact structured summaries instead of JD-style rewriting
  - tries to merge overlap and keep applicant-relevant details

Logging And Monitoring
----------------------

- normal runner logs in `data/logs/linkedin_jd_enrichment.latest.log`
- shared LLM client logs:
  - response time
  - token usage when available from provider
  - request/response payload size
  - schema name and finish reason

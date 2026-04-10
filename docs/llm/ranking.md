Ranking LLM Stage
=================

Purpose
-------

Rank enriched jobs for this candidate using structured metadata and enrichment sections.

Current Runtime Version
-----------------------

- prompt version: `v7`
- profile version: `v2`
- model: configured in `system.llm.ranking`

Current Behavior
----------------

- reads jobs at stage `enriched`
- writes ranking rows into `job_rankings`
- may also mark jobs:
  - `not_applicable`

Current Output Shape
--------------------

- `role_match` — domain, function, skills fit
- `level_match` — seniority, experience, scope fit
- `preference_match` — work mode, salary, employment type
- `recommendation`
  - `apply_focus`
  - `apply_auto`
  - `low_priority`

Version Notes
-------------

- `v1`
  - early numeric scoring shape

- `v2`
  - moved to label-based fit judgments

- `v3`
  - added hard-ineligibility handling that can mark jobs `not_applicable`

- `v4`
  - reduced over-penalization of light ownership language

- `v5`
  - added domain-aware role fit via profile preferences

- `v6`
  - concrete experience requirements outweigh inflated prestige wording
  - ranking now uses structured metadata and enrichment only
  - raw `job_description` is no longer sent to the ranking LLM

- `v7`
  - collapsed 5 overlapping fit dimensions into 3 orthogonal dimensions:
    - role_match (domain + skills), level_match (seniority + experience), preference_match (logistics)
  - removed candidate_fit (was a derived composite of other dimensions)
  - removed skill_fit and experience_fit (merged into role_match and level_match respectively)
  - added input schema description, few-shot example, calibration anchors, and edge case guidance
  - prompt follows standard template: task > input schema > dimensions > rules > edge cases > example

Profile Notes
-------------

- `v2`
  - added preferred vs acceptable domains
  - added explicit student-status constraints

Logging And Monitoring
----------------------

- normal runner logs in `data/logs/linkedin_ranking.latest.log`
- shared LLM client logs:
  - response time
  - token usage when available from provider
  - request/response payload size
  - schema name and finish reason

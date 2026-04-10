Project Overview
================

Purpose
-------

Automated job-finding agent: source jobs, screen them, and assist with applications.

Principles
----------

- One reviewed slice at a time.
- Prefer explicit pipelines over loosely coupled agent behavior.
- Every stage must have logged inputs, logged outputs, and a clear failure record.
- Write directly to SQLite instead of intermediate runtime artifacts.
- Human-in-the-loop before any submission.

Tech Stack
----------

- Python 3.11
- Pydantic models for all data boundaries
- Playwright + Chrome remote debugging (CDP) for browser automation
- SQLite for persistence (`data/job_finding.sqlite3`)
- LLM: OpenAI-compatible API (Google Gemini)
- Structured LLM output with JSON Schema validation
- IMAP for email ingestion


Implemented Pipeline
--------------------

1. **Source ingestion** — collect job listings from browser feeds and email alerts
2. **Title triage** — LLM-based title filtering to keep relevant positions
3. **Detail fetch** — scrape full job description pages
4. **JD enrichment** — LLM-based structured extraction from raw JDs
5. **Ranking** — LLM-based candidate fit scoring and recommendation
6. **Easy Apply** — deterministic + LLM answer resolution, human review before submit
7. **Confirmation** — verify submitted applications via LinkedIn UI or email

Current source: LinkedIn only (keyword search, recommended feed, job-alert email).

### Refinement notes

- **Ranking calibration** — no mechanism yet for collecting user feedback on LLM ranking decisions. Need a way for users to review/correct rankings in a dashboard and use that as calibration data to improve prompts over time. Should be collected during the initial usage phase.
- **User profile completeness** — candidate dossier fields are partially defined. Two levels of information exist: deterministic facts (name, email, authorization) and flexible questions (salary expectations, role preferences). Profile should grow over time through interaction — when a missing field is asked during an application, the answer should be saved back into the user profile in the correct section (structured memory mechanism).


Planned: External Application Agent
------------------------------------

Status: under investigation. Draft implementation in `app/application/external/agent.py`.

Goal: fill external (non-Easy Apply) job applications using an agentic web navigation system.

### Current state

- Browser-use agent handles web navigation (ReAct design, tested and working)
- Flow: navigate to application page → extract interactable fields → convert to questions → LLM service answers → flag low-confidence fields → human review before submit
- Token consumption is high with the current browser-use agent

### Architecture direction

The web navigation agent is the main loop. Other capabilities are sub-agents or tools called during form filling:

- **Form answering** — deterministic dossier lookup + LLM for flexible questions (same pattern as Easy Apply)
- **Resume tailor agent** — generates a tailored resume (LaTeX → PDF) using job description context. Not implemented yet.
- **Cover letter agent** — generates a targeted cover letter using JD context. Not implemented yet.

### Open problems

- **Token cost** — need to extract the core navigation logic from browser-use and rewrite surrounding prompts to integrate into our own workflow, reducing token consumption while keeping the working navigation
- **Interactive field edge cases** — need to handle more form field types discovered through testing
- **User communication model** — two modes not yet implemented:
  - *Online*: register a communication channel for real-time user interaction during form filling
  - *Batched*: save all unreviewed forms and wait for user to review later
- **Priority-based effort** — application effort, human-in-the-loop involvement, and resume tailoring cost should scale with job ranking priority (apply_focus gets full effort, apply_auto gets lighter treatment)


Planned: Resume Tailor Agent
-----------------------------

Status: not implemented.

- Takes job description + candidate experience as input
- Generates a tailored resume emphasizing relevant experience
- Should be capable of writing LaTeX and generating a new resume PDF
- Called as a sub-agent/tool during application form filling when a resume upload is needed
- Activation cost varies by job priority


Planned: Cover Letter Agent
----------------------------

Status: not implemented.

- Takes job description + candidate experience as input
- Generates a targeted cover letter
- Called as a sub-agent/tool during application form filling
- Activation cost varies by job priority


Planned: Job Dashboard
-----------------------

Status: not implemented.

- Job logging and application tracking UI
- Surface for user to review/correct LLM ranking decisions (feeds calibration data)
- Review queue for batched unreviewed application forms


Planned: Career Analysis (Side Agent)
--------------------------------------

Status: not implemented. Lower priority.

- Career coaching / statistics / experience analysis
- Implemented as a side agent, not part of the core pipeline


Job Lifecycle
-------------

Jobs move through persisted stages:

    discovered → triaged → detailed → enriched → ranked → applied

Any stage may also transition to `not_applicable`.

Application sessions are tracked separately in `job_applications` with states:

    opened → review_ready → submitted_pending_confirmation → applied

Easy Apply Workflow
===================

Goal
----

Assisted application for LinkedIn Easy Apply jobs. Conservative by design:

- only targets ranked jobs with `easy_apply = true`
- fills deterministic answers first, uses LLM only for unresolved questions
- pauses for unknown or missing required information
- stops before final submit unless explicitly approved

Application Flow
-----------------

1. **Select** a ranked Easy Apply job from the database
2. **Navigate** to the Easy Apply modal via Playwright
3. **Parse** each form step into structured Pydantic models
4. **Classify** each field: already filled, fillable from dossier, needs LLM, needs user
5. **Fill** deterministic and preview values into the browser
6. **Advance** through modal steps until review boundary or blocker
7. **Resolve** remaining questions via candidate dossier + LLM batch
8. **Review** — human inspects and applies overrides
9. **Submit** — explicit approval required

Module Structure
----------------

`app/application/easy_apply/`:

| File          | Stage                                                     |
|---------------|-----------------------------------------------------------|
| `parse.py`    | DOM → clean Pydantic models + text normalization          |
| `classify.py` | Classify fields, build questions, propose fill actions    |
| `answers.py`  | Resolve answers: candidate dossier lookup + LLM           |
| `fill.py`     | Browser interactions: click, type, select                 |
| `navigate.py` | Walk multi-step form to review boundary                   |
| `review.py`   | Apply answer overrides + submit                           |

Scripts
-------

- `scripts/easy_apply/probe.py` — dev probe for single job
- `scripts/easy_apply/preview_batch.py` — full preview + LLM question batch
- `scripts/easy_apply/review.py` — apply human-reviewed overrides
- `scripts/easy_apply/submit.py` — submit from review_ready session

Candidate Dossier
-----------------

Config section: `user.linkedin.application_assistant.candidate_dossier`

Model: `LinkedInCandidateDossier` in `app/models/candidate.py`

Deterministic coverage from dossier:

- name, email, phone
- city, country, phone country
- salary expectation, notice period
- headline / summary

Fields not in the dossier are routed to the LLM or flagged for user input.

Question Resolution
-------------------

1. **Dossier lookup** — `answers.resolve_candidate_value_for_label()` matches field labels to dossier values using keyword rules
2. **Option matching** — if the field has options, the dossier value is matched against available choices
3. **LLM batch** — unresolved questions are sent to the LLM with the candidate dossier context
4. **User input** — questions the LLM can't resolve are flagged for human review

Application States
------------------

Tracked in `job_applications`:

- `opened` — application session started
- `needs_user_input` — paused for unresolved required fields
- `review_ready` — reached submit boundary, waiting for human review
- `submitted_pending_confirmation` — submitted, awaiting confirmation
- `applied` — confirmed via LinkedIn UI or email

Storage
-------

- `job_applications` — application session header
- `job_application_questions` — extracted questions and proposed answers per step

Confirmation
------------

- LinkedIn UI: `scripts/confirmation/ui.py` checks `My Jobs → Applied`
- Email: `scripts/confirmation/email.py` checks LinkedIn confirmation emails
- Watcher: `scripts/confirmation/watcher.py` runs both periodically

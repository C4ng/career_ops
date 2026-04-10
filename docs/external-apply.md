# External Apply Draft

Status: development draft, not implementation-ready.

## Goal

Build an external-application workflow that can:

- open off-LinkedIn apply flows
- fill applications up to review
- stop for human review before submit
- submit only after explicit approval
- confirm completion through external-site signals or email

## Current Recommendation

Start with an agent-assisted generic workflow, not provider-specific adapters.

Why:

- ranked external jobs are still fragmented across many domains
- repetition exists, but not enough yet to justify building many hardcoded adapters up front
- long-tail sites are likely to dominate near-term development effort

## Development Path

### Phase 1: Audit and Instrumentation

Build a development-only external apply probe that records:

- provider/domain guess
- redirects and final URL
- auth wall detection
- account-creation requirement
- CAPTCHA detection
- file upload presence
- dynamic questions
- review-step presence
- success-page presence

Artifacts per run:

- structured JSON artifact
- screenshots
- Playwright trace
- per-step event log

### Phase 2: Generic Run-To-Review

Build a generic external apply workflow that:

- opens an external apply link
- classifies page state
- extracts candidate fields/questions
- fills deterministic dossier-backed answers
- batches unresolved questions to the LLM
- reaches review or pauses on blockers

Do not submit in this phase.

### Phase 3: Review Queue

Reuse the Easy Apply review model:

- persist application session in DB
- mark as `review_ready`
- allow resume/edit in the same session when possible
- reopen and recover when live tab state is gone

### Phase 4: Submit and Confirm

After explicit approval:

- submit from review
- wait for site confirmation signal if present
- otherwise rely on email confirmation as canonical fallback

External applications should use email confirmation by default.

## Architecture Direction

Shared core:

- dossier resolution
- normalized question schema
- LLM question answering
- review queue
- confirmation tracking

External frontend:

- Playwright as the browser/runtime base
- generic page interpreter loop
- optional agentic exploration for unknown navigation

Deferred:

- provider-specific adapters
- account creation
- CAPTCHA handling
- OTP/email verification loops

## Tooling Direction

Primary:

- Playwright
- current SQLite-backed workflow/session state
- current LLM routing model

Optional later:

- agentic browser exploration fallback for unknown sites
- provider-specific adapters if repeated patterns justify them

## Monitoring and Traces

Record for each run:

- `run_id`
- `job_id`
- `application_id`
- `provider_guess`
- `domain`
- `step_index`
- extracted fields
- routing decisions
- deterministic fills
- LLM input questions
- LLM output proposals
- executed browser actions
- validation failures
- stop reason
- review/submit confirmation path

Keep Playwright traces on:

- every failure
- every new provider/domain sample
- a small sample of successful runs

## Decision Rule

Stay generic/agent-assisted until one of these becomes true:

- the same provider repeatedly appears in ranked external jobs
- the same provider shows a stable DOM/form pattern across samples
- deterministic execution clearly reduces cost/risk versus the generic path

At that point, promote that provider into a dedicated adapter.

# application

Application automation. Handles filling and submitting job applications after screening.

## Submodules

### `easy_apply/`

LinkedIn Easy Apply automation. Walks multi-step modal forms, resolves answers, fills fields, and pauses for human review before submit.

| File | Stage | Purpose |
|---|---|---|
| `parse.py` | Extract | DOM extraction + text normalization. Converts raw Playwright modal into `LinkedInApplicationFormStep` models. JS companion: `parse_form.js` |
| `classify.py` | Classify | Field classification, question building, preview fill action proposals |
| `answers.py` | Resolve | Two-tier answer resolution: deterministic dossier label lookup → LLM batch for unmatched questions |
| `fill.py` | Fill | Browser interactions: click, type, select, option resolution via LLM |
| `navigate.py` | Orchestrate | `run_easy_apply_to_review()` — multi-step form walk from open to review-ready |
| `review.py` | Review | Human review: apply overrides, navigate sections, submit |

### `external/`

External (non-Easy Apply) application agent. Draft implementation using browser-use for agentic web navigation.

| File | Purpose |
|---|---|
| `agent.py` | Browser-use agent integration: tool definitions, dossier loading, prompt building, form filling orchestration |
| `audit.py` | External URL analysis: ATS provider detection (Ashby, Greenhouse, Lever, etc.), platform categorization |

### `cover_letter/` and `resume/`

Planned sub-agents for document generation. Not yet implemented.

### Top-level

| File | Purpose |
|---|---|
| `confirmation.py` | Post-submit verification: scans LinkedIn browser pages and email for application confirmation signals |

## Easy Apply flow

```
navigate to job → open modal
  → parse form step (parse.py)
  → classify fields, build questions (classify.py)
  → resolve answers from dossier + LLM (answers.py)
  → fill fields in browser (fill.py)
  → advance to next step (navigate.py)
  → ... repeat until review page ...
  → human reviews + edits (review.py)
  → submit
```

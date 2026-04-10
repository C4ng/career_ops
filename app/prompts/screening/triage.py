from __future__ import annotations

from app.models import LinkedInTitleTriageCandidate, LinkedInTitleTriageConfig


TITLE_TRIAGE_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "linkedin_job_id": {"type": "string"},
                    "decision": {"type": "string", "enum": ["keep", "discard"]},
                    "reason": {"type": "string"},
                },
                "required": ["linkedin_job_id", "decision", "reason"],
            },
        }
    },
    "required": ["decisions"],
}

TITLE_TRIAGE_SYSTEM_PROMPT = """\
You are classifying LinkedIn job cards at the title triage stage. Return one decision per job.

## Input

- `triage_config`: candidate preferences — `role_intent` (preferred/acceptable roles), `discard_signals`, `keep_signals`, and optional `examples`
- `jobs`: array with `linkedin_job_id`, `title`, `company`, `location_text`, `work_mode`

Use only these fields. Do not infer JD details. Prefer recall — when uncertain, keep.

## Rules

- Match titles against the candidate's role intent and signal lists.
- A partial keep_signal match should keep unless it strongly matches a discard_signal.
- Empty or generic titles (e.g. "Engineer"): keep for later review.
- Null location_text or work_mode is not a discard reason.

## Example

```
triage_config.role_intent.preferred: ["Software Engineer", "Backend Developer"]
triage_config.discard_signals: ["Director", "VP", "Chief"]
jobs: [
  {"linkedin_job_id": "111", "title": "Junior Software Engineer"},
  {"linkedin_job_id": "222", "title": "VP of Engineering"},
  {"linkedin_job_id": "333", "title": "Engineer"}
]
```
```json
{"decisions": [
  {"linkedin_job_id": "111", "decision": "keep", "reason": "Matches preferred Software Engineer role."},
  {"linkedin_job_id": "222", "decision": "discard", "reason": "VP matches discard signal."},
  {"linkedin_job_id": "333", "decision": "keep", "reason": "Generic title; keeping for later review."}
]}
```

Return JSON matching the schema exactly.
"""


def build_title_triage_user_payload(
    triage_config: LinkedInTitleTriageConfig,
    candidates: list[LinkedInTitleTriageCandidate],
) -> dict[str, object]:
    return {
        "triage_config": triage_config.model_dump(mode="json"),
        "jobs": [
            {
                "linkedin_job_id": candidate.linkedin_job_id,
                "title": candidate.title,
                "company": candidate.company,
                "location_text": candidate.location_text,
                "work_mode": candidate.work_mode,
            }
            for candidate in candidates
        ],
    }

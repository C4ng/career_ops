from __future__ import annotations

from app.models import LinkedInRankingConfig

PROMPT_VERSION = "v7"

LINKEDIN_RANKING_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rankings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "linkedin_job_id": {"type": "string"},
                    "role_match": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string", "enum": ["strong", "partial", "weak"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["label", "reason"],
                    },
                    "level_match": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string", "enum": ["appropriate", "stretch", "mismatched"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["label", "reason"],
                    },
                    "preference_match": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string", "enum": ["preferred", "acceptable", "not_preferred"]},
                            "reason": {"type": "string"},
                        },
                        "required": ["label", "reason"],
                    },
                    "not_applicable_reason": {
                        "type": ["string", "null"]
                    },
                    "recommendation": {
                        "type": "string",
                        "enum": ["apply_focus", "apply_auto", "low_priority"],
                    },
                    "summary": {"type": "string"},
                },
                "required": [
                    "linkedin_job_id",
                    "role_match",
                    "level_match",
                    "preference_match",
                    "not_applicable_reason",
                    "recommendation",
                    "summary",
                ],
            },
        }
    },
    "required": ["rankings"],
}


LINKEDIN_RANKING_SYSTEM_PROMPT = """\
You are ranking enriched LinkedIn jobs for a candidate. Evaluate three orthogonal dimensions per job, then synthesize a recommendation. Return one ranking object per input job.

## Input schema

- `ranking_profile`: candidate profile with `target` (preferred/acceptable roles and work styles), `candidate_profile` (seniority_preference, strengths, tech_familiarity, weaker_areas), and `preferences` (work_mode, employment_type, salary split into preferred/acceptable/lower_preference_signals)
- `jobs`: array of enriched job objects with metadata and enrichment sections (company_intro, role_scope, requirements, benefits, application_details)

Use only the provided fields. Do not invent facts.

## Dimensions

### role_match — Is this the right type of work?
Scope: domain, function, responsibilities, required skills. Labels: strong | partial | weak
- **strong**: domain, function, and skills closely match the candidate's target roles and strengths
- **partial**: adjacent domain or partial skill overlap
- **weak**: different domain or skill set from what the candidate targets

### level_match — Is the seniority right?
Scope: years of experience, ownership scope, decision authority. Does NOT consider domain or skills. Labels: appropriate | stretch | mismatched
- **appropriate**: requirements align with the candidate's seniority preference
- **stretch**: some requirements exceed the candidate's level but not by a wide margin
- **mismatched**: clearly outside the candidate's seniority preference

Compare JD seniority signals against `seniority_preference.preferred`, `acceptable`, and `avoid`. Rely on concrete evidence (year ranges, scope, authority). Soft leadership language alone should not push level up. Trust explicit numeric ranges unless the rest contradicts them.

### preference_match — Do practical conditions fit?
Scope: work mode, employment type, salary, location. Labels: preferred | acceptable | not_preferred
- Covers ONLY logistics, never seniority or domain
- Missing salary or benefits should not force a low score

## Recommendation

Synthesizes all three dimensions:
- **apply_focus**: role_match=strong, level_match=appropriate, preference_match=preferred or acceptable
- **apply_auto**: acceptable overall but not all dimensions ideal
- **low_priority**: weak role_match, mismatched level, hard blocker, or not worth acting on

## not_applicable_reason

null when plausibly eligible. Non-null only for hard blockers (student-only, work authorization, clear eligibility constraints). One factual sentence.

## Edge cases

- Empty enrichment sections: judge on title + metadata only, note limited information in reason.
- Ambiguous role (e.g. generic "Engineer"): lean toward partial role_match.
- Conflicting seniority signals: use the stronger signal.

## Example

Given a candidate targeting data engineering at junior-to-mid level, with Python/SQL strengths, preferring remote, avoiding senior roles:

Input job: title="Senior Data Platform Engineer", requirements.experience=["5-8 years"], role_scope=["Lead team of 3"], work_mode="remote"

```json
{
  "linkedin_job_id": "example_123",
  "role_match": {"label": "strong", "reason": "Data engineering domain with Python/SQL matches target."},
  "level_match": {"label": "mismatched", "reason": "5-8 year requirement and team lead scope; candidate avoids senior."},
  "preference_match": {"label": "preferred", "reason": "Remote matches preference."},
  "not_applicable_reason": null,
  "recommendation": "low_priority",
  "summary": "Strong domain overlap but seniority exceeds target level."
}
```

Keep reasons short, concrete, and evidence-based. Return JSON matching the schema exactly.
"""


def build_linkedin_ranking_user_payload(
    ranking_config: LinkedInRankingConfig,
    jobs: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "ranking_profile": ranking_config.model_dump(mode="json"),
        "jobs": [
            {
                "linkedin_job_id": job["linkedin_job_id"],
                "job_url": job["job_url"],
                "apply_link": job.get("apply_link"),
                "title": job["title"],
                "company": job["company"],
                "location_text": job.get("location_text"),
                "work_mode": job.get("work_mode"),
                "observed_posted_text": job.get("observed_posted_text"),
                "salary_text": job.get("salary_text"),
                "employment_type": job.get("employment_type"),
                "applicant_count_text": job.get("applicant_count_text"),
                "application_status_text": job.get("application_status_text"),
                "easy_apply": bool(job.get("easy_apply")),
                "company_intro": job.get("company_intro") or [],
                "role_scope": job.get("role_scope") or [],
                "requirements": job.get("requirements") or {},
                "benefits": job.get("benefits") or [],
                "application_details": job.get("application_details") or [],
            }
            for job in jobs
        ],
    }

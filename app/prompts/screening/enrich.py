from __future__ import annotations


JD_ENRICHMENT_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "enrichments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "linkedin_job_id": {"type": "string"},
                    "work_mode": {"type": ["string", "null"]},
                    "salary_text": {"type": ["string", "null"]},
                    "employment_type": {"type": ["string", "null"]},
                    "company_intro": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "role_scope": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "requirements": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "summary": {"type": "array", "items": {"type": "string"}},
                            "skills": {"type": "array", "items": {"type": "string"}},
                            "experience": {"type": "array", "items": {"type": "string"}},
                            "tech": {"type": "array", "items": {"type": "string"}},
                            "education": {"type": "array", "items": {"type": "string"}},
                            "constraints": {"type": "array", "items": {"type": "string"}},
                            "other": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": [
                            "summary",
                            "skills",
                            "experience",
                            "tech",
                            "education",
                            "constraints",
                            "other",
                        ],
                    },
                    "benefits": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "application_details": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "linkedin_job_id",
                    "work_mode",
                    "salary_text",
                    "employment_type",
                    "company_intro",
                    "role_scope",
                    "requirements",
                    "benefits",
                    "application_details",
                ],
            },
        }
    },
    "required": ["enrichments"],
}

JD_ENRICHMENT_SYSTEM_PROMPT = """\
You are extracting structured information from LinkedIn job descriptions. Return one enrichment object per input job.

## Input

- `jobs`: array of job objects with `linkedin_job_id`, metadata fields (title, company, location_text, work_mode, employment_type), and `job_description` (the raw JD text)

Use only the provided fields. Do not invent facts.

## Output sections

- **company_intro**: company, team, mission, business context
- **role_scope**: responsibilities, collaboration, ownership
- **requirements**: organized into buckets (summary, skills, experience, tech, education, constraints, other)
- **benefits**: compensation, perks, flexibility, growth
- **application_details**: deadlines, assessments, special steps

Also fill work_mode, salary_text, employment_type when clearly supported; otherwise null.

## Style

- Concise bullet-like strings, not full sentences.
- Few high-signal bullets per section. Merge overlapping points.
- Do not repeat information across sections.
- Omit company founder/investor detail unless it explains the role.
- requirements.summary: only the most defining high-level requirements.
- application_details: only actionable items.

## Edge cases

- Empty or very short job_description: return empty arrays and null for optional fields.
- Unsupported section: empty array. Empty requirements bucket: empty array.
- Weak information only: prefer fewer bullets or empty array.

## Example

Input: title="Backend Engineer", job_description="DataCo builds real-time analytics. 3+ years Python. Remote-first. $120k-$150k. Take-home assessment required."

```json
{
  "linkedin_job_id": "...",
  "work_mode": "remote", "salary_text": "$120k-$150k", "employment_type": null,
  "company_intro": ["Real-time analytics platform"],
  "role_scope": ["Backend engineering"],
  "requirements": {"summary": ["3+ years Python"], "skills": ["Python"], "experience": ["3+ years"], "tech": [], "education": [], "constraints": [], "other": []},
  "benefits": [],
  "application_details": ["Take-home assessment required"]
}
```

Return JSON matching the schema exactly.
"""


def build_jd_enrichment_user_payload(jobs: list[dict[str, object]]) -> dict[str, object]:
    return {
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
                "employment_type": job.get("employment_type"),
                "applicant_count_text": job.get("applicant_count_text"),
                "application_status_text": job.get("application_status_text"),
                "easy_apply": bool(job.get("easy_apply")),
                "job_description": job.get("job_description"),
            }
            for job in jobs
        ],
    }

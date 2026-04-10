from __future__ import annotations

import re

from app.application.easy_apply.parse import normalize_apply_text
from app.models import LinkedInApplicationQuestion, LinkedInCandidateDossier

# Limits for cover letter context payload to keep LLM token usage reasonable
MAX_EXPERIENCE_BANK_ENTRIES = 4
MAX_EVIDENCE_POINTS_PER_ENTRY = 3
MAX_TRANSFERABLE_SKILLS_PER_ENTRY = 6
MAX_DOMAINS_PER_ENTRY = 4


APPLICATION_QUESTION_MAPPING_SYSTEM_PROMPT = """\
You are answering job application questions from a candidate context. Return one proposal per question.

## Input

- `candidate_context`: subset of candidate dossier, conditionally included by topic:
  - `work_authorization`: work_country, legally_authorized, requires_sponsorship_now/future
  - `standard_answers`: pre-configured answers keyed by topic
  - `application_preferences`: notice_period, desired_salary, willing_to_relocate
  - `education`: highest_degree, currently_enrolled
  - `experience`: years_total, summary, highlights
  - `strengths`, `tech_familiarity`, `constraints`: skill inventory
  - `cover_letter_context` (if detected): professional_identity, experience_bank, etc.
- `questions`: array with `id` (echo as `question_key`), `question`, `answer_type` (yes_no|select_one|numeric|short_text|long_text), `required`, and optional `options`
- `job_context` (optional): title, company, role_scope, requirements, work_mode, employment_type

## Output fields

- `answer_source`: "deterministic" (directly derivable), "llm" (inferred from context), "user_required" (needs human review), "skip" (optional, do not fill)
- `answer_value`: answer string, or null if user_required/skip
- `confidence`: "high" (directly supported), "medium" (reasonable inference), "low" (uncertain)
- `requires_user_input`: true when candidate should review before submission
- `reason`: short factual explanation

## Rules

- Use only the provided candidate context. Do not invent credentials, years, documents, or eligibility.
- yes_no: "Yes" or "No". select_one: exact option string. short_text/long_text/numeric: text to fill.
- Be conservative for legal, authorization, education-status, compensation, criminal-history, or document questions — prefer user_required when uncertain.
- Empty/missing candidate_context for a topic: use user_required.
- select_one with poor option match: requires_user_input=true, pick closest, confidence="low".

## Example

Input: candidate has legally_authorized=true, requires_sponsorship_now=false. Question: "Will you require visa sponsorship?" (yes_no, required)

```json
{"proposals": [{"question_key": "visa", "answer_source": "deterministic", "answer_value": "No", "confidence": "high", "requires_user_input": false, "reason": "Candidate does not require sponsorship."}]}
```

Return JSON matching the schema exactly.
"""


APPLICATION_QUESTION_MAPPING_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "question_key": {"type": "string"},
                    "answer_source": {
                        "type": "string",
                        "enum": ["deterministic", "llm", "user_required", "skip"],
                    },
                    "answer_value": {"type": ["string", "null"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "requires_user_input": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "question_key",
                    "answer_source",
                    "answer_value",
                    "confidence",
                    "requires_user_input",
                    "reason",
                ],
            },
        }
    },
    "required": ["proposals"],
}
OPTION_RESOLVE_SYSTEM_PROMPT = """You are selecting the best matching option from a dropdown list.

Given a target value and a list of available options, return the option string that best matches the target.
If no option is a reasonable match, return null.

Rules:
- Return the exact option string from the list, verbatim — do not paraphrase or abbreviate.
- Prefer semantic meaning over character similarity. "Yes (Work Permit)" is a correct match for target "Yes".
- Return null only when no option is plausible given the target.
"""

OPTION_RESOLVE_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "best_match": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["best_match"],
}


def _compact_candidate_context(
    dossier: LinkedInCandidateDossier,
    questions: list[LinkedInApplicationQuestion],
) -> dict[str, object]:
    labels = " ".join(normalize_apply_text(question.prompt_text) for question in questions)
    payload: dict[str, object] = {}

    def _labels_match_any(*tokens: str) -> bool:
        return any(re.search(rf"\b{re.escape(t)}\b", labels) for t in tokens)

    if _labels_match_any("authorized", "sponsorship", "work permit", "criminal", "conviction"):
        payload["work_authorization"] = {
            "work_country": dossier.work_authorization.work_country,
            "legally_authorized": dossier.work_authorization.legally_authorized,
            "requires_sponsorship_now": dossier.work_authorization.requires_sponsorship_now,
            "requires_sponsorship_future": dossier.work_authorization.requires_sponsorship_future,
        }
        payload["standard_answers"] = dossier.standard_answers

    if _labels_match_any("salary", "notice period", "start date", "how much notice"):
        payload["application_preferences"] = {
            "notice_period": dossier.application_preferences.notice_period,
            "desired_salary": dossier.application_preferences.desired_salary,
            "willing_to_relocate": dossier.application_preferences.willing_to_relocate,
        }

    if _labels_match_any("headline", "summary", "cover letter", "experience", "python", "skill", "years", "saas", "nlp", "llm"):
        payload["education"] = {
            "highest_degree": dossier.education.highest_degree,
            "currently_enrolled": dossier.education.currently_enrolled,
        }
        payload["experience"] = {
            "years_total": dossier.experience.years_total,
            "summary": dossier.experience.summary,
            "highlights": dossier.experience.highlights,
        }
        payload["strengths"] = dossier.strengths
        payload["tech_familiarity"] = dossier.tech_familiarity
        payload["constraints"] = dossier.constraints
        payload["standard_answers"] = dossier.standard_answers

    if _labels_match_any("cover letter") and (dossier.cover_letter_profile.professional_identity or dossier.experience_bank):
        payload["cover_letter_context"] = {
            "professional_identity": dossier.cover_letter_profile.professional_identity,
            "transition_statement": dossier.cover_letter_profile.transition_statement,
            "motivation_themes": dossier.cover_letter_profile.motivation_themes,
            "tone": dossier.cover_letter_profile.tone,
            "experience_bank": [
                {
                    "title": entry.title,
                    "organization": entry.organization,
                    "summary": entry.summary,
                    "evidence_points": entry.evidence_points[:MAX_EVIDENCE_POINTS_PER_ENTRY],
                    "transferable_skills": entry.transferable_skills[:MAX_TRANSFERABLE_SKILLS_PER_ENTRY],
                    "domains": entry.domains[:MAX_DOMAINS_PER_ENTRY],
                }
                for entry in dossier.experience_bank[:MAX_EXPERIENCE_BANK_ENTRIES]
            ],
        }

    return payload


def _answer_type(question: LinkedInApplicationQuestion) -> str:
    options = [normalize_apply_text(option) for option in question.options]
    if options == ["yes", "no"] or options == ["no", "yes"]:
        return "yes_no"
    if question.options:
        return "select_one"
    input_type = normalize_apply_text(question.input_type)
    if input_type in {"numeric", "numeric_text", "number"}:
        return "numeric"
    if input_type in {"textarea", "long_text"}:
        return "long_text"
    return "short_text"


def build_application_question_mapping_user_payload(
    dossier: LinkedInCandidateDossier,
    questions: list[LinkedInApplicationQuestion],
    *,
    job_context: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        "candidate_context": _compact_candidate_context(dossier, questions),
        "questions": [
            {
                "id": question.question_key,
                "question": question.prompt_text,
                "answer_type": _answer_type(question),
                "required": question.required,
                **({"options": question.options} if question.options else {}),
            }
            for question in questions
        ],
    }
    if job_context:
        payload["job_context"] = {
            key: value
            for key, value in job_context.items()
            if key in {"title", "company", "role_scope", "requirements", "work_mode", "employment_type"}
        }
    return payload



# models

Pydantic data contracts shared across the entire pipeline. No business logic — only structure, validation, and serialization.

## Files

| File | What it defines |
|---|---|
| `job.py` | `LinkedInJobCard`, `LinkedInJobRequirements`, `LinkedInRawCard` — core job posting data |
| `candidate.py` | `LinkedInCandidateDossier` and nested profiles (contact, experience, education, work authorization, cover letter, documents, links, preferences) |
| `application.py` | Form-level models for Easy Apply: form steps, elements, constraints, questions, answer proposals, actions |
| `screening.py` | LLM output models for title triage decisions and ranking results |
| `email.py` | `LinkedInRawEmailMessage`, `LinkedInApplicationConfirmation` — email ingestion schemas |
| `linkedin_config.py` | User/system config models: connection, source, email, title triage, ranking (with validation) |
| `linkedin_result.py` | Composite result types returned by source/connection stages (wrap job data + metadata) |
| `interfaces.py` | Abstract base classes (`JobSource`, `ApplicationAgent`, `DocumentAgent`) for pluggable components |

## Convention

- Every model is a `pydantic.BaseModel` with explicit field types.
- `__init__.py` re-exports all public models for convenience (`from app.models import LinkedInJobCard`).
- Config models use Pydantic validators for cross-field rules (e.g. keyword search requires `keywords`).

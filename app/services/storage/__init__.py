from app.services.storage.applications import (
    create_job_application,
    get_or_create_job_application,
    load_ranked_easy_apply_jobs,
    load_application_questions,
    load_job_application,
    load_submitted_pending_applications,
    mark_job_as_applied_from_confirmation,
    mark_job_as_applied_from_confirmation_email,
    replace_application_questions,
    update_application_question_answer,
    update_job_application_status,
)
from app.services.storage.db import SQLiteConfig, connect_sqlite, initialize_schema, resolve_db_path
from app.services.storage.email_confirmations import (
    build_confirmation_dedupe_key,
    process_confirmation_emails,
)
from app.services.storage.job_details import (
    load_triaged_jobs_for_detail_fetch,
    save_job_details,
)
from app.services.storage.enrichment import (
    load_detailed_jobs_for_enrichment,
    save_job_enrichments,
)
from app.services.storage.jobs import persist_linkedin_job_cards
from app.services.storage.ranking import load_enriched_jobs_for_ranking, save_job_rankings
from app.services.storage.title_triage import load_discovered_jobs, save_title_triage_results

__all__ = [
    "SQLiteConfig",
    "build_confirmation_dedupe_key",
    "connect_sqlite",
    "create_job_application",
    "get_or_create_job_application",
    "initialize_schema",
    "load_application_questions",
    "load_detailed_jobs_for_enrichment",
    "load_discovered_jobs",
    "load_enriched_jobs_for_ranking",
    "load_job_application",
    "load_ranked_easy_apply_jobs",
    "load_submitted_pending_applications",
    "load_triaged_jobs_for_detail_fetch",
    "mark_job_as_applied_from_confirmation",
    "mark_job_as_applied_from_confirmation_email",
    "persist_linkedin_job_cards",
    "process_confirmation_emails",
    "replace_application_questions",
    "resolve_db_path",
    "save_job_details",
    "save_job_enrichments",
    "save_job_rankings",
    "save_title_triage_results",
    "update_application_question_answer",
    "update_job_application_status",
]

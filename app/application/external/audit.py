from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse


ADAPTER_CANDIDATE_PROVIDERS = {
    "ashby",
    "avature",
    "eightfold",
    "greenhouse",
    "icims",
    "lever",
    "phenom",
    "recruitee",
    "workable",
    "workday",
}


def extract_apply_host(apply_link: str | None) -> str | None:
    if not apply_link:
        return None
    parsed = urlparse(apply_link)
    host = (parsed.netloc or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def infer_external_apply_provider(apply_link: str | None) -> str:
    if not apply_link:
        return "unknown"

    parsed = urlparse(apply_link)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()

    if "linkedin.com" in host:
        return "linkedin"
    if "ashbyhq.com" in host:
        return "ashby"
    if "greenhouse.io" in host or "grnh.se" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "workable.com" in host:
        return "workable"
    if "eightfold.ai" in host:
        return "eightfold"
    if "myworkdayjobs.com" in host or host.startswith("workday.") or ".wd" in host:
        return "workday"
    if "icims.com" in host:
        return "icims"
    if "avature.net" in host:
        return "avature"
    if "recruitee.com" in host:
        return "recruitee"
    if "getro.com" in host:
        return "getro"
    if "amazon.jobs" in host:
        return "amazon_jobs"
    if "careers.google.com" in host or ("google.com" in host and "/jobs/results/" in path):
        return "google_jobs"
    if "dataannotation.tech" in host:
        return "dataannotation"
    if "apexsystems.com" in host:
        return "apexsystems"
    if "boardy.ai" in host:
        return "boardy"
    if "mercor.com" in host:
        return "mercor"
    if "phenom-feeds" in query or "/global/en/job/" in path:
        return "phenom"
    if host.startswith("careers.") or host.startswith("jobs."):
        return "company_careers"
    return "unknown"


def _host_category(provider: str, host: str | None) -> str:
    if provider in ADAPTER_CANDIDATE_PROVIDERS:
        return "ats_platform"
    if provider in {"amazon_jobs", "google_jobs", "dataannotation", "apexsystems", "boardy", "mercor"}:
        return "company_or_marketplace"
    if provider in {"company_careers", "getro", "unknown"}:
        return "custom_or_unknown"
    if provider == "linkedin":
        return "linkedin"
    return "custom_or_unknown"


def _recommended_mode(provider: str, provider_count: int) -> str:
    if provider in ADAPTER_CANDIDATE_PROVIDERS and provider_count >= 2:
        return "adapter_candidate"
    if provider in ADAPTER_CANDIDATE_PROVIDERS:
        return "adapter_candidate_low_volume"
    if provider in {"company_careers", "getro", "unknown"}:
        return "agent_or_manual"
    return "manual_or_agent"


def _value_known_from_url_only(field_name: str) -> str:
    if field_name in {"provider", "domain", "host_category", "recommended_mode"}:
        return "derived"
    return "unknown"


def build_external_apply_audit_rows(jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    provider_counts = Counter(
        infer_external_apply_provider(str(job.get("apply_link") or ""))
        for job in jobs
    )

    rows: list[dict[str, object]] = []
    for job in jobs:
        apply_link = str(job.get("apply_link") or "")
        host = extract_apply_host(apply_link)
        provider = infer_external_apply_provider(apply_link)
        rows.append(
            {
                "job_id": job.get("job_id"),
                "linkedin_job_id": job.get("linkedin_job_id"),
                "title": job.get("title"),
                "company": job.get("company"),
                "apply_link": apply_link,
                "domain": host,
                "provider": provider,
                "host_category": _host_category(provider, host),
                "recommendation": job.get("recommendation"),
                "stage": job.get("stage"),
                "public_form_access": "unknown",
                "requires_login_before_form_access": "unknown",
                "requires_account_creation": "unknown",
                "requires_email_or_otp_verification": "unknown",
                "captcha_present": "unknown",
                "has_file_upload": "unknown",
                "has_resume_parsing": "unknown",
                "has_dynamic_questions": "unknown",
                "has_review_step": "unknown",
                "has_success_page": "unknown",
                "confirmation_email_recognizable": "unknown",
                "evidence_source": ["stored_apply_link", "stored_job_row"],
                "recommended_mode": _recommended_mode(provider, provider_counts[provider]),
            }
        )
    return rows


def summarize_external_apply_audit(rows: list[dict[str, object]]) -> dict[str, object]:
    domain_counts = Counter(row["domain"] for row in rows if row.get("domain"))
    provider_counts = Counter(row["provider"] for row in rows if row.get("provider"))
    recommended_mode_counts = Counter(row["recommended_mode"] for row in rows if row.get("recommended_mode"))

    adapter_candidate_providers = [
        {"provider": provider, "count": count}
        for provider, count in provider_counts.most_common()
        if provider in ADAPTER_CANDIDATE_PROVIDERS and count >= 2
    ]

    unknown_fields = [
        "public_form_access",
        "requires_login_before_form_access",
        "requires_account_creation",
        "requires_email_or_otp_verification",
        "captcha_present",
        "has_file_upload",
        "has_resume_parsing",
        "has_dynamic_questions",
        "has_review_step",
        "has_success_page",
        "confirmation_email_recognizable",
    ]

    return {
        "external_job_count": len(rows),
        "provider_counts": [
            {"provider": provider, "count": count}
            for provider, count in provider_counts.most_common()
        ],
        "domain_counts": [
            {"domain": domain, "count": count}
            for domain, count in domain_counts.most_common()
        ],
        "recommended_mode_counts": [
            {"recommended_mode": mode, "count": count}
            for mode, count in recommended_mode_counts.most_common()
        ],
        "adapter_candidate_providers": adapter_candidate_providers,
        "unknown_live_probe_fields": [
            {
                "field": field_name,
                "known_from_url_only": _value_known_from_url_only(field_name),
            }
            for field_name in unknown_fields
        ],
    }

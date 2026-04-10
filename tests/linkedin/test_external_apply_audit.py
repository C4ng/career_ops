from __future__ import annotations

from app.application.external.audit import (
    build_external_apply_audit_rows,
    infer_external_apply_provider,
    summarize_external_apply_audit,
)


def test_infer_external_apply_provider_recognizes_common_ats_hosts() -> None:
    assert infer_external_apply_provider("https://jobs.ashbyhq.com/company/123") == "ashby"
    assert infer_external_apply_provider("https://job-boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert infer_external_apply_provider("https://grnh.se/abc123") == "greenhouse"
    assert infer_external_apply_provider("https://apply.workable.com/acme/j/123") == "workable"
    assert infer_external_apply_provider("https://elementfleet.wd3.myworkdayjobs.com/job/123") == "workday"
    assert infer_external_apply_provider("https://careers-kinaxis.icims.com/jobs/34480/job") == "icims"


def test_infer_external_apply_provider_recognizes_phenom_style_custom_domains() -> None:
    url = "https://careers.bcg.com/global/en/job/BCG1US123?utm_medium=phenom-feeds"
    assert infer_external_apply_provider(url) == "phenom"


def test_external_apply_audit_summary_counts_adapter_candidates() -> None:
    jobs = [
        {
            "job_id": 1,
            "linkedin_job_id": "1",
            "title": "AI Engineer",
            "company": "A",
            "apply_link": "https://job-boards.greenhouse.io/acme/jobs/1",
            "stage": "ranked",
            "recommendation": "apply_auto",
        },
        {
            "job_id": 2,
            "linkedin_job_id": "2",
            "title": "ML Engineer",
            "company": "B",
            "apply_link": "https://job-boards.greenhouse.io/acme/jobs/2",
            "stage": "ranked",
            "recommendation": "apply_focus",
        },
        {
            "job_id": 3,
            "linkedin_job_id": "3",
            "title": "Applied Scientist",
            "company": "C",
            "apply_link": "https://www.boardy.ai/partners?talent",
            "stage": "enriched",
            "recommendation": None,
        },
    ]

    rows = build_external_apply_audit_rows(jobs)
    summary = summarize_external_apply_audit(rows)

    assert summary["external_job_count"] == 3
    assert {"provider": "greenhouse", "count": 2} in summary["provider_counts"]
    assert {"provider": "greenhouse", "count": 2} in summary["adapter_candidate_providers"]

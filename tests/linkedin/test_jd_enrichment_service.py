from __future__ import annotations

from app.screening import enrich_linkedin_job_descriptions
from app.services.llm.config import JDEnrichmentLLMConfig


def test_enrich_linkedin_job_descriptions_validates_structured_output(monkeypatch) -> None:
    llm_config = JDEnrichmentLLMConfig(model="gpt-5-mini")
    jobs = [
        {
            "job_id": 1,
            "linkedin_job_id": "123",
            "job_url": "https://www.linkedin.com/jobs/view/123/",
            "apply_link": "https://example.com/apply",
            "title": "AI Engineer",
            "company": "Example",
            "location_text": "Toronto, ON",
            "work_mode": "hybrid",
            "observed_posted_text": "2 days ago",
            "employment_type": "Full-time",
            "applicant_count_text": "Over 100 applicants",
            "application_status_text": None,
            "easy_apply": False,
            "job_description": "Build agent systems with Python and LLMs.",
        }
    ]

    captured: dict[str, object] = {}

    def fake_request(*args, **kwargs):
        captured["user_payload"] = kwargs["user_payload"]
        captured["schema_name"] = kwargs["schema_name"]
        return (
            {},
            {
                "choices": [
                    {
                        "message": {
                            "content": """{"enrichments":[{"linkedin_job_id":"123","work_mode":"hybrid","salary_text":"$140,000-$170,000 CAD","employment_type":"Full-time","company_intro":["AI company"],"role_scope":["Build agent systems"],"requirements":{"summary":["Applied AI role"],"skills":["Python","LLMs"],"experience":["Production software experience"],"tech":["PyTorch"],"education":[],"constraints":[],"other":[]},"benefits":["Flexible work"],"application_details":["Applications reviewed on a rolling basis"]}]}"""
                        }
                    }
                ]
            },
            """{"enrichments":[{"linkedin_job_id":"123","work_mode":"hybrid","salary_text":"$140,000-$170,000 CAD","employment_type":"Full-time","company_intro":["AI company"],"role_scope":["Build agent systems"],"requirements":{"summary":["Applied AI role"],"skills":["Python","LLMs"],"experience":["Production software experience"],"tech":["PyTorch"],"education":[],"constraints":[],"other":[]},"benefits":["Flexible work"],"application_details":["Applications reviewed on a rolling basis"]}]}""",
        )

    monkeypatch.setattr("app.screening.enrich.request_structured_chat_completion", fake_request)

    enrichments = enrich_linkedin_job_descriptions(llm_config, jobs)

    assert len(enrichments) == 1
    assert enrichments[0]["linkedin_job_id"] == "123"
    assert enrichments[0]["work_mode"] == "hybrid"
    assert enrichments[0]["salary_text"] == "$140,000-$170,000 CAD"
    assert enrichments[0]["employment_type"] == "Full-time"
    assert enrichments[0]["requirements"]["skills"] == ["Python", "LLMs"]
    assert captured["schema_name"] == "linkedin_jd_enrichment_batch"
    assert captured["user_payload"]["jobs"][0]["job_description"] == "Build agent systems with Python and LLMs."

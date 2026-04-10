from __future__ import annotations

from app.models import LinkedInRankingConfig
from app.services.llm.config import RankingLLMConfig
from app.screening import rank_linkedin_jobs


def test_rank_linkedin_jobs_validates_structured_output(monkeypatch) -> None:
    llm_config = RankingLLMConfig(model="gpt-5-mini")
    ranking_config = LinkedInRankingConfig.model_validate(
        {
            "profile_version": "v1",
            "target": {
                "preferred_roles": ["Applied AI Engineer"],
                "acceptable_roles": ["Software Engineer with explicit AI/ML cue"],
                "preferred_work_styles": ["agent_system_building"],
                "acceptable_work_styles": ["pure_research"],
            },
            "candidate_profile": {
                "seniority_preference": {
                    "preferred": ["entry", "junior"],
                    "acceptable": ["mid"],
                    "avoid": ["senior"],
                },
                "strengths": ["Python", "LLM applications"],
                "tech_familiarity": ["PyTorch"],
                "weaker_areas": ["very senior production ownership"],
            },
            "preferences": {
                "preferred": {"work_mode": ["remote"], "employment_type": ["full-time"]},
                "acceptable": {"work_mode": ["hybrid_toronto"], "employment_type": ["contract"]},
                "lower_preference_signals": ["very busy environment"],
            },
        }
    )
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
            "salary_text": "$140,000-$170,000 CAD",
            "employment_type": "Full-time",
            "applicant_count_text": "Over 100 applicants",
            "application_status_text": None,
            "easy_apply": False,
            "company_intro": ["AI company"],
            "role_scope": ["Build agent systems"],
            "requirements": {
                "summary": [],
                "skills": ["Python"],
                "experience": [],
                "tech": ["PyTorch"],
                "education": [],
                "constraints": [],
                "other": [],
            },
            "benefits": ["Flexible work"],
            "application_details": [],
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
                            "content": """{"rankings":[{"linkedin_job_id":"123","role_match":{"label":"strong","reason":"Strong applied AI scope."},"level_match":{"label":"stretch","reason":"Some stretch on years of experience."},"preference_match":{"label":"acceptable","reason":"Hybrid Toronto full-time is acceptable."},"not_applicable_reason":null,"recommendation":"apply_auto","summary":"Strong domain fit with slight experience stretch."}]}"""
                        }
                    }
                ]
            },
            """{"rankings":[{"linkedin_job_id":"123","role_match":{"label":"strong","reason":"Strong applied AI scope."},"level_match":{"label":"stretch","reason":"Some stretch on years of experience."},"preference_match":{"label":"acceptable","reason":"Hybrid Toronto full-time is acceptable."},"not_applicable_reason":null,"recommendation":"apply_auto","summary":"Strong domain fit with slight experience stretch."}]}""",
        )

    monkeypatch.setattr("app.screening.rank.request_structured_chat_completion", fake_request)

    rankings = rank_linkedin_jobs(llm_config, ranking_config, jobs)

    assert len(rankings) == 1
    assert rankings[0].linkedin_job_id == "123"
    assert rankings[0].role_match.label == "strong"
    assert rankings[0].level_match.label == "stretch"
    assert rankings[0].not_applicable_reason is None
    assert rankings[0].recommendation == "apply_auto"
    assert captured["schema_name"] == "linkedin_job_ranking_batch"
    assert "job_description" not in captured["user_payload"]["jobs"][0]

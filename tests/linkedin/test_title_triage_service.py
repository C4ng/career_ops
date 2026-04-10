from __future__ import annotations

from app.models import (
    LinkedInTitleTriageCandidate,
    LinkedInTitleTriageConfig,
)
from app.services.llm.config import TitleTriageLLMConfig
from app.screening import triage_linkedin_job_titles


def test_triage_linkedin_job_titles_validates_structured_output(monkeypatch) -> None:
    llm_config = TitleTriageLLMConfig(model="gpt-5-mini")
    triage_config = LinkedInTitleTriageConfig(
        goal="Triage LinkedIn titles",
        role_intent={
            "applied_ai_engineering": "Build AI systems in products.",
            "research_and_modeling": "Work on models, inference, and research.",
        },
        wanted_roles=["Machine Learning Engineer"],
        wanted_technical_cues=["llm"],
        decision_rules=["Prefer keep when uncertain."],
        strong_keep_patterns=["Titles with explicit AI cues should usually be kept."],
        discard_patterns=["Discard broad software titles without AI cues."],
        location_policy=["Remote is acceptable anywhere."],
        important_examples={
            "keep": ["Member of Technical Staff, AI Models Research"],
            "discard": ["Backend Engineer"],
        },
    )
    candidates = [
        LinkedInTitleTriageCandidate(
            job_id=1,
            linkedin_job_id="123",
            title="LLM Engineer",
            company="Example",
            location_text="Canada (Remote)",
            work_mode="remote",
        )
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
                            "content": '{"decisions":[{"linkedin_job_id":"123","decision":"keep","reason":"Explicit LLM title and remote is acceptable."}]}'
                        }
                    }
                ]
            },
            '{"decisions":[{"linkedin_job_id":"123","decision":"keep","reason":"Explicit LLM title and remote is acceptable."}]}',
        )

    monkeypatch.setattr("app.screening.filter.request_structured_chat_completion", fake_request)

    decisions = triage_linkedin_job_titles(llm_config, triage_config, candidates)

    assert len(decisions) == 1
    assert decisions[0].linkedin_job_id == "123"
    assert decisions[0].decision == "keep"
    assert captured["schema_name"] == "linkedin_title_triage_batch"
    assert captured["user_payload"]["triage_config"]["role_intent"]["applied_ai_engineering"] == "Build AI systems in products."
    assert captured["user_payload"]["triage_config"]["strong_keep_patterns"] == ["Titles with explicit AI cues should usually be kept."]
    assert captured["user_payload"]["triage_config"]["discard_patterns"] == ["Discard broad software titles without AI cues."]
    assert captured["user_payload"]["triage_config"]["important_examples"]["keep"] == ["Member of Technical Staff, AI Models Research"]

from __future__ import annotations

from app.application.easy_apply.answers import (
    map_questions_with_llm as map_easy_apply_questions_with_llm,
    resolve_questions_from_dossier as resolve_easy_apply_questions_from_dossier,
)
from app.models import (
    LinkedInApplicationQuestion,
    LinkedInCandidateDossier,
)
from app.services.llm.config import ApplicationQuestionMappingLLMConfig


def test_map_easy_apply_questions_with_llm_validates_structured_output(monkeypatch) -> None:
    llm_config = ApplicationQuestionMappingLLMConfig(model="gpt-5-mini")
    dossier = LinkedInCandidateDossier()
    dossier.work_authorization.legally_authorized = True
    dossier.standard_answers["canada_work_authorization_status"] = "Yes (Work Permit)"
    questions = [
        LinkedInApplicationQuestion(
            question_key="visa_sponsorship",
            prompt_text="Will you now or in the future require visa sponsorship?",
            input_type="yes_no",
            required=True,
            options=["Yes", "No"],
        )
    ]

    captured: dict[str, object] = {}

    def fake_request(*args, **kwargs):
        captured["schema_name"] = kwargs["schema_name"]
        captured["user_payload"] = kwargs["user_payload"]
        return (
            {},
            {
                "choices": [
                    {
                        "message": {
                            "content": """{"proposals":[{"question_key":"visa_sponsorship","answer_source":"llm","answer_value":"No","confidence":"high","requires_user_input":false,"reason":"The dossier says the candidate does not require sponsorship."}]}"""
                        }
                    }
                ]
            },
            """{"proposals":[{"question_key":"visa_sponsorship","answer_source":"llm","answer_value":"No","confidence":"high","requires_user_input":false,"reason":"The dossier says the candidate does not require sponsorship."}]}""",
        )

    monkeypatch.setattr("app.application.easy_apply.answers.request_structured_chat_completion", fake_request)

    proposals = map_easy_apply_questions_with_llm(llm_config, dossier, questions)

    assert len(proposals) == 1
    assert proposals[0].question_key == "visa_sponsorship"
    assert proposals[0].answer_value == "No"
    assert captured["schema_name"] == "job_application_question_mapping"
    assert captured["user_payload"]["questions"][0]["question"] == questions[0].prompt_text
    assert captured["user_payload"]["questions"][0]["answer_type"] == "yes_no"


def test_resolve_easy_apply_questions_from_dossier_does_not_hardcode_screening_question_keywords() -> None:
    dossier = LinkedInCandidateDossier()
    dossier.standard_answers["english_proficiency"] = "Professional"
    questions = [
        LinkedInApplicationQuestion(
            question_key="english_proficiency",
            prompt_text="What is your level of proficiency in English?",
            input_type="select_one",
            required=True,
            options=["None", "Conversational", "Professional", "Native or bilingual"],
        )
    ]

    resolved, unresolved = resolve_easy_apply_questions_from_dossier(dossier, questions)

    assert resolved == []
    assert unresolved == questions


def test_map_easy_apply_questions_with_llm_uses_llm_for_screening_questions_even_when_standard_answers_exist(monkeypatch) -> None:
    llm_config = ApplicationQuestionMappingLLMConfig(model="gpt-5-mini")
    dossier = LinkedInCandidateDossier()
    dossier.standard_answers["english_proficiency"] = "Professional"
    questions = [
        LinkedInApplicationQuestion(
            question_key="english_proficiency",
            prompt_text="What is your level of proficiency in English?",
            input_type="select_one",
            required=True,
            options=["None", "Conversational", "Professional", "Native or bilingual"],
        )
    ]

    def fake_request(*args, **kwargs):
        return (
            {},
            {
                "choices": [
                    {
                        "message": {
                            "content": """{"proposals":[{"question_key":"english_proficiency","answer_source":"llm","answer_value":"Professional","confidence":"high","requires_user_input":false,"reason":"The candidate dossier standard answers specify Professional English proficiency."}]}"""
                        }
                    }
                ]
            },
            """{"proposals":[{"question_key":"english_proficiency","answer_source":"llm","answer_value":"Professional","confidence":"high","requires_user_input":false,"reason":"The candidate dossier standard answers specify Professional English proficiency."}]}""",
        )

    monkeypatch.setattr("app.application.easy_apply.answers.request_structured_chat_completion", fake_request)

    proposals = map_easy_apply_questions_with_llm(llm_config, dossier, questions)

    assert len(proposals) == 1
    assert proposals[0].answer_value == "Professional"
    assert proposals[0].answer_source == "llm"

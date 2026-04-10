from __future__ import annotations

from app.application.easy_apply.fill import resolve_option_with_llm
from app.application.easy_apply.parse import _coerce_form_elements
from app.application.easy_apply.classify import collect_preview_questions_from_step
from app.application.easy_apply.classify import propose_preview_fill_action
from app.models import LinkedInApplicationFormStep, LinkedInCandidateDossier
from app.services.llm.config import ApplicationQuestionMappingLLMConfig


def test_coerce_form_elements_marks_numeric_text_when_validation_requires_number() -> None:
    elements = _coerce_form_elements(
        [
            {
                "element_id": "salary_expectations",
                "label": "What are your salary expectations for the role?",
                "control_type": "text",
                "required": True,
                "current_value": None,
                "options": [],
                "options_count": 0,
                "suggestions": [],
                "html_type": "text",
                "input_mode": "decimal",
                "pattern": None,
                "placeholder": None,
                "validation_message": "Enter a decimal number",
                "field_name": "salary",
                "field_id": "salary-input",
            }
        ]
    )

    assert len(elements) == 1
    assert elements[0].control_type == "numeric_text"
    assert elements[0].required is True
    assert elements[0].constraints.input_mode == "decimal"


def test_coerce_form_elements_normalizes_duplicated_labels() -> None:
    elements = _coerce_form_elements(
        [
            {
                "element_id": "email",
                "label": "Email addressEmail address",
                "control_type": "select",
                "required": True,
                "current_value": "user@example.com",
                "options": ["user@example.com"],
                "options_count": 1,
                "suggestions": [],
                "html_type": "select",
                "input_mode": None,
                "pattern": None,
                "placeholder": None,
                "validation_message": None,
                "field_name": "email",
                "field_id": "email-input",
            }
        ]
    )

    assert elements[0].label == "Email address"


def test_coerce_form_elements_normalizes_repeated_question_sentence() -> None:
    elements = _coerce_form_elements(
        [
            {
                "element_id": "custom_ai_models",
                "label": "Do you have hands on experience with training custom AI models? Do you have hands on experience with training custom AI models?",
                "control_type": "select",
                "required": True,
                "current_value": None,
                "options": ["Yes", "No"],
                "options_count": 2,
                "suggestions": [],
                "html_type": "select",
                "input_mode": None,
                "pattern": None,
                "placeholder": None,
                "validation_message": None,
                "field_name": "custom_ai_models",
                "field_id": "custom-ai-models",
            }
        ]
    )

    assert elements[0].label == "Do you have hands on experience with training custom AI models?"


def test_probe_action_for_required_typeahead_uses_candidate_city() -> None:
    dossier = LinkedInCandidateDossier()
    dossier.contact.city = "Toronto"
    element = _coerce_form_elements(
        [
            {
                "element_id": "location_city",
                "label": "Location (city)",
                "control_type": "typeahead",
                "required": True,
                "current_value": None,
                "options": [],
                "options_count": 0,
                "suggestions": [],
                "html_type": "text",
                "input_mode": None,
                "pattern": None,
                "placeholder": None,
                "validation_message": None,
                "field_name": "location",
                "field_id": "location-input",
            }
        ]
    )[0]

    action = propose_preview_fill_action(dossier, element)

    assert action is not None
    assert action.action_type == "select_suggestion"
    assert action.target_value == "Toronto"


def test_probe_action_for_required_radio_group_picks_visible_option() -> None:
    dossier = LinkedInCandidateDossier()
    element = _coerce_form_elements(
        [
            {
                "element_id": "work_auth",
                "label": "Are you legally authorized to work in Canada?",
                "control_type": "radio_group",
                "required": True,
                "current_value": None,
                "options": ["No", "Yes (Canadian Citizen)", "Yes (Permanent Resident)", "Yes (Work Permit)"],
                "options_count": 4,
                "suggestions": [],
                "html_type": "radio",
                "input_mode": None,
                "pattern": None,
                "placeholder": None,
                "validation_message": None,
                "field_name": "work_auth",
                "field_id": "work-auth-input",
            }
        ]
    )[0]

    action = propose_preview_fill_action(dossier, element)

    assert action is not None
    assert action.action_type == "choose_option"
    assert action.target_value == "Yes (Work Permit)"


def test_probe_action_for_required_numeric_text_uses_numeric_dummy() -> None:
    dossier = LinkedInCandidateDossier()
    element = _coerce_form_elements(
        [
            {
                "element_id": "salary_expectations",
                "label": "Salary expectations",
                "control_type": "numeric_text",
                "required": True,
                "current_value": None,
                "options": [],
                "options_count": 0,
                "suggestions": [],
                "html_type": "text",
                "input_mode": "decimal",
                "pattern": None,
                "placeholder": None,
                "validation_message": "Enter a decimal number",
                "field_name": "salary",
                "field_id": "salary-input",
            }
        ]
    )[0]

    action = propose_preview_fill_action(dossier, element)

    assert action is not None
    assert action.action_type == "set_text"
    assert action.target_value == "1"


def test_probe_action_for_saas_numeric_text_uses_constraint_aware_preview_value() -> None:
    dossier = LinkedInCandidateDossier()
    element = _coerce_form_elements(
        [
            {
                "element_id": "saas_years",
                "label": "How many years of work experience do you have with Software as a Service (SaaS)?",
                "control_type": "numeric_text",
                "required": True,
                "current_value": None,
                "options": [],
                "options_count": 0,
                "suggestions": [],
                "html_type": "text",
                "input_mode": "decimal",
                "pattern": None,
                "placeholder": None,
                "validation_message": "Enter a whole number between 0 and 99",
                "field_name": "saas",
                "field_id": "saas-input",
            }
        ]
    )[0]

    action = propose_preview_fill_action(dossier, element)

    assert action is not None
    assert action.action_type == "set_text"
    assert action.target_value == "0"


def test_resolve_option_with_llm_returns_best_match(monkeypatch) -> None:
    llm_config = ApplicationQuestionMappingLLMConfig(model="gpt-5-mini")
    candidates = [
        "Toronto, Ontario, Canada",
        "Toronto, Ohio, United States",
        "Greater Toronto and Hamilton Area, Ontario, Canada",
    ]

    def fake_request(*args, **kwargs):
        return ({}, {}, '{"best_match": "Toronto, Ontario, Canada"}')

    monkeypatch.setattr("app.application.easy_apply.fill.request_structured_chat_completion", fake_request)

    result = resolve_option_with_llm(llm_config, "Toronto, Canada", candidates)
    assert result == "Toronto, Ontario, Canada"


def test_probe_action_for_required_radio_group_uses_option_label() -> None:
    dossier = LinkedInCandidateDossier()
    element = _coerce_form_elements(
        [
            {
                "element_id": "question_python_stack",
                "label": "Experience with Python data stack",
                "control_type": "radio_group",
                "required": True,
                "current_value": None,
                "options": ["Yes", "No"],
                "options_count": 2,
                "suggestions": [],
                "html_type": "radio",
                "input_mode": None,
                "pattern": None,
                "placeholder": None,
                "validation_message": None,
                "field_name": "experience_python_stack",
                "field_id": "experience_python_stack-0",
            }
        ]
    )[0]

    action = propose_preview_fill_action(dossier, element)

    assert action is not None
    assert action.action_type == "choose_option"
    assert action.target_value == "Yes"


def test_collect_preview_questions_from_step_omits_satisfied_fields() -> None:
    step = LinkedInApplicationFormStep(
        step_title="Apply to Test",
        progress_percent=17,
        primary_action_label="Next",
        page_url="https://www.linkedin.com/jobs/view/123/apply",
        elements=_coerce_form_elements(
            [
                {
                    "element_id": "email",
                    "label": "Email address",
                    "control_type": "select",
                    "required": True,
                    "current_value": "user@example.com",
                    "options": ["user@example.com"],
                    "options_count": 1,
                    "suggestions": [],
                    "html_type": "select",
                    "input_mode": None,
                    "pattern": None,
                    "placeholder": None,
                    "validation_message": None,
                    "field_name": "email",
                    "field_id": "email-input",
                },
                {
                    "element_id": "salary",
                    "label": "What are your salary expectations for the role?",
                    "control_type": "numeric_text",
                    "required": True,
                    "current_value": None,
                    "options": [],
                    "options_count": 0,
                    "suggestions": [],
                    "html_type": "text",
                    "input_mode": "decimal",
                    "pattern": None,
                    "placeholder": None,
                    "validation_message": "Enter a decimal number",
                    "field_name": "salary",
                    "field_id": "salary-input",
                },
                {
                    "element_id": "headline",
                    "label": "Headline",
                    "control_type": "text",
                    "required": False,
                    "current_value": None,
                    "options": [],
                    "options_count": 0,
                    "suggestions": [],
                    "html_type": "text",
                    "input_mode": "text",
                    "pattern": None,
                    "placeholder": None,
                    "validation_message": None,
                    "field_name": "headline",
                    "field_id": "headline-input",
                },
            ]
        ),
    )

    questions = collect_preview_questions_from_step(step)

    assert [question.question_key for question in questions] == ["salary", "headline"]
    assert questions[0].input_type == "numeric"
    assert questions[1].input_type == "short_text"


def test_coerce_form_elements_strips_placeholder_option_values() -> None:
    elements = _coerce_form_elements(
        [
            {
                "element_id": "custom_ai_models",
                "label": "Do you have hands on experience with training custom AI models?",
                "control_type": "select",
                "required": True,
                "current_value": "Select an option",
                "options": ["Select an option", "Yes", "No"],
                "options_count": 3,
                "suggestions": [],
                "html_type": "select",
                "input_mode": None,
                "pattern": None,
                "placeholder": None,
                "validation_message": "Please enter a valid answer",
                "field_name": "custom_ai_models",
                "field_id": "custom-ai-models",
            }
        ]
    )

    assert elements[0].options == ["Yes", "No"]

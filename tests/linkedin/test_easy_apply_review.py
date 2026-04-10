from __future__ import annotations

from app.application.easy_apply import review
from app.models import LinkedInApplicationFormStep


class _FakePage:
    pass


def test_apply_review_overrides_does_not_submit_with_pending_overrides(monkeypatch) -> None:
    submit_clicked = {"value": False}

    monkeypatch.setattr(
        review,
        "extract_easy_apply_form_step",
        lambda _page: LinkedInApplicationFormStep(
            step_title="Review your application",
            progress_percent=100,
            primary_action_label="Submit application",
            secondary_action_labels=["Back"],
            elements=[],
            record_lists=[],
            page_url="https://www.linkedin.com/jobs/view/123/apply/",
        ),
    )
    monkeypatch.setattr(review, "_open_matching_edit_section", lambda *args, **kwargs: False)
    monkeypatch.setattr(review, "_click_back", lambda *args, **kwargs: False)

    def _record_submit(*args, **kwargs):
        submit_clicked["value"] = True
        return "Submit application"

    monkeypatch.setattr(review, "_click_primary", _record_submit)

    result = review.apply_review_overrides_in_open_modal(
        _FakePage(),
        question_rows=[
            {
                "question_key": "english_proficiency",
                "prompt_text": "What is your level of proficiency in English?",
                "field_name": "englishProficiency",
                "field_id": "english-proficiency-select",
            }
        ],
        overrides={"english_proficiency": "Professional"},
        submit=True,
    )

    assert result["status"] == "submit_blocked_pending_overrides"
    assert result["pending_overrides"] == {"english_proficiency": "Professional"}
    assert submit_clicked["value"] is False


def test_infer_review_section_labels_routes_screening_question_to_additional_questions() -> None:
    labels = review._infer_review_section_labels(
        {
            "question_key": "english_proficiency",
            "prompt_text": "What is your level of proficiency in English?",
            "input_type": "select_one",
        }
    )

    assert labels == ["Additional Questions"]


def test_apply_review_overrides_reports_submit_not_confirmed_when_no_success_signal(monkeypatch) -> None:
    submit_clicked = {"value": False}

    monkeypatch.setattr(
        review,
        "extract_easy_apply_form_step",
        lambda _page: LinkedInApplicationFormStep(
            step_title="Review your application",
            progress_percent=100,
            primary_action_label="Submit application",
            secondary_action_labels=["Back"],
            elements=[],
            record_lists=[],
            page_url="https://www.linkedin.com/jobs/view/123/apply/",
        ),
    )

    def _record_submit(*args, **kwargs):
        submit_clicked["value"] = True
        return "Submit application"

    monkeypatch.setattr(review, "_click_primary", _record_submit)
    monkeypatch.setattr(review, "_wait_for_submit_success_signal", lambda *args, **kwargs: False)
    monkeypatch.setattr(review, "_click_back", lambda *args, **kwargs: False)

    result = review.apply_review_overrides_in_open_modal(
        _FakePage(),
        question_rows=[],
        overrides={},
        submit=True,
    )

    assert result["status"] == "submit_not_confirmed"
    assert submit_clicked["value"] is True


def test_apply_review_overrides_reports_submitted_clicked_when_success_signal_detected(monkeypatch) -> None:
    submit_clicked = {"value": False}

    monkeypatch.setattr(
        review,
        "extract_easy_apply_form_step",
        lambda _page: LinkedInApplicationFormStep(
            step_title="Review your application",
            progress_percent=100,
            primary_action_label="Submit application",
            secondary_action_labels=["Back"],
            elements=[],
            record_lists=[],
            page_url="https://www.linkedin.com/jobs/view/123/apply/",
        ),
    )

    def _record_submit(*args, **kwargs):
        submit_clicked["value"] = True
        return "Submit application"

    monkeypatch.setattr(review, "_click_primary", _record_submit)
    monkeypatch.setattr(review, "_wait_for_submit_success_signal", lambda *args, **kwargs: True)
    monkeypatch.setattr(review, "_click_back", lambda *args, **kwargs: False)

    result = review.apply_review_overrides_in_open_modal(
        _FakePage(),
        question_rows=[],
        overrides={},
        submit=True,
    )

    assert result["status"] == "submitted_clicked"
    assert submit_clicked["value"] is True

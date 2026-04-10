from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LinkedInApplicationQuestion(BaseModel):
    question_key: str
    prompt_text: str
    input_type: str
    required: bool = False
    options: list[str] = Field(default_factory=list)
    current_value: str | None = None
    step_name: str | None = None
    field_name: str | None = None
    field_id: str | None = None


class LinkedInApplicationAnswerProposal(BaseModel):
    question_key: str
    answer_source: Literal["deterministic", "llm", "user_required", "skip"]
    answer_value: str | None = None
    confidence: Literal["high", "medium", "low"] = "low"
    requires_user_input: bool = False
    reason: str


class LinkedInApplicationElementConstraints(BaseModel):
    html_type: str | None = None
    input_mode: str | None = None
    pattern: str | None = None
    placeholder: str | None = None
    validation_message: str | None = None
    min_value: str | None = None
    max_value: str | None = None


class LinkedInApplicationFormElement(BaseModel):
    element_id: str
    label: str
    control_type: str
    required: bool = False
    current_value: str | None = None
    options: list[str] = Field(default_factory=list)
    options_count: int = 0
    suggestions: list[str] = Field(default_factory=list)
    constraints: LinkedInApplicationElementConstraints = Field(
        default_factory=LinkedInApplicationElementConstraints
    )
    field_name: str | None = None
    field_id: str | None = None


class LinkedInApplicationRecordList(BaseModel):
    section_title: str
    item_previews: list[str] = Field(default_factory=list)
    item_count: int = 0


class LinkedInApplicationFormStep(BaseModel):
    step_title: str | None = None
    progress_percent: int | None = None
    section_titles: list[str] = Field(default_factory=list)
    primary_action_label: str | None = None
    secondary_action_labels: list[str] = Field(default_factory=list)
    elements: list[LinkedInApplicationFormElement] = Field(default_factory=list)
    record_lists: list[LinkedInApplicationRecordList] = Field(default_factory=list)
    page_url: str


class LinkedInApplicationFormAction(BaseModel):
    element_id: str
    action_type: Literal[
        "leave_as_is",
        "set_text",
        "choose_option",
        "select_suggestion",
        "choose_existing",
        "upload_file",
        "edit_item",
        "remove_item",
        "add_item",
        "ask_user",
    ]
    target_value: str | None = None
    reason: str | None = None
    confidence: Literal["high", "medium", "low"] = "low"
    review_required: bool = False

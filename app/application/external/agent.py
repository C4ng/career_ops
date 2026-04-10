from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import yaml


logger = logging.getLogger(__name__)

# Default fallback model names for browser-use agent providers.
# Override via preferred_model parameter or environment-specific config.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"
DEFAULT_GOOGLE_MODEL = "gemini-2.5-flash"


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def load_project_env(repo_root: Path) -> None:
    load_dotenv(repo_root / ".env")


def add_local_browser_use_repo_to_path(repo_path: Path | None) -> Path | None:
    if repo_path is None or not repo_path.exists():
        return None
    if str(repo_path) not in sys.path:
        sys.path.insert(0, str(repo_path))
    return repo_path


def load_candidate_dossier(repo_root: Path, dossier_path: Path) -> Any:
    from app.models import LinkedInCandidateDossier

    if not dossier_path.exists():
        logger.warning("Candidate dossier file not found", extra={"dossier_path": str(dossier_path)})
        return LinkedInCandidateDossier()
    payload = yaml.safe_load(dossier_path.read_text(encoding="utf-8")) or {}
    return LinkedInCandidateDossier.model_validate(payload)


def import_browser_use() -> dict[str, Any]:
    try:
        from browser_use import (
            ActionResult,
            Agent,
            BrowserProfile,
            BrowserSession,
            ChatAnthropic,
            ChatBrowserUse,
            ChatGoogle,
            ChatOpenAI,
            Tools,
        )
    except Exception as exc:  # pragma: no cover - runtime dependency gate
        raise RuntimeError(
            "browser-use is not installed in the current environment. "
            "Run this script with `uv run --with browser-use ...` or install browser-use first."
        ) from exc
    return {
        "ActionResult": ActionResult,
        "Agent": Agent,
        "BrowserProfile": BrowserProfile,
        "BrowserSession": BrowserSession,
        "ChatAnthropic": ChatAnthropic,
        "ChatBrowserUse": ChatBrowserUse,
        "ChatGoogle": ChatGoogle,
        "ChatOpenAI": ChatOpenAI,
        "Tools": Tools,
    }


def select_browser_use_llm(browser_use_exports: dict[str, Any], preferred_model: str) -> tuple[Any, dict[str, str]]:
    if os.environ.get("BROWSER_USE_API_KEY"):
        return browser_use_exports["ChatBrowserUse"](), {"provider": "browser_use", "model": "default"}
    if os.environ.get("OPENAI_API_KEY"):
        return browser_use_exports["ChatOpenAI"](model=preferred_model), {"provider": "openai", "model": preferred_model}
    if os.environ.get("ANTHROPIC_API_KEY"):
        model = DEFAULT_ANTHROPIC_MODEL
        return browser_use_exports["ChatAnthropic"](model=model), {"provider": "anthropic", "model": model}
    if os.environ.get("GOOGLE_API_KEY"):
        model = DEFAULT_GOOGLE_MODEL
        return browser_use_exports["ChatGoogle"](model=model), {"provider": "google", "model": model}
    raise RuntimeError(
        "No supported LLM credentials found. Expected one of: "
        "BROWSER_USE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY."
    )


def build_candidate_context_text(dossier: Any) -> str:
    contact = dossier.contact
    education = dossier.education
    experience = dossier.experience
    preferences = dossier.application_preferences
    lines = [
        "Candidate profile to use as the source of truth for straightforward fields:",
        f"- name: {contact.first_name or ''} {contact.last_name or ''}".strip(),
        f"- email: {contact.email or 'unknown'}",
        f"- phone: {contact.phone or 'unknown'}",
        f"- location: {', '.join(part for part in [contact.city, contact.region, contact.country] if part) or 'unknown'}",
        f"- highest degree: {education.highest_degree or 'unknown'}",
        f"- currently enrolled: {education.currently_enrolled}",
        f"- total years of experience: {experience.years_total or 'unknown'}",
        f"- experience summary: {experience.summary or 'unknown'}",
        f"- notice period: {preferences.notice_period or 'unknown'}",
        f"- desired salary: {preferences.desired_salary or 'unknown'}",
    ]
    if dossier.strengths:
        lines.append(f"- strengths: {', '.join(dossier.strengths)}")
    if dossier.tech_familiarity:
        lines.append(f"- tech familiarity: {', '.join(dossier.tech_familiarity)}")
    if dossier.standard_answers:
        lines.append("- standard answers:")
        for key, value in dossier.standard_answers.items():
            lines.append(f"  - {key}: {value}")
    return "\n".join(lines)


def _normalize_memory_key(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return normalized or "user_answer"


def _candidate_location_variants(dossier: Any) -> list[str]:
    contact = dossier.contact
    city = (contact.city or "").strip()
    region = (contact.region or "").strip()
    country = (contact.country or "").strip()
    variants: list[str] = []
    for value in [
        country,
        region,
        city,
        ", ".join(part for part in [city, region] if part),
        ", ".join(part for part in [city, country] if part),
        ", ".join(part for part in [city, region, country] if part),
    ]:
        if value and value not in variants:
            variants.append(value)
    return variants


def _load_raw_dossier_payload(dossier_path: Path) -> dict[str, Any]:
    if not dossier_path.exists():
        return {}
    payload = yaml.safe_load(dossier_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _ensure_nested_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    nested = payload.get(key)
    if not isinstance(nested, dict):
        nested = {}
        payload[key] = nested
    return nested


def persist_user_answers_to_dossier(
    *,
    dossier_path: Path,
    answers: list[dict[str, str]],
) -> list[dict[str, str]]:
    payload = _load_raw_dossier_payload(dossier_path)
    standard_answers = _ensure_nested_dict(payload, "standard_answers")
    contact = _ensure_nested_dict(payload, "contact")
    links = _ensure_nested_dict(payload, "links")
    preferences = _ensure_nested_dict(payload, "application_preferences")
    persisted: list[dict[str, str]] = []

    for item in answers:
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        if not question or not answer:
            continue

        key = _normalize_memory_key(question)
        question_lower = question.lower()
        if "github" in question_lower and "username" in question_lower:
            standard_answers["github_username"] = answer
            links.setdefault("github_url", None)
        elif "english" in question_lower and "proficiency" in question_lower:
            standard_answers["english_proficiency"] = answer
        elif "notice period" in question_lower:
            preferences["notice_period"] = answer
        elif "salary" in question_lower or "compensation" in question_lower:
            preferences["desired_salary"] = answer
        elif "phone" in question_lower:
            contact["phone"] = answer
        elif "email" in question_lower:
            contact["email"] = answer
        elif "location" in question_lower and "," not in answer and len(answer.split()) <= 4:
            contact["city"] = answer
            standard_answers.setdefault("preferred_location_answer", answer)
        else:
            standard_answers[key] = answer

        persisted.append({"question": question, "answer": answer, "memory_key": key})

    if persisted:
        dossier_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
    return persisted


class HumanQuestionItem(BaseModel):
    question: str = Field(description="The exact question to ask the user.")
    field_label: str | None = Field(default=None, description="Visible field label when available.")
    required: bool = Field(default=True, description="Whether the field is required to continue.")


class HumanQuestionBatch(BaseModel):
    questions: list[HumanQuestionItem] = Field(default_factory=list)
    page_context: str | None = Field(default=None, description="Short description of the current page or step.")


class ApplicationQuestionForAnswering(BaseModel):
    id: str = Field(description="Temporary correlation id for this current-page question, e.g. an element index.")
    question: str = Field(description="The exact visible question or field label.")
    options: list[str] = Field(default_factory=list, description="Visible answer options, if constrained.")


class ApplicationQuestionBatch(BaseModel):
    questions: list[ApplicationQuestionForAnswering] = Field(default_factory=list)
    page_context: str | None = Field(default=None, description="Short description of the current form page or step.")


def _has_incomplete_yes_no_options(question: ApplicationQuestionForAnswering) -> bool:
    normalized_options = {option.strip().lower() for option in question.options if option.strip()}
    if normalized_options == {"yes", "no"}:
        return False
    if not (normalized_options & {"yes", "no"}):
        return False
    question_text = question.question.strip().lower()
    yes_no_starters = (
        "are you ",
        "will you ",
        "do you ",
        "did you ",
        "can you ",
        "have you ",
        "is this ",
        "is your ",
        "would you ",
    )
    return question_text.startswith(yes_no_starters)


def _question_input_type(question: ApplicationQuestionForAnswering) -> str:
    normalized_options = {option.strip().lower() for option in question.options}
    if normalized_options == {"yes", "no"}:
        return "yes_no"
    if question.options:
        return "select_one"
    return "short_text"


def build_browser_use_tools(*, browser_use_exports: dict[str, Any], dossier_path: Path) -> Any:
    Tools = browser_use_exports["Tools"]
    ActionResult = browser_use_exports["ActionResult"]

    tools = Tools(exclude_actions=["write_file", "read_file"])

    @tools.registry.action(
        description=(
            "Answer current-page job application questions from the candidate profile. "
            "Pass only a temporary id, exact visible question text, and options when present. "
            "Do not include browser element indexes except as the temporary id for correlating the response."
        ),
        param_model=ApplicationQuestionBatch,
        domains=["*"],
    )
    async def answer_application_questions(params: ApplicationQuestionBatch) -> Any:
        from app.application.easy_apply.answers import map_questions_with_llm_debug as map_application_questions_with_llm_debug
        from app.models import LinkedInApplicationQuestion
        from app.settings import load_application_question_mapping_llm_config

        incomplete_option_questions = [
            item
            for item in params.questions
            if item.options and _has_incomplete_yes_no_options(item)
        ]
        if incomplete_option_questions:
            result_payload = {
                "page_context": params.page_context,
                "needs_page_inspection": True,
                "answers": [
                    {
                        "id": item.id,
                        "answer": None,
                        "confidence": "low",
                        "requires_user_input": False,
                        "source": "page_inspection_required",
                        "reason": (
                            "Only one visible yes/no option was provided. Expand the dropdown/select control "
                            "and re-observe the page before asking for an answer."
                        ),
                    }
                    for item in incomplete_option_questions
                ],
            }
            logger.info("answer_application_questions input: %s", json.dumps(params.model_dump(mode="json"), ensure_ascii=False))
            logger.info("answer_application_questions output: %s", json.dumps(result_payload, ensure_ascii=False))
            return ActionResult(
                extracted_content=json.dumps(result_payload, ensure_ascii=False),
                include_in_memory=True,
                long_term_memory=(
                    "Question answer deferred because the page only exposed the current dropdown value, "
                    "not the full option set."
                ),
            )

        dossier = load_candidate_dossier(Path.cwd(), dossier_path)
        llm_config = load_application_question_mapping_llm_config()
        mapped_questions = [
            LinkedInApplicationQuestion(
                question_key=item.id,
                prompt_text=item.question,
                input_type=_question_input_type(item),
                required=True,
                options=item.options,
            )
            for item in params.questions
        ]
        tool_input = params.model_dump(mode="json")
        logger.info("answer_application_questions input: %s", json.dumps(tool_input, ensure_ascii=False))
        llm_input, raw_response_payload, raw_output_text, proposals = map_application_questions_with_llm_debug(
            llm_config,
            dossier,
            mapped_questions,
            job_context={"source": "external_browser_use_current_page", "page_context": params.page_context},
        )
        compact_result_payload = {
            "page_context": params.page_context,
            "answers": [
                {
                    "id": proposal.question_key,
                    "answer": proposal.answer_value,
                    "confidence": proposal.confidence,
                    "requires_user_input": proposal.requires_user_input,
                    "source": proposal.answer_source,
                    "reason": proposal.reason,
                }
                for proposal in proposals
            ],
        }
        logger.info("answer_application_questions output: %s", json.dumps(compact_result_payload, ensure_ascii=False))
        logger.debug(
            "answer_application_questions debug: %s",
            json.dumps(
                {
                    "llm_input": llm_input,
                    "raw_output_text": raw_output_text,
                    "raw_response_payload": raw_response_payload,
                },
                ensure_ascii=False,
            ),
        )
        return ActionResult(
            extracted_content=json.dumps(compact_result_payload, ensure_ascii=False),
            include_in_memory=True,
            long_term_memory=(
                "answer_application_questions returned candidate answers. "
                f"Use this result to fill the current page before scrolling/continuing/done: "
                f"{json.dumps(compact_result_payload, ensure_ascii=False)}"
            ),
        )

    @tools.registry.action(
        description=(
            "Ask the human one batched set of unresolved questions for the current visible page. "
            "Use this after answer_application_questions returns answers that require user input."
        ),
        param_model=HumanQuestionBatch,
        domains=["*"],
    )
    async def ask_human_batch(params: HumanQuestionBatch, browser_session) -> Any:
        del browser_session

        print("\n=== Browser-use needs user input for the current page ===")
        if params.page_context:
            print(f"Page context: {params.page_context}")
        collected: list[dict[str, str]] = []
        for index, item in enumerate(params.questions, start=1):
            field_hint = f" [{item.field_label}]" if item.field_label else ""
            required_hint = "required" if item.required else "optional"
            answer = input(f"{index}. {item.question}{field_hint} ({required_hint}) > ").strip()
            if answer:
                collected.append(
                    {
                        "question": item.question,
                        "field_label": item.field_label or "",
                        "answer": answer,
                    }
                )

        persisted = persist_user_answers_to_dossier(dossier_path=dossier_path, answers=collected)
        result_payload = {
            "page_context": params.page_context,
            "answers": collected,
            "persisted": persisted,
        }
        return ActionResult(
            extracted_content=json.dumps(result_payload, ensure_ascii=False),
            include_in_memory=True,
            long_term_memory=(
                f"Asked the user {len(params.questions)} batched question(s) and received {len(collected)} answer(s)."
            ),
        )

    return tools


def build_external_apply_probe_task(apply_link: str, dossier: Any) -> str:
    resume_path = (
        Path(dossier.documents.resume_path).resolve()
        if hasattr(dossier, "documents") and dossier.documents and dossier.documents.resume_path
        else (Path.cwd() / "files" / "resume.pdf").resolve()
    )
    return f"""
You are exploring an external job application website.

Primary goal:
- Reach the application form for this job, fill all current-page fields that can be answered, and stop before submit/review: {apply_link}

Available application documents:
- resume_pdf: {resume_path}

Required behavior:
- Do not submit any application.
- Do not create an account.
- Do not sign in.
- Do not use the file system unless explicitly required by the task. Do not create todo.md, results.md, or any scratch files.
- Stop immediately if you encounter login, account creation, email verification, phone verification, OTP, or CAPTCHA.
- If you reach a real application form, do not answer screening/profile questions directly from this prompt. Instead, collect the visible fields/questions on the current rendered page and call answer_application_questions once with each field/question's exact visible text and options.
- If a dropdown/select field is collapsed and the page only shows the current selected value, do not treat that as the full option list. Open the dropdown/select control, observe again, then call answer_application_questions with the full visible option list.
- Use the visible element index only as a temporary id in answer_application_questions when helpful for correlating the answer back to the current page. Do not treat that id as durable after the page changes.
- Calling answer_application_questions does not fill the web page. It only returns candidate answers for the current page.
- If answer_application_questions returns source=page_inspection_required or needs_page_inspection=true, inspect/expand the relevant page control and re-observe before answering or asking the user.
- After answer_application_questions returns, treat the returned answers as a fill plan, not as completed page filling.
- If answer_application_questions returns any non-null answer, execute browser actions to apply all returned non-null answers to their matching current-page fields before scrolling, continuing, or calling done. If there are more answers than can fit in one browser-use action batch, continue applying the remaining returned answers in the next step before doing anything else.
- If answer_application_questions returns requires_user_input=true for any required current-page field/question, call ask_human_batch once with all unresolved required questions from that current page before scrolling, continuing, or calling done. After ask_human_batch returns, apply the user answers to the matching fields before moving on.
- If a resume/file-upload field is visible and required, upload the available resume_pdf path above before moving away from the current page.
- After executing an answer batch, observe the rendered page again. If new fields, validation errors, or changed options appear, repeat the collect -> answer_application_questions -> execute -> observe cycle before moving to the next page.
- Only scroll away from the current viewport after the visible fields in that viewport are filled, intentionally skipped as optional, or sent to ask_human_batch.
- Only click Next/Continue/Review or call done after the current rendered page is filled and re-observed without visible required-field errors.
- Do not invent work history, years of experience, account credentials, legal answers, or screening answers.
- If a popup blocks the page and can be safely closed, you may close it.
- If you reach a review page, stop there.

When you stop, use the done action and report:
1. what page type you reached
2. what actions you took
3. whether a real form was reached
4. whether a blocker was encountered
5. whether this looked structured enough for deterministic code or still better suited to an agent
""".strip()


def classify_final_state(final_result: str | None, final_url: str | None, last_state_message: str | None) -> str:
    text = " ".join(part for part in [final_result, final_url, last_state_message] if part).lower()
    if "application submitted" in text or "thank you for applying" in text:
        return "success_page"
    if any(token in text for token in ["resume", "cover letter", "application form", "first name", "last name"]):
        return "application_form"
    if "review" in text and "submit" in text:
        return "review_page"
    if "verify your email" in text or "verification code" in text or "one-time passcode" in text:
        return "verification_required"
    if "create account" in text or "sign up" in text or "register" in text:
        return "account_required"
    if "sign in" in text or "log in" in text or "login" in text:
        return "login_required"
    if any(
        token in text
        for token in ["encountered captcha", "captcha challenge", "captcha required", "captcha blocked", "recaptcha"]
    ):
        return "captcha_blocked"
    return "unknown"


def build_browser_use_artifact(
    *,
    apply_link: str,
    cdp_url: str,
    llm_info: dict[str, str],
    history: Any,
    conversations_dir: Path,
    local_browser_use_repo: Path | None,
) -> dict[str, Any]:
    final_result = history.final_result()
    urls = history.urls()
    last_state_message = history.history[-1].state_message if history.history else None
    final_url = urls[-1] if urls else None
    final_state = classify_final_state(final_result, final_url, last_state_message)
    action_history = history.action_history()
    flattened_actions = history.model_actions()
    return {
        "apply_link": apply_link,
        "cdp_url": cdp_url,
        "local_browser_use_repo": str(local_browser_use_repo) if local_browser_use_repo else None,
        "llm": llm_info,
        "task_mode": "external_apply_navigation_probe",
        "status": {
            "is_done": history.is_done(),
            "is_successful": history.is_successful(),
            "final_state": final_state,
        },
        "history_summary": {
            "step_count": history.number_of_steps(),
            "total_duration_seconds": history.total_duration_seconds(),
            "final_result": final_result,
            "urls": urls,
            "action_names": history.action_names(),
            "errors": history.errors(),
            "screenshot_paths": history.screenshot_paths(return_none_if_not_screenshot=False),
            "conversation_dir": str(conversations_dir),
        },
        "steps": _jsonable(history.model_dump()),
        "action_history": _jsonable(action_history),
        "flattened_actions": _jsonable(flattened_actions),
        "last_state_message": _jsonable(last_state_message),
    }


def write_browser_use_artifacts(
    *,
    artifact: dict[str, Any],
    output_path: Path,
    history: Any,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    history_output = output_path.with_suffix(".history.json")
    history.save_to_file(history_output)
    logger.info(
        "Saved browser-use probe artifacts",
        extra={
            "artifact_path": str(output_path),
            "history_path": str(history_output),
        },
    )

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.models import DEFAULT_CDP_URL
from app.application.external.agent import (
    add_local_browser_use_repo_to_path,
    build_browser_use_artifact,
    build_external_apply_probe_task,
    build_browser_use_tools,
    import_browser_use,
    load_candidate_dossier,
    load_project_env,
    select_browser_use_llm,
    write_browser_use_artifacts,
)
from app.logging_setup import setup_logging


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Development-only browser-use spike for external job applications.")
    parser.add_argument("--apply-link", required=True, help="External application link to probe.")
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help="Chrome DevTools Protocol URL for the logged-in browser session.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="Preferred model if OPENAI_API_KEY is available.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Maximum browser-use steps for the probe run.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "data" / "reviews" / "external_apply_browser_use_probe.latest.json"),
        help="Where to write the main JSON artifact.",
    )
    parser.add_argument(
        "--conversation-dir",
        default=str(REPO_ROOT / "data" / "reviews" / "external_apply_browser_use_probe.latest.conversations"),
        help="Directory for browser-use per-step conversation dumps.",
    )
    parser.add_argument(
        "--browser-use-repo",
        default=str(REPO_ROOT.parent / "browser-use"),
        help="Optional local browser-use repo checkout to import from during the spike.",
    )
    parser.add_argument(
        "--dossier-file",
        default=str(REPO_ROOT / "secrets" / "application_candidate_dossier.dev.yaml"),
        help="Candidate dossier YAML used to supply direct application answers during the spike.",
    )
    parser.add_argument(
        "--resume-file",
        default=str(REPO_ROOT / "files" / "Resume_Yuhe_Fan_Feb.pdf"),
        help="Resume PDF path made available to browser-use upload_file actions.",
    )
    return parser.parse_args()


async def run_probe(args: argparse.Namespace) -> None:
    load_project_env(REPO_ROOT)
    local_repo = add_local_browser_use_repo_to_path(Path(args.browser_use_repo))
    dossier = load_candidate_dossier(REPO_ROOT, Path(args.dossier_file))
    browser_use_exports = import_browser_use()
    llm, llm_info = select_browser_use_llm(browser_use_exports, preferred_model=args.model)

    BrowserProfile = browser_use_exports["BrowserProfile"]
    BrowserSession = browser_use_exports["BrowserSession"]
    Agent = browser_use_exports["Agent"]
    tools = build_browser_use_tools(browser_use_exports=browser_use_exports, dossier_path=Path(args.dossier_file))

    output_path = Path(args.output)
    conversations_dir = Path(args.conversation_dir)
    conversations_dir.mkdir(parents=True, exist_ok=True)

    browser_profile = BrowserProfile(cdp_url=args.cdp_url, is_local=True, headless=False)
    browser_session = BrowserSession(browser_profile=browser_profile)
    task = build_external_apply_probe_task(args.apply_link, dossier)
    available_file_paths = [str(Path(args.resume_file).resolve())] if args.resume_file else []

    def _log_step(browser_state_summary, model_output, step_number: int) -> None:
        logger.info(
            "browser-use step",
            extra={
                "step_number": step_number,
                "url": browser_state_summary.url,
                "title": browser_state_summary.title,
                "tabs": [tab.model_dump(mode="json") for tab in browser_state_summary.tabs],
                "model_current_state": model_output.current_state.model_dump(mode="json"),
                "actions": [action.model_dump(exclude_none=True, mode="json") for action in model_output.action],
            },
        )

    agent = Agent(
        task=task,
        llm=llm,
        browser_session=browser_session,
        max_actions_per_step=3,
        max_failures=4,
        use_vision=True,
        max_history_items=20,
        save_conversation_path=conversations_dir,
        directly_open_url=True,
        enable_planning=True,
        tools=tools,
        available_file_paths=available_file_paths,
        register_new_step_callback=_log_step,
    )

    try:
        history = await agent.run(max_steps=args.max_steps)
        artifact = build_browser_use_artifact(
            apply_link=args.apply_link,
            cdp_url=args.cdp_url,
            llm_info=llm_info,
            history=history,
            conversations_dir=conversations_dir,
            local_browser_use_repo=local_repo,
        )
        write_browser_use_artifacts(artifact=artifact, output_path=output_path, history=history)
        logger.info(
            "External browser-use probe completed",
            extra={
                "apply_link": args.apply_link,
                "final_state": artifact["status"]["final_state"],
                "step_count": artifact["history_summary"]["step_count"],
                "action_names": artifact["history_summary"]["action_names"],
                "final_result": artifact["history_summary"]["final_result"],
            },
        )
    finally:
        await browser_session.kill()


def main() -> None:
    args = parse_args()
    log_paths = setup_logging("linkedin_external_apply_browser_use_probe")
    logger.info("Starting external browser-use probe", extra={"log_paths": {k: str(v) for k, v in log_paths.items()}})
    asyncio.run(run_probe(args))


if __name__ == "__main__":
    main()

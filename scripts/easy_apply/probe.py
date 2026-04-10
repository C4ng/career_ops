from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from playwright.sync_api import sync_playwright

from app.application.easy_apply.navigate import run_easy_apply_to_review
from app.models import DEFAULT_CDP_URL, LinkedInCandidateDossier
from app.logging_setup import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Development probe for LinkedIn Easy Apply modal extraction.")
    parser.add_argument("--apply-link", required=True, help="Saved LinkedIn Easy Apply link to probe.")
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help="Chrome DevTools Protocol URL for the logged-in browser session.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "data" / "reviews" / "easy_apply_probe.latest.json"),
        help="Where to write the normalized probe output JSON.",
    )
    parser.add_argument(
        "--screenshots-dir",
        default=str(REPO_ROOT / "data" / "reviews" / "easy_apply_probe.latest"),
        help="Directory for step screenshots.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum modal steps to walk before stopping.",
    )
    parser.add_argument(
        "--dossier-file",
        default=str(REPO_ROOT / "secrets" / "application_candidate_dossier.dev.yaml"),
        help="Optional development-only candidate dossier YAML override.",
    )
    return parser.parse_args()


def _load_dossier_override(path: Path) -> LinkedInCandidateDossier:
    if not path.exists():
        return LinkedInCandidateDossier()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return LinkedInCandidateDossier.model_validate(payload)


def main() -> int:
    args = parse_args()
    setup_logging("linkedin_easy_apply_probe")
    dossier = _load_dossier_override(Path(args.dossier_file))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    screenshots_dir = Path(args.screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        context = browser.contexts[0]
        page = context.new_page()
        result = run_easy_apply_to_review(
            page,
            apply_link=args.apply_link,
            dossier=dossier,
            screenshot_dir=screenshots_dir,
            max_steps=args.max_steps,
        )

    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

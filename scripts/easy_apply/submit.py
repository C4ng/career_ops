from __future__ import annotations

import argparse
import json

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.models import DEFAULT_CDP_URL

from scripts.easy_apply.review import _load_overrides, run_easy_apply_review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit an Easy Apply application from an existing review_ready session."
    )
    parser.add_argument("--application-id", type=int, required=True)
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help="Chrome DevTools Protocol URL for the logged-in browser session.",
    )
    parser.add_argument(
        "--overrides-file",
        default=None,
        help="Optional YAML/JSON file mapping question_key to the reviewed answer before submit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            run_easy_apply_review(
                application_id=args.application_id,
                cdp_url=args.cdp_url,
                overrides=_load_overrides(args.overrides_file),
                submit=True,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

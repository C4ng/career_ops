from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from scripts._bootstrap import REPO_ROOT  # noqa: F401

from app.application.external import build_external_apply_audit_rows, summarize_external_apply_audit
from app.sources.linkedin.log_payloads import item_examples_for_logging
from app.logging_setup import setup_logging
from app.settings import load_sqlite_config
from app.services.storage.db import resolve_db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Development-only audit of external application links and provider distribution."
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "data" / "reviews" / "external_apply_audit.latest.json"),
        help="Where to write the external apply audit JSON.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of external application rows to audit.",
    )
    return parser.parse_args()


def _load_external_apply_jobs(limit: int) -> list[dict[str, object]]:
    sqlite_config = load_sqlite_config()
    db_path = resolve_db_path(REPO_ROOT, sqlite_config)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                j.id,
                j.linkedin_job_id,
                j.title,
                j.company,
                j.apply_link,
                j.stage,
                (
                    SELECT r.recommendation
                    FROM job_rankings r
                    WHERE r.linkedin_job_id = j.linkedin_job_id
                    ORDER BY r.id DESC
                    LIMIT 1
                ) AS recommendation
            FROM jobs j
            WHERE j.apply_link IS NOT NULL
              AND j.easy_apply = 0
            ORDER BY j.updated_at DESC, j.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "job_id": int(row["id"]),
            "linkedin_job_id": row["linkedin_job_id"],
            "title": row["title"],
            "company": row["company"],
            "apply_link": row["apply_link"],
            "stage": row["stage"],
            "recommendation": row["recommendation"],
        }
        for row in rows
    ]


def main() -> int:
    args = parse_args()
    setup_logging("linkedin_external_apply_audit")
    jobs = _load_external_apply_jobs(args.limit)
    audit_rows = build_external_apply_audit_rows(jobs)
    summary = summarize_external_apply_audit(audit_rows)

    result = {
        "scope": "development_analysis",
        "source": "stored_external_apply_links_only",
        "summary": summary,
        "sample_rows": item_examples_for_logging(
            audit_rows,
            limit=20,
            include_keys=[
                "linkedin_job_id",
                "title",
                "company",
                "domain",
                "provider",
                "host_category",
                "stage",
                "recommendation",
                "recommended_mode",
            ],
        ),
        "rows": audit_rows,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

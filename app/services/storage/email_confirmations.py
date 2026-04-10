from __future__ import annotations

import sqlite3

from app.models import LinkedInApplicationConfirmation
from app.services.storage._shared import now_iso
from app.services.storage.applications import mark_job_as_applied_from_confirmation_email


def build_confirmation_dedupe_key(confirmation: LinkedInApplicationConfirmation) -> str:
    if confirmation.message_id:
        return f"message_id:{confirmation.message_id.strip()}"
    fallback_bits = [
        confirmation.sequence_id or "",
        confirmation.received_at or "",
        confirmation.linkedin_job_id or confirmation.job_url or "",
    ]
    return f"fallback:{'|'.join(fallback_bits)}"


def load_processed_confirmation_dedupe_keys(
    connection: sqlite3.Connection,
    dedupe_keys: list[str],
) -> set[str]:
    if not dedupe_keys:
        return set()
    placeholders = ", ".join("?" for _ in dedupe_keys)
    rows = connection.execute(
        f"""
        SELECT dedupe_key
        FROM processed_linkedin_confirmation_emails
        WHERE dedupe_key IN ({placeholders})
        """,
        dedupe_keys,
    ).fetchall()
    return {str(row["dedupe_key"]) for row in rows}


def record_processed_confirmation_email(
    connection: sqlite3.Connection,
    *,
    confirmation: LinkedInApplicationConfirmation,
    dedupe_key: str,
    processing_result: str,
    application_created: bool,
    application_updated: bool,
    job_updated: bool,
) -> None:
    now = now_iso()
    with connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO processed_linkedin_confirmation_emails (
                dedupe_key,
                message_id,
                sequence_id,
                received_at,
                sender,
                linkedin_job_id,
                job_url,
                company,
                title,
                processing_result,
                application_created,
                application_updated,
                job_updated,
                processed_at,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dedupe_key,
                confirmation.message_id,
                confirmation.sequence_id,
                confirmation.received_at,
                confirmation.from_address,
                confirmation.linkedin_job_id,
                confirmation.job_url,
                confirmation.company,
                confirmation.title,
                processing_result,
                int(application_created),
                int(application_updated),
                int(job_updated),
                now,
                now,
            ),
        )


def process_confirmation_emails(
    connection: sqlite3.Connection,
    confirmations: list[LinkedInApplicationConfirmation],
    *,
    application_type: str = "external_apply",
) -> dict[str, object]:
    dedupe_keys = [build_confirmation_dedupe_key(item) for item in confirmations]
    processed_keys = load_processed_confirmation_dedupe_keys(connection, dedupe_keys)

    updates: list[dict[str, object]] = []
    skipped_already_processed = 0
    newly_processed = 0

    for confirmation in confirmations:
        dedupe_key = build_confirmation_dedupe_key(confirmation)
        if dedupe_key in processed_keys:
            skipped_already_processed += 1
            updates.append(
                {
                    "dedupe_key": dedupe_key,
                    "message_id": confirmation.message_id,
                    "linkedin_job_id": confirmation.linkedin_job_id,
                    "already_processed": True,
                }
            )
            continue

        if not confirmation.linkedin_job_id or not confirmation.received_at:
            record_processed_confirmation_email(
                connection,
                confirmation=confirmation,
                dedupe_key=dedupe_key,
                processing_result="skipped_missing_job_id_or_received_at",
                application_created=False,
                application_updated=False,
                job_updated=False,
            )
            processed_keys.add(dedupe_key)
            newly_processed += 1
            updates.append(
                {
                    "dedupe_key": dedupe_key,
                    "message_id": confirmation.message_id,
                    "linkedin_job_id": confirmation.linkedin_job_id,
                    "already_processed": False,
                    "job_found": False,
                    "application_created": False,
                    "application_updated": False,
                    "job_updated": False,
                    "skip_reason": "missing_job_id_or_received_at",
                }
            )
            continue

        summary = mark_job_as_applied_from_confirmation_email(
            connection,
            linkedin_job_id=confirmation.linkedin_job_id,
            application_type=application_type,
            applied_at=confirmation.received_at,
            last_seen_url=confirmation.job_url,
        )
        record_processed_confirmation_email(
            connection,
            confirmation=confirmation,
            dedupe_key=dedupe_key,
            processing_result="processed",
            application_created=bool(summary["application_created"]),
            application_updated=bool(summary["application_updated"]),
            job_updated=bool(summary["job_updated"]),
        )
        processed_keys.add(dedupe_key)
        newly_processed += 1
        updates.append(
            {
                "dedupe_key": dedupe_key,
                "message_id": confirmation.message_id,
                "already_processed": False,
                **summary,
            }
        )

    return {
        "confirmations_read": len(confirmations),
        "newly_processed": newly_processed,
        "already_processed": skipped_already_processed,
        "job_matches": sum(1 for update in updates if update.get("job_found")),
        "applications_created": sum(1 for update in updates if update.get("application_created")),
        "applications_updated": sum(1 for update in updates if update.get("application_updated")),
        "jobs_updated": sum(1 for update in updates if update.get("job_updated")),
        "updates": updates,
    }

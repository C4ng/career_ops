from __future__ import annotations

from app.models import LinkedInJobCard
from app.sources.linkedin.feed.dedupe import job_card_dedupe_key


def test_job_card_dedupe_key_prefers_linkedin_job_id() -> None:
    card = LinkedInJobCard(
        source_type="keyword_search",
        linkedin_job_id="4389722027",
        job_url="https://www.linkedin.com/jobs/view/4389722027/",
        title="AI Engineer",
        company="Example",
        location_text="Toronto",
    )

    assert job_card_dedupe_key(card) == "linkedin_job_id:4389722027"


def test_job_card_dedupe_key_falls_back_to_job_url() -> None:
    card = LinkedInJobCard(
        source_type="keyword_search",
        job_url="https://www.linkedin.com/jobs/view/4389722027/",
        title="AI Engineer",
        company="Example",
        location_text="Toronto",
    )

    assert job_card_dedupe_key(card) == "job_url:https://www.linkedin.com/jobs/view/4389722027/"


def test_job_card_dedupe_key_falls_back_to_normalized_text_key() -> None:
    card = LinkedInJobCard(
        source_type="keyword_search",
        title=" AI Engineer ",
        company=" Example Co ",
        location_text=" Toronto, ON ",
    )

    assert job_card_dedupe_key(card) == "title_company_location:ai engineer|example co|toronto, on"


def test_job_card_dedupe_key_returns_none_for_empty_card() -> None:
    assert job_card_dedupe_key(LinkedInJobCard(source_type="keyword_search")) is None

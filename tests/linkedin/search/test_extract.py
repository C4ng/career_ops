from __future__ import annotations

from datetime import UTC, datetime

from app.models import LinkedInRawCard
from app.sources.linkedin.feed.extract import (
    clean_badges,
    extract_posted_text,
    extract_salary_text,
    should_drop_raw_card,
    to_dropped_raw_card_payload,
    to_job_card,
)
from app.sources.linkedin.utils import (
    absolute_link,
    canonical_linkedin_job_url,
    extract_easy_apply,
    extract_job_id_from_href,
    extract_work_mode,
    normalize_linkedin_apply_link,
    title_matches_exclusion,
)


def test_extract_job_id_from_jobs_view_href() -> None:
    href = "/jobs/view/4389722027/?trackingId=abc"

    assert extract_job_id_from_href(href) == "4389722027"


def test_extract_job_id_from_current_job_id_query_param() -> None:
    href = "/jobs/search/?currentJobId=4389310564&keywords=AI"

    assert extract_job_id_from_href(href) == "4389310564"


def test_absolute_link_builds_full_link() -> None:
    assert absolute_link("/jobs/view/123/") == "https://www.linkedin.com/jobs/view/123/"


def test_canonical_linkedin_job_url_removes_tracking_parameters() -> None:
    href = "https://www.linkedin.com/comm/jobs/view/4390302068/?trackingId=abc"

    assert canonical_linkedin_job_url(href) == "https://www.linkedin.com/jobs/view/4390302068/"


def test_normalize_linkedin_apply_link_unwraps_safety_redirect() -> None:
    href = (
        "https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fwww%2Evirtusa%2Ecom%2Fcareers%2Fca"
        "%2Ftoronto%2Faiml%2Fgen-ai-developer%2Fcreq249175%3Fsource%3Dtaleo&urlhash=mkAe&isSdui=true"
    )

    assert normalize_linkedin_apply_link(href) == (
        "https://www.virtusa.com/careers/ca/toronto/aiml/gen-ai-developer/creq249175?source=taleo"
    )


def test_normalize_linkedin_apply_link_keeps_easy_apply_link() -> None:
    href = "https://www.linkedin.com/jobs/view/4389703403/apply/?openSDUIApplyFlow=true&trackingId=abc"

    assert normalize_linkedin_apply_link(href) == href


def test_extract_work_mode_handles_remote_hybrid_and_on_site() -> None:
    assert extract_work_mode("Toronto, ON (Remote)") == "remote"
    assert extract_work_mode("Toronto, ON (Hybrid)") == "hybrid"
    assert extract_work_mode("Toronto, ON (On-site)") == "on_site"


def test_extract_posted_text_picks_relative_time_badge() -> None:
    badges = ["Promoted", "2 days ago", "Easy Apply"]

    assert extract_posted_text(badges) == "2 days ago"


def test_extract_salary_text_finds_range() -> None:
    card_text = "Software Engineer Toronto, ON $126.2K/yr - $189.2K/yr Easy Apply"

    assert extract_salary_text(card_text) == "$126.2K/yr - $189.2K/yr"


def test_extract_easy_apply_detects_badge() -> None:
    assert extract_easy_apply(["Promoted", "Easy Apply"]) is True
    assert extract_easy_apply(["Promoted"]) is False


def test_clean_badges_removes_posted_text_only() -> None:
    badges = ["2 days ago", "Promoted", "Easy Apply"]

    assert clean_badges(badges, "2 days ago") == ["Promoted", "Easy Apply"]


def test_title_matches_exclusion_returns_matched_term() -> None:
    title = "Senior Machine Learning Engineer"
    excluded_terms = ["staff", "senior", "manager"]

    assert title_matches_exclusion(title, excluded_terms) == "senior"


def test_title_matches_exclusion_ignores_staff_for_technical_staff_titles() -> None:
    title = "Member of Technical Staff, AI Models Research"
    excluded_terms = ["staff", "senior", "manager"]

    assert title_matches_exclusion(title, excluded_terms) is None


def test_should_drop_raw_card_detects_empty_placeholder() -> None:
    raw_card = LinkedInRawCard(index=1)

    assert should_drop_raw_card(raw_card) == "empty_placeholder_row"


def test_to_dropped_raw_card_payload_keeps_debug_fields() -> None:
    raw_card = LinkedInRawCard(
        index=3,
        href="/jobs/view/123/",
        current_job_id_guess="123",
        card_text="Example card",
        card_html="<li>Example</li>",
    )

    payload = to_dropped_raw_card_payload(raw_card, "title_excluded")

    assert payload["index"] == 3
    assert payload["drop_reason"] == "title_excluded"
    assert payload["current_job_id_guess"] == "123"


def test_to_job_card_maps_runtime_fields_from_raw_card() -> None:
    observed_at = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    raw_card = LinkedInRawCard(
        index=1,
        title_text="Gen AI Data Engineer",
        company_text="CONFLUX SYSTEMS",
        location_text="Toronto, ON (Hybrid)",
        badge_texts=["25 minutes ago", "Easy Apply", "Promoted"],
        href="/jobs/view/4389722027/",
        current_job_id_guess="4389722027",
        card_text="Gen AI Data Engineer Toronto, ON (Hybrid) $126.2K/yr - $189.2K/yr",
    )

    job_card = to_job_card(raw_card, observed_at)

    assert job_card.observed_at == observed_at
    assert job_card.linkedin_job_id == "4389722027"
    assert job_card.job_url == "https://www.linkedin.com/jobs/view/4389722027/"
    assert job_card.title == "Gen AI Data Engineer"
    assert job_card.company == "CONFLUX SYSTEMS"
    assert job_card.work_mode == "hybrid"
    assert job_card.observed_posted_text == "25 minutes ago"
    assert job_card.salary_text == "$126.2K/yr - $189.2K/yr"
    assert job_card.easy_apply is True
    assert job_card.badges == ["Easy Apply", "Promoted"]

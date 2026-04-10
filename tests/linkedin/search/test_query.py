from __future__ import annotations

from app.models import (
    LinkedInKeywordSearchSource,
    LinkedInRecommendedFeedSource,
    LinkedInSourceConfig,
)
from app.sources.linkedin.feed.query import build_search_url, build_source_url, source_page_step


def test_build_search_url_includes_expected_query_fields() -> None:
    config = LinkedInKeywordSearchSource(
        keywords="AI Engineer",
        location="Toronto, Ontario, Canada",
        posted_window="past_week",
        experience_levels=["internship", "entry", "mid_senior"],
        start=25,
    )

    url = build_search_url(config)

    assert url.startswith("https://www.linkedin.com/jobs/search/?")
    assert "keywords=AI+Engineer" in url
    assert "location=Toronto%2C+Ontario%2C+Canada" in url
    assert "start=25" in url
    assert "f_TPR=r604800" in url
    assert "f_E=1%2C2%2C4" in url


def test_build_search_url_omits_unknown_posted_window() -> None:
    config = LinkedInKeywordSearchSource(
        keywords="ML Engineer",
        location="Toronto",
        posted_window="unknown_window",
    )

    url = build_search_url(config)

    assert "f_TPR=" not in url


def test_build_search_url_ignores_unknown_experience_levels() -> None:
    config = LinkedInKeywordSearchSource(
        keywords="ML Engineer",
        location="Toronto",
        experience_levels=["entry", "unknown_level"],
    )

    url = build_search_url(config)

    assert "f_E=2" in url
    assert "unknown_level" not in url


def test_build_source_url_dispatches_keyword_search_with_start_override() -> None:
    config = LinkedInSourceConfig(
        source_type=["keyword_search"],
        keyword_search_page_step=25,
        recommended_feed_page_step=24,
        keyword_search=LinkedInKeywordSearchSource(
            keywords="AI Engineer",
            location="Toronto, Ontario, Canada",
            posted_window="past_week",
            experience_levels=["entry"],
            start=0,
        ),
    )

    url = build_source_url(config, "keyword_search", start=50)

    assert "start=50" in url
    assert "keywords=AI+Engineer" in url
    assert "location=Toronto%2C+Ontario%2C+Canada" in url


def test_build_source_url_dispatches_recommended_feed_with_start_override() -> None:
    config = LinkedInSourceConfig(
        source_type=["recommended_feed"],
        keyword_search_page_step=25,
        recommended_feed_page_step=24,
        recommended_feed=LinkedInRecommendedFeedSource(
            recommended_url="https://www.linkedin.com/jobs/collections/recommended/?currentJobId=123&discover=recommended"
        ),
    )

    url = build_source_url(config, "recommended_feed", start=24)

    assert url.startswith("https://www.linkedin.com/jobs/collections/recommended/?")
    assert "currentJobId=123" in url
    assert "discover=recommended" in url
    assert "start=24" in url


def test_source_page_step_uses_source_specific_values() -> None:
    config = LinkedInSourceConfig(
        source_type=["keyword_search", "recommended_feed"],
        keyword_search_page_step=25,
        recommended_feed_page_step=24,
        keyword_search=LinkedInKeywordSearchSource(
            keywords="AI Engineer",
            location="Toronto",
        ),
        recommended_feed=LinkedInRecommendedFeedSource(
            recommended_url="https://www.linkedin.com/jobs/collections/recommended/?currentJobId=123"
        ),
    )

    assert source_page_step(config, "keyword_search") == 25
    assert source_page_step(config, "recommended_feed") == 24
